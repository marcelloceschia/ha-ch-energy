import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('checker', Path(__file__).resolve().parents[1] / 'scripts/check_dso_urls.py')
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class CheckerTests(unittest.TestCase):
    def test_year_map_is_checked_without_string_crash(self):
        with patch.object(checker.urllib.request, 'urlopen', side_effect=OSError('offline')) as request:
            result = checker.check(('DSO', {2026: 'https://example/2026.json'}), year=2026)
        self.assertFalse(result['ok'])
        self.assertEqual(request.call_args.args[0].full_url, 'https://example/2026.json')

    def test_future_only_is_unavailable_not_healthy(self):
        with patch.object(checker.urllib.request, 'urlopen') as request:
            result = checker.check(('DSO', {2027: 'https://example/2027.json'}), year=2026)
        request.assert_not_called()
        self.assertFalse(result['ok'])
        self.assertTrue(result['unavailable'])


if __name__ == '__main__':
    unittest.main()
