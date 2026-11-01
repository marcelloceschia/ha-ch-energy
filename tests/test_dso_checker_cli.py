"""Offline process-level tests: real CLI/exit codes, injected HTTP boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_dso_urls.py'
HARNESS = '''import io, os, runpy, sys, urllib.request, urllib.error
from unittest.mock import patch
class Response(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
def fetch(request, **kwargs):
    mode = os.environ['CHECKER_TEST_RESPONSE']
    if mode == 'network': raise urllib.error.URLError('offline test failure')
    return Response(mode.encode())
with patch.object(urllib.request, 'urlopen', side_effect=fetch):
    runpy.run_path(sys.argv.pop(1), run_name='__main__')
'''


class CheckerCliTests(unittest.TestCase):
    def run_cli(self, mode, sources, response):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'custom_components/sec_energy/config_flow.py'
            config.parent.mkdir(parents=True)
            config.write_text('PREDEFINED_DSOS = ' + repr(sources))
            harness = root / 'harness.py'
            harness.write_text(HARNESS)
            env = dict(os.environ, SEC_ENERGY_REPO=str(root), CHECKER_TEST_RESPONSE=response)
            result = subprocess.run([sys.executable, str(harness), str(SCRIPT), *mode],
                                    env=env, cwd=root, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.stderr, '')
        if '--json' in mode:
            return result, json.loads(result.stdout)
        return result, None

    def test_network_failure_exits_nonzero_in_every_mode(self):
        for mode in ([], ['--all'], ['--json']):
            with self.subTest(mode=mode):
                result, rows = self.run_cli(mode, {'DSO': 'https://example/tariffs.json'}, 'network')
                self.assertEqual(result.returncode, 1, result.stdout)
                if rows is not None:
                    self.assertFalse(rows[0]['ok'])
                    self.assertIn('URL error', rows[0]['detail'])

    def test_invalid_empty_and_wrong_shape_json_fail_in_every_mode(self):
        for response in ('not JSON', '{}', '{"tariffs":[]}', '[]',
                         '{"tariffs":{}}', '{"tariffs":[null]}'):
            for mode in ([], ['--all'], ['--json']):
                with self.subTest(response=response, mode=mode):
                    result, rows = self.run_cli(mode, {'DSO': 'https://example/tariffs.json'}, response)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    if rows is not None:
                        self.assertFalse(rows[0]['ok'])

    def test_unavailable_only_is_separate_and_never_healthy(self):
        year = datetime.now(ZoneInfo('Europe/Zurich')).year
        for mode in ([], ['--all'], ['--json']):
            with self.subTest(mode=mode):
                result, rows = self.run_cli(mode, {'IBI': {year + 1: 'https://example/future.json'}}, 'network')
                self.assertEqual(result.returncode, 0, result.stdout)
                if rows is not None:
                    self.assertTrue(rows[0]['unavailable'])
                    self.assertFalse(rows[0]['ok'])
                    self.assertIsNone(rows[0]['status'])
                else:
                    self.assertIn('0/0 gesund, 0 defekt, 1 ohne aktuelle Jahres-URL', result.stdout)

    def test_healthy_integer_year_map_and_custom_skip(self):
        year = datetime.now(ZoneInfo('Europe/Zurich')).year
        sources = {'DSO': {year: 'https://example/current.json'}, 'Custom / Other': 'custom'}
        for mode in ([], ['--all'], ['--json']):
            with self.subTest(mode=mode):
                result, rows = self.run_cli(mode, sources, '{"tariffs":[{"startDate":"2026-01-01"}]}')
                self.assertEqual(result.returncode, 0, result.stdout)
                if rows is not None:
                    custom, dso = rows
                    self.assertTrue(custom['skipped'])
                    self.assertTrue(dso['ok'])
                    self.assertEqual(dso['url'], 'https://example/current.json')
                else:
                    self.assertIn('1/1 gesund, 0 defekt', result.stdout)


if __name__ == '__main__':
    unittest.main()
