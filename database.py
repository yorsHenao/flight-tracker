import secrets
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

import config


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(searches)")}
    for name, ddl in (
        ("last_checked_at", "TEXT"),
        ("last_check_ok", "INTEGER"),
        ("last_check_error", "TEXT"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE searches ADD COLUMN {name} {ddl}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invite_usage (
            code_hash TEXT PRIMARY KEY,
            uses INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )
        """
    )


def init_db(db_path: str | None = None) -> None:
    """Inicializa todas las tablas SQLite y asegura el usuario administrador inicial."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    origin_input TEXT NOT NULL,
                    origin_iata TEXT NOT NULL,
                    origin_label TEXT NOT NULL,
                    destination_input TEXT NOT NULL,
                    destination_iata TEXT NOT NULL,
                    destination_label TEXT NOT NULL,
                    travel_date TEXT NOT NULL,
                    travel_month TEXT NOT NULL,
                    stop_filter TEXT NOT NULL DEFAULT 'all',
                    target_price REAL,
                    notify_email TEXT NOT NULL,
                    tracking_days INTEGER NOT NULL DEFAULT 15,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    status TEXT NOT NULL DEFAULT 'activa',
                    stop_token TEXT NOT NULL UNIQUE,
                    best_price REAL,
                    best_direct_price REAL,
                    best_layover_price REAL,
                    best_provider TEXT,
                    best_is_direct INTEGER DEFAULT 1,
                    best_stops_label TEXT,
                    best_url TEXT,
                    best_flight_date TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    provider_id TEXT NOT NULL,
                    provider_name TEXT NOT NULL,
                    flight_date TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'COP',
                    is_direct INTEGER NOT NULL DEFAULT 1,
                    stops_count INTEGER NOT NULL DEFAULT 0,
                    layover_info TEXT NOT NULL,
                    airline TEXT NOT NULL,
                    departure_time TEXT,
                    arrival_time TEXT,
                    duration TEXT,
                    deep_link TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_calendar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    flight_date TEXT NOT NULL,
                    day_number INTEGER NOT NULL,
                    weekday_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'COP',
                    is_direct INTEGER NOT NULL DEFAULT 1,
                    stops_count INTEGER NOT NULL DEFAULT 0,
                    layover_info TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    provider_name TEXT NOT NULL,
                    airline TEXT NOT NULL,
                    deep_link TEXT NOT NULL,
                    FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    notify_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    friendly_message TEXT NOT NULL,
                    html_preview TEXT NOT NULL,
                    price REAL NOT NULL,
                    previous_best REAL,
                    is_direct INTEGER NOT NULL DEFAULT 1,
                    stops_label TEXT NOT NULL,
                    provider_name TEXT NOT NULL,
                    flight_date TEXT NOT NULL,
                    deep_link TEXT NOT NULL,
                    email_sent INTEGER NOT NULL DEFAULT 0,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

            # --- Migraciones seguras (idempotentes, sin pérdida de datos) ---
            _migrate(conn)

            # Crear usuario inicial si no existe
            cur = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (config.DEFAULT_ADMIN_USER.lower(),),
            )
            if not cur.fetchone():
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """
                    INSERT INTO users (username, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        config.DEFAULT_ADMIN_USER.lower(),
                        config.DEFAULT_ADMIN_EMAIL.lower(),
                        generate_password_hash(config.DEFAULT_ADMIN_PASSWORD),
                        now_str,
                    ),
                )
    finally:
        conn.close()


# --- Gestión de Usuarios (Consultas 100 % parametrizadas) ---

def authenticate_user(username_or_email: str, password: str, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        ident = username_or_email.strip().lower()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (ident, ident),
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            return dict(row)
        return None
    finally:
        conn.close()


def create_user(username: str, email: str, password: str, db_path: str | None = None) -> dict:
    conn = get_connection(db_path)
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    username.lower(),
                    email.lower(),
                    generate_password_hash(password),
                    now_str,
                ),
            )
            user_id = cur.lastrowid
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_user_by_id(user_id: int, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --- Gestión de Búsquedas Múltiples y Límites de Seguimiento ---

def create_search(
    user_id: int,
    origin_input: str,
    origin_iata: str,
    origin_label: str,
    destination_input: str,
    destination_iata: str,
    destination_label: str,
    travel_date: str,
    travel_month: str,
    stop_filter: str,
    target_price: float | None,
    notify_email: str,
    tracking_days: int,
    db_path: str | None = None,
) -> dict:
    now = datetime.now()
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (now + timedelta(days=int(tracking_days))).strftime("%Y-%m-%d %H:%M:%S")
    stop_token = secrets.token_urlsafe(24)

    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO searches (
                    user_id, origin_input, origin_iata, origin_label,
                    destination_input, destination_iata, destination_label,
                    travel_date, travel_month, stop_filter, target_price,
                    notify_email, tracking_days, created_at, expires_at,
                    status, stop_token
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa', ?)
                """,
                (
                    user_id,
                    origin_input,
                    origin_iata,
                    origin_label,
                    destination_input,
                    destination_iata,
                    destination_label,
                    travel_date,
                    travel_month,
                    stop_filter,
                    target_price,
                    notify_email,
                    int(tracking_days),
                    created_at,
                    expires_at,
                    stop_token,
                ),
            )
            search_id = cur.lastrowid
        row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def find_duplicate_search(user_id: int, origin_iata: str, destination_iata: str,
                          travel_date: str, stop_filter: str, db_path: str | None = None) -> dict | None:
    """Devuelve una ruta igual que siga vigente (activa o en pausa), si existe."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT * FROM searches
            WHERE user_id = ? AND origin_iata = ? AND destination_iata = ?
              AND travel_date = ? AND stop_filter = ? AND status IN ('activa', 'pausada')
            LIMIT 1
            """,
            (user_id, origin_iata, destination_iata, travel_date, stop_filter),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def expire_due_searches(db_path: str | None = None) -> int:
    """
    Revisa todas las búsquedas activas o pausadas cuyo límite de días ya venció,
    las pasa automáticamente a estado 'finalizada' y elimina las alertas
    de cualquier búsqueda que ya no esté activa.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                UPDATE searches
                SET status = 'finalizada'
                WHERE status IN ('activa', 'pausada')
                  AND (expires_at <= ? OR (travel_date IS NOT NULL AND travel_date < ?))
                """,
                (now_str, now_str[:10]),
            )
            return cur.rowcount
    finally:
        conn.close()


def _enrich_search_row(s: dict) -> dict:
    """Calcula días/horas restantes de seguimiento para mostrar en la interfaz."""
    try:
        exp = datetime.strptime(s["expires_at"], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        delta = exp - now
        total_seconds = delta.total_seconds()
        if total_seconds <= 0 or s["status"] in ("detenida", "finalizada"):
            s["days_remaining"] = 0
            s["hours_remaining"] = 0
        else:
            s["days_remaining"] = max(0, delta.days)
            s["hours_remaining"] = max(1, int(total_seconds // 3600))
    except Exception:
        s["days_remaining"] = s.get("tracking_days", 0)
        s["hours_remaining"] = 24
    return s


def get_user_searches(user_id: int, db_path: str | None = None) -> list[dict]:
    expire_due_searches(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM searches WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        results = []
        for row in rows:
            s = _enrich_search_row(dict(row))
            offers = conn.execute(
                "SELECT * FROM offers WHERE search_id = ? ORDER BY price ASC",
                (s["id"],),
            ).fetchall()
            calendar_rows = conn.execute(
                "SELECT * FROM monthly_calendar WHERE search_id = ? ORDER BY day_number ASC",
                (s["id"],),
            ).fetchall()
            s["offers"] = [dict(o) for o in offers]
            s["monthly_calendar"] = [dict(c) for c in calendar_rows]
            s["best_direct_offer"] = next((o for o in s["offers"] if o.get("is_direct")), None)
            s["best_layover_offer"] = next((o for o in s["offers"] if not o.get("is_direct")), None)
            if s["monthly_calendar"]:
                cheapest_day = min(s["monthly_calendar"], key=lambda x: x["price"])
                s["cheapest_month_day"] = cheapest_day
            else:
                s["cheapest_month_day"] = None
            results.append(s)
        return results
    finally:
        conn.close()


def get_active_searches_all_users(db_path: str | None = None) -> list[dict]:
    expire_due_searches(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM searches WHERE status = 'activa' ORDER BY id ASC"
        ).fetchall()
        return [_enrich_search_row(dict(r)) for r in rows]
    finally:
        conn.close()


def get_search_by_id(search_id: int, user_id: int | None = None, db_path: str | None = None) -> dict | None:
    conn = get_connection(db_path)
    try:
        if user_id is not None:
            row = conn.execute(
                "SELECT * FROM searches WHERE id = ? AND user_id = ?",
                (search_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM searches WHERE id = ?",
                (search_id,),
            ).fetchone()
        return _enrich_search_row(dict(row)) if row else None
    finally:
        conn.close()


def update_search_status(
    search_id: int,
    user_id: int,
    new_status: str,
    db_path: str | None = None,
) -> bool:
    if new_status not in ("activa", "pausada", "detenida", "finalizada"):
        return False
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                "UPDATE searches SET status = ? WHERE id = ? AND user_id = ?",
                (new_status, search_id, user_id),
            )
            # Pausar conserva el historial; solo terminar la ruta limpia sus avisos
            if cur.rowcount > 0 and new_status in ("detenida", "finalizada"):
                conn.execute(
                    "DELETE FROM alerts WHERE search_id = ? AND user_id = ?",
                    (search_id, user_id),
                )
            return cur.rowcount > 0
    finally:
        conn.close()


def stop_search_by_token(stop_token: str, db_path: str | None = None) -> dict | None:
    """Termina una búsqueda mediante su token único desde el enlace del correo."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM searches WHERE stop_token = ?",
            (stop_token,),
        ).fetchone()
        if not row:
            return None
        with conn:
            conn.execute(
                "UPDATE searches SET status = 'detenida' WHERE id = ?",
                (row["id"],),
            )
            conn.execute(
                "DELETE FROM alerts WHERE search_id = ?",
                (row["id"],),
            )
        updated = conn.execute(
            "SELECT * FROM searches WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return dict(updated) if updated else None
    finally:
        conn.close()


def delete_search(search_id: int, user_id: int, db_path: str | None = None) -> bool:
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM searches WHERE id = ? AND user_id = ?",
                (search_id, user_id),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def save_search_results(
    search_id: int,
    date_offers: list[dict],
    monthly_offers: list[dict],
    db_path: str | None = None,
) -> dict:
    """
    Guarda las ofertas de la fecha seleccionada y el calendario del mes completo,
    actualizando el mejor precio general, el mejor precio directo y el mejor precio con escala.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection(db_path)
    try:
        # El mejor precio de la búsqueda corresponde a la fecha elegida por el usuario
        # (mientras que la tarjeta 4 muestra por separado la fecha más barata del mes).
        if date_offers:
            best_overall = min(date_offers, key=lambda x: x["price"])
        elif monthly_offers:
            best_overall = min(monthly_offers, key=lambda x: x["price"])
        else:
            best_overall = None
        direct_candidates = [o for o in date_offers if o.get("is_direct")]
        layover_candidates = [o for o in date_offers if not o.get("is_direct")]

        best_direct_price = min((o["price"] for o in direct_candidates), default=None)
        best_layover_price = min((o["price"] for o in layover_candidates), default=None)

        with conn:
            conn.execute("DELETE FROM offers WHERE search_id = ?", (search_id,))
            for o in date_offers:
                conn.execute(
                    """
                    INSERT INTO offers (
                        search_id, provider_id, provider_name, flight_date,
                        price, currency, is_direct, stops_count, layover_info,
                        airline, departure_time, arrival_time, duration,
                        deep_link, checked_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        search_id,
                        o["provider_id"],
                        o["provider_name"],
                        o["flight_date"],
                        o["price"],
                        o.get("currency", "COP"),
                        1 if o.get("is_direct") else 0,
                        int(o.get("stops_count", 0)),
                        o["layover_info"],
                        o["airline"],
                        o.get("departure_time", ""),
                        o.get("arrival_time", ""),
                        o.get("duration", ""),
                        o["deep_link"],
                        now_str,
                    ),
                )

            conn.execute("DELETE FROM monthly_calendar WHERE search_id = ?", (search_id,))
            for m in monthly_offers:
                conn.execute(
                    """
                    INSERT INTO monthly_calendar (
                        search_id, flight_date, day_number, weekday_name,
                        price, currency, is_direct, stops_count, layover_info,
                        provider_id, provider_name, airline, deep_link
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        search_id,
                        m["flight_date"],
                        int(m["day_number"]),
                        m["weekday_name"],
                        m["price"],
                        m.get("currency", "COP"),
                        1 if m.get("is_direct") else 0,
                        int(m.get("stops_count", 0)),
                        m["layover_info"],
                        m["provider_id"],
                        m["provider_name"],
                        m["airline"],
                        m["deep_link"],
                    ),
                )

            if best_overall:
                conn.execute(
                    """
                    UPDATE searches
                    SET last_checked_at = ?,
                        best_price = ?,
                        best_direct_price = ?,
                        best_layover_price = ?,
                        best_provider = ?,
                        best_is_direct = ?,
                        best_stops_label = ?,
                        best_url = ?,
                        best_flight_date = ?
                    WHERE id = ?
                    """,
                    (
                        now_str,
                        best_overall["price"],
                        best_direct_price,
                        best_layover_price,
                        best_overall["provider_name"],
                        1 if best_overall.get("is_direct") else 0,
                        best_overall["layover_info"],
                        best_overall["deep_link"],
                        best_overall["flight_date"],
                        search_id,
                    ),
                )

        return {
            "best_overall": best_overall,
            "best_direct_price": best_direct_price,
            "best_layover_price": best_layover_price,
        }
    finally:
        conn.close()


# --- Gestión de Alertas y Bandeja de Notificaciones ---

def create_alert(
    search_id: int,
    user_id: int,
    notify_email: str,
    subject: str,
    friendly_message: str,
    html_preview: str,
    price: float,
    previous_best: float | None,
    is_direct: bool,
    stops_label: str,
    provider_name: str,
    flight_date: str,
    deep_link: str,
    email_sent: bool,
    db_path: str | None = None,
) -> dict:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO alerts (
                    search_id, user_id, notify_email, subject,
                    friendly_message, html_preview, price, previous_best,
                    is_direct, stops_label, provider_name, flight_date,
                    deep_link, email_sent, is_read, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    search_id,
                    user_id,
                    notify_email,
                    subject,
                    friendly_message,
                    html_preview,
                    price,
                    previous_best,
                    1 if is_direct else 0,
                    stops_label,
                    provider_name,
                    flight_date,
                    deep_link,
                    1 if email_sent else 0,
                    now_str,
                ),
            )
            alert_id = cur.lastrowid
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_user_alerts(user_id: int, limit: int = 30, db_path: str | None = None) -> list[dict]:
    expire_due_searches(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT a.*, s.origin_label, s.destination_label, s.origin_iata, s.destination_iata
            FROM alerts a
            JOIN searches s ON a.search_id = s.id
            WHERE a.user_id = ? AND s.status IN ('activa', 'pausada')
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def record_check_status(search_id: int, ok: bool, error: str | None = None, db_path: str | None = None) -> None:
    """Guarda el resultado de la última consulta (para mostrar avisos de error en la interfaz)."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE searches SET last_checked_at = ?, last_check_ok = ?, last_check_error = ? WHERE id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1 if ok else 0, None if ok else error, search_id),
            )
    finally:
        conn.close()


def count_active_searches(user_id: int, db_path: str | None = None) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM searches WHERE user_id = ? AND status = 'activa'", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _invite_hash(code: str) -> str:
    import hashlib
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def invite_uses(code: str, db_path: str | None = None) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT uses FROM invite_usage WHERE code_hash = ?", (_invite_hash(code),)).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def register_invite_use(code: str, db_path: str | None = None) -> None:
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO invite_usage (code_hash, uses, updated_at) VALUES (?, 1, ?)
                ON CONFLICT(code_hash) DO UPDATE SET uses = uses + 1, updated_at = excluded.updated_at
                """,
                (_invite_hash(code), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    finally:
        conn.close()
