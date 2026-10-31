"""Regression tests for the SEC-Energy JSON schema validator.

Runs without Home Assistant: validate_schema is extracted from
config_flow.py via AST, because that module imports homeassistant.

Usage:
    python3 -m pytest tests/ -v
or without pytest:
    python3 tests/test_validate_schema.py
"""

import ast
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FLOW = REPO_ROOT / "custom_components" / "sec_energy" / "config_flow.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_validate_schema():
    """Extract validate_schema() from config_flow.py without importing HA.

    Also pulls in the SEC_ENERGY_SCHEMA constant, which the validator
    reads from module scope.
    """
    tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SEC_ENERGY_SCHEMA" for t in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "validate_schema":
            nodes.append(node)
    if not any(isinstance(n, ast.FunctionDef) for n in nodes):
        raise AssertionError("validate_schema not found in config_flow.py")
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {}
    exec(compile(module, str(CONFIG_FLOW), "exec"), namespace)
    return namespace["validate_schema"]


validate_schema = load_validate_schema()


def load_fixture(name):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def make_tariff(tariff_type, prices):
    return {
        "tariffName": "Test",
        "tariffType": tariff_type,
        "tariffForm": "constant",
        "prices": prices,
    }


def make_document(tariffs):
    return {"dsoName": "Test DSO", "dsoNumber": 12345, "tariffs": tariffs}


class TestRealWorldFiles(unittest.TestCase):
    """Real DSO files must validate — regression test for issue #2."""

    def test_flawil_2026(self):
        """TB Flawil has metering (base only) and regional_fees
        (municipalityTaxes only) tariffs. These were wrongly rejected."""
        errors = validate_schema(load_fixture("flawil_2026.json"))
        self.assertEqual(errors, [], f"Flawil rejected: {errors}")

    def test_flawil_covers_all_tariff_types(self):
        """Guard: the fixture must really exercise the special types,
        otherwise the regression test above would be vacuous."""
        data = load_fixture("flawil_2026.json")
        types = {t["tariffType"] for t in data["tariffs"]}
        self.assertIn("metering", types)
        self.assertIn("regional_fees", types)


class TestTariffTypeRules(unittest.TestCase):
    def test_electricity_requires_energy(self):
        doc = make_document([make_tariff("electricity", {"base": {"price": 0}})])
        self.assertTrue(validate_schema(doc))

    def test_grid_requires_energy(self):
        doc = make_document([make_tariff("grid", {"base": {"price": 0}})])
        self.assertTrue(validate_schema(doc))

    def test_electricity_with_energy_valid(self):
        doc = make_document([make_tariff("electricity", {"energy": []})])
        self.assertEqual(validate_schema(doc), [])

    def test_metering_with_base_only_valid(self):
        doc = make_document([
            make_tariff("metering", {"base": {"price": 4.8, "priceUnit": "CHF/M"}})
        ])
        self.assertEqual(validate_schema(doc), [])

    def test_metering_without_base_rejected(self):
        doc = make_document([make_tariff("metering", {"energy": []})])
        self.assertTrue(validate_schema(doc))

    def test_regional_fees_with_municipality_taxes_valid(self):
        doc = make_document([
            make_tariff("regional_fees", {"municipalityTaxes": {"price": 0.01}})
        ])
        self.assertEqual(validate_schema(doc), [])

    def test_regional_fees_without_taxes_rejected(self):
        doc = make_document([make_tariff("regional_fees", {"base": {"price": 0}})])
        self.assertTrue(validate_schema(doc))

    def test_energy_must_be_list(self):
        doc = make_document([make_tariff("electricity", {"energy": {}})])
        self.assertTrue(validate_schema(doc))


class TestDocumentLevel(unittest.TestCase):
    def test_missing_dso_name(self):
        doc = make_document([make_tariff("electricity", {"energy": []})])
        del doc["dsoName"]
        self.assertTrue(validate_schema(doc))

    def test_empty_tariffs_rejected(self):
        self.assertTrue(validate_schema(make_document([])))

    def test_valid_document(self):
        doc = make_document([make_tariff("electricity", {"energy": []})])
        self.assertEqual(validate_schema(doc), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
