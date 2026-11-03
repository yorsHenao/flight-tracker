import base64
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
import hashlib
import json
import random
import logging

import config

_log = logging.getLogger("vuelos")
import re
import threading
import time
import urllib.parse
import requests

from providers.airport_resolver import resolve_location

# Catálogo de portales soportados (incluye Rappi Travel y aerolíneas directas)
PORTALS = [
    {
        "id": "google_flights",
        "name": "Google Flights",
        "home": "https://www.google.com/travel/flights",
        "badge_color": "#0EA5E9",
    },
    {
        "id": "rappitravel",
        "name": "Rappi Travel",
        "home": "https://travel.rappi.com/co/flights",
        "badge_color": "#FF441F",
    },
    {
        "id": "latam",
        "name": "LATAM",
        "home": "https://www.latamairlines.com/co/es",
        "badge_color": "#4F46E5",
    },
    {
        "id": "jetsmart",
        "name": "JetSMART",
        "home": "https://jetsmart.com/co/es/",
        "badge_color": "#0284C7",
    },
    {
        "id": "wingo",
        "name": "Wingo",
        "home": "https://www.wingo.com/",
        "badge_color": "#7C3AED",
    },
    {
        "id": "avianca",
        "name": "Avianca",
        "home": "https://www.avianca.com/es",
        "badge_color": "#E11D48",
    },
    {
        "id": "skyscanner",
        "name": "Skyscanner",
        "home": "https://www.skyscanner.com.co/",
        "badge_color": "#0770E3",
    },
    {
        "id": "kayak",
        "name": "Kayak",
        "home": "https://www.kayak.com.co/flights",
        "badge_color": "#FF690F",
    },
    {
        "id": "kiwi",
        "name": "Kiwi.com",
        "home": "https://www.kiwi.com/co",
        "badge_color": "#00A991",
    },
]

_PORTAL_BY_ID = {p["id"]: p for p in PORTALS}

# Caché en memoria (TTL 15 minutos) para tareas de fondo
_LIVE_CACHE: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 900.0

_DS1_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:(.*?), sideChannel:",
    re.DOTALL,
)

_DS1_START_RE = re.compile(r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:", re.DOTALL)
_JSON_DECODER = json.JSONDecoder()


def _extract_ds1_payloads(text: str) -> list:
    """
    Devuelve los bloques JSON de 'ds:1' de la página de Google Flights.
    Usa raw_decode para leer solo el primer valor JSON completo (evita el error
    'Extra data' cuando después vienen más campos o fragmentos) y tolera el
    prefijo anti-XSSI )]}' y respuestas por fragmentos.
    """
    payloads = []
    if not text:
        return payloads
    for m in _DS1_START_RE.finditer(text):
        pos = m.end()
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        try:
            value, _ = _JSON_DECODER.raw_decode(text, pos)
            payloads.append(value)
        except ValueError:
            continue
    if not payloads:
        stripped = text.lstrip()
        if stripped.startswith(")]}'"):
            stripped = stripped[4:]
        idx = 0
        while idx < len(stripped):
            while idx < len(stripped) and stripped[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(stripped) or stripped[idx] not in "[{":
                # Fragmentos con longitud al inicio (formato por bloques)
                nl = stripped.find("\n", idx)
                if nl == -1:
                    break
                idx = nl + 1
                continue
            try:
                value, idx = _JSON_DECODER.raw_decode(stripped, idx)
                if isinstance(value, list):
                    payloads.append(value)
            except ValueError:
                break
    return payloads


def _safe_snippet(text: str, limit: int = 120) -> str:
    snippet = re.sub(r"\s+", " ", (text or "")[:limit])
    return re.sub(r"[^\x20-\x7E]", "?", snippet)


_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}


# --- Codificador Protobuf ligero para `tfs` y `tfu` de Google Flights ---

def _pb_varint(n: int) -> bytes:
    out = bytearray()
    while n > 127:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _pb_tag(field: int, wire: int) -> bytes:
    return _pb_varint((field << 3) | wire)


def _pb_vf(field: int, val: int) -> bytes:
    return _pb_tag(field, 0) + _pb_varint(val)


def _pb_sf(field: int, text: str) -> bytes:
    b = text.encode("utf-8")
    return _pb_tag(field, 2) + _pb_varint(len(b)) + b


def _pb_mf(field: int, payload: bytes) -> bytes:
    return _pb_tag(field, 2) + _pb_varint(len(payload)) + payload


def build_google_flights_tfs(orig_iata: str, dest_iata: str, flight_date: str) -> str:
    """
    Construye el token protobuf `tfs` de Google Flights para un vuelo solo ida
    (1 adulto, clase económica) en la fecha y ruta indicadas.
    """
    orig_msg = _pb_vf(1, 1) + _pb_sf(2, orig_iata.upper())
    dest_msg = _pb_vf(1, 1) + _pb_sf(2, dest_iata.upper())
    leg_msg = _pb_sf(2, flight_date) + _pb_mf(13, orig_msg) + _pb_mf(14, dest_msg)
    payload = (
        _pb_vf(1, 28)
        + _pb_vf(2, 2)
        + _pb_mf(3, leg_msg)
        + _pb_vf(8, 1)
        + _pb_vf(9, 1)
        + _pb_vf(14, 1)
        + _pb_vf(19, 2)
    )
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def build_google_flights_booking_url(
    orig_iata: str,
    dest_iata: str,
    flight_date: str,
    legs_data: list[dict],
    raw_tfu_token: str = "",
) -> str:
    """
    Construye el enlace directo a la página de RESERVA (`/travel/flights/booking`)
    de un vuelo específico en Google Flights codificando el tramo exacto (aerolínea +
    número de vuelo) en el campo 4 de `leg_msg` dentro de `tfs` y envolviendo el token
    `tfu` del vuelo. Reduce los clics del usuario abriendo directamente 'Opciones de reserva'
    con el botón 'Continuar' hacia la aerolínea.
    """
    if not legs_data or not raw_tfu_token:
        tfs = build_google_flights_tfs(orig_iata, dest_iata, flight_date)
        return f"https://www.google.com/travel/flights?tfs={tfs}&hl=es-419&gl=CO&curr=COP"

    orig_msg = _pb_vf(1, 1) + _pb_sf(2, orig_iata.upper())
    dest_msg = _pb_vf(1, 1) + _pb_sf(2, dest_iata.upper())

    seg_bytes = b""
    for seg in legs_data:
        seg_msg = (
            _pb_sf(1, str(seg.get("orig", orig_iata)).upper())
            + _pb_sf(2, str(seg.get("date", flight_date)))
            + _pb_sf(3, str(seg.get("dest", dest_iata)).upper())
            + _pb_sf(5, str(seg.get("carrier", "")))
            + _pb_sf(6, str(seg.get("number", "")))
        )
        seg_bytes += _pb_mf(4, seg_msg)

    leg_msg = _pb_sf(2, flight_date) + seg_bytes + _pb_mf(13, orig_msg) + _pb_mf(14, dest_msg)
    payload = (
        _pb_vf(1, 28)
        + _pb_vf(2, 2)
        + _pb_mf(3, leg_msg)
        + _pb_vf(8, 1)
        + _pb_vf(9, 1)
        + _pb_vf(14, 1)
        + _pb_mf(16, b"\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01")
        + _pb_vf(19, 2)
    )
    tfs = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    tfu_proto = _pb_sf(1, raw_tfu_token) + _pb_mf(2, _pb_vf(1, 0)) + _pb_sf(4, "")
    tfu = base64.urlsafe_b64encode(tfu_proto).decode("ascii").rstrip("=")
    return f"https://www.google.com/travel/flights/booking?tfs={tfs}&tfu={tfu}&hl=es-419&gl=CO&curr=COP"


def build_deep_link(
    provider_id: str,
    orig_iata: str,
    dest_iata: str,
    flight_date: str,
    orig_slug: str = "",
    dest_slug: str = "",
) -> str:
    """
    Construye el enlace directo de compra hacia cada portal o aerolínea
    con origen, destino y fecha exacta precargados.
    """
    orig = orig_iata.upper()
    dest = dest_iata.upper()
    yymmdd = flight_date.replace("-", "")[2:]

    if provider_id == "google_flights":
        tfs = build_google_flights_tfs(orig, dest, flight_date)
        return f"https://www.google.com/travel/flights?tfs={tfs}&hl=es-419&gl=CO&curr=COP"

    if provider_id == "rappitravel":
        return (
            f"https://travel.rappi.com/co/flights?origin={orig}&destination={dest}"
            f"&departureDate={flight_date}&adults=1&cabinClass=economy"
        )

    if provider_id == "latam":
        return (
            f"https://www.latamairlines.com/co/es/ofertas-vuelos?origin={orig}"
            f"&inbound=null&outbound={flight_date}T12%3A00%3A00.000Z&destination={dest}"
            f"&adt=1&chd=0&inf=0&trip=OW&cabin=Economy&redemption=false&sort=PRICE%2Casc"
        )

    if provider_id == "kiwi":
        o_slug = orig_slug or orig.lower()
        d_slug = dest_slug or dest.lower()
        return f"https://www.kiwi.com/co/search/results/{o_slug}/{d_slug}/{flight_date}/no-return?sortBy=price"

    if provider_id == "kayak":
        return f"https://www.kayak.com.co/flights/{orig}-{dest}/{flight_date}?sort=price_a"

    if provider_id == "jetsmart":
        return (
            f"https://jetsmart.com/co/es/booking/search?o1={orig}&d1={dest}"
            f"&dd1={flight_date}&ADT=1&CHD=0&INF=0&currency=COP"
        )

    if provider_id == "skyscanner":
        return f"https://www.skyscanner.com.co/transporte/vuelos/{orig.lower()}/{dest.lower()}/{yymmdd}/?adultsv2=1&cabinclass=economy"

    if provider_id == "avianca":
        return (
            f"https://www.avianca.com/es/booking/select/?origin1={orig}"
            f"&destination1={dest}&departure1={flight_date}&adt1=1&tng1=0&chd1=0&inf1=0&currency=COP"
        )

    if provider_id == "wingo":
        return f"https://www.wingo.com/es/vuelos/{orig.lower()}-{dest.lower()}?date={flight_date}&adults=1&currency=COP"

    if provider_id == "booking":
        return (
            f"https://www.booking.com/flights/index.es.html?type=ONEWAY"
            f"&from={orig}&to={dest}&depart={flight_date}&adults=1&cabinClass=ECONOMY&sort=CHEAPEST"
        )

    tfs = build_google_flights_tfs(orig, dest, flight_date)
    return f"https://www.google.com/travel/flights?tfs={tfs}&hl=es-419&gl=CO&curr=COP"


def _format_hhmm(time_arr: list | None) -> str:
    if not isinstance(time_arr, list) or not time_arr:
        return "08:00"
    hour = time_arr[0] if len(time_arr) > 0 and isinstance(time_arr[0], int) else 0
    minute = time_arr[1] if len(time_arr) > 1 and isinstance(time_arr[1], int) else 0
    return f"{hour:02d}:{minute:02d}"


def _format_duration(minutes_val: int | float | None) -> str:
    if not isinstance(minutes_val, (int, float)) or minutes_val <= 0:
        return "1h 15m"
    total_m = int(round(minutes_val))
    h, m = divmod(total_m, 60)
    if h > 0 and m > 0:
        return f"{h}h {m:02d}m"
    if h > 0:
        return f"{h}h 00m"
    return f"{m}m"


def _parse_google_flights_ds1(data: list, flight_date: str) -> list[dict]:
    """
    Extrae todos los vuelos reales del bloque `ds:1` de Google Flights con sus precios
    reales en COP, aerolíneas, números de vuelo, horarios, duración, escalas y el token
    `tfu` + segmentos para abrir directamente la página de Reserva de cada vuelo.
    """
    parsed = []
    if not isinstance(data, list):
        return parsed

    seen = set()
    for group_idx in (2, 3):
        if len(data) <= group_idx or not isinstance(data[group_idx], list) or not data[group_idx]:
            continue
        rows = data[group_idx][0]
        if not isinstance(rows, list):
            continue

        for row in rows:
            try:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                detail = row[0]
                price_block = row[1]
                if (
                    not isinstance(detail, list)
                    or not isinstance(price_block, list)
                    or not price_block
                    or not isinstance(price_block[0], list)
                    or len(price_block[0]) < 2
                ):
                    continue

                raw_price = price_block[0][-1]
                if isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
                    continue
                price = float(raw_price)
                if price < 25_000:
                    continue

                raw_tfu_token = (
                    price_block[1]
                    if len(price_block) > 1 and isinstance(price_block[1], str)
                    else ""
                )

                airlines_list = detail[1] if len(detail) > 1 and isinstance(detail[1], list) else []
                airline_str = " / ".join(str(a) for a in airlines_list if a) or "Aerolínea"

                legs = detail[2] if len(detail) > 2 and isinstance(detail[2], list) else []
                if not legs:
                    continue

                first_leg = legs[0]
                flight_num_label = ""
                if isinstance(first_leg, list) and len(first_leg) > 22 and isinstance(first_leg[22], list):
                    carrier_code = first_leg[22][0] if len(first_leg[22]) > 0 else ""
                    fnum = first_leg[22][1] if len(first_leg[22]) > 1 else ""
                    if carrier_code and fnum:
                        flight_num_label = f"{carrier_code} {fnum}"

                legs_data = []
                for l in legs:
                    if not isinstance(l, list) or len(l) <= 22:
                        continue
                    l_orig = l[3] if len(l) > 3 and isinstance(l[3], str) else ""
                    l_dest = l[6] if len(l) > 6 and isinstance(l[6], str) else ""
                    l_dt = flight_date
                    if len(l) > 20 and isinstance(l[20], list) and len(l[20]) >= 3:
                        try:
                            l_dt = f"{int(l[20][0]):04d}-{int(l[20][1]):02d}-{int(l[20][2]):02d}"
                        except Exception:
                            l_dt = flight_date
                    l_carrier = ""
                    l_fnum = ""
                    if isinstance(l[22], list) and len(l[22]) >= 2:
                        l_carrier = str(l[22][0])
                        l_fnum = str(l[22][1])
                    if l_orig and l_dest and l_carrier and l_fnum:
                        legs_data.append(
                            {
                                "orig": l_orig,
                                "dest": l_dest,
                                "date": l_dt,
                                "carrier": l_carrier,
                                "number": l_fnum,
                            }
                        )

                dep_str = _format_hhmm(detail[5] if len(detail) > 5 else None)
                arr_str = _format_hhmm(detail[8] if len(detail) > 8 else None)
                dur_str = _format_duration(detail[9] if len(detail) > 9 else None)

                stops_count = max(0, len(legs) - 1)
                is_direct = stops_count == 0

                if is_direct:
                    layover_info = "Directo (sin escalas)"
                else:
                    layovers_raw = detail[13] if len(detail) > 13 and isinstance(detail[13], list) else []
                    via_parts = []
                    for lv in layovers_raw:
                        if isinstance(lv, list) and len(lv) >= 2:
                            lv_min = lv[0] if isinstance(lv[0], int) else None
                            lv_code = lv[1] if isinstance(lv[1], str) else ""
                            if lv_code and lv_min:
                                via_parts.append(f"{lv_code} ({_format_duration(lv_min)})")
                            elif lv_code:
                                via_parts.append(lv_code)
                    if not via_parts:
                        via_codes = [
                            str(l[6]) for l in legs[:-1] if isinstance(l, list) and len(l) > 6 and l[6]
                        ]
                        via_parts = via_codes or ["conexión"]

                    if stops_count == 1:
                        layover_info = f"1 escala en {via_parts[0]}"
                    else:
                        short_vias = ", ".join(p.split()[0] for p in via_parts)
                        layover_info = f"{stops_count} escalas (vía {short_vias})"

                dedup_key = (airline_str, dep_str, arr_str, stops_count, int(round(price)))
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                parsed.append(
                    {
                        "flight_date": flight_date,
                        "price": price,
                        "currency": "COP",
                        "is_direct": is_direct,
                        "stops_count": stops_count,
                        "layover_info": layover_info,
                        "airline": airline_str,
                        "flight_number": flight_num_label,
                        "departure_time": dep_str,
                        "arrival_time": arr_str,
                        "duration": dur_str,
                        "legs_data": legs_data,
                        "raw_tfu": raw_tfu_token,
                    }
                )
            except Exception:
                continue

    parsed.sort(key=lambda x: (x["price"], 0 if x["is_direct"] else 1))
    return parsed


def fetch_live_google_flights(
    orig_iata: str,
    dest_iata: str,
    flight_date: str,
    timeout: float = 7.0,
    bypass_cache: bool = False,
) -> list[dict]:
    orig = orig_iata.upper()
    dest = dest_iata.upper()
    cache_key = (orig, dest, flight_date)
    now_ts = time.time()

    if not bypass_cache:
        with _CACHE_LOCK:
            cached = _LIVE_CACHE.get(cache_key)
            if cached and (now_ts - cached[0]) < _CACHE_TTL_SECONDS:
                return [dict(item) for item in cached[1]]

    try:
        target_dt = datetime.strptime(flight_date, "%Y-%m-%d").date()
        if target_dt < date.today():
            return []
    except ValueError:
        return []

    tfs = build_google_flights_tfs(orig, dest, flight_date)
    # Cadena de variantes: desde algunas IP (p. ej. PythonAnywhere) Google responde a
    # veces con un ErrorResponse vacío; la ruta /search y hl=en suelen devolver datos.
    urls = [
        f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=es-419&gl=CO&curr=COP",
        f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=en&gl=CO&curr=COP",
        f"https://www.google.com/travel/flights?tfs={tfs}&hl=es-419&gl=CO&curr=COP",
        f"https://www.google.com/travel/flights?tfs={tfs}&hl=en&curr=COP",
    ]

    session = requests.Session()
    session.trust_env = True  # respeta HTTP(S)_PROXY (proxy de PythonAnywhere gratis)
    for attempt, url in enumerate(urls):
        resp = None
        try:
            resp = session.get(url, headers=_HTTP_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                _log.warning(
                    "Google Flights HTTP %s (%s-%s %s) tipo=%s inicio=%s",
                    resp.status_code, orig, dest, flight_date,
                    resp.headers.get("Content-Type", ""), _safe_snippet(resp.text),
                )
                continue
            flights = []
            payloads = _extract_ds1_payloads(resp.text)
            for data in payloads:
                try:
                    flights = _parse_google_flights_ds1(data, flight_date)
                except Exception:
                    flights = []
                if flights:
                    break
            if flights:
                with _CACHE_LOCK:
                    _LIVE_CACHE[cache_key] = (time.time(), flights)
                return [dict(item) for item in flights]
            _log.warning(
                "Google Flights sin datos (%s-%s %s) variante=%d bloques=%d error_google=%s",
                orig, dest, flight_date, attempt + 1, len(payloads),
                "ErrorResponse" in json.dumps(payloads)[:400] if payloads else False,
            )
        except Exception as exc:
            _log.warning(
                "Google Flights falló (%s-%s %s): %s: %s estado=%s",
                orig, dest, flight_date, type(exc).__name__, exc,
                getattr(resp, "status_code", "-"),
            )
        if attempt < len(urls) - 1:
            time.sleep(0.3)

    return []


def _build_offers_from_live_flights(
    live_flights: list[dict],
    orig_info: dict,
    dest_info: dict,
    flight_date: str,
) -> list[dict]:
    """
    Convierte los vuelos reales obtenidos en vivo en ofertas verificadas.
    Cada oferta enlaza DIRECTAMENTE a la página de 'Opciones de reserva'
    (`/travel/flights/booking?tfs=...&tfu=...`) de ese vuelo exacto en Google Flights,
    eliminando el paso de buscar el vuelo en la lista general.
    """
    orig_iata = orig_info["primary"]
    dest_iata = dest_info["primary"]

    offers: list[dict] = []
    if not live_flights:
        return offers

    for fl in live_flights[:20]:
        fnum = fl.get("flight_number", "").strip()
        airline_display = f"{fl['airline']} ({fnum})" if fnum else fl["airline"]

        direct_booking_url = build_google_flights_booking_url(
            orig_iata=orig_iata,
            dest_iata=dest_iata,
            flight_date=flight_date,
            legs_data=fl.get("legs_data", []),
            raw_tfu_token=fl.get("raw_tfu", ""),
        )

        offers.append(
            {
                "provider_id": "google_flights",
                "provider_name": "Google Flights",
                "flight_date": flight_date,
                "price": float(fl["price"]),
                "currency": "COP",
                "is_direct": bool(fl["is_direct"]),
                "stops_count": int(fl["stops_count"]),
                "layover_info": fl["layover_info"],
                "airline": airline_display,
                "departure_time": fl["departure_time"],
                "arrival_time": fl["arrival_time"],
                "duration": fl["duration"],
                "deep_link": direct_booking_url,
            }
        )

    offers.sort(key=lambda x: (x["price"], 0 if x["is_direct"] else 1))
    return offers


def _estimate_base_route_profile(orig_info: dict, dest_info: dict) -> dict:
    orig_country = orig_info.get("country", "CO")
    dest_country = dest_info.get("country", "INT")
    orig_region = orig_info.get("region", "SA")
    dest_region = dest_info.get("region", "INT")
    orig_iata = orig_info["primary"]
    dest_iata = dest_info["primary"]

    if orig_country == "CO" and dest_country == "CO":
        return {
            "base_cop": 148_000,
            "direct_available": True,
            "direct_duration": "1h 10m",
            "layover_duration": "3h 40m",
            "layover_hubs": ["BOG (1h 20m)", "MDE (1h 15m)", "CLO (1h 30m)"],
            "airlines_direct": ["LATAM", "JetSMART", "Wingo", "Avianca"],
            "airlines_layover": ["Avianca", "LATAM", "JetSMART"],
            "lowcost_applicable": True,
            "domestic_direct_cheaper": True,
        }

    if (
        {orig_region, dest_region} <= {"SA", "CA"}
        or dest_country in ("PA", "PE", "EC", "DO", "CR", "AW", "CW", "MX")
        or orig_country in ("PA", "PE", "EC", "DO", "CR", "MX")
    ):
        return {
            "base_cop": 840_000,
            "direct_available": True,
            "direct_duration": "3h 35m",
            "layover_duration": "6h 50m",
            "layover_hubs": ["PTY (1h 45m)", "BOG (1h 55m)", "LIM (2h 10m)"],
            "airlines_direct": ["Wingo", "Avianca", "Copa Airlines", "JetSMART"],
            "airlines_layover": ["Copa Airlines", "Avianca", "JetSMART"],
            "lowcost_applicable": True,
            "domestic_direct_cheaper": False,
        }

    if "NA" in (orig_region, dest_region):
        return {
            "base_cop": 1_120_000,
            "direct_available": True,
            "direct_duration": "4h 10m",
            "layover_duration": "7h 45m",
            "layover_hubs": ["PTY (1h 50m)", "MIA (2h 25m)", "BOG (1h 40m)", "CUN (2h 05m)"],
            "airlines_direct": ["Avianca", "American Airlines", "LATAM", "Spirit"],
            "airlines_layover": ["Copa Airlines", "Spirit", "JetBlue", "Avianca"],
            "lowcost_applicable": False,
            "domestic_direct_cheaper": False,
        }

    if "EU" in (orig_region, dest_region):
        direct_eu = (orig_iata in ("BOG", "MDE", "CLO") and dest_iata in ("MAD", "BCN", "CDG", "LHR")) or (
            dest_iata in ("BOG", "MDE", "CLO") and orig_iata in ("MAD", "BCN", "CDG", "LHR")
        )
        return {
            "base_cop": 2_450_000,
            "direct_available": direct_eu,
            "direct_duration": "10h 05m",
            "layover_duration": "14h 20m",
            "layover_hubs": [
                "MAD (2h 15m)",
                "PTY (1h 55m)",
                "MIA (2h 40m)",
                "BOG (1h 50m)",
                "CDG (2h 10m)",
            ],
            "airlines_direct": ["Iberia", "Avianca", "Air Europa", "Plus Ultra"],
            "airlines_layover": ["Air France", "Iberia", "KLM", "Air Europa", "Turkish Airlines"],
            "lowcost_applicable": False,
            "domestic_direct_cheaper": False,
        }

    return {
        "base_cop": 1_390_000,
        "direct_available": True,
        "direct_duration": "5h 45m",
        "layover_duration": "8h 55m",
        "layover_hubs": ["LIM (1h 55m)", "PTY (2h 05m)", "BOG (1h 40m)", "SCL (2h 15m)"],
        "airlines_direct": ["Avianca", "JetSMART", "LATAM"],
        "airlines_layover": ["JetSMART", "Copa Airlines", "LATAM", "Sky Airline"],
        "lowcost_applicable": True,
        "domestic_direct_cheaper": False,
    }


def _seasonal_and_day_factor(flight_date: str) -> float:
    try:
        dt = datetime.strptime(flight_date, "%Y-%m-%d")
        weekday = dt.weekday()
        month = dt.month
        day = dt.day
    except ValueError:
        return 1.0

    weekday_multipliers = {
        0: 0.99,
        1: 0.94,
        2: 0.95,
        3: 0.98,
        4: 1.08,
        5: 1.05,
        6: 1.07,
    }
    w_factor = weekday_multipliers.get(weekday, 1.0)

    if (month == 12 and day >= 16) or (month == 1 and day <= 14):
        season_factor = 1.22
        if month == 12 and 23 <= day <= 27:
            season_factor = 1.45
    elif month == 12 and day < 16:
        season_factor = 0.92
    elif month in (6, 7):
        season_factor = 1.15
    else:
        season_factor = 1.0

    return w_factor * season_factor


def _seeded_rng(seed_text: str) -> random.Random:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def search_flights_for_date(
    origin_input: str,
    destination_input: str,
    flight_date: str,
    stop_filter: str = "all",
    jitter_seed: str = "",
    attempt_live: bool = True,
    bypass_cache: bool = False,
) -> list[dict]:
    orig_info = resolve_location(origin_input)
    dest_info = resolve_location(destination_input)
    orig_iata = orig_info["primary"]
    dest_iata = dest_info["primary"]

    offers: list[dict] = []

    if attempt_live:
        live_flights = fetch_live_google_flights(orig_iata, dest_iata, flight_date, bypass_cache=bypass_cache)
        if live_flights:
            offers = _build_offers_from_live_flights(live_flights, orig_info, dest_info, flight_date)

    if not offers and not config.DEMO_MODE:
        # Producción: nunca inventar precios. Sin datos reales => lista vacía.
        _log.warning("Sin vuelos reales para %s-%s el %s", orig_iata, dest_iata, flight_date)
        return []

    if not offers:
        profile = _estimate_base_route_profile(orig_info, dest_info)
        base_cop = profile["base_cop"]
        day_factor = _seasonal_and_day_factor(flight_date)

        if not jitter_seed:
            jitter_seed = datetime.now().strftime("%Y-%m-%d-%H")

        for portal in PORTALS:
            pid = portal["id"]
            pname = portal["name"]
            is_lowcost_longhaul = (not profile["lowcost_applicable"]) and pid in ("wingo", "jetsmart")
            rng = _seeded_rng(f"{orig_iata}-{dest_iata}-{flight_date}-{pid}-{jitter_seed}")

            deep_link = build_deep_link(
                pid,
                orig_iata,
                dest_iata,
                flight_date,
                orig_info.get("city_slug", ""),
                dest_info.get("city_slug", ""),
            )

            if profile["direct_available"] and not is_lowcost_longhaul:
                direct_factor = rng.uniform(0.96, 1.15)
                if pid in ("jetsmart", "wingo", "google_flights", "rappitravel") and profile["lowcost_applicable"]:
                    direct_factor *= 0.96
                direct_price = round((base_cop * day_factor * direct_factor) / 1000) * 1000
                airline_direct = (
                    pname if pid in ("avianca", "wingo", "jetsmart", "latam") else rng.choice(profile["airlines_direct"])
                )
                dep_h2 = rng.randint(5, 21)
                dep_m2 = rng.choice(["05", "20", "35", "50"])
                arr_h2 = (dep_h2 + rng.randint(1, 9)) % 24

                offers.append(
                    {
                        "provider_id": pid,
                        "provider_name": pname,
                        "flight_date": flight_date,
                        "price": float(direct_price),
                        "currency": "COP",
                        "is_direct": True,
                        "stops_count": 0,
                        "layover_info": "Directo (sin escalas)",
                        "airline": airline_direct,
                        "departure_time": f"{dep_h2:02d}:{dep_m2}",
                        "arrival_time": f"{arr_h2:02d}:{dep_m2}",
                        "duration": profile["direct_duration"],
                        "deep_link": deep_link,
                    }
                )

            if profile.get("domestic_direct_cheaper"):
                layover_factor = rng.uniform(1.55, 1.85)
            else:
                layover_factor = rng.uniform(0.92, 1.12)

            layover_price = round((base_cop * day_factor * layover_factor) / 1000) * 1000
            stops_count = 1 if rng.random() < 0.85 else 2
            hub_choice = profile["layover_hubs"][0]
            for h in profile["layover_hubs"]:
                if not h.startswith(orig_iata) and not h.startswith(dest_iata):
                    hub_choice = h
                    break

            stops_label = (
                f"1 escala en {hub_choice}"
                if stops_count == 1
                else f"2 escalas (vía {hub_choice.split()[0]})"
            )
            airline_layover = (
                pname if pid in ("avianca", "wingo", "jetsmart", "latam") else rng.choice(profile["airlines_layover"])
            )
            dep_hour = rng.randint(6, 20)
            dep_min = rng.choice(["00", "15", "30", "45"])
            arr_hour = (dep_hour + rng.randint(3, 12)) % 24

            offers.append(
                {
                    "provider_id": pid,
                    "provider_name": pname,
                    "flight_date": flight_date,
                    "price": float(layover_price),
                    "currency": "COP",
                    "is_direct": False,
                    "stops_count": stops_count,
                    "layover_info": stops_label,
                    "airline": airline_layover,
                    "departure_time": f"{dep_hour:02d}:{dep_min}",
                    "arrival_time": f"{arr_hour:02d}:{dep_min}",
                    "duration": profile["layover_duration"],
                    "deep_link": deep_link,
                }
            )

    if stop_filter == "direct":
        filtered = [o for o in offers if o["is_direct"]]
        if filtered:
            offers = filtered
    elif stop_filter == "layover":
        filtered = [o for o in offers if not o["is_direct"]]
        if filtered:
            offers = filtered

    offers.sort(key=lambda x: (x["price"], 0 if x["is_direct"] else 1))
    return offers


def generate_monthly_calendar_offers(
    origin_input: str,
    destination_input: str,
    travel_month: str,
    stop_filter: str = "all",
    jitter_seed: str = "",
    attempt_live: bool = True,
) -> list[dict]:
    try:
        year, month = map(int, travel_month.split("-"))
    except Exception:
        now = date.today()
        year, month = now.year, now.month

    _, num_days = calendar.monthrange(year, month)
    today_dt = date.today()
    day_names_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    orig_info = resolve_location(origin_input)
    dest_info = resolve_location(destination_input)
    orig_iata = orig_info["primary"]
    dest_iata = dest_info["primary"]

    days_to_query = []
    for day in range(1, num_days + 1):
        dt_obj = date(year, month, day)
        if dt_obj >= today_dt:
            days_to_query.append((day, dt_obj, f"{year:04d}-{month:02d}-{day:02d}"))

    if attempt_live and days_to_query:
        def _warm_day(item):
            _, _, f_date = item
            fetch_live_google_flights(orig_iata, dest_iata, f_date, timeout=6.5)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(_warm_day, days_to_query))

    monthly_best = []
    for day, dt_obj, f_date in days_to_query:
        day_offers = search_flights_for_date(
            origin_input=origin_input,
            destination_input=destination_input,
            flight_date=f_date,
            stop_filter=stop_filter,
            jitter_seed=jitter_seed,
            attempt_live=attempt_live,
        )
        if not day_offers:
            continue
        best = day_offers[0]
        monthly_best.append(
            {
                "flight_date": f_date,
                "day_number": day,
                "weekday_name": day_names_es[dt_obj.weekday()],
                "price": best["price"],
                "currency": best["currency"],
                "is_direct": best["is_direct"],
                "stops_count": best["stops_count"],
                "layover_info": best["layover_info"],
                "provider_id": best["provider_id"],
                "provider_name": best["provider_name"],
                "airline": best["airline"],
                "deep_link": best["deep_link"],
            }
        )

    return monthly_best
