"""Parser regression tests, without Home Assistant or network access."""
from datetime import date
import ast
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "custom_components/sec_energy/tariff_document.py"


def parse_document(text, today):
    spec = importlib.util.spec_from_file_location("tariff_document", PARSER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_tariff_document(text, today=today)


class TestIWB(unittest.TestCase):
    def test_real_iwb_selects_current_year_not_first_document(self):
        text = (ROOT / "tests/fixtures/iwb_concatenated.txt").read_text()
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)
        data = parse_document(text, date(2026, 10, 31))
        self.assertEqual(data["dsoName"], "IWB")
        self.assertEqual(len(data["tariffs"]), 77)
        self.assertEqual({t["startDate"] for t in data["tariffs"]}, {"2026-01-01"})
        self.assertEqual({t["endDate"] for t in data["tariffs"]}, {"2026-12-31"})

    def test_predefined_iwb_uses_official_endpoint(self):
        tree = ast.parse((ROOT / "custom_components/sec_energy/config_flow.py").read_text())
        dsos = next(ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS"
                        for t in n.targets))
        url = next(v for k, v in dsos.items() if k.startswith("IWB"))
        self.assertEqual(url, "https://www.iwb.ch/dam/jcr:0e220410-b22a-4383-a29e-e32910532b53/maschinell-lesbare-tarife.json")

    def test_all_fetch_paths_share_parser(self):
        counts = {"config_flow.py": 2, "__init__.py": 2}
        for filename, expected in counts.items():
            tree = ast.parse((ROOT / "custom_components/sec_energy" / filename).read_text())
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
            self.assertEqual(sum(isinstance(n.func, ast.Name) and n.func.id == "parse_tariff_document"
                                 for n in calls), expected)
            self.assertFalse(any(isinstance(n.func, ast.Attribute) and n.func.attr == "loads"
                                 for n in calls))

    def test_cantonal_taxes_must_be_array(self):
        from test_validate_schema import validate_schema, make_document, make_tariff
        for value in [None, {}, "invalid", 42]:
            with self.subTest(value=value):
                data = make_document([make_tariff("regional_fees", {"cantonalTaxes": value})])
                self.assertTrue(validate_schema(data))

    def test_year_boundaries(self):
        text = (ROOT / "tests/fixtures/iwb_concatenated.txt").read_text()
        for day, year in [(date(2026, 1, 1), 2026), (date(2026, 12, 31), 2026),
                          (date(2027, 1, 1), 2027), (date(2027, 12, 31), 2027)]:
            with self.subTest(day=day):
                data = parse_document(text, day)
                self.assertEqual({t["startDate"] for t in data["tariffs"]}, {f"{year}-01-01"})
                from test_validate_schema import validate_schema
                self.assertEqual(validate_schema(data), [])

    def test_valid_single_documents_unchanged(self):
        for data in [{"tariffs": []}, [1, 2], None]:
            self.assertEqual(parse_document(json.dumps(data), date(2026, 1, 1)), data)
        text = (ROOT / "tests/fixtures/flawil_2026.json").read_text()
        self.assertEqual(parse_document(text, date(2026, 1, 1)), json.loads(text))

    def test_rejects_trailing_garbage_unknown_identity_and_ambiguous_dates(self):
        text = (ROOT / "tests/fixtures/iwb_concatenated.txt").read_text()
        current = parse_document(text, date(2026, 10, 31))
        unknown = copy.deepcopy(current)
        unknown["dsoName"] = "Other DSO"
        invalid = copy.deepcopy(current)
        invalid["tariffs"][0]["startDate"] = "invalid"
        reversed_dates = copy.deepcopy(current)
        reversed_dates["tariffs"][0]["endDate"] = "2025-01-01"
        for bad in [text + "garbage", text + "{}", json.dumps(current) * 2,
                    json.dumps(unknown) + json.dumps(current),
                    json.dumps(invalid) + json.dumps(current),
                    json.dumps(reversed_dates) + json.dumps(current)]:
            with self.subTest(bad=bad[-80:]):
                with self.assertRaises(json.JSONDecodeError):
                    parse_document(bad, date(2026, 10, 31))
        for day in [date(2025, 12, 31), date(2028, 1, 1)]:
            with self.assertRaises(json.JSONDecodeError):
                parse_document(text, day)


if __name__ == "__main__":
    unittest.main(verbosity=2)
