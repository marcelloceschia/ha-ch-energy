"""Runtime coverage of the unmodified official Muhen fixture (offline)."""
import copy
from datetime import date
import json
import unittest

from test_validate_schema import FIXTURES, validate_schema
from test_year_change import tariffs
from test_muhen import MUHEN_URL


class MuhenRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = json.loads((FIXTURES / 'muhen_2026.json').read_text())

    async def fetch(self, url):
        return self.document

    async def test_real_boundaries_cover_and_resolve_inclusive_calendar_dates(self):
        self.assertEqual(validate_schema(self.document), [])
        original = copy.deepcopy(self.document)
        for day in (date(2026, 1, 1), date(2026, 6, 15),
                    date(2026, 11, 1), date(2026, 12, 31)):
            with self.subTest(day=day):
                for entry in self.document['tariffs']:
                    self.assertTrue(tariffs.covers(entry, day))
                    self.assertEqual(tariffs.select_tariff(
                        self.document, entry['tariffName'], day), entry)
                    self.assertEqual(await tariffs.resolve_document(
                        {2026: MUHEN_URL}, day, self.fetch, validate_schema,
                        entry['tariffName']), (MUHEN_URL, self.document))
        self.assertEqual(self.document, original)

    async def test_outside_year_is_not_current(self):
        for day in (date(2025, 12, 31), date(2027, 1, 1)):
            for entry in self.document['tariffs']:
                self.assertFalse(tariffs.covers(entry, day))
                self.assertIsNone(tariffs.select_tariff(self.document, entry['tariffName'], day))
        with self.assertRaises(ValueError):
            await tariffs.resolve_document({2026: MUHEN_URL}, date(2027, 1, 1),
                                          self.fetch, validate_schema)
        # Q4 may prefetch next year's document, but must never select it today.
        self.assertEqual(await tariffs.resolve_document(
            {2026: MUHEN_URL}, date(2025, 12, 31), self.fetch, validate_schema),
            (MUHEN_URL, self.document))
        with self.assertRaises(ValueError):
            await tariffs.resolve_document({2026: MUHEN_URL}, date(2025, 9, 30),
                                          self.fetch, validate_schema)

    async def test_malformed_boundaries_cannot_resolve_or_select(self):
        for boundary in ('startDate', 'endDate'):
            for value in ('invalid', '2026-02-30T00:00:00',
                          '2026-01-01T00:00:00junk', '2026-01-01T25:00:00',
                          '2026-01-01T00:00:00\n', '2026-01-01T00:00:00Z',
                          '2026-01-01T12:00:00', 20260101, True):
                with self.subTest(boundary=boundary, value=value):
                    document = copy.deepcopy(self.document)
                    for entry in document['tariffs']:
                        entry[boundary] = value
                        self.assertFalse(tariffs.covers(entry, date(2026, 11, 1)))
                        self.assertIsNone(tariffs.select_tariff(
                            document, entry['tariffName'], date(2026, 11, 1)))
                    async def fetch(url):
                        return document
                    with self.assertRaises(ValueError):
                        await tariffs.resolve_document({2026: MUHEN_URL}, date(2026, 11, 1),
                                                      fetch, validate_schema)

    async def test_week_date_timestamps_rejected_on_both_boundaries(self):
        for boundary, value in (
            ('startDate', '2026-W01-1T00:00:00'),
            ('endDate', '2026-W53-7T00:00:00'),
        ):
            with self.subTest(boundary=boundary):
                document = copy.deepcopy(self.document)
                for entry in document['tariffs']:
                    entry[boundary] = value
                day = date(2026, 11, 1)
                for entry in document['tariffs']:
                    self.assertFalse(tariffs.covers(entry, day))
                    self.assertIsNone(tariffs.select_tariff(
                        document, entry['tariffName'], day))
                async def fetch(url):
                    return document
                with self.assertRaises(ValueError):
                    await tariffs.resolve_document(
                        {2026: MUHEN_URL}, day, fetch, validate_schema)

    def test_merged_main_boundary_forms_preserved(self):
        for boundary in ('startDate', 'endDate'):
            for value in ('2026-06-15', '20260615', '2026-W25-1',
                          '2026-06-15T00:00:00', '2026-06-15T00:00:00.000000',
                          None, ''):
                with self.subTest(boundary=boundary, value=value):
                    self.assertTrue(tariffs.covers({boundary: value}, date(2026, 6, 15)))
            for value in (False, 0, '２０２６-06-15T00:00:00'):
                with self.subTest(boundary=boundary, invalid=value):
                    self.assertFalse(tariffs.covers({boundary: value}, date(2026, 6, 15)))

    async def test_schema_and_selected_name_still_enforced(self):
        for validate, name in ((lambda doc: ['invalid'], None),
                               (validate_schema, 'not a Muhen tariff')):
            with self.assertRaises(ValueError):
                await tariffs.resolve_document({2026: MUHEN_URL}, date(2026, 11, 1),
                                              self.fetch, validate, name)


if __name__ == '__main__':
    unittest.main()
