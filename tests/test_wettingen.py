"""Combined-year official Wettingen document: deterministic, offline regression."""
import ast
from collections import Counter
from copy import deepcopy
from datetime import date
import json
import unittest

from test_validate_schema import FIXTURES, validate_schema
from test_year_change import ROOT, tariffs

URL = 'https://www.energiewettingen.ch/upload/rm/20/26/20260824-enw-2027-tariffs-1.json'


class WettingenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = json.loads((FIXTURES / 'wettingen_2026_2027.json').read_text())

    async def fetch(self, url):
        if url != URL:
            raise OSError('No fixture for guessed URL')
        return self.document

    def test_catalogue_preserves_shared_source_for_both_years(self):
        tree = ast.parse((ROOT / 'custom_components/sec_energy/config_flow.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'PREDEFINED_DSOS' for t in n.targets))
        self.assertEqual(ast.literal_eval(node.value)['Energie Wettingen AG'],
                         {2026: URL, 2027: URL})
        self.assertEqual(validate_schema(self.document), [])
        self.assertEqual(Counter(t['startDate'][:4] for t in self.document['tariffs']),
                         {'2026': 10, '2027': 10})

    async def test_all_twenty_tariffs_resolve_only_in_their_calendar_year(self):
        for entry in self.document['tariffs']:
            year = int(entry['startDate'][:4])
            for day in (date(year, 1, 1), date(year, 6, 15), date(year, 12, 31)):
                with self.subTest(name=entry['tariffName'], day=day):
                    self.assertTrue(tariffs.covers(entry, day))
                    self.assertEqual(tariffs.select_tariff(
                        self.document, entry['tariffName'], day), entry)
                    self.assertEqual(await tariffs.resolve_document(
                        {2026: URL, 2027: URL}, day, self.fetch, validate_schema,
                        entry['tariffName']), (URL, self.document))
            for day in (date(year - 1, 12, 31), date(year + 1, 1, 1)):
                with self.subTest(name=entry['tariffName'], outside=day):
                    self.assertFalse(tariffs.covers(entry, day))
                    self.assertIsNone(tariffs.select_tariff(
                        self.document, entry['tariffName'], day))
            # Before Q4, a next-year name must not resolve at all.
            with self.assertRaises(ValueError):
                await tariffs.resolve_document(
                    {2026: URL, 2027: URL}, date(year - 1, 9, 30),
                    self.fetch, validate_schema, entry['tariffName'])

    def test_rollover_selects_correct_price_with_same_tariff_name(self):
        # Different prices/order prevent minimum-price or first-entry fallbacks
        # from masquerading as successful date-aware selection.
        entries = []
        for year, price in ((2027, .09), (2026, .31)):
            entry = deepcopy(next(t for t in self.document['tariffs']
                                  if t['startDate'].startswith(str(year))))
            entry['tariffName'] = 'Shared name'
            entry['prices']['energy'][0]['price'] = price
            entries.append(entry)
        document = {'tariffs': entries}
        for day, price in ((date(2026, 12, 31), .31), (date(2027, 1, 1), .09)):
            self.assertEqual(tariffs.select_tariff(document, 'Shared name', day)
                             ['prices']['energy'][0]['price'], price)
        self.assertIsNone(tariffs.select_tariff(document, 'Shared name', date(2028, 1, 1)))


if __name__ == '__main__':
    unittest.main()
