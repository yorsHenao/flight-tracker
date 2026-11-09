#!/usr/bin/env python3
"""
Motor autónomo de rastreo de vuelos para PythonAnywhere.
Se puede ejecutar directamente en la pestaña 'Tasks' de PythonAnywhere:
    python3 /home/tu_usuario/vuelos_tracker/scheduler_task.py
O ser invocado internamente por la aplicación Flask.
"""
import logging
import os
import time
from datetime import datetime

import config

from database import (
    init_db,
    expire_due_searches,
    get_active_searches_all_users,
    get_search_by_id,
    save_search_results,
    record_check_status,
    offer_matches_tracked_date,
)
from notifier import notify_lowest_price
from providers.flight_engine import (
    search_flights_for_date,
    generate_monthly_calendar_offers,
)


def run_check_for_search(
    search_id: int,
    jitter_seed: str = "",
    force_alert: bool = False,
    attempt_live: bool = True,
    bypass_cache: bool = False,
    db_path: str | None = None,
) -> dict | None:
    """
    Ejecuta la búsqueda completa (fecha elegida + calendario de todo el mes).
    El calendario solo se muestra. La alerta, el enlace y el precio de referencia
    salen de la fecha elegida (y de la vuelta, si el registro la tiene).
    """
    expire_due_searches(db_path)
    search_row = get_search_by_id(search_id, db_path=db_path)
    if not search_row or search_row["status"] != "activa":
        return None

    previous_best = search_row.get("best_price")
    seed = jitter_seed or datetime.now().strftime("%Y-%m-%d-%H-%M")

    # 1. Buscar ofertas reales en vivo para la fecha seleccionada
    date_offers = search_flights_for_date(
        origin_input=search_row["origin_input"],
        destination_input=search_row["destination_input"],
        flight_date=search_row["travel_date"],
        stop_filter=search_row["stop_filter"],
        jitter_seed=seed,
        attempt_live=attempt_live,
        bypass_cache=bypass_cache,
    )

    # 2. Buscar mejores precios reales día por día dentro del rango del mes
    monthly_offers = generate_monthly_calendar_offers(
        origin_input=search_row["origin_input"],
        destination_input=search_row["destination_input"],
        travel_month=search_row["travel_month"],
        stop_filter=search_row["stop_filter"],
        jitter_seed=seed,
        attempt_live=attempt_live,
    )

    # 3. Sin datos reales: no se guarda nada, no se envía correo, se registra el error
    if not date_offers and not monthly_offers:
        msg = "No pudimos consultar precios ahora. Lo intentaremos de nuevo."
        logging.getLogger("vuelos").error(
            "Ruta %s (%s-%s %s): el proveedor no devolvió vuelos",
            search_id, search_row.get("origin_iata"), search_row.get("destination_iata"), search_row.get("travel_date"),
        )
        record_check_status(search_id, ok=False, error=msg, db_path=db_path)
        return {"search_id": search_id, "best_overall": None, "best_direct_price": None,
                "best_layover_price": None, "alert_created": None, "error": msg}

    # 4. Guardar en SQLite y obtener el mejor resultado
    summary = save_search_results(
        search_id=search_id,
        date_offers=date_offers,
        monthly_offers=monthly_offers,
        db_path=db_path,
    )
    record_check_status(search_id, ok=True, db_path=db_path)

    best_overall = summary.get("best_overall")
    if best_overall and not offer_matches_tracked_date(best_overall, search_row):
        best_overall = None
    alert_created = None

    if best_overall:
        new_price = float(best_overall["price"])
        target_price = search_row.get("target_price")
        prev = float(previous_best) if previous_best is not None else None
        # Solo bajadas reales: al menos ALERT_MIN_DROP_PCT % por debajo del mejor anterior
        real_drop = prev is not None and new_price <= prev * (1 - config.ALERT_MIN_DROP_PCT / 100.0)
        # Precio objetivo: avisar solo cuando se cruza (no en cada revisión)
        crossed_target = (
            target_price is not None and new_price <= float(target_price)
            and (prev is None or prev > float(target_price))
        )
        should_notify = force_alert or prev is None or real_drop or crossed_target

        if should_notify:
            alert_created = notify_lowest_price(
                search_row=search_row,
                best_offer=best_overall,
                previous_best=prev,
                db_path=db_path,
            )

    return {
        "search_id": search_id,
        "best_overall": best_overall,
        "best_direct_price": summary.get("best_direct_price"),
        "best_layover_price": summary.get("best_layover_price"),
        "alert_created": alert_created,
        "error": None,
    }


LOCK_STALE_SECONDS = 900  # un candado más viejo que esto se considera abandonado
DEFAULT_TIME_BUDGET_SECONDS = 240  # margen bajo el límite de ~300 s de PythonAnywhere


def _lock_path(db_path: str | None) -> str:
    return (db_path or config.DB_PATH) + ".revision.lock"


def _acquire_lock(path: str) -> bool:
    """Candado por archivo (funciona en Linux y Windows). Evita revisiones simultáneas."""
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(time.time()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > LOCK_STALE_SECONDS:
                    os.remove(path)
                    continue
            except OSError:
                continue
            return False
    return False


def _release_lock(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def run_all_active_searches(db_path: str | None = None, time_budget: float | None = None) -> dict:
    """
    Recorre las búsquedas activas de todos los usuarios, finaliza las que cumplieron
    su límite de días y actualiza precios y alertas de las vigentes.

    Las rutas se procesan de la menos reciente a la más reciente; si se agota
    time_budget (segundos) se detiene y las pendientes quedan para la siguiente
    llamada. Un candado impide que dos revisiones corran al mismo tiempo.
    """
    started = time.monotonic()
    result = {
        "ok": True,
        "skipped_running": False,
        "checked_count": 0,
        "failed_count": 0,
        "expired_count": 0,
        "alerts_triggered": 0,
        "pending_count": 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    lock = _lock_path(db_path)
    if not _acquire_lock(lock):
        result["skipped_running"] = True
        return result
    try:
        init_db(db_path)
        result["expired_count"] = expire_due_searches(db_path) or 0
        active_list = get_active_searches_all_users(db_path)
        active_list.sort(key=lambda r: (r.get("last_checked_at") or "", r["id"]))

        for i, s in enumerate(active_list):
            if time_budget is not None and time.monotonic() - started > time_budget:
                result["pending_count"] = len(active_list) - i
                break
            try:
                res = run_check_for_search(s["id"], db_path=db_path)
            except Exception as exc:  # una ruta con datos dañados no debe frenar las demás
                logging.getLogger("vuelos").error("Ruta %s omitida por error: %s", s["id"], exc)
                result["failed_count"] += 1
                continue
            if res:
                if res.get("error"):
                    result["failed_count"] += 1
                else:
                    result["checked_count"] += 1
                if res.get("alert_created"):
                    result["alerts_triggered"] += 1
    finally:
        _release_lock(lock)
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config.validate_required_settings()
    result = run_all_active_searches()
    if result["skipped_running"]:
        print("Ya hay una revisión en curso; se omite esta ejecución.")
        raise SystemExit(0)
    print(
        f"[{result['timestamp']}] Escaneo autónomo completado: "
        f"{result['checked_count']} búsquedas revisadas, "
        f"{result['alerts_triggered']} alertas enviadas, "
        f"{result['expired_count']} finalizadas por límite de días."
    )
