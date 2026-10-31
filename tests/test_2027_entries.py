"""Regression test: verified 2027 Jahres-Map entries added in t_b22c3b6c.

Covers three representative, individually verified 2027 URLs (two official
sources, one SEC-Energy mirror). Offline AST read, no network access.
"""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FLOW = ROOT / "custom_components" / "sec_energy" / "config_flow.py"


def load_catalog():
    tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "PREDEFINED_DSOS"
                        for t in n.targets))
    return ast.literal_eval(node.value)


CATALOG = load_catalog()


class Test2027Entries(unittest.TestCase):
    def assert_2027_entry(self, key, expected_url):
        source = CATALOG[key]
        self.assertIsInstance(source, dict, f"{key}: not a Jahres-Map")
        self.assertIn(2026, source, f"{key}: lost 2026 entry")
        self.assertEqual(source[2027], expected_url)
        self.assertTrue(all(type(y) is int for y in source))

    def test_arbon_sec_mirror_2027(self):
        self.assert_2027_entry(
            "Arbon Energie AG",
            "https://sec-energy.ch/tarifdaten/arbon/"
            "tariffs-10047012345-arbon-energie-ag-2027.json")

    def test_flawil_2027_retained(self):
        self.assert_2027_entry(
            "Technische Betriebe Flawil (TBF)",
            "https://www.tbflawil.ch/tarifkommunikation/2027_tariffs.json")

    def test_eschlikon_sec_mirror_2027(self):
        self.assert_2027_entry(
            "Technische Werke Eschlikon",
            "https://sec-energy.ch/tarifdaten/eschlikon/"
            "tariffs-10011012345-technische-werke-eschlikon-2027.json")

    def test_windisch_yearless_2027_source_added(self):
        self.assert_2027_entry(
            "Elektrizitäts- und Wasserwerk Windisch",
            "https://regionalwerke.ch/fileadmin/Strompreise_ElCom/Windisch_tariffs.json")

    def test_no_third_party_2027_urls(self):
        """Muhen, Würenlingen, Gossau etc. must stay out pending decision."""
        for key, source in CATALOG.items():
            urls = source.values() if isinstance(source, dict) else [source]
            for url in urls:
                self.assertNotRegex(url, re.compile(r"strompreisvergleich|youtility"),
                                    f"{key}: third-party URL leaked into catalog")


if __name__ == "__main__":
    unittest.main(verbosity=2)
