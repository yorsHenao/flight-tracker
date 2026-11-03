"""Pruebas del botón 'Enviar correo de prueba'. Ejecutar: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
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


class AdminTestEmailTest(unittest.TestCase):
    def setUp(self):
        init_db(config.DB_PATH)
        app_module.rate_limiter.reset()
        self.client = app_module.app.test_client()

    def _login(self, username, user_id=1):
        with self.client.session_transaction() as s:
            s["user_id"] = user_id
            s["username"] = username
            s["_csrf_token"] = "tok" * 10
        return "tok" * 10

    def _alert_count(self):
        conn = get_connection(config.DB_PATH)
        try:
            return conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        finally:
            conn.close()

    def test_admin_sends_to_own_email_without_saving(self):
        tok = self._login(config.DEFAULT_ADMIN_USER)
        before = self._alert_count()
        with mock.patch.object(notifier, "send_smtp_email", return_value=True) as m:
            r = self.client.post("/admin/correo-prueba", data={"csrf_token": tok})
        self.assertEqual(r.status_code, 302)
        kw = m.call_args.kwargs
        self.assertEqual(kw["to_email"], config.DEFAULT_ADMIN_EMAIL)
        self.assertTrue(kw["subject"].startswith("Prueba:"))
        self.assertIn("correo de prueba", kw["html_body"])
        self.assertIn("Vuelos Economicos", kw["html_body"])
        self.assertEqual(self._alert_count(), before)

    def test_smtp_failure_flashes_error(self):
        tok = self._login(config.DEFAULT_ADMIN_USER)
        with mock.patch.object(notifier, "send_smtp_email", return_value=False):
            self.client.post("/admin/correo-prueba", data={"csrf_token": tok})
        with self.client.session_transaction() as s:
            msgs = s.get("_flashes", [])
        self.assertTrue(any("SMTP" in m for _, m in msgs))

    def test_non_admin_denied(self):
        tok = self._login("otro_usuario", user_id=99)
        with mock.patch.object(notifier, "send_smtp_email") as m:
            r = self.client.post("/admin/correo-prueba", data={"csrf_token": tok})
        self.assertEqual(r.status_code, 404)
        m.assert_not_called()

    def test_csrf_required(self):
        self._login(config.DEFAULT_ADMIN_USER)
        with mock.patch.object(notifier, "send_smtp_email") as m:
            self.client.post("/admin/correo-prueba", data={"csrf_token": "malo"})
        m.assert_not_called()

    def test_rate_limit(self):
        tok = self._login(config.DEFAULT_ADMIN_USER)
        with mock.patch.object(notifier, "send_smtp_email", return_value=True) as m:
            for _ in range(4):
                self.client.post("/admin/correo-prueba", data={"csrf_token": tok})
        self.assertEqual(m.call_count, 3)

    def test_button_only_for_admin(self):
        self._login(config.DEFAULT_ADMIN_USER)
        self.assertIn("Enviar correo de prueba", self.client.get("/").get_data(as_text=True))
        self._login("otro_usuario", user_id=1)
        self.assertNotIn("Enviar correo de prueba", self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
