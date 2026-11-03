"""Pruebas de los sitios y filtros que se conservan. Ejecutar: python -m pytest tests"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VUELOS_SECRET_KEY", "x" * 64)
os.environ.setdefault("VUELOS_INVITE_CODE", "codigo-de-prueba-123")
os.environ.setdefault("VUELOS_ADMIN_PASS", "clave-de-prueba-123")

from providers.flight_engine import PORTALS, build_deep_link  # noqa: E402

D = "2026-11-24"


def test_removed_portals_are_gone():
    ids = {p["id"] for p in PORTALS}
    assert "rappitravel" not in ids and "kiwi" not in ids
    assert {"google_flights", "kayak", "skyscanner", "booking"} <= ids


def test_working_search_links_prefill_route():
    assert build_deep_link("kayak", "BOG", "CLO", D) == "https://www.kayak.com.co/flights/BOG-CLO/2026-11-24?sort=price_a"
    assert "/bog/clo/261124/" in build_deep_link("skyscanner", "BOG", "CLO", D)
    b = build_deep_link("booking", "BOG", "CLO", D)
    assert "booking.com/flights" in b and "from=BOG" in b and "to=CLO" in b and "depart=2026-11-24" in b


def test_airlines_and_removed_ids_fall_back_to_google():
    for pid in ["avianca", "latam", "jetsmart", "wingo", "rappitravel", "kiwi"]:
        assert build_deep_link(pid, "BOG", "CLO", D).startswith("https://www.google.com/travel/flights?tfs=")
