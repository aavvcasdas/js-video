from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from pixelle_agent.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_starter_manifest_validates_without_assets(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["validate", str(REPO_ROOT / "examples/starter/project.json")])
        self.assertEqual(status, 0)
        self.assertIn("3 scene(s)", stdout.getvalue())
        self.assertIn("--check-assets", stdout.getvalue())

    def test_asset_validation_reports_missing_arena_output(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(
                [
                    "validate",
                    str(REPO_ROOT / "examples/starter/project.json"),
                    "--check-assets",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("does not exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
