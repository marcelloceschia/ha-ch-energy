"""Sensor diagnostic and last-known-price behavior without HA imports."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'custom_components/sec_energy/sensor.py'


class SensorTests(unittest.TestCase):
    def test_tariff_boundaries_preserve_zurich_timezone(self):
        from datetime import timedelta, timezone
        from zoneinfo import ZoneInfo
        from test_year_coordinator import load_code
        ns = load_code()
        ns['datetime'] = datetime
        tree = ast.parse(PATH.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'get_next_tariff_change')
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(PATH), 'exec'), ns)
        tz = ZoneInfo('Europe/Zurich')
        item = {'prices': {'energy': [
            {'months': ['Jan', 'Jul', 'Mar', 'Oct'],
             'weekdays': ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
             'from': '00:00', 'to': '18:00'}]}}
        for month, offset in [(1, 1), (7, 2)]:
            for hour in (17, 23):
                with self.subTest(month=month, hour=hour):
                    now = datetime(2026, month, 15, hour, tzinfo=tz)
                    expected = (now.replace(hour=18) if hour == 17 else
                                (now + timedelta(days=1)).replace(hour=0))
                    actual = ns['get_next_tariff_change'](item, now)
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual.utcoffset(), timedelta(hours=offset))
                    self.assertEqual(actual.astimezone(timezone.utc), expected.astimezone(timezone.utc))
        # Midnight across DST transitions uses the destination day's local offset.
        for month, day, offset in [(3, 29, 2), (10, 25, 1)]:
            now = datetime(2026, month, day, 23, tzinfo=tz)
            actual = ns['get_next_tariff_change'](item, now)
            self.assertEqual(actual, (now + timedelta(days=1)).replace(hour=0))
            self.assertEqual(actual.utcoffset(), timedelta(hours=offset))

    def test_midnight_does_not_use_expired_tariff_between_fetches(self):
        from test_year_change import tariffs, tariff
        tree = ast.parse(PATH.read_text())
        ns = {'datetime': datetime, 'get_current_price': lambda t, dt: t['prices']['energy'][0]['price'],
              'covers': tariffs.covers, 'select_tariff': tariffs.select_tariff}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'coordinator_price']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PATH), 'exec'), ns)
        coordinator = SimpleNamespace(data={'tariff':tariff(2026), 'last_price':20, 'data_expired':False,
                                           'raw':{'tariffs':[tariff(2026), tariff(2027,30)]}})
        self.assertEqual(ns['coordinator_price'](coordinator, datetime(2027,1,1)),30)
        coordinator.data['raw'] = {}
        self.assertEqual(ns['coordinator_price'](coordinator, datetime(2027,1,1)),20)

    def test_forecast_price_does_not_overwrite_last_current_price(self):
        tree = ast.parse(PATH.read_text())
        ns = {'datetime': datetime, 'get_current_price': lambda t, dt: 30,
              'covers': lambda t, day: True, 'select_tariff': lambda doc, name, day: None}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'coordinator_price']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PATH), 'exec'), ns)
        coordinator = SimpleNamespace(data={'tariff': {'tariffName':'Standard'}, 'last_price':20, 'data_expired':False})
        self.assertEqual(ns['coordinator_price'](coordinator, datetime(2027, 1, 1)), 30)
        self.assertEqual(coordinator.data['last_price'], 20)

    def test_expired_price_is_frozen_and_diagnostics_are_visible(self):
        tree = ast.parse(PATH.read_text())
        ns = {'datetime': datetime}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('coordinator_price', 'tariff_attributes')]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PATH), 'exec'), ns)
        coordinator = SimpleNamespace(data={'tariff': {}, 'last_price': 20, 'data_expired': True,
                                           'valid_from': '2026-01-01', 'valid_until': '2026-12-31',
                                           'resolved_url': 'https://new', 'tariff_url': 'https://old'})
        self.assertEqual(ns['coordinator_price'](coordinator, datetime(2027, 1, 1)), 20)
        self.assertEqual(ns['tariff_attributes'](coordinator)['valid_until'], '2026-12-31')
        self.assertTrue(ns['tariff_attributes'](coordinator)['data_expired'])

    def test_diagnostics_mark_calendar_expiry_before_next_refresh(self):
        from test_year_change import tariffs, tariff
        tree = ast.parse(PATH.read_text())
        ns = {'dt_util':SimpleNamespace(now=lambda:datetime(2027,1,1)), 'covers':tariffs.covers,
              'select_tariff':tariffs.select_tariff}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'tariff_attributes']
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PATH), 'exec'), ns)
        c = SimpleNamespace(data={'tariff':tariff(2026), 'data_expired':False})
        self.assertTrue(ns['tariff_attributes'](c)['data_expired'])


if __name__ == '__main__':
    unittest.main()
