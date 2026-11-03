# Mis Vuelos (`vuelos_tracker`) — Guía para PythonAnywhere

Sistema web autónomo en Python + Flask + SQLite para monitorear precios reales de vuelos en **Google Flights, Rappi Travel, LATAM, JetSMART, Wingo, Avianca, Skyscanner, Kayak y Kiwi.com**, diseñado para ejecutarse dentro de los límites de una cuenta de **PythonAnywhere** (< 1 MB en disco).

---

## 1. Credenciales y seguridad (obligatorio)

La app **no arranca** si en `.env` faltan estas variables o tienen valores de ejemplo o conocidos
(el error aparece en el *error log* de la pestaña **Web**):

| Variable | Requisito |
|---|---|
| `VUELOS_SECRET_KEY` | Aleatoria, mínimo 32 caracteres |
| `VUELOS_INVITE_CODE` | Mínimo 8 caracteres, que no sea el de ejemplo |
| `VUELOS_ADMIN_PASS` | Mínimo 10 caracteres, que no sea la de ejemplo |

Genera valores seguros en la consola Bash:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # VUELOS_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(12))"   # VUELOS_INVITE_CODE
```

`VUELOS_ADMIN_PASS` solo se usa para crear el admin la primera vez; si el admin ya existe, su contraseña
actual no cambia.

Otras variables:

- `VUELOS_INVITE_MAX_USES` (por defecto 5): cuántas cuentas se pueden crear con el mismo código. Al cambiar el código, el contador empieza de cero. `0` = sin límite.
- `VUELOS_MAX_ACTIVE_ROUTES` (por defecto 10): rutas activas por usuario.
- `VUELOS_ALERT_MIN_DROP_PCT` (por defecto 2): bajada mínima en % para enviar un correo nuevo.
- `VUELOS_HTTPS`: activa cookie `Secure` y HSTS. Si no se define, se activa sola en PythonAnywhere (que siempre sirve https) o si `VUELOS_BASE_URL` empieza por `https://`. Pon `false` solo para desarrollo local por http.
- `VUELOS_DEMO_MODE` (por defecto `false`): precios simulados y "simular caída" solo para el admin, sin enviar correos. **No lo actives en producción.**

Sin precios reales (Google Flights no responde), la app no guarda precios inventados ni envía correos: muestra
"No pudimos consultar precios ahora. Lo intentaremos de nuevo." y lo registra en el log.

Las contraseñas nuevas deben tener al menos 10 caracteres, no solo números y no ser comunes.

---

## 2. Pasos para subirlo a PythonAnywhere (en 3 minutos)

### Paso 1: Subir y descomprimir el proyecto
1. Entra a tu cuenta en [PythonAnywhere](https://www.pythonanywhere.com/).
2. Ve a la pestaña **Files** y sube el archivo `vuelos_tracker_pythonanywhere.zip`.
3. Abre una consola **Bash** desde la pestaña **Consoles** y ejecuta:
   ```bash
   unzip vuelos_tracker_pythonanywhere.zip -d ~/vuelos_tracker
   cd ~/vuelos_tracker
   cp .env.example .env
   pip3 install --user -r requirements.txt
   ```

### Paso 2: Configurar la aplicación Web
1. Ve a la pestaña **Web** y haz clic en **Add a new web app**.
2. Elige **Manual configuration** y selecciona **Python 3.10 / 3.11 / 3.12**.
3. En la sección **Code**:
   - **Source code**: `/home/TU_USUARIO/vuelos_tracker`
   - Haz clic en el enlace de **WSGI configuration file**, borra todo su contenido y deja únicamente esto:
     ```python
     import sys
     path = "/home/TU_USUARIO/vuelos_tracker"
     if path not in sys.path:
         sys.path.insert(0, path)

     from wsgi import application
     ```
     *(Reemplaza `TU_USUARIO` por tu nombre de usuario de PythonAnywhere).*
4. Haz clic en el botón **Reload** arriba en la pestaña **Web**.

### Paso 3: Activar el rastreo autónomo (Pestaña Tasks)
1. Ve a la pestaña **Tasks** en PythonAnywhere.
2. En **Scheduled tasks**, agrega el comando:
   ```bash
   python3 /home/TU_USUARIO/vuelos_tracker/scheduler_task.py
   ```

---

## 3. Cómo activar el envío de correos reales (Archivo `.env`)

1. Abre el archivo `/home/TU_USUARIO/vuelos_tracker/.env`.
2. Configura tus variables:
   ```env
   VUELOS_SMTP_ENABLED=true
   VUELOS_SMTP_USER=tu_correo@gmail.com
   VUELOS_SMTP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
   *(En `VUELOS_SMTP_PASSWORD` coloca tu Contraseña de Aplicación de 16 letras de Google).*
3. Recarga la aplicación desde la pestaña **Web -> Reload**.
