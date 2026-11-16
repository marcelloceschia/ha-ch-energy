"""Year-local catalogue visibility, independent of Home Assistant."""
import ast
from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'custom_components/sec_energy/config_flow.py').read_text())
CATALOG_NODE = next(
    n for n in TREE.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == 'PREDEFINED_DSOS' for t in n.targets)
)
CATALOG = ast.literal_eval(CATALOG_NODE.value)


def available(sources, day):
    nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'available_dsos']
    ns = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<availability>', 'exec'), ns)
    return ns['available_dsos'](sources, day)


class AvailabilityTests(unittest.TestCase):
    def test_future_only_provider_appears_at_new_year(self):
        sources = {'IBI': {2027: 'https://example/2027.json'},
                   'Current': {2026: 'https://example/2026.json'},
                   'Fixed': 'https://example/data.json', 'Custom / Other': 'custom'}
        self.assertEqual(list(available(sources, date(2026, 12, 31))),
                         ['Current', 'Fixed', 'Custom / Other'])
        self.assertEqual(list(available(sources, date(2027, 1, 1))),
                         ['IBI', 'Fixed', 'Custom / Other'])
        self.assertEqual(sources['IBI'], {2027: 'https://example/2027.json'})

    def test_ibi_remains_future_only_until_2027(self):
        name = 'Industrielle Betriebe Interlaken AG'
        expected = {2027: 'https://www.ibi.ch/media/documents/20260821_tariffs.json'}
        self.assertEqual(CATALOG[name], expected)
        self.assertNotIn(name, available(CATALOG, date(2026, 12, 31)))
        self.assertEqual(available(CATALOG, date(2027, 1, 1))[name], expected)


if __name__ == '__main__':
    unittest.main()
