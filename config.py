import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")


def _load_env_file(filepath: str) -> None:
    """
    Carga automaticamente las variables del archivo .env sin requerir librerias externas.
    """
    if not os.path.isfile(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ[key] = val
    except Exception:
        pass


_load_env_file(ENV_FILE_PATH)

# Clave secreta para sesiones y tokens CSRF
SECRET_KEY = os.environ.get("VUELOS_SECRET_KEY", "").strip()

# Base de datos SQLite local (ideal para PythonAnywhere)
DB_PATH = os.environ.get("VUELOS_DB_PATH", os.path.join(BASE_DIR, "vuelos_tracker.db"))

# Seguridad de Acceso: Multiusuario con Codigo Maestro de Invitacion
INVITATION_CODE = os.environ.get("VUELOS_INVITE_CODE", "").strip()
# Cuántas cuentas se pueden crear con el mismo código (0 = sin límite)
INVITE_MAX_USES = int(os.environ.get("VUELOS_INVITE_MAX_USES", "5") or 5)

# Usuario administrador creado por defecto al iniciar por primera vez
DEFAULT_ADMIN_USER = os.environ.get("VUELOS_ADMIN_USER", "admin")
DEFAULT_ADMIN_EMAIL = os.environ.get("VUELOS_ADMIN_EMAIL", "alertas@misvuelos.co")
DEFAULT_ADMIN_PASSWORD = os.environ.get("VUELOS_ADMIN_PASS", "").strip()

# Configuracion de Correo SMTP (para enviar alertas reales por Gmail)
SMTP_ENABLED = os.environ.get("VUELOS_SMTP_ENABLED", "true").lower() in ("true", "1", "yes", "si")
SMTP_HOST = os.environ.get("VUELOS_SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.environ.get("VUELOS_SMTP_PORT", "587"))
SMTP_USE_TLS = os.environ.get("VUELOS_SMTP_USE_TLS", "true").lower() in ("true", "1", "yes", "si")
SMTP_USER = os.environ.get("VUELOS_SMTP_USER", "").strip()
# Google entrega las Contrasenas de Aplicacion en bloques de 4 letras con espacios; los limpiamos automaticamente
SMTP_PASSWORD = os.environ.get("VUELOS_SMTP_PASSWORD", "").replace(" ", "").strip()
SMTP_FROM_NAME = os.environ.get("VUELOS_SMTP_FROM_NAME", "Mis Vuelos Alertas").strip()

# URL base de la aplicacion
APP_BASE_URL = os.environ.get("VUELOS_BASE_URL", "http://localhost:5000")

# Limites de operacion y autonomia en PythonAnywhere
DEFAULT_CURRENCY = "COP"
MIN_TRACKING_DAYS = 1
MAX_TRACKING_DAYS = 90
DEFAULT_TRACKING_DAYS = 15

# Intervalo del hilo autonomo secundario (en segundos)
BACKGROUND_CHECK_INTERVAL_SECONDS = int(os.environ.get("VUELOS_CHECK_INTERVAL", "1800"))  # 30 min
ENABLE_BACKGROUND_THREAD = os.environ.get("VUELOS_BG_THREAD", "true").lower() in ("true", "1", "yes", "si")


def _flag(name: str, default: str = "false") -> bool:
    raw = (os.environ.get(name) or "").strip() or default
    return raw.lower() in ("true", "1", "yes", "si")


# Modo demo: precios simulados y botón "Simular caída" (solo admin). Nunca en producción.
DEMO_MODE = _flag("VUELOS_DEMO_MODE", "false")

# Límite de rutas activas por usuario
MAX_ACTIVE_ROUTES = int(os.environ.get("VUELOS_MAX_ACTIVE_ROUTES", "10") or 10)

# Bajada mínima (en %) frente al mejor precio anterior para enviar un nuevo correo
ALERT_MIN_DROP_PCT = float(os.environ.get("VUELOS_ALERT_MIN_DROP_PCT", "2") or 2)

# HTTPS: cookie Secure + HSTS. Por defecto activo en PythonAnywhere (siempre https)
# o si la URL base es https; inactivo en desarrollo local por http.
_ON_PYTHONANYWHERE = bool(os.environ.get("PYTHONANYWHERE_DOMAIN") or os.environ.get("PYTHONANYWHERE_SITE"))
HTTPS_ENABLED = _flag(
    "VUELOS_HTTPS",
    "true" if (_ON_PYTHONANYWHERE or APP_BASE_URL.lower().startswith("https://")) else "false",
)

# Valores de ejemplo o publicados que nunca deben usarse en producción
KNOWN_INSECURE_VALUES = {
    "", "vuelos-tracker-ultra-secret-key-2026-pa", "VUELOS-VIP-2026", "Vuelos2026!",
    "cambia_esto", "CAMBIA_ESTO", "changeme", "secret", "admin", "password",
    "genera_una_clave_larga_y_aleatoria", "pon_aqui_tu_codigo", "pon_aqui_tu_clave",
}


def validate_required_settings() -> None:
    """Se niega a arrancar si faltan secretos o tienen valores de ejemplo/conocidos."""
    problems = []
    if SECRET_KEY in KNOWN_INSECURE_VALUES or len(SECRET_KEY) < 32:
        problems.append("VUELOS_SECRET_KEY (falta, es de ejemplo o tiene menos de 32 caracteres)")
    if INVITATION_CODE in KNOWN_INSECURE_VALUES or len(INVITATION_CODE) < 8:
        problems.append("VUELOS_INVITE_CODE (falta, es de ejemplo o tiene menos de 8 caracteres)")
    if DEFAULT_ADMIN_PASSWORD in KNOWN_INSECURE_VALUES or len(DEFAULT_ADMIN_PASSWORD) < 10:
        problems.append("VUELOS_ADMIN_PASS (falta, es de ejemplo o tiene menos de 10 caracteres)")
    if problems:
        msg = (
            "Mis Vuelos no puede arrancar: revisa el archivo .env. Variables con problema: "
            + "; ".join(problems)
            + ". Genera una clave con: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
        import logging
        logging.getLogger("vuelos").error(msg)
        raise RuntimeError(msg)
