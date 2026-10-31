"""Exercise real coordinator/migration/sensor code with small HA boundary doubles."""
import ast
import asyncio
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from test_year_change import tariffs, tariff
from test_validate_schema import validate_schema

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/sec_energy'


class Coordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass
        self.data = None


def load_code():
    namespace = dict(DataUpdateCoordinator=Coordinator, timedelta=timedelta,
                     _LOGGER=logging.getLogger('test'), DOMAIN='sec_energy', DEFAULT_SCAN_INTERVAL=86400,
                     PREDEFINED_DSOS={'Test DSO': 'https://test/{year}.json'},
                     dt_util=SimpleNamespace(now=lambda: datetime(2026, 12, 31, 12)),
                     ir=SimpleNamespace(async_create_issue=Mock(), async_delete_issue=Mock(),
                                        IssueSeverity=SimpleNamespace(WARNING='warning')),
                     Store=Mock(return_value=SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())),
                     validate_schema=validate_schema, json=json, aiohttp=SimpleNamespace(ClientError=ConnectionError),
                     ConfigEntry=object, HomeAssistant=object)
    namespace.update({name: getattr(tariffs, name) for name in ['select_tariff', 'covers', 'resolve_document', 'match_dso']})
    price_tree = ast.parse((ROOT / 'sensor.py').read_text())
    price_nodes = [n for n in price_tree.body if isinstance(n, (ast.FunctionDef, ast.Assign)) and
                   (isinstance(n, ast.FunctionDef) and n.name in ('get_current_price', 'time_in_range') or
                    isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('WEEKDAY_MAP', 'MONTH_MAP') for t in n.targets))]
    exec(compile(ast.Module(body=price_nodes, type_ignores=[]), str(ROOT / 'sensor.py'), 'exec'), namespace)
    tree = ast.parse((ROOT / '__init__.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) or
             isinstance(n, ast.AsyncFunctionDef) and n.name == 'async_migrate_entry']
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / '__init__.py'), 'exec'), namespace)
    return namespace


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = load_code()
        self.entry = SimpleNamespace(entry_id='test', version=1, data={
            'dso_url': 'https://test/2026.json', 'dso_key': 'Test DSO', 'tariff': 'Standard'})
        def update(entry, **kwargs):
            for key, value in kwargs.items():
                setattr(entry, key, value)
        self.hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock(side_effect=update)))
        self.coordinator = self.ns['SECEnergyCoordinator'](self.hass, self.entry)
        self.coordinator._fetch_document = AsyncMock(return_value={
            'dsoName': 'Test', 'dsoNumber': 1, 'tariffs': [tariff(2026)]})

    async def test_cached_new_year_price_is_used_even_when_offline(self):
        self.coordinator._fetch_document.return_value['tariffs'].append(tariff(2027, 30))
        await self.coordinator._async_update_data()
        self.ns['dt_util'].now = lambda: datetime(2027, 1, 1, 12)
        self.coordinator._fetch_document.side_effect = OSError('offline')
        after = await self.coordinator._async_update_data()
        self.assertEqual(after['last_price'], 30)
        self.assertTrue(after['data_expired'])  # source health remains visible

    async def test_expiry_keeps_last_price_and_creates_repair(self):
        before = await self.coordinator._async_update_data()
        self.ns['dt_util'].now = lambda: datetime(2027, 1, 1, 12)
        after = await self.coordinator._async_update_data()
        self.assertEqual(after['tariff'], before['tariff'])
        self.assertTrue(after['data_expired'])
        self.assertEqual(after['valid_until'], '2026-12-31')
        self.ns['ir'].async_create_issue.assert_called()

    async def test_all_urls_dead_uses_persistent_cache_without_reset(self):
        before = await self.coordinator._async_update_data()
        self.coordinator._fetch_document.side_effect = OSError('offline')
        after = await self.coordinator._async_update_data()
        self.assertEqual(after['tariff'], before['tariff'])
        self.assertTrue(after['data_expired'])
        self.coordinator._store.async_save.assert_awaited()
        # A new coordinator must also recover through the on-disk store.
        self.ns['Store'].return_value.async_load.return_value = self.coordinator._store.async_save.call_args.args[0]
        restarted = self.ns['SECEnergyCoordinator'](self.hass, self.entry)
        restarted._fetch_document = AsyncMock(side_effect=OSError('offline'))
        self.assertEqual((await restarted._async_update_data())['tariff'], before['tariff'])

    async def test_q4_future_url_updates_entry_but_not_current_price(self):
        before = await self.coordinator._async_update_data()
        self.ns['dt_util'].now = lambda: datetime(2026, 10, 31, 12)
        async def fetch(url):
            if '2026' in url:
                raise OSError('404')
            return {'dsoName': 'Test', 'dsoNumber': 1, 'tariffs': [tariff(2027, 30)]}
        self.coordinator._fetch_document = fetch
        after = await self.coordinator._async_update_data()
        self.assertEqual(self.entry.data['resolved_url'], 'https://test/2027.json')
        self.assertEqual(after['tariff'], before['tariff'])
        self.ns['dt_util'].now = lambda: datetime(2027, 1, 1, 12)
        after = await self.coordinator._async_update_data()
        self.assertEqual(after['tariff']['prices']['energy'][0]['price'], 30)
        self.assertFalse(after['data_expired'])
        self.ns['ir'].async_delete_issue.assert_called()

    async def test_no_dates_remains_valid(self):
        item = tariff(2026)
        del item['startDate'], item['endDate']
        self.coordinator._fetch_document.return_value['tariffs'] = [item]
        self.assertFalse((await self.coordinator._async_update_data())['data_expired'])

    async def test_migration_keeps_key_and_reads_updated_catalogue(self):
        await self.ns['async_migrate_entry'](self.hass, self.entry)
        self.assertEqual(self.entry.version, 2)
        self.assertEqual(self.entry.data['dso_key'], 'Test DSO')
        self.ns['PREDEFINED_DSOS']['Test DSO'] = {2026: 'https://new/2026.json'}
        await self.coordinator._async_update_data()
        self.coordinator._fetch_document.assert_awaited_with('https://new/2026.json')


if __name__ == '__main__':
    unittest.main()
