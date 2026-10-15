from __future__ import annotations

import unittest

from pixelle_agent.jianying import _safe_draft_name


class JianyingNameTests(unittest.TestCase):
    def test_replaces_windows_invalid_characters(self) -> None:
        result = _safe_draft_name('Draft: "A/B?"')
        self.assertNotIn("/", result)
        self.assertNotIn(":", result)
        self.assertTrue(result)

    def test_avoids_windows_reserved_device_names(self) -> None:
        self.assertEqual(_safe_draft_name("CON"), "video-CON")

    def test_empty_name_gets_a_safe_default(self) -> None:
        self.assertEqual(_safe_draft_name("..."), "Arena Video")


if __name__ == "__main__":
    unittest.main()
