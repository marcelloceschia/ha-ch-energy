"""Config flow uses the same Jahres-Map resolver as runtime."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from test_year_change import tariffs, tariff
from test_validate_schema import validate_schema


class Flow:
    def __init__(self):
        self.context = {}
    def async_create_entry(self, **kwargs):
        return kwargs
    def async_show_form(self, **kwargs):
        return kwargs
    def async_abort(self, **kwargs):
        return {'abort': kwargs}


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'custom_components/sec_energy/config_flow.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SECEnergyConfigFlow')
        cls.decorator_list = []
        cls.bases = [ast.Name(id='Flow', ctx=ast.Load())]
        cls.keywords = []
        identity = lambda value, **kwargs: value
        vol = SimpleNamespace(Schema=identity, Required=identity, Optional=identity, In=identity,
                              All=lambda *args: None, Coerce=identity, Range=lambda **kwargs: None)
        self.ns = dict(Flow=Flow, callback=identity, vol=vol, validate_schema=validate_schema,
                       PREDEFINED_DSOS={'DSO': {2026: 'https://test/2026.json'}},
                       dt_util=SimpleNamespace(now=lambda: datetime(2026, 10, 31)),
                       resolve_document=tariffs.resolve_document, covers=tariffs.covers,
                       select_tariff=tariffs.select_tariff,
                       fetch_document=AsyncMock(return_value={'dsoName':'DSO', 'dsoNumber':1, 'tariffs':[tariff(2026)]}),
                       _LOGGER=SimpleNamespace(debug=lambda *args: None, warning=lambda *args: None, error=lambda *args, **kwargs: None),
                       json=__import__('json'), aiohttp=SimpleNamespace(ClientError=OSError))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'available_dsos'), cls], type_ignores=[])), str(path), 'exec'), self.ns)
        self.flow = self.ns['SECEnergyConfigFlow']()

    async def test_dropdown_changes_at_local_new_year_and_rejects_stale_selection(self):
        self.ns['PREDEFINED_DSOS']['Future'] = {2027: 'https://test/2027.json'}
        result = await self.flow.async_step_user()
        self.assertEqual(next(iter(result['data_schema'].values())), ['DSO'])
        self.assertEqual(await self.flow.async_step_user({'dso': 'Future'}),
                         {'abort': {'reason': 'no_tariffs'}})
        self.ns['dt_util'].now = lambda: datetime(2027, 1, 1)
        result = await self.flow.async_step_user()
        self.assertEqual(next(iter(result['data_schema'].values())), ['Future'])

    async def test_new_entry_persists_key_and_resolved_string_not_year_map(self):
        await self.flow.async_step_user({'dso': 'DSO'})
        result = await self.flow.async_step_tariff({'tariff': 'Standard'})
        self.assertEqual(self.flow.VERSION, 2)
        self.assertEqual(result['data']['dso_key'], 'DSO')
        self.assertEqual(result['data']['resolved_url'], 'https://test/2026.json')
        self.assertEqual(result['data']['valid_until'], '2026-12-31')
        self.assertIsInstance(result['data']['dso_url'], str)


if __name__ == '__main__':
    unittest.main()
