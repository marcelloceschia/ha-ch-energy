"""Offline year-change regressions; no Home Assistant installation required."""
import importlib.util
from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tariffs", ROOT / "custom_components/sec_energy/tariffs.py")
tariffs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tariffs)


def tariff(year, price=20):
    return {"tariffName": "Standard", "tariffType": "electricity", "tariffForm": "constant",
            "startDate": f"{year}-01-01", "endDate": f"{year}-12-31",
            "prices": {"energy": [{"price": price, "months": [], "weekdays": [], "from": "00:00", "to": "00:00"}]}}


class SelectionTests(unittest.TestCase):
    def test_two_year_document_selects_today_inclusively(self):
        document = {"tariffs": [tariff(2026), tariff(2027, 30)]}
        for day, year in [(date(2026, 12, 31), 2026), (date(2027, 1, 1), 2027)]:
            self.assertEqual(tariffs.select_tariff(document, "Standard", day), tariff(year, 30 if year == 2027 else 20))
        self.assertIsNone(tariffs.select_tariff(document, "Standard", date(2028, 1, 1)))


class ResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_grace_source_beats_future_only_document(self):
        async def fetch(url):
            if '2026' in url:
                raise OSError('404')
            return {'tariffs':[tariff(2027) if '2027' in url else tariff(2026)]}
        url, _ = await tariffs.resolve_document('https://test/{year}.json', date(2026,10,31), fetch, lambda d: [], 'Standard')
        self.assertEqual(url, 'https://test/2025.json')

    async def test_template_404_switches_to_next_year_only_in_q4(self):
        calls = []
        async def fetch(url):
            calls.append(url)
            if '2027' not in url:
                raise OSError('404')
            return {"tariffs": [tariff(2027)]}
        result = await tariffs.resolve_document('https://test/{year}.json', date(2026, 10, 1), fetch, lambda d: [], 'Standard')
        self.assertEqual(result[0], 'https://test/2027.json')
        self.assertEqual(calls, ['https://test/2026.json', 'https://test/2027.json', 'https://test/2025.json'])
        with self.assertRaises(ValueError):
            await tariffs.resolve_document('https://test/{year}.json', date(2026, 9, 30), fetch, lambda d: [], 'Standard')


class CatalogueTests(unittest.TestCase):
    def test_hybrid_sources_and_migration_identity(self):
        day = date(2026, 10, 31)
        self.assertEqual(tariffs.source_candidates({2025: 'old', 2026: 'now', 2027: 'next'}, day), ['now', 'next', 'old'])
        self.assertEqual(tariffs.source_candidates('fixed', day), ['fixed'])
        self.assertEqual(tariffs.match_dso('https://test/2026.json', {'DSO': 'https://test/{year}.json'}), 'DSO')
        self.assertFalse(tariffs.covers({'endDate': 'invalid'}, day))
        self.assertTrue(tariffs.covers({}, day))


if __name__ == "__main__":
    unittest.main()
