"""Offline regression checks for Energie Gossau AG (ZH, not Gossau SG)."""
import ast
import unittest

from test_validate_schema import CONFIG_FLOW, load_fixture, validate_schema

URL = "https://strompreisvergleich.ch/tarife/data/10766012345/tarife.json"


class TestGossauTariffs(unittest.TestCase):
    def test_predefined_url(self):
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        dsos = next(
            ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS"
                    for t in node.targets)
        )
        self.assertEqual(dsos["Energie Gossau AG"], URL)

    def test_published_document_validates(self):
        data = load_fixture("gossau_2026_2027.json")
        self.assertEqual(data["dsoName"], "Energie Gossau AG")
        self.assertEqual(data["dsoNumber"], "10766012345")
        self.assertEqual(len(data["tariffs"]), 30)
        self.assertEqual({t["startDate"][:4] for t in data["tariffs"]},
                         {"2026", "2027"})
        self.assertEqual(validate_schema(data), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
