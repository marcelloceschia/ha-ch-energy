"""Official Birwinken feed regression; no network or HA installation required."""
import ast
from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import unittest

from test_year_change import tariffs
from test_year_coordinator import load_code, ROOT
from test_validate_schema import validate_schema

FIXTURE = Path(__file__).parent / 'fixtures/birwinken_2027.json'


class DateTests(unittest.TestCase):
    def test_all_six_midnight_boundaries(self):
        document = json.loads(FIXTURE.read_text())
        self.assertEqual(validate_schema(document), [])
        self.assertEqual(len(document['tariffs']), 6)
        for tariff in document['tariffs']:
            with self.subTest(name=tariff['tariffName']):
                for day in (date(2027, 1, 1), date(2027, 12, 31)):
                    self.assertTrue(tariffs.covers(tariff, day))
                for day in (date(2026, 12, 31), date(2028, 1, 1)):
                    self.assertFalse(tariffs.covers(tariff, day))

    def test_malformed_or_non_midnight_dates_rejected(self):
        for boundary in ('2027-02-30', '2027-01-01T00:00:00junk',
                         '2027-01-01T12:00:00', '2027-01-01T00:00:00.000001',
                         '2027-01-01T00:00:00+01:00', '2027-01-01T00:00:00Z',
                         '2027-01-01garbage', True, False, 123):
            with self.subTest(boundary=boundary):
                self.assertFalse(tariffs.covers({'startDate': boundary}, date(2027, 6, 1)))


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_code()
        tree = ast.parse((ROOT / 'sensor.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'get_next_tariff_change')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<next>', 'exec'), self.ns)

    def test_unrestricted_filters_current_and_next(self):
        now = datetime(2027, 1, 4, 12)  # Monday
        for field in ('months', 'weekdays'):
            for value in ('missing', None, []):
                with self.subTest(field=field, value=value):
                    tier = {'months': ['Jan'], 'weekdays': ['Mo'],
                            'from': '06:00', 'to': '20:00', 'price': .25}
                    if value == 'missing':
                        del tier[field]
                    else:
                        tier[field] = value
                    item = {'prices': {'energy': [tier, {
                        'from': '20:00', 'to': '06:00', 'price': .141}]}}
                    self.assertEqual(self.ns['get_current_price'](item, now), .25)
                    self.assertEqual(self.ns['get_next_tariff_change'](item, now),
                                     now.replace(hour=20))

    def test_explicit_restrictions_still_apply(self):
        item = {'prices': {'energy': [
            {'months': ['Feb'], 'from': '00:00', 'to': '15:00', 'price': .3},
            {'weekdays': ['Tu'], 'from': '00:00', 'to': '16:00', 'price': .2},
            {'from': '00:00', 'to': '20:00', 'price': .1}]}}
        now = datetime(2027, 1, 4, 12)
        self.assertEqual(self.ns['get_current_price'](item, now), .1)
        self.assertEqual(self.ns['get_next_tariff_change'](item, now), now.replace(hour=20))


class FeedCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_six_selected_tariff_sensors_and_future_guard(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock
        document = json.loads(FIXTURE.read_text())
        expected = {'Haushalt (E)': .141, 'Haushalt (N)': .0925,
                    'Industrie NS (E)': .135, 'Industrie NS (N)': .0535,
                    'Baustrom (E)': .149, 'Baustrom (N)': .2335}
        for tariff in document['tariffs']:
            with self.subTest(name=tariff['tariffName']):
                ns = load_code()
                ns['dt_util'].now = lambda: datetime(2026, 11, 1, 12)
                entry = SimpleNamespace(entry_id='birwinken', data={
                    'dso_url': 'https://birwinken.test/2027.json',
                    'tariff': tariff['tariffName']})
                hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock()))
                coordinator = ns['SECEnergyCoordinator'](hass, entry)
                coordinator._fetch_document = AsyncMock(return_value=deepcopy(document))
                tree = ast.parse((ROOT / 'sensor.py').read_text())
                cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                           and n.name == 'SECEnergyPriceSensor')
                getter = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                              and n.name == 'native_value')
                getter.decorator_list = []
                exec(compile(ast.Module(body=[getter], type_ignores=[]), '<sensor>', 'exec'), ns)
                sensor = SimpleNamespace(coordinator=coordinator)
                coordinator.data = await coordinator._async_update_data()
                self.assertIsNone(ns['native_value'](sensor))
                self.assertIsNone(coordinator.data['tariff'])
                self.assertTrue(coordinator.data['data_expired'])
                self.assertEqual(len(coordinator.data['raw']['tariffs']), 6)
                ns['dt_util'].now = lambda: datetime(2027, 1, 4, 12)
                coordinator.data = await coordinator._async_update_data()
                self.assertFalse(coordinator.data['data_expired'])
                self.assertEqual(ns['native_value'](sensor), expected[tariff['tariffName']])
                # Fee fields remain intact, but are not folded into this energy sensor.
                self.assertEqual(coordinator.data['tariff']['prices'], tariff['prices'])
                base_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                                and n.name == 'SECEnergyBasePriceSensor')
                base_getter = next(n for n in base_cls.body if isinstance(n, ast.FunctionDef)
                                   and n.name == 'native_value')
                base_getter.decorator_list = []
                exec(compile(ast.Module(body=[base_getter], type_ignores=[]), '<base>', 'exec'), ns)
                expected_base = 10.5 if tariff['tariffName'] in (
                    'Haushalt (N)', 'Industrie NS (N)') else 0
                self.assertEqual(ns['native_value'](sensor), expected_base)


if __name__ == '__main__':
    unittest.main()
