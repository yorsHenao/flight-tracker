"""La alerta y el precio de referencia solo usan la fecha elegida.

El día más barato del mes se guarda para mostrarlo, pero no dispara avisos,
no entra en el enlace y no sustituye el mínimo de la fecha vigilada.
"""
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
os.environ["VUELOS_SMTP_ENABLED"] = "false"
os.environ["VUELOS_BREVO_API_KEY"] = ""

import notifier  # noqa: E402
import scheduler_task  # noqa: E402
from database import (  # noqa: E402
    create_search,
    create_user,
    get_connection,
    get_user_searches,
    init_db,
    offer_matches_tracked_date,
    tracked_flight_dates,
)

EXACT = "2026-12-20"
OTHER = "2026-12-03"
RETURN = "2027-01-04"
EXACT_LINK = "https://example.test/fecha-exacta"
OTHER_LINK = "https://example.test/otro-dia"
RETURN_LINK = "https://example.test/regreso"


def _offer(flight_date, price, link, direct=True):
    return {
        "provider_id": "google_flights",
        "provider_name": "Google Flights",
        "flight_date": flight_date,
        "price": float(price),
        "currency": "COP",
        "is_direct": direct,
        "stops_count": 0 if direct else 1,
        "layover_info": "Directo (sin escalas)" if direct else "1 escala en MAD",
        "airline": "Iberia",
        "departure_time": "08:00",
        "arrival_time": "09:10",
        "duration": "1h 10m",
        "deep_link": link,
    }


def _month(flight_date, price, link):
    return {
        "flight_date": flight_date,
        "day_number": int(flight_date[-2:]),
        "weekday_name": "Lun",
        "price": float(price),
        "currency": "COP",
        "is_direct": True,
        "stops_count": 0,
        "layover_info": "Directo (sin escalas)",
        "provider_id": "google_flights",
        "provider_name": "Google Flights",
        "airline": "Vueling",
        "deep_link": link,
    }


class ExactDateAlertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "alertas.db")
        init_db(self.db)
        self.user = create_user("ana", "ana@example.com", "clave-larga-1", db_path=self.db)
        self.search = create_search(
            user_id=self.user["id"],
            origin_input="Bogotá, Colombia (BOG)",
            origin_iata="BOG",
            origin_label="Bogotá, Colombia (BOG)",
            destination_input="Madrid, España (MAD)",
            destination_iata="MAD",
            destination_label="Madrid, España (MAD)",
            travel_date=EXACT,
            travel_month="2026-12",
            stop_filter="direct",
            target_price=None,
            notify_email="ana@example.com",
            tracking_days=40,
            db_path=self.db,
        )
        self.sid = self.search["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _set_baseline(self, price, flight_date=EXACT, link=EXACT_LINK, target=None):
        conn = get_connection(self.db)
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE searches
                    SET best_price = ?, best_flight_date = ?, best_url = ?,
                        best_provider = ?, target_price = ?
                    WHERE id = ?
                    """,
                    (price, flight_date, link, "Google Flights", target, self.sid),
                )
        finally:
            conn.close()

    def _run(self, date_offers, monthly, force_alert=False):
        with mock.patch.object(scheduler_task, "search_flights_for_date", return_value=list(date_offers)) as search, \
             mock.patch.object(scheduler_task, "generate_monthly_calendar_offers", return_value=list(monthly)) as month, \
             mock.patch.object(notifier, "deliver_email", return_value=True) as mail:
            result = scheduler_task.run_check_for_search(
                self.sid, force_alert=force_alert, db_path=self.db,
            )
        return result, search, month, mail

    def _row(self):
        conn = get_connection(self.db)
        try:
            return dict(conn.execute("SELECT * FROM searches WHERE id = ?", (self.sid,)).fetchone())
        finally:
            conn.close()

    def _alerts(self):
        conn = get_connection(self.db)
        try:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM alerts WHERE search_id = ? ORDER BY id", (self.sid,)
            )]
        finally:
            conn.close()

    def _offer_dates(self):
        conn = get_connection(self.db)
        try:
            return [r[0] for r in conn.execute(
                "SELECT flight_date FROM offers WHERE search_id = ? ORDER BY price", (self.sid,)
            )]
        finally:
            conn.close()

    def test_cheaper_month_does_not_trigger_or_replace_exact_baseline(self):
        self._set_baseline(500_000)
        monthly = [
            _month(EXACT, 500_000, EXACT_LINK),
            _month(OTHER, 90_000, OTHER_LINK),
        ]
        result, search, month, mail = self._run(
            [_offer(EXACT, 500_000, EXACT_LINK)], monthly,
        )
        self.assertIsNone(result["alert_created"])
        self.assertEqual(result["best_overall"]["price"], 500_000)
        self.assertEqual(result["best_overall"]["flight_date"], EXACT)
        mail.assert_not_called()
        self.assertEqual(self._alerts(), [])
        row = self._row()
        self.assertEqual(row["best_price"], 500_000)
        self.assertEqual(row["best_flight_date"], EXACT)
        self.assertEqual(row["best_url"], EXACT_LINK)
        self.assertNotIn(OTHER_LINK, row["best_url"])
        self.assertEqual(self._offer_dates(), [EXACT])
        shown = get_user_searches(self.user["id"], db_path=self.db)[0]
        self.assertEqual(shown["cheapest_month_day"]["flight_date"], OTHER)
        self.assertEqual(shown["cheapest_month_day"]["price"], 90_000)
        self.assertEqual(shown["cheapest_month_day"]["deep_link"], OTHER_LINK)
        self.assertEqual(search.call_args.kwargs["flight_date"], EXACT)
        self.assertEqual(search.call_args.kwargs["stop_filter"], "direct")
        self.assertEqual(search.call_args.kwargs["origin_input"], "Bogotá, Colombia (BOG)")
        self.assertEqual(search.call_args.kwargs["destination_input"], "Madrid, España (MAD)")
        self.assertEqual(month.call_args.kwargs["travel_month"], "2026-12")

    def test_first_exact_price_alerts_even_if_month_is_cheaper(self):
        result, _search, _calendar, mail = self._run(
            [_offer(EXACT, 500_000, EXACT_LINK)],
            [_month(OTHER, 90_000, OTHER_LINK)],
        )
        self.assertIsNotNone(result["alert_created"])
        mail.assert_called_once()
        _args, kwargs = mail.call_args
        blob = kwargs["plain_text"] + kwargs["html_body"] + kwargs["subject"]
        self.assertIn("20-12-2026", blob)
        self.assertIn("BOG", blob)
        self.assertIn("MAD", blob)
        self.assertNotIn("03-12-2026", blob)
        self.assertNotIn(OTHER_LINK, blob)
        self.assertNotIn("90.000", blob)
        self.assertIn(EXACT_LINK, blob)
        alert = self._alerts()[0]
        self.assertEqual(alert["price"], 500_000)
        self.assertEqual(alert["flight_date"], EXACT)
        self.assertEqual(alert["deep_link"], EXACT_LINK)
        self.assertIsNone(alert["previous_best"])
        self.assertEqual(self._row()["best_price"], 500_000)

    def test_exact_date_drop_alerts_with_exact_offer_only(self):
        self._set_baseline(500_000)
        result, _search, _calendar, mail = self._run(
            [_offer(EXACT, 400_000, EXACT_LINK)],
            [_month(OTHER, 90_000, OTHER_LINK), _month(EXACT, 400_000, EXACT_LINK)],
        )
        self.assertEqual(result["alert_created"]["price"], 400_000)
        self.assertEqual(result["alert_created"]["previous_best"], 500_000)
        self.assertEqual(result["alert_created"]["flight_date"], EXACT)
        self.assertEqual(result["alert_created"]["deep_link"], EXACT_LINK)
        mail.assert_called_once()
        blob = mail.call_args.kwargs["plain_text"] + mail.call_args.kwargs["html_body"]
        self.assertIn("20-12-2026", blob)
        self.assertIn("400.000", blob)
        self.assertNotIn("03-12-2026", blob)
        self.assertNotIn(OTHER_LINK, blob)
        self.assertNotIn("90.000", blob)
        row = self._row()
        self.assertEqual(row["best_price"], 400_000)
        self.assertEqual(row["best_url"], EXACT_LINK)
        self.assertEqual(row["best_flight_date"], EXACT)

    def test_small_exact_change_does_not_alert_when_month_is_cheaper(self):
        self._set_baseline(500_000)
        result, _search, _calendar, mail = self._run(
            [_offer(EXACT, 495_000, EXACT_LINK)],
            [_month(OTHER, 90_000, OTHER_LINK)],
        )
        self.assertIsNone(result["alert_created"])
        mail.assert_not_called()
        self.assertEqual(self._alerts(), [])
        self.assertEqual(self._row()["best_price"], 495_000)
        self.assertNotEqual(self._row()["best_price"], 90_000)

    def test_target_cross_uses_exact_date_not_month(self):
        self._set_baseline(451_000, target=450_000)
        result, _search, _calendar, mail = self._run(
            [_offer(EXACT, 449_500, EXACT_LINK)],
            [_month(OTHER, 90_000, OTHER_LINK)],
        )
        mail.assert_called_once()
        self.assertEqual(result["alert_created"]["price"], 449_500)
        self.assertEqual(result["alert_created"]["previous_best"], 451_000)
        self.assertEqual(result["alert_created"]["flight_date"], EXACT)
        self.assertEqual(self._row()["best_price"], 449_500)

    def test_missing_exact_offer_does_not_fall_back_to_monthly_fare(self):
        self._set_baseline(500_000)
        result, _search, _calendar, mail = self._run(
            [],
            [_month(OTHER, 90_000, OTHER_LINK), _month(EXACT, 80_000, "https://example.test/mes-mismo-dia")],
            force_alert=True,
        )
        self.assertIsNone(result["best_overall"])
        self.assertIsNone(result["alert_created"])
        mail.assert_not_called()
        self.assertEqual(self._alerts(), [])
        row = self._row()
        self.assertEqual(row["best_price"], 500_000)
        self.assertEqual(row["best_flight_date"], EXACT)
        self.assertEqual(row["best_url"], EXACT_LINK)
        self.assertEqual(self._offer_dates(), [])
        shown = get_user_searches(self.user["id"], db_path=self.db)[0]
        self.assertEqual(shown["cheapest_month_day"]["price"], 80_000)
        self.assertEqual(shown["best_price"], 500_000)

    def test_missing_exact_offer_without_baseline_stays_empty(self):
        result, _search, _calendar, mail = self._run(
            [],
            [_month(OTHER, 90_000, OTHER_LINK)],
            force_alert=True,
        )
        self.assertIsNone(result["best_overall"])
        self.assertIsNone(result["alert_created"])
        mail.assert_not_called()
        row = self._row()
        self.assertIsNone(row["best_price"])
        self.assertIsNone(row["best_url"])
        self.assertIsNone(row["best_flight_date"])
        shown = get_user_searches(self.user["id"], db_path=self.db)[0]
        self.assertEqual(shown["cheapest_month_day"]["flight_date"], OTHER)

    def test_off_date_offer_mixed_into_date_results_is_ignored(self):
        result, _search, _calendar, mail = self._run(
            [
                _offer(OTHER, 90_000, OTHER_LINK),
                _offer(EXACT, 500_000, EXACT_LINK),
            ],
            [_month(OTHER, 70_000, OTHER_LINK)],
        )
        mail.assert_called_once()
        self.assertEqual(result["alert_created"]["price"], 500_000)
        self.assertEqual(result["alert_created"]["flight_date"], EXACT)
        self.assertEqual(result["alert_created"]["deep_link"], EXACT_LINK)
        self.assertNotIn(OTHER_LINK, mail.call_args.kwargs["plain_text"])
        self.assertEqual(self._offer_dates(), [EXACT])
        self.assertEqual(self._row()["best_price"], 500_000)
        self.assertEqual(self._row()["best_url"], EXACT_LINK)

    def test_force_alert_still_uses_exact_date(self):
        self._set_baseline(500_000)
        result, _search, _calendar, mail = self._run(
            [_offer(EXACT, 500_000, EXACT_LINK)],
            [_month(OTHER, 90_000, OTHER_LINK)],
            force_alert=True,
        )
        mail.assert_called_once()
        self.assertEqual(result["alert_created"]["price"], 500_000)
        self.assertEqual(result["alert_created"]["flight_date"], EXACT)
        self.assertEqual(result["alert_created"]["deep_link"], EXACT_LINK)

    def test_return_date_counts_when_present_and_other_dates_do_not(self):
        row = dict(self.search)
        row["return_date"] = RETURN
        self.assertEqual(tracked_flight_dates(row), {EXACT, RETURN})
        self.assertTrue(offer_matches_tracked_date(_offer(RETURN, 300_000, RETURN_LINK), row))
        self.assertTrue(offer_matches_tracked_date(_offer(EXACT, 500_000, EXACT_LINK), row))
        self.assertFalse(offer_matches_tracked_date(_offer(OTHER, 90_000, OTHER_LINK), row))
        self.assertNotIn("return_date", self.search)

        with mock.patch.object(notifier, "deliver_email", return_value=True) as mail:
            accepted = notifier.notify_lowest_price(
                row, _offer(RETURN, 300_000, RETURN_LINK), previous_best=400_000,
                db_path=self.db, send_email=True,
            )
            rejected = notifier.notify_lowest_price(
                row, _offer(OTHER, 90_000, OTHER_LINK), previous_best=400_000,
                db_path=self.db, send_email=True,
            )
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["flight_date"], RETURN)
        self.assertEqual(accepted["deep_link"], RETURN_LINK)
        self.assertEqual(accepted["price"], 300_000)
        self.assertIsNone(rejected)
        self.assertEqual(mail.call_count, 1)
        blob = mail.call_args.kwargs["plain_text"] + mail.call_args.kwargs["html_body"]
        self.assertIn("04-01-2027", blob)
        self.assertIn(RETURN_LINK, blob)
        self.assertNotIn(OTHER_LINK, blob)
        self.assertNotIn("03-12-2026", blob)
        stored = self._alerts()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["flight_date"], RETURN)


if __name__ == "__main__":
    unittest.main()
