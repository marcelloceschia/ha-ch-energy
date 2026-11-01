"""Offline Birwinken catalogue/year-resolution regressions using real documents."""
import ast
from datetime import date
import json
import unittest

from test_validate_schema import CONFIG_FLOW, REPO_ROOT, validate_schema
from test_year_change import tariffs

DSO = 'Technische Werke der Gemeinde Birwinken'
URL_2026 = 'https://marcelloceschia.github.io/ha-ch-energy/tariffs/birwinken/2026_tariffs.json'
URL_2027 = 'https://www.birwinken.ch/public/upload/assets/2496/Tarife%202027_maschinenlesbar.json?fp=2'


def catalogue_namespace():
    tree = ast.parse(CONFIG_FLOW.read_text())
    nodes: list[ast.stmt] = [node for node in tree.body if (
        isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'PREDEFINED_DSOS'
            for target in node.targets)
    ) or (isinstance(node, ast.FunctionDef) and node.name == 'available_dsos')]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(CONFIG_FLOW), 'exec'), namespace)
    return namespace


class BirwinkenCatalogueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.namespace = catalogue_namespace()
        self.source = self.namespace['PREDEFINED_DSOS'][DSO]
        self.documents = {
            URL_2026: json.loads((REPO_ROOT / 'tariffs/birwinken/2026_tariffs.json').read_text()),
            URL_2027: json.loads((REPO_ROOT / 'tests/fixtures/birwinken_2027.json').read_text()),
        }

    def test_explicit_year_urls_and_setup_availability(self):
        self.assertEqual(self.source, {2026: URL_2026, 2027: URL_2027})
        for year in (2026, 2027):
            with self.subTest(year=year):
                self.assertIn(DSO, self.namespace['available_dsos'](
                    self.namespace['PREDEFINED_DSOS'], date(year, 1, 1)))
                self.assertEqual(tariffs.match_dso(self.source[year],
                    self.namespace['PREDEFINED_DSOS']), DSO)

    async def test_resolver_uses_exact_year_and_selects_every_current_tariff(self):
        for year, url in ((2026, URL_2026), (2027, URL_2027)):
            for day in (date(year, 1, 1), date(year, 12, 31)):
                with self.subTest(day=day):
                    calls = []

                    async def fetch(candidate):
                        calls.append(candidate)
                        return self.documents[candidate]

                    resolved_url, document = await tariffs.resolve_document(
                        self.source, day, fetch, validate_schema)
                    self.assertEqual(resolved_url, url)
                    self.assertEqual(calls, [url])
                    self.assertEqual(validate_schema(document), [])
                    for tariff in document['tariffs']:
                        self.assertIsNotNone(tariffs.select_tariff(
                            document, tariff['tariffName'], day))

    async def test_2026_only_tariff_is_rejected_in_2027(self):
        old_document = self.documents[URL_2026]
        names_2027 = {t['tariffName'] for t in self.documents[URL_2027]['tariffs']}
        old_name = next(t['tariffName'] for t in old_document['tariffs']
                        if t['tariffName'] not in names_2027)
        day = date(2027, 1, 1)
        self.assertIsNone(tariffs.select_tariff(old_document, old_name, day))
        calls = []

        async def fetch(url):
            calls.append(url)
            if url not in self.documents:
                raise OSError('No fixture for guessed URL')
            return self.documents[url]

        with self.assertRaisesRegex(ValueError, 'No valid tariff source'):
            await tariffs.resolve_document(self.source, day, fetch, validate_schema, old_name)
        self.assertEqual(calls, [URL_2027, URL_2026])


if __name__ == '__main__':
    unittest.main()
