"""Búsquedas en segundo plano con cola acotada y caché en memoria.

PythonAnywhere gratis tiene un solo worker uWSGI: si una búsqueda larga se hace
dentro de la petición, las demás personas esperan (y aparece el 502). Aquí la
consulta se ejecuta en hilos daemon (máximo MAX_WORKERS a la vez, en orden de
llegada) y el navegador pregunta por el estado cada 2 segundos.
"""
from __future__ import annotations

import logging
import queue
import secrets
import threading
import time
from typing import Any, Callable

_log = logging.getLogger("vuelos.jobs")

MAX_WORKERS = 2
MAX_QUEUE = 20
RESULT_TTL_SECONDS = 1800.0  # 30 min de caché por ruta + fechas
JOB_TTL_SECONDS = 1800.0

_lock = threading.Lock()
_queue: "queue.Queue[str]" = queue.Queue()
_jobs: dict[str, dict[str, Any]] = {}
_by_key: dict[str, str] = {}          # clave de búsqueda -> job_id en curso
_results: dict[str, tuple[float, Any]] = {}  # clave -> (momento, resultado)
_workers: list[threading.Thread] = []


class QueueFull(Exception):
    pass


def cache_key(p: dict) -> str:
    return "|".join(str(p.get(k, "")) for k in
                    ("origin_iata", "destination_iata", "origin_label", "destination_label",
                     "travel_date", "travel_month", "stop_filter"))


def get_cached(key: str):
    with _lock:
        hit = _results.get(key)
        if hit and time.time() - hit[0] < RESULT_TTL_SECONDS:
            return hit[1]
        if hit:
            _results.pop(key, None)
    return None


def _cleanup_locked():
    now = time.time()
    for jid in [j for j, v in _jobs.items() if now - v["created"] > JOB_TTL_SECONDS]:
        job = _jobs.pop(jid)
        if _by_key.get(job["key"]) == jid:
            _by_key.pop(job["key"], None)
    for k in [k for k, v in _results.items() if now - v[0] > RESULT_TTL_SECONDS]:
        _results.pop(k, None)


def _ensure_workers():
    _workers[:] = [t for t in _workers if t.is_alive()]
    while len(_workers) < MAX_WORKERS:
        t = threading.Thread(target=_worker_loop, name=f"vuelos-job-{len(_workers)}", daemon=True)
        t.start()
        _workers.append(t)


def submit(key: str, fn: Callable[[Callable[[int], None]], Any]) -> str:
    """Encola fn(set_step) y devuelve job_id. Reutiliza un trabajo igual en curso."""
    with _lock:
        _cleanup_locked()
        existing = _by_key.get(key)
        if existing and existing in _jobs and _jobs[existing]["status"] in ("queued", "running"):
            return existing
        pending = sum(1 for j in _jobs.values() if j["status"] in ("queued", "running"))
        if pending >= MAX_QUEUE:
            raise QueueFull("Hay muchas búsquedas en curso. Intenta en un minuto.")
        jid = secrets.token_urlsafe(12)
        _jobs[jid] = {"key": key, "fn": fn, "status": "queued", "step": 1,
                      "created": time.time(), "error": None}
        _by_key[key] = jid
        _ensure_workers()
    _queue.put(jid)
    return jid


def status(jid: str) -> dict | None:
    with _lock:
        job = _jobs.get(jid)
        if not job:
            return None
        ahead = 0
        if job["status"] == "queued":
            ahead = sum(1 for j in _jobs.values()
                        if j["status"] in ("queued", "running") and j["created"] < job["created"])
        return {"status": job["status"], "step": job["step"], "error": job["error"], "ahead": ahead}


def wait(jid: str, timeout: float) -> dict | None:
    end = time.time() + timeout
    while True:
        st = status(jid)
        if not st or st["status"] in ("done", "error") or time.time() >= end:
            return st
        time.sleep(0.05)


def _worker_loop():
    while True:
        jid = _queue.get()
        with _lock:
            job = _jobs.get(jid)
            if not job:
                continue
            job["status"], job["step"] = "running", 2
            fn = job.pop("fn")

        def set_step(n: int, _job=job):
            _job["step"] = max(_job["step"], min(int(n), 3))

        try:
            result = fn(set_step)
            with _lock:
                if result is not None:
                    _results[job["key"]] = (time.time(), result)
                job["status"], job["step"] = "done", 3
        except Exception as exc:  # nunca tumbar el hilo
            _log.exception("Búsqueda en segundo plano falló")
            with _lock:
                job["status"], job["error"] = "error", type(exc).__name__
        finally:
            with _lock:
                if _by_key.get(job["key"]) == jid:
                    _by_key.pop(job["key"], None)


def reset():
    """Solo para pruebas."""
    with _lock:
        _jobs.clear()
        _by_key.clear()
        _results.clear()
