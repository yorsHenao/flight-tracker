"""Pruebas del modo invitado. Ejecutar: python -m pytest tests"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VUELOS_SECRET_KEY", "x" * 64)
os.environ.setdefault("VUELOS_INVITE_CODE", "codigo-de-prueba-123")
os.environ.setdefault("VUELOS_ADMIN_PASS", "clave-de-prueba-123")
os.environ.setdefault("VUELOS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ["VUELOS_BG_THREAD"] = "false"

import config  # noqa: E402
config.DB_PATH = os.environ["VUELOS_DB_PATH"]
config.ENABLE_BACKGROUND_THREAD = False
import app as app_module  # noqa: E402
import notifier  # noqa: E402
from database import get_connection, init_db  # noqa: E402

TOKEN = "tok" * 10
FAKE_OFFERS = [
    {"price": p, "airline": a, "is_direct": True, "departure_time": "06:00", "arrival_time": "07:05",
     "provider_name": "Google Flights", "deep_link": f"https://example.com/{a}", "flight_date": "2026-11-24"}
    for p, a in [(300000, "Avianca"), (150000, "Wingo"), (180000, "LATAM"), (210000, "JetSMART"), (400000, "Otra")]
]


def _counts():
    conn = get_connection(config.DB_PATH)
    try:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("searches", "offers", "alerts", "monthly_calendar"))
    finally:
        conn.close()


class GuestModeTest(unittest.TestCase):
    def setUp(self):
        init_db(config.DB_PATH)
        app_module.rate_limiter.reset()
        app_module.search_jobs.reset()
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as s:
            s["_csrf_token"] = TOKEN
        self.date = (datetime.now() + timedelta(days=21)).strftime("%d-%m-%Y")

    def _search(self):
        return self.client.post("/searches/preview", data={
            "csrf_token": TOKEN, "origin": "Bogotá, Colombia (BOG)", "destination": "Cali, Colombia (CLO)",
            "travel_date": self.date, "travel_month": "", "stop_filter": "all"})

    def test_home_is_public_and_empty(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('id="create-search-form"', html)
        self.assertIn("Busca una ruta para ver los precios más bajos", html)
        self.assertIn("Iniciar sesión", html)
        self.assertNotIn("Bogotá, Colombia (BOG)\" />", html)
        self.assertNotIn("Activar seguimiento", html)
        self.assertNotIn("Cerrar sesión", html)

    def test_guest_search_shows_4_cheapest_without_db_or_email(self):
        before = _counts()
        with mock.patch.object(app_module, "search_flights_for_date", return_value=list(FAKE_OFFERS)), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]), \
             mock.patch.object(notifier, "deliver_email") as de:
            r = self._search()
            self.assertEqual(r.status_code, 302)
            html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(html.count('class="gx-card"'), 4)
        self.assertIn("$150.000", html)
        self.assertNotIn("$400.000", html)
        self.assertIn("Reservar", html)
        self.assertIn("Crea una cuenta", html)
        self.assertNotIn("Activar seguimiento", html)
        de.assert_not_called()
        self.assertEqual(_counts(), before)
        for chip in ['data-portal-filter="kayak"', 'data-portal-filter="skyscanner"', 'data-portal-filter="booking"',
                     'data-portal-filter="avianca"', 'data-portal-filter="wingo"']:
            self.assertIn(chip, html)
        self.assertNotIn("rappitravel", html)
        self.assertNotIn('data-portal-filter="kiwi"', html)
        self.assertIn('data-airline-key="wingo"', html)
        self.assertIn('data-gf-booking="https://example.com/Wingo"', html)

    def test_guest_rate_limit_10_per_hour(self):
        with mock.patch.object(app_module, "search_flights_for_date", return_value=[]), \
             mock.patch.object(app_module, "generate_monthly_calendar_offers", return_value=[]):
            for _ in range(10):
                self._search()
            self.assertIn("guest_preview", self._session())
            with self.client.session_transaction() as s:
                s.pop("guest_preview", None)
            r = self._search()
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("guest_preview", self._session())
        with self.client.session_transaction() as s:
            flashes = s.get("_flashes", [])
        self.assertTrue(any("10 búsquedas por hora" in m for _, m in flashes))

    def _session(self):
        with self.client.session_transaction() as s:
            return dict(s)

    def test_guest_search_requires_csrf(self):
        r = self.client.post("/searches/preview", data={"origin": "BOG", "destination": "CLO", "travel_date": self.date})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("guest_preview", self._session())

    def test_protected_endpoints_redirect_guests(self):
        before = _counts()
        for path in ["/searches/create", "/api/searches", "/searches/check-all", "/searches/1/check",
                     "/searches/1/status", "/searches/1/delete", "/searches/1/simulate-drop",
                     "/admin/correo-prueba", "/logout"]:
            r = self.client.post(path, data={"csrf_token": TOKEN})
            self.assertIn(r.status_code, (302, 401, 404), path)
            if r.status_code == 302:
                self.assertIn("/login", r.headers["Location"], path)
        self.assertEqual(self.client.get("/tareas/revisar").status_code, 404)
        self.assertEqual(_counts(), before)


if __name__ == "__main__":
    unittest.main()
