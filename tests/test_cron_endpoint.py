"""Pruebas de la ruta /tareas/revisar. Ejecutar: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp()
os.environ.setdefault("VUELOS_SECRET_KEY", "x" * 64)
os.environ.setdefault("VUELOS_INVITE_CODE", "codigo-de-prueba-123")
os.environ.setdefault("VUELOS_ADMIN_PASS", "clave-de-prueba-123")
os.environ.setdefault("VUELOS_DB_PATH", os.path.join(_TMP, "test.db"))
os.environ["VUELOS_BG_THREAD"] = "false"
os.environ["VUELOS_SMTP_ENABLED"] = "false"

import config  # noqa: E402
config.DB_PATH = os.environ["VUELOS_DB_PATH"]
config.ENABLE_BACKGROUND_THREAD = False
config.SMTP_ENABLED = False
import app as app_module  # noqa: E402
import scheduler_task  # noqa: E402

TOKEN = "t" * 40


class CronEndpointTest(unittest.TestCase):
    def setUp(self):
        app_module.rate_limiter.reset()
        self.client = app_module.app.test_client()
        self.p = mock.patch.object(config, "CRON_TOKEN", TOKEN)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_missing_token_404(self):
        self.assertEqual(self.client.get("/tareas/revisar").status_code, 404)

    def test_wrong_token_404(self):
        r = self.client.get("/tareas/revisar", headers={"X-Cron-Token": "malo"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.get("/tareas/revisar?token=" + "t" * 39).status_code, 404)

    def test_unset_token_404(self):
        with mock.patch.object(config, "CRON_TOKEN", ""):
            r = self.client.get("/tareas/revisar", headers={"X-Cron-Token": ""})
            self.assertEqual(r.status_code, 404)

    def test_correct_token_header_and_query(self):
        fake = {"ok": True, "skipped_running": False, "checked_count": 2, "failed_count": 0,
                "expired_count": 0, "alerts_triggered": 1, "pending_count": 0, "elapsed_seconds": 1.0,
                "timestamp": "x"}
        with mock.patch.object(app_module, "run_all_active_searches", return_value=fake) as m:
            r = self.client.get("/tareas/revisar", headers={"X-Cron-Token": TOKEN})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["checked_count"], 2)
            self.assertNotIn("timestamp", r.get_json())
            self.assertIn("Content-Security-Policy", r.headers)
            r = self.client.post("/tareas/revisar?token=" + TOKEN)  # POST sin CSRF
            self.assertEqual(r.status_code, 200)
            self.assertEqual(m.call_count, 2)

    def test_real_run_no_routes(self):
        r = self.client.get("/tareas/revisar", headers={"X-Cron-Token": TOKEN})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_lock_prevents_overlap(self):
        lock = scheduler_task._lock_path(None)
        open(lock, "w").close()
        try:
            res = scheduler_task.run_all_active_searches()
            self.assertTrue(res["skipped_running"])
        finally:
            os.remove(lock)
        self.assertFalse(scheduler_task.run_all_active_searches()["skipped_running"])

    def test_time_budget_leaves_pending(self):
        rows = [{"id": 1, "last_checked_at": None}, {"id": 2, "last_checked_at": "2026-01-01"}]
        with mock.patch.object(scheduler_task, "get_active_searches_all_users", return_value=rows), \
             mock.patch.object(scheduler_task, "run_check_for_search", return_value={"error": None}) as m:
            res = scheduler_task.run_all_active_searches(time_budget=-1)
            self.assertEqual(res["pending_count"], 2)
            m.assert_not_called()

    def test_rate_limit(self):
        with mock.patch.object(app_module, "run_all_active_searches", return_value={"ok": True}):
            codes = [self.client.get("/tareas/revisar", headers={"X-Cron-Token": TOKEN}).status_code
                     for _ in range(7)]
        self.assertEqual(codes[-1], 429)


if __name__ == "__main__":
    unittest.main()
