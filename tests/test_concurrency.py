"""Búsqueda en segundo plano, polling, caché y corte temprano de Google (simulado)."""
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VUELOS_SECRET_KEY", "x" * 64)
os.environ.setdefault("VUELOS_INVITE_CODE", "codigo-de-prueba-123")
os.environ.setdefault("VUELOS_ADMIN_PASS", "clave-de-prueba-123")
os.environ.setdefault("VUELOS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ["VUELOS_BG_THREAD"] = "false"

import requests  # noqa: E402
import config  # noqa: E402
config.DB_PATH = os.environ["VUELOS_DB_PATH"]
config.ENABLE_BACKGROUND_THREAD = False
import app as app_module  # noqa: E402
import search_jobs  # noqa: E402
from database import init_db  # noqa: E402
from providers import flight_engine  # noqa: E402

TOKEN = "tok" * 10
OFFERS = [{"price": 150000, "airline": "Wingo", "is_direct": True, "departure_time": "06:00",
           "arrival_time": "07:05", "provider_name": "Google Flights", "deep_link": "https://example.com/w",
           "flight_date": "2026-12-20"}]


class JobsTest(unittest.TestCase):
    def setUp(self):
        init_db(config.DB_PATH)
        app_module.rate_limiter.reset()
        search_jobs.reset()
        flight_engine._LIVE_CACHE.clear()
        self.date = (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")

    def _client(self):
        c = app_module.app.test_client()
        with c.session_transaction() as s:
            s["_csrf_token"] = TOKEN
        return c

    def _post(self, c, dest="Cali, Colombia (CLO)", json=True):
        headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"} if json else {}
        return c.post("/searches/preview", headers=headers, data={
            "csrf_token": TOKEN, "origin": "Bogotá, Colombia (BOG)", "destination": dest,
            "travel_date": self.date, "travel_month": "", "stop_filter": "all"})

    def test_preview_returns_job_immediately_and_polling_finishes(self):
        gate = threading.Event()

        def slow(**kw):
            gate.wait(5)
            return list(OFFERS)

        c = self._client()
        with mock.patch.object(app_module, "search_flights_for_date", side_effect=slow), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]):
            t0 = time.time()
            r = self._post(c)
            self.assertLess(time.time() - t0, 1.0)
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            data = r.get_json()
            self.assertTrue(data["job_id"])
            st = c.get(data["status_url"]).get_json()
            self.assertIn(st["status"], ("queued", "running"))
            # La página muestra el avión mientras tanto
            app_module.PREVIEW_INLINE_WAIT = 0.1
            html = c.get("/").get_data(as_text=True)
            self.assertIn('data-job="' + data["job_id"] + '"', html)
            self.assertIn("Buscando los vuelos más baratos", html)
            self.assertIn(">BOG<", html)
            self.assertIn(">CLO<", html)
            gate.set()
            search_jobs.wait(data["job_id"], 5)
            self.assertEqual(c.get(data["status_url"]).get_json()["status"], "done")
            html = c.get("/").get_data(as_text=True)
            app_module.PREVIEW_INLINE_WAIT = 1.5
        self.assertIn("$150.000", html)
        self.assertNotIn('data-job="', html)

    def test_status_of_other_session_is_hidden(self):
        c = self._client()
        with mock.patch.object(app_module, "search_flights_for_date", return_value=list(OFFERS)), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]):
            data = self._post(c).get_json()
        other = self._client()
        self.assertEqual(other.get(data["status_url"]).status_code, 404)

    def test_result_cache_avoids_second_query(self):
        m = mock.Mock(return_value=list(OFFERS))
        with mock.patch.object(app_module, "search_flights_for_date", m), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]):
            c1, c2 = self._client(), self._client()
            self._post(c1, json=False)
            self.assertIn("$150.000", c1.get("/").get_data(as_text=True))
            r = self._post(c2)
            self.assertIsNone(r.get_json()["job_id"])  # ya estaba en caché
            self.assertIn("$150.000", c2.get("/").get_data(as_text=True))
        self.assertEqual(m.call_count, 1)

    def test_max_two_concurrent_jobs_in_order(self):
        running, peak, lock = [0], [0], threading.Lock()
        order = []

        def work(i):
            def fn(set_step):
                with lock:
                    running[0] += 1
                    peak[0] = max(peak[0], running[0])
                time.sleep(0.15)
                with lock:
                    running[0] -= 1
                    order.append(i)
                return {"i": i}
            return fn

        ids = [search_jobs.submit(f"k{i}", work(i)) for i in range(5)]
        for j in ids:
            search_jobs.wait(j, 5)
        self.assertLessEqual(peak[0], 2)
        self.assertEqual(sorted(order), list(range(5)))
        self.assertIn(order.index(0), (0, 1))
        self.assertTrue(all(t.daemon for t in search_jobs._workers))

    def test_two_guest_searches_concurrently_do_not_block_status(self):
        gate = threading.Event()

        def slow(**kw):
            gate.wait(5)
            return list(OFFERS)

        with mock.patch.object(app_module, "search_flights_for_date", side_effect=slow), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]):
            c1, c2 = self._client(), self._client()
            t0 = time.time()
            j1 = self._post(c1).get_json()
            j2 = self._post(c2, dest="Medellín, Colombia (MDE)").get_json()
            self.assertNotEqual(j1["job_id"], j2["job_id"])
            self.assertLess(time.time() - t0, 1.0)
            self.assertEqual(c1.get("/login").status_code, 200)  # la app sigue respondiendo
            gate.set()
            for j in (j1, j2):
                search_jobs.wait(j["job_id"], 5)
            self.assertEqual(c2.get(j2["status_url"]).get_json()["status"], "done")


class GoogleTimeoutTest(unittest.TestCase):
    def setUp(self):
        flight_engine._LIVE_CACHE.clear()
        self.day = (datetime.now() + timedelta(days=40)).strftime("%Y-%m-%d")

    def test_default_timeout_is_8s(self):
        seen = []

        def fake_get(self_, url, headers=None, timeout=None):
            seen.append(timeout)
            raise requests.exceptions.Timeout("lento")

        with mock.patch.object(requests.Session, "get", fake_get), mock.patch.object(flight_engine.time, "sleep"):
            self.assertEqual(flight_engine.fetch_live_google_flights("BOG", "CLO", self.day), [])
        self.assertTrue(seen)
        self.assertTrue(all(t == 8.0 for t in seen))
        self.assertLessEqual(len(seen), 2)  # no prueba las 4 variantes si la red falla

    def test_ssl_eof_trips_breaker_for_month(self):
        calls = [0]

        def fake_get(self_, url, headers=None, timeout=None):
            calls[0] += 1
            raise requests.exceptions.SSLError("EOF occurred in violation of protocol")

        month = (datetime.now() + timedelta(days=40)).strftime("%Y-%m")
        with mock.patch.object(requests.Session, "get", fake_get), mock.patch.object(flight_engine.time, "sleep"):
            t0 = time.time()
            res = flight_engine.generate_monthly_calendar_offers("BOG", "CLO", month)
        self.assertEqual(res, [])
        self.assertLess(time.time() - t0, 5)
        # ~30 días x 4 variantes serían 120 llamadas; con el corte quedan muy pocas
        self.assertLessEqual(calls[0], 3 + flight_engine.MONTH_WORKERS * 2)

    def test_empty_result_is_cached_briefly(self):
        calls = [0]

        def fake_get(self_, url, headers=None, timeout=None):
            calls[0] += 1
            raise requests.exceptions.SSLError("EOF")

        with mock.patch.object(requests.Session, "get", fake_get), mock.patch.object(flight_engine.time, "sleep"):
            flight_engine.fetch_live_google_flights("BOG", "CLO", self.day)
            n = calls[0]
            flight_engine.fetch_live_google_flights("BOG", "CLO", self.day)
        self.assertEqual(calls[0], n)


if __name__ == "__main__":
    unittest.main()
