"""Pruebas del lector de Google Flights y del registro de errores SMTP."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VUELOS_SECRET_KEY", "x" * 64)
os.environ.setdefault("VUELOS_INVITE_CODE", "codigo-de-prueba-123")
os.environ.setdefault("VUELOS_ADMIN_PASS", "clave-de-prueba-123")
os.environ.setdefault("VUELOS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import config  # noqa: E402
import notifier  # noqa: E402
from providers import flight_engine as fe  # noqa: E402


class Ds1ExtractTest(unittest.TestCase):
    def test_extra_data_after_json(self):
        html = ("<script>AF_initDataCallback({key: 'ds:1', hash: '9', data:[[1,2],[\"a\"]], "
                "errorHasStatus: false, x:[3], sideChannel: {}});</script>")
        self.assertEqual(fe._extract_ds1_payloads(html), [[[1, 2], ["a"]]])

    def test_old_regex_would_fail(self):
        html = "AF_initDataCallback({key: 'ds:1', data:[1] , extra:[2], sideChannel: {}})"
        self.assertEqual(fe._extract_ds1_payloads(html), [[1]])

    def test_xssi_prefix_chunks(self):
        text = ")]}'\n\n123\n[[\"wrb.fr\",null,\"[1]\"]]\n45\n[[\"di\",9]]\n"
        self.assertEqual(len(fe._extract_ds1_payloads(text)), 2)

    def test_garbage_returns_empty(self):
        self.assertEqual(fe._extract_ds1_payloads("<html>consent</html>"), [])

    def test_fetch_logs_and_returns_empty_without_fake_prices(self):
        resp = mock.Mock(status_code=200, text="<html>Antes de ir a Google</html>",
                         url="https://consent.google.com/x", headers={"Content-Type": "text/html"})
        with mock.patch("requests.Session.get", return_value=resp), \
             self.assertLogs(fe._log, level="WARNING") as logs:
            self.assertEqual(fe.fetch_live_google_flights("MDE", "CLO", "2099-12-06", bypass_cache=True), [])
        self.assertTrue(any("sin datos legibles" in m for m in logs.output))


class SmtpLogTest(unittest.TestCase):
    def test_exception_logged_without_password(self):
        env = {"VUELOS_SMTP_ENABLED": "true", "VUELOS_SMTP_USER": "a@dominio.co",
               "VUELOS_SMTP_PASSWORD": "secretoabcdefgh"}
        err = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(config, "_load_env_file"), \
             mock.patch("smtplib.SMTP", side_effect=OSError("fallo secretoabcdefgh")), redirect_stderr(err):
            self.assertFalse(notifier.send_smtp_email("b@x.co", "s", "t", "<p>t</p>"))
        out = err.getvalue()
        self.assertIn("OSError", out)
        self.assertNotIn("secretoabcdefgh", out)


if __name__ == "__main__":
    unittest.main()
