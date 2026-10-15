"""Render Pixelle's bundled HTML image templates to still frames.

Image generation is intentionally not implemented here: an Arena agent creates the
images with its native image-generation tool, saves them in the project folder, and
this renderer only consumes those local files.
"""

from __future__ import annotations

import base64
import html
import math
import mimetypes
import re
from pathlib import Path
from typing import Any

from .manifest import REPO_ROOT, ProjectSpec

_PLACEHOLDER = re.compile(
    r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-z]+))?(?:=([^}]*))?\}\}"
)
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _image_data_uri(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0]
    if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError(f"Unsupported image type for local frame asset: {image_path.name}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _format_placeholder_value(name: str, value: Any, value_type: str | None) -> str:
    if value is None:
        return ""

    if value_type == "number":
        if isinstance(value, bool):
            raise ValueError(f"Template parameter {name!r} must be numeric")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Template parameter {name!r} must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError(f"Template parameter {name!r} must be finite")
        return str(int(number)) if number.is_integer() else str(number)

    if value_type == "bool":
        if isinstance(value, str):
            normalized = value.strip().lower() in {"true", "1", "yes", "on"}
        else:
            normalized = bool(value)
        return "true" if normalized else "false"

    rendered = str(value)
    if value_type == "color" and not _COLOR.fullmatch(rendered):
        raise ValueError(f"Template parameter {name!r} must be a hex color (for example #764ba2)")

    # Text is escaped before insertion because the source template is HTML. Line breaks
    # in captions are converted to safe <br> tags, never interpreted as user HTML.
    escaped = html.escape(rendered, quote=True)
    if name == "text":
        escaped = escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return escaped


def fill_template(template: str, values: dict[str, Any]) -> str:
    """Safely replace Pixelle's ``{{name:type=default}}`` placeholders."""

    def replace(match: re.Match[str]) -> str:
        name, value_type, default = match.groups()
        value = values[name] if name in values else default
        return _format_placeholder_value(name, value, value_type)

    return _PLACEHOLDER.sub(replace, template)


def _load_template(template_name: str) -> str:
    template_path = (REPO_ROOT / "templates" / template_name).resolve()
    template_root = (REPO_ROOT / "templates").resolve()
    if not template_path.is_relative_to(template_root) or not template_path.is_file():
        raise FileNotFoundError(f"Bundled template not found: {template_name}")
    return template_path.read_text(encoding="utf-8")


def render_frames(project: ProjectSpec, frame_dir: Path) -> list[Path]:
    """Create one PNG frame per scene using a shared headless Chromium instance."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Frame rendering requires Playwright. Install with `pip install -e '.[render]'` "
            "and then run `playwright install chromium`."
        ) from exc

    template = _load_template(project.template)
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not start Chromium. Install the browser with `playwright install chromium`."
            ) from exc

        try:
            page = browser.new_page(
                viewport={"width": project.width, "height": project.height},
                device_scale_factor=1,
            )
            for index, scene in enumerate(project.scenes, start=1):
                values: dict[str, Any] = {
                    "title": scene.title,
                    "text": scene.caption,
                    "image": _image_data_uri(scene.image_path),
                    "index": index,
                    "author": project.author,
                    "subtitle": project.author,
                    "signature": project.author,
                    "brand": "",
                    "describe": "",
                }
                values.update(project.template_params)
                markup = fill_template(template, values)

                page.set_content(markup, wait_until="load")
                page.evaluate("() => document.fonts.ready")
                images_ready = page.evaluate(
                    "() => Array.from(document.images).every((img) => img.complete && img.naturalWidth > 0)"
                )
                if not images_ready:
                    raise RuntimeError(f"Template image failed to load in scene {scene.scene_id}")

                frame_path = frame_dir / f"{scene.scene_id}.png"
                page.screenshot(path=str(frame_path), type="png", animations="disabled")
                frame_paths.append(frame_path)
        finally:
            browser.close()

    return frame_paths
