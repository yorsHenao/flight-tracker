# Mis Vuelos

Rastreador de precios de vuelos con alertas por correo. Vigila una ruta y una fecha durante los días que elijas y te avisa cuando el precio real baja.

## Funciones

- Búsqueda con vista previa: ves los vuelos y precios antes de guardar nada; con "Activar seguimiento" la ruta queda vigilada.
- Filtro de vuelos directos o con escalas.
- Ciudades de Colombia (más de 40 aeropuertos) e internacionales, con autocompletado y alias sin tildes.
- Días de vigilancia configurables; la ruta se finaliza sola al vencer o cuando pasa la fecha del viaje.
- Mis rutas: pausar, reanudar, terminar y eliminar.
- Avisos enviados: historial de alertas por ruta (pausar conserva el historial).
- Correo cuando el precio baja al menos un porcentaje mínimo o cruza el precio objetivo.
- Modo claro y oscuro.
- Multiusuario con registro por código de invitación (con máximo de usos) y límite de rutas activas por usuario.

## Stack

- Python 3.10+ y Flask 3
- SQLite (archivo local, se crea solo)
- Jinja2, HTML, CSS y JavaScript sin frameworks
- requests y BeautifulSoup para consultar Google Flights
- SMTP (por ejemplo Gmail con contraseña de aplicación) para los avisos

## Estructura

```
tracker-vuelos/
  app.py                    Rutas web de Flask
  config.py                 Configuración desde .env y validación al arrancar
  database.py               Esquema SQLite, migraciones automáticas y consultas
  security.py               CSRF, CSP, rate limit y validaciones
  notifier.py               Envío de correos de aviso
  scheduler_task.py         Revisión periódica de las rutas activas
  wsgi.py                   Punto de entrada para PythonAnywhere
  providers/
    airport_resolver.py     Ciudades y códigos IATA
    flight_engine.py        Consulta de precios en Google Flights
  templates/                Plantillas HTML
  static/                   CSS, JavaScript y logo
  .env.example              Plantilla de variables de entorno
  README_PYTHONANYWHERE.md  Guía de despliegue
```

## Instalación local

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # en Windows: copy .env.example .env
```

Genera una clave secreta y pégala en `VUELOS_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Define también `VUELOS_INVITE_CODE` y `VUELOS_ADMIN_PASS` con valores propios. La app no arranca si faltan o si son valores de ejemplo.

```bash
python app.py
```

Abre http://localhost:5000. La base de datos `vuelos_tracker.db` y el usuario admin se crean solos en el primer arranque.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| VUELOS_SECRET_KEY | Sí | Clave de sesión, mínimo 32 caracteres aleatorios |
| VUELOS_INVITE_CODE | Sí | Código para registrarse, mínimo 8 caracteres |
| VUELOS_ADMIN_PASS | Sí | Contraseña del admin creado en el primer arranque, mínimo 10 caracteres |
| VUELOS_ADMIN_USER | No | Usuario del admin (por defecto admin) |
| VUELOS_ADMIN_EMAIL | No | Correo del admin |
| VUELOS_INVITE_MAX_USES | No | Máximo de registros por código de invitación (5) |
| VUELOS_MAX_ACTIVE_ROUTES | No | Máximo de rutas activas por usuario (10) |
| VUELOS_ALERT_MIN_DROP_PCT | No | Bajada mínima en % para enviar aviso (2) |
| VUELOS_HTTPS | No | Cookie Secure y HSTS; vacío = automático en PythonAnywhere |
| VUELOS_DEMO_MODE | No | Solo para pruebas: precios estimados y simulación (false) |
| VUELOS_BASE_URL | No | URL pública usada en los enlaces de los correos |
| VUELOS_DB_PATH | No | Ruta del archivo SQLite |
| VUELOS_SMTP_ENABLED | No | Activa el envío de correos (true) |
| VUELOS_SMTP_HOST | No | Servidor SMTP (smtp.gmail.com) |
| VUELOS_SMTP_PORT | No | Puerto SMTP (587) |
| VUELOS_SMTP_USE_TLS | No | STARTTLS (true) |
| VUELOS_SMTP_USER | Para correos | Usuario SMTP |
| VUELOS_SMTP_PASSWORD | Para correos | Contraseña de aplicación SMTP |
| VUELOS_SMTP_FROM_NAME | No | Nombre del remitente |
| VUELOS_CHECK_INTERVAL | No | Segundos entre revisiones en segundo plano (1800) |
| VUELOS_BG_THREAD | No | Hilo de revisión dentro de la app (true) |

Nunca subas el archivo `.env` al repositorio; ya está en `.gitignore`.

## Despliegue en PythonAnywhere

Resumen: sube el código, crea el `.env` con tus valores, configura la Web app apuntando a `wsgi.py`, instala las dependencias y programa la revisión de precios (pestaña Tasks o, en cuentas gratuitas, cron-job.org llamando a `/tareas/revisar`). HTTPS se activa solo. La guía paso a paso está en [README_PYTHONANYWHERE.md](README_PYTHONANYWHERE.md).

## Tarea programada

`scheduler_task.py` revisa todas las rutas activas, guarda los precios reales, envía los avisos que correspondan y finaliza las rutas vencidas. Se ejecuta con:

```bash
python scheduler_task.py
```

También se puede disparar por HTTP en `/tareas/revisar` con la cabecera `X-Cron-Token` (variable `VUELOS_CRON_TOKEN`); sin token válido responde 404. Ambas formas comparten la misma función, usan un candado para no correr dos veces a la vez y tienen un tiempo máximo por llamada.

Una ruta con error no detiene a las demás, y una segunda corrida sin cambios de precio no reenvía correos.

## Seguridad

- Token CSRF en todos los formularios y acciones.
- Content Security Policy sin scripts en línea (`script-src 'self'`).
- Límite de intentos en login y registro.
- Contraseñas nuevas de mínimo 10 caracteres, sin claves comunes ni solo números.
- Validación en el servidor de ciudades, fechas y acciones; cada usuario solo ve y modifica sus rutas.
- Cookies HttpOnly y SameSite; Secure y HSTS cuando hay HTTPS.
- La app se niega a arrancar con secretos faltantes o de ejemplo.

## Datos de precios

Los precios se consultan en Google Flights en el momento. Si no hay datos o la consulta falla, no se guarda ni se envía ningún precio: la app muestra "No pudimos consultar precios ahora. Lo intentaremos de nuevo." y lo reintenta en la siguiente revisión. No hay precios inventados fuera del modo demo. Los precios son orientativos; confirma siempre en el sitio de la aerolínea o agencia antes de comprar.

## Licencia

Pendiente de definir. Hasta entonces, todos los derechos reservados.
