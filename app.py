import hmac
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import (
    abort,
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

import config
from database import (
    init_db,
    find_duplicate_search,
    count_active_searches,
    invite_uses,
    register_invite_use,
    authenticate_user,
    create_user,
    get_user_by_id,
    create_search,
    get_user_searches,
    get_search_by_id,
    update_search_status,
    stop_search_by_token,
    delete_search,
    get_user_alerts,
    save_search_results,
)
from notifier import format_cop, format_date_dmy, format_month_my, notify_lowest_price
from providers.airport_resolver import resolve_location, list_popular_suggestions, display_city, LocationNotFound, list_all_location_labels
from providers.flight_engine import PORTALS, build_deep_link, search_flights_for_date, generate_monthly_calendar_offers
from scheduler_task import run_check_for_search, run_all_active_searches
from security import (
    ValidationError,
    wants_json_response,
    check_no_injection,
    validate_location,
    validate_email,
    validate_username,
    validate_password,
    validate_new_password,
    validate_date_and_month,
    validate_tracking_days,
    validate_stop_filter,
    validate_target_price,
    validate_stop_token,
    get_csrf_token,
    csrf_required,
    login_required,
    rate_limiter,
    get_client_ip,
    apply_security_headers,
)

config.validate_required_settings()

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.HTTPS_ENABLED,
)

# Inicializar base de datos al cargar la aplicación
init_db()


@app.after_request
def add_security_headers(response):
    response = apply_security_headers(response)
    if config.HTTPS_ENABLED:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.context_processor
def inject_template_globals():
    return {
        "csrf_token": get_csrf_token,
        "format_cop": format_cop,
        "portals_catalog": PORTALS,
        "format_date_dmy": format_date_dmy,
        "format_month_my": format_month_my,
        "build_deep_link": build_deep_link,
    }


@app.template_filter("cop")
def cop_filter(value):
    return format_cop(value)


# Nunca mostrar "None" en plantillas
app.jinja_env.finalize = lambda v: "" if v is None else v


@app.template_filter("ciudad")
def ciudad_filter(value):
    return display_city(value)


@app.template_filter("fecha")
def fecha_filter(value):
    return format_date_dmy(value)


@app.template_filter("mes")
def mes_filter(value):
    return format_month_my(value)


def _wants_json() -> bool:
    return wants_json_response()


# --- Autenticación y Registro Protegido con Código de Invitación ---

@app.route("/login", methods=["GET", "POST"])
@csrf_required
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        client_ip = get_client_ip()
        if not rate_limiter.is_allowed(f"login:{client_ip}", max_requests=10, window_seconds=300):
            msg = "Demasiados intentos de inicio de sesión. Espera unos minutos."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 429
            flash(msg, "error")
            return render_template("login.html", mode="login"), 429

        data = request.get_json(silent=True) if request.is_json else request.form
        try:
            username_or_email = check_no_injection(
                (data or {}).get("username", ""), "Usuario o correo"
            )
            password = validate_password((data or {}).get("password", ""))
        except ValidationError as exc:
            if _wants_json():
                return jsonify({"ok": False, "error": str(exc)}), 400
            flash(str(exc), "error")
            return render_template("login.html", mode="login"), 400

        user = authenticate_user(username_or_email, password)
        if not user:
            msg = "Credenciales incorrectas. Verifica tu usuario y contraseña."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 401
            flash(msg, "error")
            return render_template("login.html", mode="login"), 401

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        get_csrf_token()

        if _wants_json():
            return jsonify({"ok": True, "user": user["username"]})
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="login")


@app.route("/register", methods=["GET", "POST"])
@csrf_required
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        client_ip = get_client_ip()
        if not rate_limiter.is_allowed(f"register:{client_ip}", max_requests=8, window_seconds=300):
            msg = "Demasiados intentos de registro. Intenta más tarde."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 429
            flash(msg, "error")
            return render_template("login.html", mode="register"), 429

        data = request.get_json(silent=True) if request.is_json else request.form
        try:
            username = validate_username((data or {}).get("username", ""))
            email = validate_email((data or {}).get("email", ""), "Correo de cuenta")
            password = validate_new_password((data or {}).get("password", ""))
            invite_code = check_no_injection(
                (data or {}).get("invitation_code", ""), "Código de invitación"
            )
        except ValidationError as exc:
            if _wants_json():
                return jsonify({"ok": False, "error": str(exc)}), 400
            flash(str(exc), "error")
            return render_template("login.html", mode="register"), 400

        if not hmac.compare_digest(invite_code, config.INVITATION_CODE):
            msg = "Código Maestro de Invitación inválido. El registro es privado."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 403
            flash(msg, "error")
            return render_template("login.html", mode="register"), 403

        if config.INVITE_MAX_USES > 0 and invite_uses(invite_code) >= config.INVITE_MAX_USES:
            msg = "Este código de invitación ya alcanzó su límite de usos. Pide uno nuevo al administrador."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 403
            flash(msg, "error")
            return render_template("login.html", mode="register"), 403

        try:
            user = create_user(username=username, email=email, password=password)
            register_invite_use(invite_code)
        except sqlite3.IntegrityError:
            msg = "Ese nombre de usuario o correo ya está registrado."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 409
            flash(msg, "error")
            return render_template("login.html", mode="register"), 409

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        get_csrf_token()

        flash("Cuenta creada con éxito. Bienvenido a tu radar privado de vuelos.", "success")
        if _wants_json():
            return jsonify({"ok": True, "user": user["username"]}), 201
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="register")


@app.route("/logout", methods=["POST"])
@login_required
@csrf_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Panel Principal y Gestión de Múltiples Búsquedas ---

def _alert_airline(msg: str) -> str:
    """Extrae la aerolínea del texto guardado del aviso (formato nuevo y antiguo)."""
    import re
    m = re.search(r"^Vuelo: (.+?)(?: · |$)", msg, re.M) or re.search(r"Modalidad: .*? con (.+)$", msg, re.M)
    return m.group(1).strip() if m else ""


@app.route("/", methods=["GET"])
@login_required
def dashboard():
    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return redirect(url_for("login"))

    searches = get_user_searches(user_id)
    alerts = get_user_alerts(user_id, limit=25)
    for a in alerts:
        a["airline"] = _alert_airline(a.get("friendly_message") or "")

    active_count = sum(1 for s in searches if s["status"] == "activa")
    lowest_global = min(
        (s["best_price"] for s in searches if s.get("best_price") is not None),
        default=None,
    )

    default_dt = datetime.now() + timedelta(days=21)
    default_date = default_dt.strftime("%d-%m-%Y")
    default_date_iso = default_dt.strftime("%Y-%m-%d")
    default_month = default_dt.strftime("%Y-%m")

    preview = None
    if session.get("search_preview"):
        preview = _build_preview(session["search_preview"])
        if preview is None:
            session.pop("search_preview", None)

    return render_template(
        "index.html",
        user=user,
        preview=preview,
        searches=searches,
        alerts=alerts,
        active_count=active_count,
        lowest_global=lowest_global,
        default_date=default_date,
        default_date_iso=default_date_iso,
        default_month=default_month,
        default_tracking_days=config.DEFAULT_TRACKING_DAYS,
        suggestions=list(dict.fromkeys(resolve_location(x)["label"] for x in list_popular_suggestions())),
        all_locations=[x for x in list_all_location_labels() if x not in {resolve_location(y)["label"] for y in list_popular_suggestions()}],
    )


def _validate_search_input(data) -> dict:
    """Valida y resuelve los datos de una ruta en el servidor (nunca confía en el cliente)."""
    origin_clean = validate_location(data.get("origin", ""), "Ciudad o país de salida")
    dest_clean = validate_location(data.get("destination", ""), "Ciudad o país de destino")
    travel_date, travel_month = validate_date_and_month(data.get("travel_date", ""), data.get("travel_month", ""))
    stop_filter = validate_stop_filter(data.get("stop_filter", "all"))
    tracking_days = validate_tracking_days(data.get("tracking_days", config.DEFAULT_TRACKING_DAYS))
    account_user = get_user_by_id(session["user_id"]) or {}
    # Los avisos van siempre al correo de la cuenta (no se acepta un correo ajeno del cliente)
    notify_email = validate_email(
        account_user.get("email", ""),
        "Correo para recibir alertas",
    )
    target_price = validate_target_price(data.get("target_price", ""))
    orig = resolve_location(origin_clean)
    dest = resolve_location(dest_clean)
    if orig["primary"] == dest["primary"]:
        raise ValidationError("El origen y el destino deben ser diferentes.")
    return {"orig": orig, "dest": dest, "travel_date": travel_date, "travel_month": travel_month,
            "stop_filter": stop_filter, "tracking_days": tracking_days, "notify_email": notify_email,
            "target_price": target_price}


def _build_preview(p: dict) -> dict | None:
    """Consulta precios para la vista previa, sin guardar nada ni enviar correos."""
    try:
        date_offers = search_flights_for_date(
            origin_input=p["origin_label"], destination_input=p["destination_label"],
            flight_date=p["travel_date"], stop_filter=p["stop_filter"], jitter_seed="preview",
        )
        monthly = generate_monthly_calendar_offers(
            origin_input=p["origin_label"], destination_input=p["destination_label"],
            travel_month=p["travel_month"], stop_filter=p["stop_filter"], jitter_seed="preview",
        )
    except LocationNotFound:
        return None
    date_offers = sorted(date_offers, key=lambda o: o["price"])
    cheapest_day = min(monthly, key=lambda o: o["price"]) if monthly else None
    return dict(p, offers=date_offers[:6], total=len(date_offers),
                best=date_offers[0] if date_offers else None, cheapest_day=cheapest_day)


@app.route("/searches/preview", methods=["POST"])
@login_required
@csrf_required
def preview_search():
    client_ip = get_client_ip()
    if not rate_limiter.is_allowed(f"preview_search:{client_ip}", max_requests=25, window_seconds=60):
        flash("Demasiadas solicitudes seguidas. Espera unos segundos.", "error")
        return redirect(url_for("dashboard"))
    try:
        v = _validate_search_input(request.form)
    except (ValidationError, LocationNotFound) as exc:
        flash(str(exc), "error")
        return redirect(url_for("dashboard"))
    # Solo parámetros pequeños en la sesión; los precios se consultan al mostrar
    session["search_preview"] = {
        "origin_label": v["orig"]["label"], "origin_iata": v["orig"]["primary"],
        "destination_label": v["dest"]["label"], "destination_iata": v["dest"]["primary"],
        "travel_date": v["travel_date"], "travel_month": v["travel_month"],
        "stop_filter": v["stop_filter"], "tracking_days": v["tracking_days"],
        "target_price": v["target_price"],
    }
    return redirect(url_for("dashboard") + "#vista-previa")


@app.route("/searches/preview/discard", methods=["POST"])
@login_required
@csrf_required
def discard_preview():
    session.pop("search_preview", None)
    return redirect(url_for("dashboard"))



_create_lock = threading.Lock()


@app.route("/api/searches", methods=["POST"])
@app.route("/search/create", methods=["POST"])
@app.route("/searches/create", methods=["POST"])
@login_required
@csrf_required
def add_search():
    client_ip = get_client_ip()
    if not rate_limiter.is_allowed(f"create_search:{client_ip}", max_requests=25, window_seconds=60):
        msg = "Demasiadas solicitudes seguidas. Espera unos segundos."
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 429
        flash(msg, "error")
        return redirect(url_for("dashboard"))

    data = request.get_json(silent=True) if request.is_json else request.form
    try:
        v = _validate_search_input(data or {})
    except (ValidationError, LocationNotFound) as exc:
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("dashboard"))
    session.pop("search_preview", None)
    orig_resolved, dest_resolved = v["orig"], v["dest"]
    with _create_lock:
        duplicate = find_duplicate_search(
            session["user_id"], orig_resolved["primary"], dest_resolved["primary"],
            v["travel_date"], v["stop_filter"],
        )
        if duplicate:
            msg = "Ya estás siguiendo esta ruta para esa fecha."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 409
            flash(msg, "error")
            return redirect(url_for("dashboard"))
        if count_active_searches(session["user_id"]) >= config.MAX_ACTIVE_ROUTES:
            msg = (f"Ya tienes {config.MAX_ACTIVE_ROUTES} rutas activas, el máximo permitido. "
                   "Pausa o elimina una para seguir otra.")
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 409
            flash(msg, "error")
            return redirect(url_for("dashboard"))
        search_row = _create_search_from(v)
    return _after_create(search_row)


def _create_search_from(v: dict) -> dict:
    orig_resolved, dest_resolved = v["orig"], v["dest"]
    travel_date, travel_month = v["travel_date"], v["travel_month"]
    stop_filter, target_price = v["stop_filter"], v["target_price"]
    notify_email, tracking_days = v["notify_email"], v["tracking_days"]

    search_row = create_search(
        user_id=session["user_id"],
        origin_input=orig_resolved["label"],
        origin_iata=orig_resolved["primary"],
        origin_label=orig_resolved["label"],
        destination_input=dest_resolved["label"],
        destination_iata=dest_resolved["primary"],
        destination_label=dest_resolved["label"],
        travel_date=travel_date,
        travel_month=travel_month,
        stop_filter=stop_filter,
        target_price=target_price,
        notify_email=notify_email,
        tracking_days=tracking_days,
    )
    return search_row


def _after_create(search_row: dict):
    check_result = run_check_for_search(search_row["id"], force_alert=True, bypass_cache=True)
    updated_search = get_search_by_id(search_row["id"], user_id=session["user_id"])

    if _wants_json():
        return jsonify(
            {
                "ok": True,
                "search": updated_search,
                "check_result": check_result,
            }
        ), 201

    # Sin banner de búsqueda activa creada (aparece directamente en la lista)
    return redirect(url_for("dashboard"))


@app.route("/api/searches/<int:search_id>/check", methods=["POST"])
@app.route("/search/<int:search_id>/refresh", methods=["POST"])
@app.route("/searches/<int:search_id>/check", methods=["POST"])
@login_required
@csrf_required
def manual_check_search(search_id: int):
    s = get_search_by_id(search_id, user_id=session["user_id"])
    if not s:
        if _wants_json():
            return jsonify({"ok": False, "error": "Búsqueda no encontrada."}), 404
        flash("Búsqueda no encontrada.", "error")
        return redirect(url_for("dashboard"))

    if s["status"] != "activa":
        msg = "Solo se pueden escanear búsquedas en estado Activa."
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 400
        flash(msg, "error")
        return redirect(url_for("dashboard"))

    seed = f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    res = run_check_for_search(search_id, jitter_seed=seed, force_alert=False, bypass_cache=True)
    updated = get_search_by_id(search_id, user_id=session["user_id"])

    if _wants_json():
        return jsonify({"ok": True, "search": updated, "result": res})

    flash(
        f"Tarifas actualizadas para {updated['origin_iata']} a {updated['destination_iata']}: "
        f"Mejor tarifa {format_cop(updated['best_price'])} ({updated['best_stops_label']}).",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/api/searches/<int:search_id>/simulate-drop", methods=["POST"])
@app.route("/searches/<int:search_id>/simulate-drop", methods=["POST"])
@login_required
@csrf_required
def simulate_price_drop(search_id: int):
    """
    Simula una caída real de tarifa durante el rastreo de una ruta activa,
    actualizando la oferta más baja y generando de inmediato la alerta en interfaz y correo.
    Solo existe con VUELOS_DEMO_MODE=true y para el administrador; nunca envía correo real.
    """
    if not config.DEMO_MODE or (session.get("username") or "").lower() != config.DEFAULT_ADMIN_USER.lower():
        abort(404)
    s = get_search_by_id(search_id, user_id=session["user_id"])
    if not s:
        if _wants_json():
            return jsonify({"ok": False, "error": "Búsqueda no encontrada."}), 404
        flash("Búsqueda no encontrada.", "error")
        return redirect(url_for("dashboard"))

    previous_best = float(s["best_price"]) if s.get("best_price") else None
    seed = f"drop-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    date_offers = search_flights_for_date(
        origin_input=s["origin_input"],
        destination_input=s["destination_input"],
        flight_date=s["travel_date"],
        stop_filter=s["stop_filter"],
        jitter_seed=seed,
        attempt_live=False,
    )
    monthly_offers = generate_monthly_calendar_offers(
        origin_input=s["origin_input"],
        destination_input=s["destination_input"],
        travel_month=s["travel_month"],
        stop_filter=s["stop_filter"],
        jitter_seed=seed,
    )

    if date_offers:
        baseline = min(previous_best or date_offers[0]["price"], date_offers[0]["price"])
        discounted = max(65_000.0, float(round((baseline * 0.88) / 1000) * 1000))
        date_offers[0]["price"] = discounted
        date_offers.sort(key=lambda x: x["price"])

    summary = save_search_results(
        search_id=search_id,
        date_offers=date_offers,
        monthly_offers=monthly_offers,
    )
    best_overall = summary.get("best_overall")
    alert_created = None
    if best_overall:
        alert_created = notify_lowest_price(
            search_row=s,
            best_offer=best_overall,
            previous_best=previous_best,
            send_email=False,
            subject_prefix="[PRUEBA] ",
        )

    updated = get_search_by_id(search_id, user_id=session["user_id"])
    if _wants_json():
        return jsonify({"ok": True, "search": updated, "alert": alert_created})

    flash(
        f"Nuevo mínimo detectado en {updated['origin_iata']} a {updated['destination_iata']}: "
        f"{format_cop(updated['best_price'])} en {updated['best_provider']}. Aviso de prueba registrado (sin correo).",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/api/searches/check-all", methods=["POST"])
@app.route("/search/refresh-all", methods=["POST"])
@app.route("/searches/check-all", methods=["POST"])
@login_required
@csrf_required
def manual_check_all():
    user_searches = get_user_searches(session["user_id"])
    count = 0
    for s in user_searches:
        if s["status"] == "activa":
            run_check_for_search(
                s["id"],
                jitter_seed=f"batch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{s['id']}",
                bypass_cache=True,
            )
            count += 1

    if _wants_json():
        return jsonify({"ok": True, "checked": count})

    if count == 0:
        flash("No hay búsquedas activas en este momento para actualizar.", "error")
    else:
        flash(f"Se verificaron {count} búsquedas activas en todos los portales.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/searches/<int:search_id>/status", methods=["POST"])
@app.route("/search/<int:search_id>/action", methods=["POST"])
@app.route("/searches/<int:search_id>/status", methods=["POST"])
@login_required
@csrf_required
def change_search_status(search_id: int):
    data = request.get_json(silent=True) if request.is_json else request.form
    raw_action = check_no_injection((data or {}).get("action", ""), "Acción").lower()

    action_map = {
        "stop": "detenida",
        "detener": "detenida",
        "terminar": "detenida",
        "pause": "pausada",
        "pausar": "pausada",
        "resume": "activa",
        "reanudar": "activa",
    }
    if raw_action not in action_map:
        if _wants_json():
            return jsonify({"ok": False, "error": "Acción no válida."}), 400
        flash("Acción de estado no válida.", "error")
        return redirect(url_for("dashboard"))

    new_status = action_map[raw_action]
    if new_status == "activa":
        current = get_search_by_id(search_id, user_id=session["user_id"])
        if current and current["status"] != "activa" and count_active_searches(session["user_id"]) >= config.MAX_ACTIVE_ROUTES:
            msg = (f"Ya tienes {config.MAX_ACTIVE_ROUTES} rutas activas, el máximo permitido. "
                   "Pausa o elimina una para reanudar esta.")
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 409
            flash(msg, "error")
            return redirect(url_for("dashboard"))
    ok = update_search_status(search_id, session["user_id"], new_status)
    if not ok:
        if _wants_json():
            return jsonify({"ok": False, "error": "Búsqueda no encontrada."}), 404
        flash("No se pudo actualizar la búsqueda.", "error")
        return redirect(url_for("dashboard"))

    status_labels = {
        "detenida": "Seguimiento de la ruta terminado definitivamente.",
        "pausada": "Seguimiento en pausa temporal.",
        "activa": "Seguimiento reanudado y vigilando precios.",
    }
    if _wants_json():
        return jsonify({"ok": True, "status": new_status})

    flash(status_labels[new_status], "success")
    return redirect(url_for("dashboard"))


@app.route("/api/searches/<int:search_id>/delete", methods=["POST"])
@app.route("/search/<int:search_id>/delete", methods=["POST"])
@app.route("/searches/<int:search_id>/delete", methods=["POST"])
@login_required
@csrf_required
def remove_search(search_id: int):
    ok = delete_search(search_id, session["user_id"])
    if _wants_json():
        return jsonify({"ok": ok}), (200 if ok else 404)
    if ok:
        flash("Búsqueda eliminada correctamente.", "success")
    else:
        flash("No se encontró la búsqueda solicitada.", "error")
    return redirect(url_for("dashboard"))


# --- Enlace Directo de 1 Clic para Terminar Búsqueda desde el Correo ---

@app.route("/stop/<stop_token>", methods=["GET", "POST"])
def stop_from_email_link(stop_token: str):
    try:
        clean_token = validate_stop_token(stop_token)
    except ValidationError:
        return render_template("stop_confirm.html", search=None, error="Enlace inválido."), 400

    stopped_search = stop_search_by_token(clean_token)
    if not stopped_search:
        return (
            render_template(
                "stop_confirm.html",
                search=None,
                error="No encontramos una búsqueda asociada a este enlace.",
            ),
            404,
        )

    return render_template("stop_confirm.html", search=stopped_search, error=None)


@app.route("/tareas/revisar", methods=["GET", "POST"])
def cron_check_all():
    """Revisión de precios disparada por cron-job.org. Sin token válido responde 404."""
    if not rate_limiter.is_allowed(f"cron_ip:{get_client_ip()}", max_requests=30, window_seconds=600):
        abort(404)
    expected = config.CRON_TOKEN
    provided = request.headers.get("X-Cron-Token", "") or request.args.get("token", "")
    if not expected or len(expected) < 24 or not provided or not hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        abort(404)
    if not rate_limiter.is_allowed("cron_check_all", max_requests=6, window_seconds=600):
        return jsonify({"ok": False, "error": "rate_limited"}), 429
    result = run_all_active_searches(time_budget=config.CRON_TIME_BUDGET_SECONDS)
    resp = jsonify({k: result.get(k) for k in (
        "ok", "skipped_running", "checked_count", "failed_count",
        "expired_count", "alerts_triggered", "pending_count", "elapsed_seconds",
    )})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="logo.svg"), code=301)


# --- Hilo Ligero Opcional (Autonomía Secundaria en Vivo) ---

_bg_thread_started = False
_bg_lock = threading.Lock()


def _background_monitor_loop():
    while True:
        time.sleep(config.BACKGROUND_CHECK_INTERVAL_SECONDS)
        try:
            run_all_active_searches()
        except Exception:
            pass


def start_background_worker_once():
    global _bg_thread_started
    if not config.ENABLE_BACKGROUND_THREAD:
        return
    with _bg_lock:
        if not _bg_thread_started:
            t = threading.Thread(target=_background_monitor_loop, daemon=True)
            t.start()
            _bg_thread_started = True


start_background_worker_once()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
