import unicodedata


def _normalize(text: str) -> str:
    """Elimina tildes y pasa a minúsculas para búsqueda flexible."""
    if not text:
        return ""
    text = text.strip().lower()
    # Si viene con código entre paréntesis ej. "Bogotá (BOG)", extraer también
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Diccionario de ciudades y países -> código IATA principal, aeropuertos alternos y etiqueta legible
LOCATIONS_DB = {
    # --- COLOMBIA ---
    "colombia": {
        "primary": "BOG",
        "iatas": ["BOG", "MDE", "CLO", "CTG", "BAQ"],
        "label": "Colombia (Bogotá BOG, Medellín MDE)",
        "city_slug": "bogota-colombia",
        "country": "CO",
        "region": "SA",
    },
    "bogota": {
        "primary": "BOG",
        "iatas": ["BOG"],
        "label": "Bogotá, Colombia (BOG)",
        "city_slug": "bogota-colombia",
        "country": "CO",
        "region": "SA",
    },
    "medellin": {
        "primary": "MDE",
        "iatas": ["MDE"],
        "label": "Medellín, Colombia (MDE)",
        "city_slug": "medellin-colombia",
        "country": "CO",
        "region": "SA",
    },
    "cali": {
        "primary": "CLO",
        "iatas": ["CLO"],
        "label": "Cali, Colombia (CLO)",
        "city_slug": "cali-colombia",
        "country": "CO",
        "region": "SA",
    },
    "cartagena": {
        "primary": "CTG",
        "iatas": ["CTG"],
        "label": "Cartagena, Colombia (CTG)",
        "city_slug": "cartagena-colombia",
        "country": "CO",
        "region": "SA",
    },
    "barranquilla": {
        "primary": "BAQ",
        "iatas": ["BAQ"],
        "label": "Barranquilla, Colombia (BAQ)",
        "city_slug": "barranquilla-colombia",
        "country": "CO",
        "region": "SA",
    },
    "santa marta": {
        "primary": "SMR",
        "iatas": ["SMR"],
        "label": "Santa Marta, Colombia (SMR)",
        "city_slug": "santa-marta-colombia",
        "country": "CO",
        "region": "SA",
    },
    "san andres": {
        "primary": "ADZ",
        "iatas": ["ADZ"],
        "label": "San Andrés, Colombia (ADZ)",
        "city_slug": "san-andres-colombia",
        "country": "CO",
        "region": "SA",
    },
    "pereira": {
        "primary": "PEI",
        "iatas": ["PEI"],
        "label": "Pereira, Colombia (PEI)",
        "city_slug": "pereira-colombia",
        "country": "CO",
        "region": "SA",
    },
    "bucaramanga": {
        "primary": "BGA",
        "iatas": ["BGA"],
        "label": "Bucaramanga, Colombia (BGA)",
        "city_slug": "bucaramanga-colombia",
        "country": "CO",
        "region": "SA",
    },

    # --- ESPAÑA Y EUROPA ---
    "espana": {
        "primary": "MAD",
        "iatas": ["MAD", "BCN"],
        "label": "España (Madrid MAD, Barcelona BCN)",
        "city_slug": "madrid-spain",
        "country": "ES",
        "region": "EU",
    },
    "madrid": {
        "primary": "MAD",
        "iatas": ["MAD"],
        "label": "Madrid, España (MAD)",
        "city_slug": "madrid-spain",
        "country": "ES",
        "region": "EU",
    },
    "barcelona": {
        "primary": "BCN",
        "iatas": ["BCN"],
        "label": "Barcelona, España (BCN)",
        "city_slug": "barcelona-spain",
        "country": "ES",
        "region": "EU",
    },
    "francia": {
        "primary": "CDG",
        "iatas": ["CDG", "ORY"],
        "label": "Francia (París CDG)",
        "city_slug": "paris-france",
        "country": "FR",
        "region": "EU",
    },
    "paris": {
        "primary": "CDG",
        "iatas": ["CDG", "ORY"],
        "label": "París, Francia (CDG)",
        "city_slug": "paris-france",
        "country": "FR",
        "region": "EU",
    },
    "italia": {
        "primary": "FCO",
        "iatas": ["FCO", "MXP"],
        "label": "Italia (Roma FCO, Milán MXP)",
        "city_slug": "rome-italy",
        "country": "IT",
        "region": "EU",
    },
    "roma": {
        "primary": "FCO",
        "iatas": ["FCO"],
        "label": "Roma, Italia (FCO)",
        "city_slug": "rome-italy",
        "country": "IT",
        "region": "EU",
    },
    "milan": {
        "primary": "MXP",
        "iatas": ["MXP"],
        "label": "Milán, Italia (MXP)",
        "city_slug": "milan-italy",
        "country": "IT",
        "region": "EU",
    },
    "reino unido": {
        "primary": "LHR",
        "iatas": ["LHR", "LGW"],
        "label": "Reino Unido (Londres LHR)",
        "city_slug": "london-united-kingdom",
        "country": "GB",
        "region": "EU",
    },
    "londres": {
        "primary": "LHR",
        "iatas": ["LHR", "LGW"],
        "label": "Londres, Reino Unido (LHR)",
        "city_slug": "london-united-kingdom",
        "country": "GB",
        "region": "EU",
    },
    "alemania": {
        "primary": "FRA",
        "iatas": ["FRA", "MUC"],
        "label": "Alemania (Fráncfort FRA)",
        "city_slug": "frankfurt-germany",
        "country": "DE",
        "region": "EU",
    },
    "francfort": {
        "primary": "FRA",
        "iatas": ["FRA"],
        "label": "Fráncfort, Alemania (FRA)",
        "city_slug": "frankfurt-germany",
        "country": "DE",
        "region": "EU",
    },
    "amsterdam": {
        "primary": "AMS",
        "iatas": ["AMS"],
        "label": "Ámsterdam, Países Bajos (AMS)",
        "city_slug": "amsterdam-netherlands",
        "country": "NL",
        "region": "EU",
    },
    "holanda": {
        "primary": "AMS",
        "iatas": ["AMS"],
        "label": "Países Bajos (Ámsterdam AMS)",
        "city_slug": "amsterdam-netherlands",
        "country": "NL",
        "region": "EU",
    },
    "portugal": {
        "primary": "LIS",
        "iatas": ["LIS"],
        "label": "Portugal (Lisboa LIS)",
        "city_slug": "lisbon-portugal",
        "country": "PT",
        "region": "EU",
    },
    "lisboa": {
        "primary": "LIS",
        "iatas": ["LIS"],
        "label": "Lisboa, Portugal (LIS)",
        "city_slug": "lisbon-portugal",
        "country": "PT",
        "region": "EU",
    },

    # --- NORTEAMÉRICA Y MÉXICO ---
    "estados unidos": {
        "primary": "MIA",
        "iatas": ["MIA", "JFK", "MCO", "LAX", "FLL"],
        "label": "Estados Unidos (Miami MIA, Nueva York JFK)",
        "city_slug": "miami-florida-united-states",
        "country": "US",
        "region": "NA",
    },
    "usa": {
        "primary": "MIA",
        "iatas": ["MIA", "JFK", "MCO"],
        "label": "Estados Unidos (Miami MIA, Nueva York JFK)",
        "city_slug": "miami-florida-united-states",
        "country": "US",
        "region": "NA",
    },
    "miami": {
        "primary": "MIA",
        "iatas": ["MIA", "FLL"],
        "label": "Miami, EE. UU. (MIA)",
        "city_slug": "miami-florida-united-states",
        "country": "US",
        "region": "NA",
    },
    "orlando": {
        "primary": "MCO",
        "iatas": ["MCO"],
        "label": "Orlando, EE. UU. (MCO)",
        "city_slug": "orlando-florida-united-states",
        "country": "US",
        "region": "NA",
    },
    "nueva york": {
        "primary": "JFK",
        "iatas": ["JFK", "EWR", "LGA"],
        "label": "Nueva York, EE. UU. (JFK)",
        "city_slug": "new-york-city-new-york-united-states",
        "country": "US",
        "region": "NA",
    },
    "new york": {
        "primary": "JFK",
        "iatas": ["JFK", "EWR"],
        "label": "Nueva York, EE. UU. (JFK)",
        "city_slug": "new-york-city-new-york-united-states",
        "country": "US",
        "region": "NA",
    },
    "fort lauderdale": {
        "primary": "FLL",
        "iatas": ["FLL"],
        "label": "Fort Lauderdale, EE. UU. (FLL)",
        "city_slug": "fort-lauderdale-florida-united-states",
        "country": "US",
        "region": "NA",
    },
    "los angeles": {
        "primary": "LAX",
        "iatas": ["LAX"],
        "label": "Los Ángeles, EE. UU. (LAX)",
        "city_slug": "los-angeles-california-united-states",
        "country": "US",
        "region": "NA",
    },
    "mexico": {
        "primary": "CUN",
        "iatas": ["CUN", "MEX"],
        "label": "México (Cancún CUN, CDMX MEX)",
        "city_slug": "cancun-mexico",
        "country": "MX",
        "region": "NA",
    },
    "ciudad de mexico": {
        "primary": "MEX",
        "iatas": ["MEX"],
        "label": "Ciudad de México, México (MEX)",
        "city_slug": "mexico-city-mexico",
        "country": "MX",
        "region": "NA",
    },
    "cdmx": {
        "primary": "MEX",
        "iatas": ["MEX"],
        "label": "Ciudad de México, México (MEX)",
        "city_slug": "mexico-city-mexico",
        "country": "MX",
        "region": "NA",
    },
    "cancun": {
        "primary": "CUN",
        "iatas": ["CUN"],
        "label": "Cancún, México (CUN)",
        "city_slug": "cancun-mexico",
        "country": "MX",
        "region": "NA",
    },

    # --- CENTROAMÉRICA Y CARIBE ---
    "panama": {
        "primary": "PTY",
        "iatas": ["PTY"],
        "label": "Ciudad de Panamá, Panamá (PTY)",
        "city_slug": "panama-city-panama",
        "country": "PA",
        "region": "CA",
    },
    "ciudad de panama": {
        "primary": "PTY",
        "iatas": ["PTY"],
        "label": "Ciudad de Panamá, Panamá (PTY)",
        "city_slug": "panama-city-panama",
        "country": "PA",
        "region": "CA",
    },
    "republica dominicana": {
        "primary": "PUJ",
        "iatas": ["PUJ", "SDQ"],
        "label": "República Dominicana (Punta Cana PUJ, Santo Domingo SDQ)",
        "city_slug": "punta-cana-dominican-republic",
        "country": "DO",
        "region": "CA",
    },
    "punta cana": {
        "primary": "PUJ",
        "iatas": ["PUJ"],
        "label": "Punta Cana, Rep. Dominicana (PUJ)",
        "city_slug": "punta-cana-dominican-republic",
        "country": "DO",
        "region": "CA",
    },
    "santo domingo": {
        "primary": "SDQ",
        "iatas": ["SDQ"],
        "label": "Santo Domingo, Rep. Dominicana (SDQ)",
        "city_slug": "santo-domingo-dominican-republic",
        "country": "DO",
        "region": "CA",
    },
    "costa rica": {
        "primary": "SJO",
        "iatas": ["SJO"],
        "label": "San José, Costa Rica (SJO)",
        "city_slug": "san-jose-costa-rica",
        "country": "CR",
        "region": "CA",
    },
    "san jose": {
        "primary": "SJO",
        "iatas": ["SJO"],
        "label": "San José, Costa Rica (SJO)",
        "city_slug": "san-jose-costa-rica",
        "country": "CR",
        "region": "CA",
    },
    "aruba": {
        "primary": "AUA",
        "iatas": ["AUA"],
        "label": "Oranjestad, Aruba (AUA)",
        "city_slug": "oranjestad-aruba",
        "country": "AW",
        "region": "CA",
    },
    "curazao": {
        "primary": "CUR",
        "iatas": ["CUR"],
        "label": "Willemstad, Curazao (CUR)",
        "city_slug": "willemstad-curacao",
        "country": "CW",
        "region": "CA",
    },

    # --- SURAMÉRICA ---
    "peru": {
        "primary": "LIM",
        "iatas": ["LIM", "CUZ"],
        "label": "Perú (Lima LIM, Cusco CUZ)",
        "city_slug": "lima-peru",
        "country": "PE",
        "region": "SA",
    },
    "lima": {
        "primary": "LIM",
        "iatas": ["LIM"],
        "label": "Lima, Perú (LIM)",
        "city_slug": "lima-peru",
        "country": "PE",
        "region": "SA",
    },
    "cusco": {
        "primary": "CUZ",
        "iatas": ["CUZ"],
        "label": "Cusco, Perú (CUZ)",
        "city_slug": "cusco-peru",
        "country": "PE",
        "region": "SA",
    },
    "chile": {
        "primary": "SCL",
        "iatas": ["SCL"],
        "label": "Santiago de Chile, Chile (SCL)",
        "city_slug": "santiago-chile",
        "country": "CL",
        "region": "SA",
    },
    "santiago": {
        "primary": "SCL",
        "iatas": ["SCL"],
        "label": "Santiago de Chile, Chile (SCL)",
        "city_slug": "santiago-chile",
        "country": "CL",
        "region": "SA",
    },
    "argentina": {
        "primary": "EZE",
        "iatas": ["EZE", "AEP"],
        "label": "Argentina (Buenos Aires EZE)",
        "city_slug": "buenos-aires-argentina",
        "country": "AR",
        "region": "SA",
    },
    "buenos aires": {
        "primary": "EZE",
        "iatas": ["EZE", "AEP"],
        "label": "Buenos Aires, Argentina (EZE)",
        "city_slug": "buenos-aires-argentina",
        "country": "AR",
        "region": "SA",
    },
    "brasil": {
        "primary": "GRU",
        "iatas": ["GRU", "GIG"],
        "label": "Brasil (São Paulo GRU, Río GIG)",
        "city_slug": "sao-paulo-brazil",
        "country": "BR",
        "region": "SA",
    },
    "sao paulo": {
        "primary": "GRU",
        "iatas": ["GRU"],
        "label": "São Paulo, Brasil (GRU)",
        "city_slug": "sao-paulo-brazil",
        "country": "BR",
        "region": "SA",
    },
    "rio de janeiro": {
        "primary": "GIG",
        "iatas": ["GIG"],
        "label": "Río de Janeiro, Brasil (GIG)",
        "city_slug": "rio-de-janeiro-brazil",
        "country": "BR",
        "region": "SA",
    },
    "ecuador": {
        "primary": "UIO",
        "iatas": ["UIO", "GYE"],
        "label": "Ecuador (Quito UIO, Guayaquil GYE)",
        "city_slug": "quito-ecuador",
        "country": "EC",
        "region": "SA",
    },
    "quito": {
        "primary": "UIO",
        "iatas": ["UIO"],
        "label": "Quito, Ecuador (UIO)",
        "city_slug": "quito-ecuador",
        "country": "EC",
        "region": "SA",
    },
    "guayaquil": {
        "primary": "GYE",
        "iatas": ["GYE"],
        "label": "Guayaquil, Ecuador (GYE)",
        "city_slug": "guayaquil-ecuador",
        "country": "EC",
        "region": "SA",
    },
}



class LocationNotFound(ValueError):
    """La ciudad/país/código no se pudo resolver a un aeropuerto conocido."""


# Alias frecuentes (normalizados, sin tildes) -> clave de LOCATIONS_DB

# --- Aeropuertos comerciales de Colombia (fuente: Aerocivil / Wikipedia "Anexo:Aeropuertos de Colombia") ---
_CO_EXTRA = [
    # (clave, ciudad mostrada, IATA, alias)
    ("cucuta", "Cúcuta", "CUC", []),
    ("armenia", "Armenia", "AXM", ["la tebaida"]),
    ("manizales", "Manizales", "MZL", []),
    ("monteria", "Montería", "MTR", ["cerete"]),
    ("leticia", "Leticia", "LET", []),
    ("pasto", "Pasto", "PSO", ["chachagui", "san juan de pasto"]),
    ("neiva", "Neiva", "NVA", []),
    ("villavicencio", "Villavicencio", "VVC", ["villavo"]),
    ("valledupar", "Valledupar", "VUP", []),
    ("riohacha", "Riohacha", "RCH", []),
    ("ibague", "Ibagué", "IBE", []),
    ("popayan", "Popayán", "PPN", []),
    ("quibdo", "Quibdó", "UIB", []),
    ("yopal", "Yopal", "EYP", []),
    ("apartado", "Apartadó", "APO", ["carepa", "uraba"]),
    ("sincelejo", "Sincelejo", "CZU", ["corozal"]),
    ("barrancabermeja", "Barrancabermeja", "EJA", []),
    ("providencia", "Providencia", "PVA", ["isla de providencia"]),
    ("tumaco", "Tumaco", "TCO", []),
    ("florencia", "Florencia", "FLA", []),
    ("arauca", "Arauca", "AUC", []),
    ("puerto carreno", "Puerto Carreño", "PCR", []),
    ("mitu", "Mitú", "MVP", []),
    ("inirida", "Inírida", "PDA", ["puerto inirida"]),
    ("san jose del guaviare", "San José del Guaviare", "SJE", []),
    ("bahia solano", "Bahía Solano", "BSC", []),
    ("nuqui", "Nuquí", "NQU", []),
    ("guapi", "Guapi", "GPI", []),
    ("ipiales", "Ipiales", "IPI", []),
    ("caucasia", "Caucasia", "CAQ", []),
    ("la macarena", "La Macarena", "LMC", []),
    ("mocoa", "Mocoa", "VGZ", ["villagarzon"]),
    ("pitalito", "Pitalito", "PTX", []),
    ("puerto asis", "Puerto Asís", "PUU", []),
    ("puerto leguizamo", "Puerto Leguízamo", "LQM", []),
    ("saravena", "Saravena", "RVE", []),
    ("capurgana", "Capurganá", "CPB", []),
    ("medellin olaya herrera", "Medellín Olaya Herrera", "EOH", ["olaya herrera", "enrique olaya herrera"]),
]
_CO_EXTRA_ALIASES = {}
for _k, _city, _code, _alias in _CO_EXTRA:
    if _k not in LOCATIONS_DB:
        LOCATIONS_DB[_k] = {
            "primary": _code, "iatas": [_code], "label": f"{_city}, Colombia ({_code})",
            "city_slug": _k.replace(" ", "-") + "-colombia", "country": "CO", "region": "SA",
        }
    for _a in _alias:
        _CO_EXTRA_ALIASES[_a] = _k

# Ciudades y puertas insulares de España. Madrid (MAD) y Barcelona (BCN) ya están arriba.
_ES_EXTRA = [
    ("valencia", "Valencia", "VLC", []),
    ("sevilla", "Sevilla", "SVQ", ["seville"]),
    ("malaga", "Málaga", "AGP", []),
    ("alicante", "Alicante", "ALC", ["alicante elche"]),
    ("bilbao", "Bilbao", "BIO", []),
    ("palma", "Palma de Mallorca", "PMI", ["palma de mallorca", "mallorca"]),
    ("ibiza", "Ibiza", "IBZ", ["eivissa"]),
    ("menorca", "Menorca", "MAH", ["mahon"]),
    ("tenerife", "Tenerife", "TFS", ["tenerife sur", "reina sofia"]),
    ("tenerife norte", "Tenerife Norte", "TFN", ["los rodeos"]),
    ("gran canaria", "Gran Canaria", "LPA", ["las palmas", "las palmas de gran canaria"]),
    ("lanzarote", "Lanzarote", "ACE", ["arrecife"]),
    ("fuerteventura", "Fuerteventura", "FUE", ["puerto del rosario"]),
]
_ES_EXTRA_ALIASES = {}
for _k, _city, _code, _alias in _ES_EXTRA:
    if _k not in LOCATIONS_DB:
        LOCATIONS_DB[_k] = {
            "primary": _code, "iatas": [_code], "label": f"{_city}, España ({_code})",
            "city_slug": _k.replace(" ", "-") + "-spain", "country": "ES", "region": "EU",
        }
    for _a in _alias:
        _ES_EXTRA_ALIASES[_a] = _k

ALIASES = {
    "rionegro": "medellin", "jose maria cordova": "medellin", "aeropuerto jose maria cordova": "medellin",
    "bogota dc": "bogota", "bogota d.c.": "bogota", "eldorado": "bogota", "el dorado": "bogota",
    "cartagena de indias": "cartagena", "palmira": "cali", "santiago de cali": "cali",
    "santiago de chile": "santiago", "nyc": "nueva york", "ciudad de panama": "ciudad de panama",
    "san andres isla": "san andres", "cancun": "cancun", "lisbon": "lisboa", "london": "londres",
    "cucuta norte de santander": "cucuta", "san jose de cucuta": "cucuta",
}
ALIASES.update(_CO_EXTRA_ALIASES)
ALIASES.update(_ES_EXTRA_ALIASES)

import re as _re


def _is_country(info: dict) -> bool:
    return "," not in info["label"].split("(")[0]


# Índice por código IATA: preferir entradas de ciudad sobre las de país
LOCATIONS_DB.setdefault("paises bajos", LOCATIONS_DB["holanda"])

CODE_INDEX = {}
for _key, _info in LOCATIONS_DB.items():
    if not _is_country(_info):
        CODE_INDEX.setdefault(_info["primary"], _info)
for _key, _info in LOCATIONS_DB.items():
    CODE_INDEX.setdefault(_info["primary"], _info)
IATA_INDEX = CODE_INDEX


def _lookup(key: str):
    key = key.strip(" .-")
    if key in LOCATIONS_DB:
        return LOCATIONS_DB[key]
    if key in ALIASES:
        return LOCATIONS_DB[ALIASES[key]]
    return None


def _generic_code(code: str) -> dict:
    return {"primary": code, "iatas": [code], "label": code, "city_slug": code.lower(),
            "country": "INT", "region": "INT"}


def resolve_location(user_input: str) -> dict:
    """
    Convierte ciudad, país o código IATA en la info del aeropuerto.
    Orden: código entre paréntesis "(MDE)"/"(Mde)" > nombre exacto/alias >
    primer tramo antes de la coma > código de 3 letras > ciudad contenida (palabra completa).
    Nunca cae silenciosamente a la capital del país: si no se reconoce, lanza LocationNotFound.
    """
    raw = (user_input or "").strip()
    if not raw:
        raise LocationNotFound("Ubicación vacía.")

    # 1. Código IATA explícito entre paréntesis al final, sin importar mayúsculas
    m = _re.search(r"\(\s*([A-Za-z]{3})\s*\)\s*$", raw)
    if m:
        code = m.group(1).upper()
        return CODE_INDEX.get(code) or _generic_code(code)

    norm = _normalize(raw)
    base = _re.sub(r"\([^)]*\)", " ", norm)
    base = _re.sub(r"\s+", " ", base).strip(" ,")

    # 2. Coincidencia exacta o alias
    hit = _lookup(base)
    if hit:
        return hit

    # 3. "Medellín, Colombia" -> primer tramo
    first = base.split(",")[0].strip()
    hit = _lookup(first)
    if hit:
        return hit

    # 4. Código IATA de 3 letras escrito directamente
    if len(first) == 3 and first.isalpha():
        code = first.upper()
        return CODE_INDEX.get(code) or _generic_code(code)

    # 5. Ciudad contenida como palabra completa (solo ciudades, nunca países); la más larga gana
    city_keys = [k for k, v in LOCATIONS_DB.items() if not _is_country(v)] + list(ALIASES)
    for key in sorted(city_keys, key=len, reverse=True):
        if _re.search(r"\b" + _re.escape(key) + r"\b", first):
            return _lookup(key)

    raise LocationNotFound(
        f"No reconocemos '{raw}'. Escribe una ciudad o un código de aeropuerto, por ejemplo Medellín o MDE."
    )


def display_city(label: str) -> str:
    """'Medellín, Colombia (MDE)' -> 'Medellín'; 'Colombia (Bogotá BOG, ...)' -> 'Colombia'."""
    return (label or "").split("(")[0].split(",")[0].strip()


def list_popular_suggestions() -> list[str]:
    """Devuelve sugerencias populares para autocompletar en la interfaz."""
    return [
        "Bogotá",
        "Medellín",
        "Cali",
        "Cartagena",
        "Colombia",
        "Madrid",
        "España",
        "Barcelona",
        "Valencia",
        "Sevilla",
        "Málaga",
        "Alicante",
        "Bilbao",
        "Palma de Mallorca",
        "Ibiza",
        "Menorca",
        "Tenerife",
        "Gran Canaria",
        "Lanzarote",
        "Fuerteventura",
        "Miami",
        "Estados Unidos",
        "Orlando",
        "Nueva York",
        "Cancún",
        "México",
        "Ciudad de México",
        "Ciudad de Panamá",
        "Punta Cana",
        "Lima",
        "Perú",
        "Santiago",
        "Buenos Aires",
        "São Paulo",
        "París",
        "Roma",
    ]


def list_all_location_labels() -> list[str]:
    """Todas las ubicaciones conocidas (etiqueta con IATA), para filtrar al escribir."""
    return sorted({v["label"] for v in LOCATIONS_DB.values()}, key=lambda x: _normalize(x))
