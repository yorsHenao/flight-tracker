from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import smtplib
import sys

import config
from database import create_alert


def format_cop(amount: float | None) -> str:
    if amount is None:
        return "N/D"
    return f"${int(round(amount)):,}".replace(",", ".") + " COP"


def format_date_dmy(date_str: str | None) -> str:
    """
    Formatea fechas YYYY-MM-DD (o YYYY-MM-DD HH:MM:SS) al formato DD-MM-YYYY (ej. 20-01-2026).
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    date_part = s[:10]
    rest = s[10:]
    parts = date_part.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}{rest}"
    return s


def format_month_my(month_str: str | None) -> str:
    """
    Formatea meses YYYY-MM al formato MM-YYYY (ej. 01-2026).
    """
    if not month_str:
        return ""
    s = str(month_str).strip()
    parts = s.split("-")
    if len(parts) == 2 and len(parts[0]) == 4:
        return f"{parts[1]}-{parts[0]}"
    return s


def _city_code(label: str, fallback: str = "") -> tuple[str, str]:
    """'Medellín, Colombia (MDE)' -> ('Medellín', 'MDE'). Tolera etiquetas antiguas como '(Mde)'."""
    import re
    label = (label or "").strip()
    m = re.search(r"\(\s*([A-Za-z]{3})\s*\)\s*$", label)
    code = (m.group(1).upper() if m else fallback.upper())
    city = label.split("(")[0].split(",")[0].strip() or code
    return city, code


def build_friendly_email(search_row: dict, best_offer: dict, previous_best: float | None = None,
                         test_notice: str = "") -> dict:
    o_city, o_code = _city_code(search_row.get("origin_label", ""), search_row.get("origin_iata", ""))
    d_city, d_code = _city_code(search_row.get("destination_label", ""), search_row.get("destination_iata", ""))
    route_txt = f"{o_city} ({o_code}) a {d_city} ({d_code})"

    price_val = float(best_offer["price"])
    price_str = format_cop(price_val)
    is_direct = bool(best_offer.get("is_direct"))
    stops_plain = "Directo" if is_direct else (best_offer.get("layover_info") or "Con escala")
    provider_plain = best_offer.get("provider_name") or "el sitio de reserva"
    airline_plain = best_offer.get("airline") or provider_plain
    times = ""
    if best_offer.get("departure_time") and best_offer.get("arrival_time"):
        times = f"{best_offer['departure_time']} – {best_offer['arrival_time']}"
    flight_date_dmy = format_date_dmy(best_offer.get("flight_date")) or "por confirmar"

    savings_plain = ""
    if previous_best and previous_best > price_val:
        savings_plain = f"Bajó {format_cop(previous_best - price_val)} frente al precio anterior."

    subject = f"Nuevo precio: {route_txt} por {price_str}"

    friendly_message = "\n".join(x for x in [
        *( [test_notice, ""] if test_notice else [] ),
        f"Encontramos un buen precio para {route_txt}.",
        "",
        f"Precio: {price_str}" + (f" · {savings_plain}" if savings_plain else ""),
        f"Vuelo: {airline_plain} · {stops_plain}" + (f" · {times}" if times else ""),
        f"Fecha: {flight_date_dmy}",
        "",
        f"Reservar en {provider_plain}:",
        best_offer["deep_link"],
    ] if x is not None)

    e = html.escape
    deep_link = e(best_offer["deep_link"], quote=True)
    badge_bg = "#E8F1FD" if is_direct else "#F2F2F5"
    badge_color = "#0A58CA" if is_direct else "#3A3A3C"
    savings_html = f'<p style="margin:10px 0 0;font-size:13px;color:#0A58CA;">{e(savings_plain)}</p>' if savings_plain else ""
    times_html = f" · {e(times)}" if times else ""
    notice_html = (
        f'<p style="margin:0 0 18px;padding:10px 14px;border-radius:12px;background:#FFF4E5;color:#8A4B00;font-size:13px;">{e(test_notice)}</p>'
        if test_notice else ""
    )

    html_body = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:#F5F5F7;padding:28px 16px;color:#1D1D1F;">
  <div style="max-width:480px;margin:0 auto;background:#FFFFFF;border-radius:18px;padding:28px;border:1px solid rgba(0,0,0,0.06);">
    <p style="margin:0 0 18px;font-size:13px;font-weight:600;color:#0A58CA;">Vuelos Economicos</p>
    {notice_html}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr>
        <td style="text-align:left;"><div style="font-size:30px;font-weight:700;letter-spacing:-0.02em;">{e(o_code)}</div><div style="font-size:13px;color:#6E6E73;">{e(o_city)}</div></td>
        <td style="text-align:center;color:#0A58CA;font-size:20px;">&rarr;</td>
        <td style="text-align:right;"><div style="font-size:30px;font-weight:700;letter-spacing:-0.02em;">{e(d_code)}</div><div style="font-size:13px;color:#6E6E73;">{e(d_city)}</div></td>
      </tr>
    </table>
    <div style="background:#F5F5F7;border-radius:14px;padding:18px 20px;margin:20px 0;">
      <div style="font-size:13px;color:#6E6E73;margin-bottom:4px;">Mejor precio encontrado</div>
      <div style="font-size:28px;font-weight:700;letter-spacing:-0.02em;">{e(price_str)}
        <span style="display:inline-block;vertical-align:middle;font-size:12px;font-weight:600;color:{badge_color};background:{badge_bg};padding:4px 10px;border-radius:980px;margin-left:6px;">{e(stops_plain)}</span>
      </div>
      <p style="margin:10px 0 0;font-size:13px;color:#3A3A3C;">{e(airline_plain)}{times_html}</p>
      <p style="margin:4px 0 0;font-size:13px;color:#3A3A3C;">Fecha del vuelo: {e(flight_date_dmy)}</p>
      {savings_html}
    </div>
    <div style="text-align:center;">
      <a href="{deep_link}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#0A58CA;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:15px;padding:12px 28px;border-radius:980px;">Ir a la reserva</a>
      <p style="margin:10px 0 0;font-size:12px;color:#86868B;">En {e(provider_plain)}</p>
    </div>
  </div>
</div>""".strip()

    return {
        "subject": subject,
        "friendly_message": friendly_message,
        "html_body": html_body,
        "stops_label": stops_plain,
    }


def send_smtp_email(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    from email.header import Header
    from email.utils import formataddr

    import os
    config._load_env_file(config.ENV_FILE_PATH)
    smtp_enabled = os.environ.get("VUELOS_SMTP_ENABLED", "true").lower() in ("true", "1", "yes", "si")
    smtp_user = os.environ.get("VUELOS_SMTP_USER", getattr(config, "SMTP_USER", "")).strip()
    smtp_pass = os.environ.get("VUELOS_SMTP_PASSWORD", getattr(config, "SMTP_PASSWORD", "")).replace(" ", "").strip()
    smtp_from_name = os.environ.get("VUELOS_SMTP_FROM_NAME", getattr(config, "SMTP_FROM_NAME", "Vuelos Economicos")).strip()

    placeholders = {"", "tu_correo@gmail.com", "xxxx_xxxx_xxxx_xxxx", "xxxxxxxxxxxxxxxx"}
    if not smtp_enabled or smtp_user in placeholders or smtp_pass in placeholders:
        print(
            f"[SMTP] Envío omitido: SMTP desactivado o sin usuario/contraseña configurados "
            f"(habilitado={smtp_enabled}, usuario_configurado={smtp_user not in placeholders}).",
            file=sys.stderr, flush=True,
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = formataddr((str(Header(smtp_from_name, "utf-8")), smtp_user))
        msg["To"] = to_email

        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if int(config.SMTP_PORT) == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, int(config.SMTP_PORT), timeout=int(os.environ.get("VUELOS_SMTP_TIMEOUT", "15") or 15)) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(config.SMTP_HOST, int(config.SMTP_PORT), timeout=int(os.environ.get("VUELOS_SMTP_TIMEOUT", "15") or 15)) as server:
                server.ehlo()
                if getattr(config, "SMTP_USE_TLS", True):
                    server.starttls()
                    server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [to_email], msg.as_string())
        return True
    except Exception as exc:
        detail = str(exc).replace(smtp_pass, "***") if smtp_pass else str(exc)
        print(
            f"[SMTP] Falló el envío a {to_email} vía {config.SMTP_HOST}:{config.SMTP_PORT} "
            f"como {smtp_user}: {type(exc).__name__}: {detail[:300]}",
            file=sys.stderr, flush=True,
        )
        return False


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _env(name: str, default: str = "") -> str:
    import os
    return (os.environ.get(name, default) or "").strip()


def send_brevo_email(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    """Envía por la API transaccional de Brevo. Nunca registra la clave."""
    import requests
    api_key = _env("VUELOS_BREVO_API_KEY")
    sender_email = _env("VUELOS_SENDER_EMAIL") or _env("VUELOS_SMTP_USER")
    sender_name = _env("VUELOS_SMTP_FROM_NAME", "Vuelos Economicos") or "Vuelos Economicos"
    if not api_key or not sender_email:
        print(f"[BREVO] Envío omitido: falta clave o remitente (remitente_configurado={bool(sender_email)}).",
              file=sys.stderr, flush=True)
        return False
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": plain_text,
    }
    headers = {"api-key": api_key, "accept": "application/json", "content-type": "application/json"}
    try:
        timeout = int(_env("VUELOS_BREVO_TIMEOUT", "15") or 15)
        resp = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:
        detail = str(exc).replace(api_key, "***")
        print(f"[BREVO] Falló la conexión al enviar a {to_email}: {type(exc).__name__}: {detail[:300]}",
              file=sys.stderr, flush=True)
        return False
    if 200 <= resp.status_code < 300:
        return True
    try:
        data = resp.json()
        message = f"{data.get('code', '')} {data.get('message', '')}".strip()
    except Exception:
        message = (resp.text or "")[:300]
    message = message.replace(api_key, "***")
    print(f"[BREVO] Falló el envío a {to_email}: HTTP {resp.status_code}: {message[:300]}",
          file=sys.stderr, flush=True)
    return False


def get_email_provider() -> str:
    config._load_env_file(config.ENV_FILE_PATH)
    provider = _env("VUELOS_EMAIL_PROVIDER").lower()
    if provider in ("brevo", "smtp"):
        return provider
    return "brevo" if _env("VUELOS_BREVO_API_KEY") else "smtp"


def deliver_email(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    """Punto único de envío: Brevo si está configurado, SMTP como respaldo."""
    if get_email_provider() == "brevo":
        if send_brevo_email(to_email, subject, plain_text, html_body):
            return True
        print("[BREVO] Intentando respaldo SMTP.", file=sys.stderr, flush=True)
    return send_smtp_email(to_email, subject, plain_text, html_body)


# Alias de compatibilidad. Dentro de notify_lowest_price el parámetro send_email (bool)
# lo ocultaría, por eso el código interno usa deliver_email.
send_email = deliver_email


def notify_lowest_price(
    search_row: dict,
    best_offer: dict,
    previous_best: float | None = None,
    db_path: str | None = None,
    send_email: bool = True,
    subject_prefix: str = "",
) -> dict:
    payload = build_friendly_email(search_row, best_offer, previous_best)
    payload["subject"] = subject_prefix + payload["subject"]
    sent_ok = False
    if send_email:
        sent_ok = deliver_email(
            to_email=search_row["notify_email"],
            subject=payload["subject"],
            plain_text=payload["friendly_message"],
            html_body=payload["html_body"],
        )

    alert_record = create_alert(
        search_id=search_row["id"],
        user_id=search_row["user_id"],
        notify_email=search_row["notify_email"],
        subject=payload["subject"],
        friendly_message=payload["friendly_message"],
        html_preview=payload["html_body"],
        price=float(best_offer["price"]),
        previous_best=previous_best,
        is_direct=bool(best_offer.get("is_direct")),
        stops_label=payload["stops_label"],
        provider_name=best_offer["provider_name"],
        flight_date=best_offer["flight_date"],
        deep_link=best_offer["deep_link"],
        email_sent=sent_ok,
        db_path=db_path,
    )
    return alert_record


TEST_EMAIL_NOTICE = "Este es un correo de prueba. Los datos son de ejemplo y no corresponden a un precio real."


def send_test_email(to_email: str) -> bool:
    """Envía un correo de prueba con la plantilla real de alertas. No guarda nada en la base de datos."""
    sample_search = {
        "origin_label": "Medellín (MDE)", "origin_iata": "MDE",
        "destination_label": "Bogotá (BOG)", "destination_iata": "BOG",
    }
    sample_offer = {
        "price": 199900, "is_direct": True, "airline": "Aerolínea de ejemplo",
        "provider_name": "Google Flights", "departure_time": "06:00", "arrival_time": "07:05",
        "flight_date": None, "deep_link": "https://www.google.com/travel/flights",
    }
    payload = build_friendly_email(sample_search, sample_offer, test_notice=TEST_EMAIL_NOTICE)
    return deliver_email(
        to_email=to_email,
        subject="Prueba: correo de alertas de Vuelos Economicos",
        plain_text=payload["friendly_message"],
        html_body=payload["html_body"],
    )
