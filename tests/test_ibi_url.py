"""Offline regression checks for IBI's migrated official tariff download."""
import ast
import unittest

from test_validate_schema import CONFIG_FLOW, load_fixture, validate_schema


class TestIbiTariffUrl(unittest.TestCase):
    def test_official_migrated_url(self):
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        dsos = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS" for t in node.targets)
        )
        self.assertEqual(
            dsos["Industrielle Betriebe Interlaken AG"],
            "https://www.ibi.ch/media/documents/20260821_tariffs.json",
        )

    def test_official_document_validates(self):
        data = load_fixture("ibi_2027.json")
        self.assertEqual(data["dsoName"], "Industrielle Betriebe Interlaken AG")
        self.assertEqual(data["dsoNumber"], 10290012345)
        self.assertEqual(len(data["tariffs"]), 14)
        self.assertEqual({t["startDate"] for t in data["tariffs"]}, {"2027-01-01"})
        self.assertEqual({t["endDate"] for t in data["tariffs"]}, {"2027-12-31"})
        self.assertEqual(
            {t["tariffType"] for t in data["tariffs"]},
            {"electricity", "grid", "metering", "regional_fees"},
        )
        self.assertEqual(validate_schema(data), [])


if __name__ == "__main__":
    unittest.main()
