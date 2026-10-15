from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pixelle_agent.manifest import ManifestError, load_project


class ProjectManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.manifest = self.root / "project.json"
        self.data = {
            "schema_version": 1,
            "project": {"title": "Test video", "language": "zh-CN"},
            "video": {
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "template": "1080x1920/image_default.html",
            },
            "scenes": [
                {
                    "id": "scene-01",
                    "narration": "A short line.",
                    "caption": "A caption",
                    "image_prompt": "An image prompt",
                    "image": "assets/scenes/scene-01.png",
                    "duration": 3.5,
                }
            ],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def save(self) -> None:
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def test_load_valid_manifest_without_assets_for_agent_planning(self) -> None:
        self.save()
        project = load_project(self.manifest)
        self.assertEqual(project.title, "Test video")
        self.assertEqual(project.template, "1080x1920/image_default.html")
        self.assertEqual(project.scenes[0].caption, "A caption")
        self.assertEqual(project.scenes[0].image_path, self.root / "assets/scenes/scene-01.png")

    def test_asset_check_requires_generated_image(self) -> None:
        self.save()
        with self.assertRaisesRegex(ManifestError, "does not exist"):
            load_project(self.manifest, check_assets=True)

    def test_asset_check_accepts_local_image(self) -> None:
        image = self.root / "assets/scenes/scene-01.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"test image")
        self.save()
        project = load_project(self.manifest, check_assets=True)
        self.assertTrue(project.scenes[0].image_path.is_file())

    def test_rejects_path_traversal_even_before_assets_exist(self) -> None:
        self.data["scenes"][0]["image"] = "../../outside.png"
        self.save()
        with self.assertRaisesRegex(ManifestError, "safe relative path"):
            load_project(self.manifest)

    def test_rejects_duplicate_scene_ids(self) -> None:
        self.data["scenes"].append(dict(self.data["scenes"][0]))
        self.save()
        with self.assertRaisesRegex(ManifestError, "Duplicate scene id"):
            load_project(self.manifest)

    def test_rejects_template_resolution_mismatch(self) -> None:
        self.data["video"]["width"] = 1920
        self.data["video"]["height"] = 1080
        self.save()
        with self.assertRaisesRegex(ManifestError, "does not match template"):
            load_project(self.manifest)

    def test_scene_needs_audio_or_duration(self) -> None:
        del self.data["scenes"][0]["duration"]
        self.save()
        with self.assertRaisesRegex(ManifestError, "either duration or audio"):
            load_project(self.manifest)

    def test_rejects_output_traversal(self) -> None:
        self.data["video"]["output"] = "../final.mp4"
        self.save()
        with self.assertRaisesRegex(ManifestError, "relative path"):
            load_project(self.manifest)


if __name__ == "__main__":
    unittest.main()
