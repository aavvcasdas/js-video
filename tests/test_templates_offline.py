from __future__ import annotations

import re
import unittest
from pathlib import Path

from pixelle_agent.renderer import fill_template

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"


class OfflineTemplateTests(unittest.TestCase):
    def test_bundled_templates_do_not_request_remote_assets(self) -> None:
        templates = list(TEMPLATE_ROOT.rglob("*.html"))
        self.assertGreater(len(templates), 0)
        for template in templates:
            with self.subTest(template=template.relative_to(TEMPLATE_ROOT)):
                self.assertIsNone(re.search(r"https?://", template.read_text(encoding="utf-8")))

    def test_all_templates_accept_the_renderer_context(self) -> None:
        context = {
            "title": "Offline test",
            "text": "Line one\nLine two",
            "image": "data:image/png;base64,AA==",
            "index": 1,
            "author": "",
            "subtitle": "",
            "signature": "",
            "brand": "",
            "describe": "",
        }
        for template in TEMPLATE_ROOT.rglob("*.html"):
            with self.subTest(template=template.relative_to(TEMPLATE_ROOT)):
                rendered = fill_template(template.read_text(encoding="utf-8"), context)
                self.assertIsNone(re.search(r"\{\{[^}]+\}\}", rendered))


if __name__ == "__main__":

    unittest.main()
