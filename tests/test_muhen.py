"""Offline regression tests for Muhen's officially published tariff file."""
import ast
import copy
import json
import unittest

from test_validate_schema import CONFIG_FLOW, FIXTURES, REPO_ROOT, validate_schema

MUHEN_URL = (
    "https://www.muhen.ch/public/upload/assets/3522/"
    "Tarife%20Elektrizit%C3%A4tswerk%20Muhen.json"
)


class TestMuhen(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FIXTURES / "muhen_2026.json").read_text())

    def test_real_document_with_string_identifier(self):
        self.assertEqual(self.document["dsoNumber"], "10013012345")
        self.assertEqual(len(self.document["tariffs"]), 9)
        original = copy.deepcopy(self.document)
        self.assertEqual(validate_schema(self.document), [])
        self.assertEqual(self.document, original, "Validation must not mutate input")

    def test_invalid_identifiers_rejected(self):
        for value in (True, False, 10013012345.0, None, [], {}, "", "12345",
                      "100130123456", "abcdefghijk", "1001301234a",
                      " 10013012345", "10013012345\n", "１００１３０１２３４５"):
            with self.subTest(value=value):
                self.document["dsoNumber"] = value
                self.assertTrue(validate_schema(self.document))

    def test_existing_integer_identifiers_remain_valid(self):
        for value in (12345, 10013012345):
            with self.subTest(value=value):
                self.document["dsoNumber"] = value
                self.assertEqual(validate_schema(self.document), [])

    def test_predefined_url(self):
        tree = ast.parse(CONFIG_FLOW.read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS"
                                  for t in node.targets))
        self.assertEqual(ast.literal_eval(assignment.value)["Elektrizitätswerk Muhen"],
                         {2026: MUHEN_URL})

    def test_schema_copies_describe_compatible_identifier(self):
        tree = ast.parse(CONFIG_FLOW.read_text())
        inline = next(ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "SEC_ENERGY_SCHEMA"
                              for t in node.targets))
        bundled = json.loads((REPO_ROOT / "custom_components/sec_energy/schema.json").read_text())
        expected = [{"type": "integer"},
                    {"type": "string", "pattern": "^[0-9]{11}$", "maxLength": 11}]
        for schema in (inline, bundled):
            self.assertEqual(schema["properties"]["dsoNumber"]["anyOf"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
