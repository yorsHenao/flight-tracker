"""Ciudades españolas en el mismo catálogo que alimenta la búsqueda y el selector."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.airport_resolver import (  # noqa: E402
    list_all_location_labels,
    list_popular_suggestions,
    resolve_location,
)

EXPECTED = {
    "Valencia": "VLC",
    "Sevilla": "SVQ",
    "Málaga": "AGP",
    "Alicante": "ALC",
    "Bilbao": "BIO",
    "Palma de Mallorca": "PMI",
    "Ibiza": "IBZ",
    "Menorca": "MAH",
    "Tenerife": "TFS",
    "Tenerife Norte": "TFN",
    "Gran Canaria": "LPA",
    "Lanzarote": "ACE",
    "Fuerteventura": "FUE",
}


class SpanishCitiesTest(unittest.TestCase):
    def test_names_iata_and_spanish_labels(self):
        labels = list_all_location_labels()
        for name, code in EXPECTED.items():
            info = resolve_location(name)
            self.assertEqual(info["primary"], code, name)
            self.assertEqual(info["country"], "ES", name)
            self.assertEqual(info["region"], "EU", name)
            self.assertIn(code, info["label"])
            self.assertIn("España", info["label"])
            self.assertEqual(labels.count(info["label"]), 1, info["label"])
            again = resolve_location(info["label"])
            self.assertEqual(again["primary"], code)
            by_code = resolve_location(code)
            self.assertEqual(by_code["primary"], code)
            self.assertIn("España", by_code["label"])

    def test_aliases_and_existing_madrid_barcelona_stay_unique(self):
        self.assertEqual(resolve_location("Malaga")["primary"], "AGP")
        self.assertEqual(resolve_location("Seville")["primary"], "SVQ")
        self.assertEqual(resolve_location("Mallorca")["primary"], "PMI")
        self.assertEqual(resolve_location("Las Palmas")["primary"], "LPA")
        self.assertEqual(resolve_location("Tenerife Sur")["primary"], "TFS")
        self.assertEqual(resolve_location("Tenerife Norte")["primary"], "TFN")
        self.assertNotEqual(resolve_location("Tenerife")["primary"], "TFN")
        self.assertEqual(resolve_location("Madrid")["primary"], "MAD")
        self.assertEqual(resolve_location("Barcelona")["primary"], "BCN")
        self.assertEqual(resolve_location("España")["primary"], "MAD")
        labels = list_all_location_labels()
        self.assertEqual(labels.count("Madrid, España (MAD)"), 1)
        self.assertEqual(labels.count("Barcelona, España (BCN)"), 1)
        self.assertEqual(len(labels), len(set(labels)))

    def test_popular_and_full_list_resolve_for_the_selector(self):
        popular = list_popular_suggestions()
        labels = list_all_location_labels()
        for name in ("Valencia", "Sevilla", "Málaga", "Alicante", "Bilbao",
                     "Palma de Mallorca", "Ibiza", "Menorca", "Tenerife",
                     "Gran Canaria", "Lanzarote", "Fuerteventura"):
            self.assertIn(name, popular)
        resolved = []
        for name in popular:
            info = resolve_location(name)
            self.assertEqual(len(info["primary"]), 3, name)
            self.assertIn(info["label"], labels)
            resolved.append(info["label"])
        self.assertEqual(len(resolved), len(set(resolved)))


if __name__ == "__main__":
    unittest.main()
