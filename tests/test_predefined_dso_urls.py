"""Offline regression for the verified Wettingen tariff URL repair."""
import ast
from pathlib import Path
import unittest

CONFIG_FLOW = Path(__file__).resolve().parents[1] / "custom_components/sec_energy/config_flow.py"


class TestPredefinedDSOURLs(unittest.TestCase):
    def test_wettingen_uses_published_2026_2027_document(self):
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
        dsos = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PREDEFINED_DSOS"
                    for target in node.targets)
        )
        # Published on energiewettingen.ch/de/strom/stromprodukte-preise.html.
        # GET verified: 20 tariffs, both 2026 and 2027, schema accepted.
        self.assertEqual(
            dsos["Energie Wettingen AG"],
            "https://www.energiewettingen.ch/upload/rm/20/26/20260824-enw-2027-tariffs-1.json",
        )


if __name__ == "__main__":
    unittest.main()
