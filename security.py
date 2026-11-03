import hmac
import re
import secrets
import time
from datetime import datetime
from functools import wraps
from flask import request, session, redirect, url_for, flash, jsonify

import config

# Expresiones regulares de lista blanca estricta (Backend Whitelist)
# Solo permite letras (incluyendo tildes y ñ), espacios, comas, guiones y paréntesis para códigos IATA
LOCATION_REGEX = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜãõâêôçàÃÕÂÊÔÇÀ\s,\.\-\(\)]{2,60}$")

# Usuario: alfanumérico, guion, punto o guion bajo (3 a 32 caracteres)
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.\-]{3,32}$")

# Correo electrónico estricto
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,12}$")

# Fecha exacta YYYY-MM-DD y Mes YYYY-MM
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_REGEX = re.compile(r"^\d{4}-\d{2}$")

# Token de parada seguro
TOKEN_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{16,64}$")

# Patrones maliciosos prohibidos explícitamente (SQLi, XSS, SSTI, Command Injection, Path Traversal)
FORBIDDEN_CHARS_REGEX = re.compile(r"[<>'\"`;$\\{}\[\]|^~]")
INJECTION_KEYWORDS_REGEX = re.compile(
    r"(--|/\*|\*/|union\s+select|drop\s+table|insert\s+into|delete\s+from|"
    r"update\s+\w+\s+set|script\b|javascript:|onerror\s*=|onload\s*=|eval\s*\(|"
    r"alert\s*\(|document\.cookie|window\.location|or\s+1\s*=\s*1|and\s+1\s*=\s*1)",
    re.IGNORECASE,
)

VALID_STOP_FILTERS = ("all", "direct", "layover")


class ValidationError(ValueError):
    """Excepción lanzada cuando un campo no supera el blindaje de seguridad."""
    pass


def wants_json_response() -> bool:
    """
    Determina si la solicitud espera explícitamente JSON (únicamente llamadas AJAX con
    X-Requested-With: XMLHttpRequest o Content-Type: application/json sin text/html en Accept).
    Para cualquier envío de formulario desde el navegador, devuelve SIEMPRE False.
    """
    accept = request.headers.get("Accept", "")
    if "text/html" in accept and request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return False
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if request.is_json:
        return True
    return False


def check_no_injection(raw_value: str, field_name: str = "Campo") -> str:
    """
    Verifica en servidor que el valor no contenga caracteres prohibidos ni
    patrones de inyección enviados desde la consola del navegador o API.
    """
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)

    cleaned = raw_value.strip()

    if FORBIDDEN_CHARS_REGEX.search(cleaned):
        raise ValidationError(
            f"{field_name} contiene caracteres no permitidos por seguridad."
        )

    if INJECTION_KEYWORDS_REGEX.search(cleaned):
        raise ValidationError(
            f"{field_name} fue rechazado por contener patrones no válidos."
        )

    return cleaned


def validate_location(value: str, field_name: str = "Ubicación") -> str:
    """Valida ciudad o país de origen/destino con lista blanca estricta."""
    cleaned = check_no_injection(value, field_name)
    if not cleaned:
        raise ValidationError(f"{field_name} es obligatorio.")
    if not LOCATION_REGEX.match(cleaned):
        raise ValidationError(
            f"{field_name} solo puede contener letras, espacios y guiones (2 a 60 caracteres)."
        )
    return cleaned


def validate_email(value: str, field_name: str = "Correo electrónico") -> str:
    """Valida formato estricto de correo electrónico sin caracteres de inyección."""
    cleaned = check_no_injection(value, field_name)
    if not cleaned:
        raise ValidationError(f"{field_name} es obligatorio.")
    if len(cleaned) > 120 or not EMAIL_REGEX.match(cleaned):
        raise ValidationError(f"{field_name} no tiene un formato válido.")
    return cleaned.lower()


def validate_username(value: str) -> str:
    """Valida nombre de usuario con lista blanca alfanumérica."""
    cleaned = check_no_injection(value, "Usuario")
    if not USERNAME_REGEX.match(cleaned):
        raise ValidationError(
            "El usuario debe tener entre 3 y 32 caracteres (letras, números, punto o guion)."
        )
    return cleaned.lower()


def validate_password(value: str) -> str:
    """Valida longitud de contraseña sin permitir caracteres nulos."""
    if not value or not isinstance(value, str):
        raise ValidationError("La contraseña es obligatoria.")
    if len(value) < 6 or len(value) > 128:
        raise ValidationError("La contraseña debe tener entre 6 y 128 caracteres.")
    if "\x00" in value:
        raise ValidationError("Contraseña no válida.")
    return value


COMMON_PASSWORDS = {
    "1234567890", "12345678910", "0123456789", "contraseña", "contrasena", "contrasena123",
    "password", "password1", "password123", "passw0rd", "qwertyuiop", "qwerty1234", "qwerty123456",
    "abcdefghij", "abc1234567", "iloveyou12", "colombia123", "colombia2026", "medellin123",
    "bogota1234", "vuelos2026", "vuelos2026!", "misvuelos1", "aaaaaaaaaa", "1111111111",
    "admin12345", "administrador", "bienvenido1", "123456789a", "a123456789", "1q2w3e4r5t",
}


def validate_new_password(value: str) -> str:
    """Política para contraseñas nuevas: mínimo 10, no solo números, no comunes."""
    value = validate_password(value)
    if len(value) < 10:
        raise ValidationError("La contraseña debe tener al menos 10 caracteres.")
    if value.isdigit():
        raise ValidationError("La contraseña no puede tener solo números. Combina letras y números.")
    if value.lower() in COMMON_PASSWORDS or len(set(value)) <= 2:
        raise ValidationError("Esa contraseña es muy común. Elige una más difícil de adivinar.")
    return value


DATE_DMY_REGEX = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")
MONTH_MY_REGEX = re.compile(r"^\d{2}[-/]\d{4}$")


def validate_date_and_month(travel_date: str, travel_month: str) -> tuple[str, str]:
    """
    Valida la fecha en formato DD-MM-YYYY (ej. 20-01-2026) o YYYY-MM-DD,
    y el mes en formato MM-YYYY o YYYY-MM. Normaliza internamente a YYYY-MM-DD.
    """
    t_date = check_no_injection(travel_date or "", "Fecha de viaje")
    t_month = check_no_injection(travel_month or "", "Mes de viaje")

    if not t_date and not t_month:
        raise ValidationError("Debes ingresar una fecha aproximada o seleccionar un mes.")

    if t_date:
        dt = None
        if DATE_DMY_REGEX.match(t_date):
            norm = t_date.replace("/", "-")
            try:
                dt = datetime.strptime(norm, "%d-%m-%Y")
            except ValueError as exc:
                raise ValidationError("La fecha ingresada no existe en el calendario.") from exc
        elif DATE_REGEX.match(t_date):
            try:
                dt = datetime.strptime(t_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValidationError("La fecha ingresada no existe en el calendario.") from exc
        else:
            raise ValidationError("Formato de fecha inválido. Usa DD-MM-AAAA (ej. 20-01-2026).")

        if dt.date() < datetime.now().date():
            raise ValidationError("La fecha de viaje ya pasó. Elige una fecha desde hoy en adelante.")
        t_date = dt.strftime("%Y-%m-%d")
        # El mes siempre se deriva de la fecha exacta (no se confía en el cliente)
        t_month = dt.strftime("%Y-%m")

    if t_month:
        if MONTH_MY_REGEX.match(t_month):
            m_norm = t_month.replace("/", "-")
            t_month = f"{m_norm[3:7]}-{m_norm[0:2]}"
        if not MONTH_REGEX.match(t_month):
            raise ValidationError("Formato de mes inválido. Usa MM-AAAA o AAAA-MM.")
        try:
            datetime.strptime(t_month + "-01", "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError("El mes ingresado no es válido.") from exc
        if not t_date:
            t_date = f"{t_month}-15"

    return t_date, t_month


def validate_tracking_days(value) -> int:
    """Valida que el límite de días de seguimiento sea un entero entre 1 y 90."""
    cleaned = check_no_injection(str(value or ""), "Días de seguimiento")
    if not cleaned.isdigit():
        raise ValidationError("El límite de días debe ser un número entero positivo.")
    days = int(cleaned)
    if days < config.MIN_TRACKING_DAYS or days > config.MAX_TRACKING_DAYS:
        raise ValidationError(
            f"El límite de seguimiento debe estar entre {config.MIN_TRACKING_DAYS} y {config.MAX_TRACKING_DAYS} días."
        )
    return days


def validate_stop_filter(value: str) -> str:
    """Valida el filtro de escalas ('all', 'direct', 'layover')."""
    cleaned = check_no_injection(value or "all", "Filtro de escalas").lower()
    if cleaned not in VALID_STOP_FILTERS:
        raise ValidationError("Filtro de escalas inválido.")
    return cleaned


def validate_target_price(value) -> float | None:
    """Valida el precio objetivo opcional."""
    if value is None or str(value).strip() == "":
        return None
    cleaned = check_no_injection(str(value), "Precio objetivo")
    cleaned = cleaned.replace(".", "").replace(",", "").strip()
    if not re.match(r"^\d+(\.\d{1,2})?$", cleaned):
        raise ValidationError("El precio objetivo debe ser un número positivo válido.")
    price = float(cleaned)
    if price <= 0 or price > 500_000_000:
        raise ValidationError("El precio objetivo está fuera del rango permitido.")
    return price


def validate_stop_token(token: str) -> str:
    """Valida el token único para detener búsquedas."""
    cleaned = check_no_injection(token or "", "Token")
    if not TOKEN_REGEX.match(cleaned):
        raise ValidationError("Token de seguridad inválido.")
    return cleaned


# --- Protección CSRF ---

def get_csrf_token() -> str:
    """Obtiene o genera el token CSRF criptográfico de la sesión actual."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


def verify_csrf_token() -> bool:
    """Verifica el token CSRF enviado por formulario o cabecera X-CSRF-Token."""
    expected = session.get("_csrf_token")
    if not expected:
        return False
    provided = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
        or ""
    )
    if not isinstance(provided, str) or not provided:
        return False
    return hmac.compare_digest(expected, provided)


def csrf_required(f):
    """
    Decorador que exige validación CSRF en peticiones mutadoras (POST/PUT/DELETE).
    Si la sesión se reinició o el token expiró en el navegador, redirige limpiamente con un
    aviso amigable en vez de mostrar una pantalla de error cruda.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not verify_csrf_token():
                get_csrf_token()
                msg = "Tu sesión de seguridad se actualizó. Por favor intenta la acción nuevamente."
                if wants_json_response():
                    return jsonify({"ok": False, "error": msg}), 403
                flash(msg, "error")
                target = "dashboard" if session.get("user_id") else "login"
                return redirect(url_for(target))
        return f(*args, **kwargs)
    return decorated_function


# --- Control de Sesión (Login) ---

def login_required(f):
    """Decorador que protege vistas y endpoints para que solo usuarios autenticados accedan."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if wants_json_response():
                return jsonify({"ok": False, "error": "No autorizado. Inicia sesión."}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# --- Rate Limiting en Memoria (Anti Fuerza Bruta y Anti Spam de Consola) ---

class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        timestamps = self._buckets.get(key, [])
        valid_timestamps = [t for t in timestamps if now - t < window_seconds]
        if len(valid_timestamps) >= max_requests:
            self._buckets[key] = valid_timestamps
            return False
        valid_timestamps.append(now)
        self._buckets[key] = valid_timestamps
        return True

    def reset(self):
        self._buckets.clear()


rate_limiter = RateLimiter()


def get_client_ip() -> str:
    # X-Real-IP lo fija el proxy de PythonAnywhere; en X-Forwarded-For el último
    # valor es el que agregó el proxy (los primeros los puede inventar el cliente)
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.remote_addr or "127.0.0.1"


# --- Cabeceras HTTP de Seguridad ---

def apply_security_headers(response):
    """Agrega cabeceras de defensa contra XSS, Clickjacking y MIME Sniffing."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "script-src 'self'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    return response
