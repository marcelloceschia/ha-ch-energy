"""Offline release safety regression tests (no GitHub writes)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseValidationTests(unittest.TestCase):
    def validate(self, version, tag, sha="a" * 40, manifest_version=None):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"version": manifest_version or version}))
            return subprocess.run(
                ["python3", str(ROOT / "scripts/validate_release.py"),
                 "--version", version, "--tag", tag, "--sha", sha,
                 "--manifest", str(manifest)], capture_output=True, text=True,
            )

    def test_rejects_invalid_or_inconsistent_metadata(self):
        for version, tag, sha, manifest in [
            ("1.2", "v1.2", "a" * 40, "1.2"),
            ("01.2.3", "v01.2.3", "a" * 40, "01.2.3"),
            ("1.2.3-beta.0", "v1.2.3-beta.0", "a" * 40, "1.2.3-beta.0"),
            ("1.2.3-rc.1", "v1.2.3-rc.1", "a" * 40, "1.2.3-rc.1"),
            ("1.2.3", "v1.2.4", "a" * 40, "1.2.3"),
            ("1.2.3", "v1.2.3", "main", "1.2.3"),
            ("1.2.3", "v1.2.3", "a" * 40, "1.1.0"),
            ("1.2.3\n", "v1.2.3\n", "a" * 40, "1.2.3\n"),
        ]:
            with self.subTest(version=version, tag=tag, sha=sha, manifest=manifest):
                self.assertNotEqual(self.validate(version, tag, sha, manifest).returncode, 0)

    def test_workflow_is_manual_and_draft_only(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("--latest=false", workflow)
        self.assertIn("prevent_self_review", workflow)
        self.assertIn("can_admins_bypass", workflow)

    def test_stable_and_beta_classification(self):
        for version, expected in [("1.2.3", False), ("1.2.3-beta.1", True)]:
            with self.subTest(version=version):
                result = self.validate(version, "v" + version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["prerelease"], expected)


if __name__ == "__main__":
    unittest.main()
