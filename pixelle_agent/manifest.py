"""Manifest parsing and validation for agent-created video projects.

The Arena agent owns research, script writing, image generation, and optional narration.
This module deliberately handles only local project files; it has no model/API clients.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPO_ROOT / "templates"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}
SCENE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
TEMPLATE_PATTERN = re.compile(r"^(1080x1920|1920x1080|1080x1080)/(image_[a-zA-Z0-9_-]+\.html)$")


class ManifestError(ValueError):
    """Raised when a project manifest is invalid or unsafe to render."""


@dataclass(frozen=True)
class SceneSpec:
    scene_id: str
    narration: str
    caption: str
    image_prompt: str
    image_path: Path
    audio_path: Path | None
    duration: float | None
    title: str


@dataclass(frozen=True)
class BgmSpec:
    path: Path
    volume: float


@dataclass(frozen=True)
class ProjectSpec:
    manifest_path: Path
    root: Path
    title: str
    language: str
    author: str
    width: int
    height: int
    fps: int
    template: str
    output: str
    template_params: dict[str, Any]
    bgm: BgmSpec | None
    scenes: tuple[SceneSpec, ...]
    sources: tuple[dict[str, str], ...]


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be an object")
    return value


def _require_text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ManifestError(f"{label} must be {qualifier}")
    return value


def _local_path(root: Path, value: Any, label: str, *, check_exists: bool) -> Path:
    raw = _require_text(value, label)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(f"{label} must be a safe relative path inside the project folder: {raw!r}")

    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ManifestError(f"{label} resolves outside the project folder: {raw!r}")
    if check_exists and not resolved.is_file():
        raise ManifestError(f"{label} does not exist: {resolved}")
    return resolved


def _validate_output_path(value: Any) -> str:
    raw = value if value is not None else "output/final.mp4"
    raw = _require_text(raw, "video.output")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError("video.output must be a relative path inside the project folder")
    if candidate.suffix.lower() != ".mp4":
        raise ManifestError("video.output must use the .mp4 extension")
    return candidate.as_posix()


def _validate_sources(value: Any) -> tuple[dict[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ManifestError("sources must be an array")

    sources: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        source = _require_mapping(item, f"sources[{index - 1}]")
        title = _require_text(source.get("title"), f"sources[{index - 1}].title")
        url = _require_text(source.get("url"), f"sources[{index - 1}].url")
        if not url.startswith(("https://", "http://")):
            raise ManifestError(f"sources[{index - 1}].url must start with http:// or https://")
        accessed_on = source.get("accessed_on", "")
        if not isinstance(accessed_on, str):
            raise ManifestError(f"sources[{index - 1}].accessed_on must be a string")
        sources.append({"title": title, "url": url, "accessed_on": accessed_on})
    return tuple(sources)


def _validate_template_params(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    params = _require_mapping(value, "video.template_params")
    if any(not isinstance(key, str) or not key.isidentifier() for key in params):
        raise ManifestError("video.template_params keys must be valid identifiers")
    reserved = {
        "title",
        "text",
        "image",
        "index",
        "author",
        "subtitle",
        "signature",
        "brand",
        "describe",
    }
    if reserved.intersection(params):
        raise ManifestError(
            "video.template_params cannot override reserved fields: "
            + ", ".join(sorted(reserved.intersection(params)))
        )
    return params


def load_project(manifest_path: str | Path, *, check_assets: bool = False) -> ProjectSpec:
    """Load and validate a project JSON file.

    When ``check_assets`` is false, paths are still checked for traversal but files may
    not have been created yet. The render command always enables asset checks.
    """

    manifest_file = Path(manifest_path).expanduser().resolve()
    if not manifest_file.is_file():
        raise ManifestError(f"Project file not found: {manifest_file}")
    try:
        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"Invalid JSON in {manifest_file} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ManifestError(f"Cannot read project file {manifest_file}: {exc}") from exc

    data = _require_mapping(raw, "project manifest")
    schema_version = data.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
        raise ManifestError("schema_version must be the number 1")

    project = _require_mapping(data.get("project"), "project")
    project_title = _require_text(project.get("title"), "project.title")
    language = project.get("language", "zh-CN")
    language = _require_text(language, "project.language")
    author = project.get("author", "")
    author = _require_text(author, "project.author", allow_empty=True)

    video = _require_mapping(data.get("video"), "video")
    width = video.get("width", 1080)
    height = video.get("height", 1920)
    fps = video.get("fps", 30)
    for name, value, minimum, maximum in (
        ("width", width, 256, 4096),
        ("height", height, 256, 4096),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ManifestError(f"video.{name} must be an integer from {minimum} to {maximum}")
        if value % 2:
            raise ManifestError(f"video.{name} must be even for H.264 output")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 12 <= fps <= 60:
        raise ManifestError("video.fps must be an integer from 12 to 60")

    template = video.get("template", "1080x1920/image_default.html")
    template = _require_text(template, "video.template")
    template_match = TEMPLATE_PATTERN.fullmatch(template)
    if not template_match:
        raise ManifestError(
            "video.template must name a bundled image template such as "
            "'1080x1920/image_default.html'"
        )
    template_size = template_match.group(1)
    template_path = (TEMPLATE_ROOT / template).resolve()
    if not template_path.is_relative_to(TEMPLATE_ROOT.resolve()):
        raise ManifestError("video.template must remain inside the bundled templates folder")
    if not template_path.is_file():
        raise ManifestError(f"Bundled template not found: {template}")
    expected_width, expected_height = (int(part) for part in template_size.split("x"))
    if (width, height) != (expected_width, expected_height):
        raise ManifestError(
            f"video resolution {width}x{height} does not match template {template_size}"
        )

    output = _validate_output_path(video.get("output", "output/final.mp4"))
    template_params = _validate_template_params(video.get("template_params"))

    bgm: BgmSpec | None = None
    bgm_raw = video.get("bgm")
    if bgm_raw is not None:
        bgm_config = _require_mapping(bgm_raw, "video.bgm")
        bgm_path = _local_path(
            manifest_file.parent,
            bgm_config.get("path"),
            "video.bgm.path",
            check_exists=check_assets,
        )
        if bgm_path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ManifestError(f"video.bgm.path must be an audio file: {bgm_path.name}")
        volume = bgm_config.get("volume", 0.12)
        if isinstance(volume, bool) or not isinstance(volume, (int, float)):
            raise ManifestError("video.bgm.volume must be a number from 0 to 1")
        volume = float(volume)
        if not math.isfinite(volume) or not 0 <= volume <= 1:
            raise ManifestError("video.bgm.volume must be a finite number from 0 to 1")
        bgm = BgmSpec(path=bgm_path, volume=volume)

    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ManifestError("scenes must be a non-empty array")
    if len(raw_scenes) > 80:
        raise ManifestError("scenes may contain at most 80 entries")

    scenes: list[SceneSpec] = []
    seen_ids: set[str] = set()
    for index, raw_scene in enumerate(raw_scenes):
        scene = _require_mapping(raw_scene, f"scenes[{index}]")
        scene_id = _require_text(scene.get("id"), f"scenes[{index}].id")
        if not SCENE_ID_PATTERN.fullmatch(scene_id):
            raise ManifestError(
                f"scenes[{index}].id must start with a letter or number and contain only "
                "letters, numbers, underscores, or hyphens (max 64 characters)"
            )
        if scene_id in seen_ids:
            raise ManifestError(f"Duplicate scene id: {scene_id}")
        seen_ids.add(scene_id)

        narration = _require_text(scene.get("narration"), f"scenes[{index}].narration")
        caption = scene.get("caption", narration)
        caption = _require_text(caption, f"scenes[{index}].caption", allow_empty=True)
        image_prompt = scene.get("image_prompt", "")
        image_prompt = _require_text(
            image_prompt, f"scenes[{index}].image_prompt", allow_empty=True
        )
        image_path = _local_path(
            manifest_file.parent,
            scene.get("image"),
            f"scenes[{index}].image",
            check_exists=check_assets,
        )
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ManifestError(
                f"scenes[{index}].image must be PNG, JPEG, or WebP: {image_path.name}"
            )

        audio_raw = scene.get("audio")
        audio_path: Path | None = None
        if audio_raw is not None:
            audio_path = _local_path(
                manifest_file.parent,
                audio_raw,
                f"scenes[{index}].audio",
                check_exists=check_assets,
            )
            if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
                raise ManifestError(
                    f"scenes[{index}].audio must be an audio file: {audio_path.name}"
                )

        duration_raw = scene.get("duration")
        duration: float | None = None
        if duration_raw is not None:
            if isinstance(duration_raw, bool) or not isinstance(duration_raw, (int, float)):
                raise ManifestError(f"scenes[{index}].duration must be a number of seconds")
            duration = float(duration_raw)
            if not math.isfinite(duration) or not 0.25 <= duration <= 120:
                raise ManifestError(f"scenes[{index}].duration must be between 0.25 and 120 seconds")
        if duration is None and audio_path is None:
            raise ManifestError(
                f"scenes[{index}] needs either duration or audio so the renderer can time the scene"
            )

        scene_title = scene.get("title", project_title)
        scene_title = _require_text(scene_title, f"scenes[{index}].title", allow_empty=True)
        scenes.append(
            SceneSpec(
                scene_id=scene_id,
                narration=narration,
                caption=caption,
                image_prompt=image_prompt,
                image_path=image_path,
                audio_path=audio_path,
                duration=duration,
                title=scene_title,
            )
        )

    sources = _validate_sources(data.get("sources"))
    return ProjectSpec(
        manifest_path=manifest_file,
        root=manifest_file.parent,
        title=project_title,
        language=language,
        author=author,
        width=width,
        height=height,
        fps=fps,
        template=template,
        output=output,
        template_params=template_params,
        bgm=bgm,
        scenes=tuple(scenes),
        sources=sources,
    )
