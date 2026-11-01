"""Offline regressions for the SEC-Energy-linked Sins source."""
import ast
import copy
from datetime import date
import json
import unittest

from test_validate_schema import CONFIG_FLOW, FIXTURES, validate_schema
from test_year_change import tariffs

SINS_URL = "https://strompreisvergleich.ch/tarife/data/10346012345/tarife.json"


def sins_source():
    tree = ast.parse(CONFIG_FLOW.read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS"
                              for t in node.targets))
    return ast.literal_eval(assignment.value)["Elektra Sins"]


class TestSins(unittest.TestCase):
    def test_predefined_year_map(self):
        self.assertEqual(sins_source(), {2026: SINS_URL, 2027: SINS_URL})

    def test_real_document_accepts_string_identifier_without_mutation(self):
        document = json.loads((FIXTURES / "sins_2026_2027.json").read_text())
        original = copy.deepcopy(document)
        self.assertEqual(document["dsoName"], "Elektra Sins")
        self.assertEqual(document["dsoNumber"], "10346012345")
        self.assertEqual(len(document["tariffs"]), 20)
        self.assertEqual(validate_schema(document), [])
        self.assertEqual(document, original)

    def test_real_tariffs_select_correct_year_at_rollover(self):
        document = json.loads((FIXTURES / "sins_2026_2027.json").read_text())
        names = {t["tariffName"] for t in document["tariffs"]}
        for day in (date(2026, 12, 31), date(2027, 1, 1)):
            self.assertEqual(tariffs.source_candidates(sins_source(), day)[0], SINS_URL)
            for name in names:
                with self.subTest(day=day, name=name):
                    selected = tariffs.select_tariff(document, name, day)
                    self.assertIsNotNone(selected)
                    self.assertEqual(selected["startDate"], f"{day.year}-01-01")
                    self.assertEqual(selected["endDate"], f"{day.year}-12-31")
        for name in names:
            self.assertIsNone(tariffs.select_tariff(document, name, date(2028, 1, 1)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
