"""Year-local catalogue visibility, independent of Home Assistant."""
import ast
from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'custom_components/sec_energy/config_flow.py').read_text())


class AvailabilityTests(unittest.TestCase):
    def test_future_only_provider_appears_at_new_year(self):
        nodes = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'available_dsos']
        self.assertTrue(nodes, 'missing current-year catalogue filter')
        ns = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<availability>', 'exec'), ns)
        sources = {'IBI': {2027: 'https://example/2027.json'},
                   'Current': {2026: 'https://example/2026.json'},
                   'Fixed': 'https://example/data.json', 'Custom / Other': 'custom'}
        self.assertEqual(list(ns['available_dsos'](sources, date(2026, 12, 31))),
                         ['Current', 'Fixed', 'Custom / Other'])
        self.assertEqual(list(ns['available_dsos'](sources, date(2027, 1, 1))),
                         ['IBI', 'Fixed', 'Custom / Other'])
        self.assertEqual(sources['IBI'], {2027: 'https://example/2027.json'})


if __name__ == '__main__':
    unittest.main()
