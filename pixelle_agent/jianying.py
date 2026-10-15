"""Optional Jianying draft export based on the user's referenced skill/library.

The exported draft uses an editable timeline of still-image scene clips, separate
voiceover clips, and an optional music clip. Captions are part of each rendered
Pixelle frame (they are therefore rasterized, not editable text layers).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .manifest import ProjectSpec, load_project
from .renderer import render_frames
from .video import _scene_durations


def _load_draft_library():
    vendor_dir = Path(__file__).resolve().parents[1] / "vendor"
    vendor_dir_str = str(vendor_dir)
    if vendor_dir_str not in sys.path:
        sys.path.insert(0, vendor_dir_str)
    try:
        import pyJianYingDraft as draft
        from pymediainfo import MediaInfo
    except ImportError as exc:
        raise RuntimeError(
            "Jianying draft export needs the optional MediaInfo dependency. "
            "Install it with `pip install -e '.[draft]'` and ensure MediaInfo can parse local media."
        ) from exc

    if not MediaInfo.can_parse():
        raise RuntimeError(
            "pymediainfo imported, but the native MediaInfo library is unavailable. "
            "Install MediaInfo for your operating system, then retry."
        )
    return draft


def _safe_draft_name(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", title).strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:80].strip().strip(".")
    if not name:
        name = "Arena Video"
    if name.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = f"video-{name}"
    return name


def _copy_media(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination.resolve()


def _build_draft(
    project: ProjectSpec,
    frame_paths: list[Path],
    durations: list[float],
    root: Path,
    *,
    draft_library,
) -> Path:
    draft_name = _safe_draft_name(project.title)
    resolved_root = root.expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    draft_path = (resolved_root / draft_name).resolve()
    if not draft_path.is_relative_to(resolved_root):
        raise RuntimeError("Draft path resolves outside the selected draft root")
    if draft_path.exists():
        raise FileExistsError(
            f"Draft already exists: {draft_path}. Choose a different project title or draft root; "
            "this command will not delete existing Jianying projects."
        )

    created = False
    try:
        draft_folder = draft_library.DraftFolder(str(resolved_root))
        script = draft_folder.create_draft(
            draft_name,
            project.width,
            project.height,
            project.fps,
            allow_replace=False,
        )
        created = True

        resources = draft_path / "Resources"
        image_dir = resources / "scenes"
        audio_dir = resources / "audio"
        script.add_track(draft_library.TrackType.video, "Arena Scenes")

        durations_us = [round(duration * 1_000_000) for duration in durations]
        cursor = 0
        for scene, frame_path, duration_us in zip(project.scenes, frame_paths, durations_us):
            local_frame = _copy_media(frame_path, image_dir / f"{scene.scene_id}.png")
            material = draft_library.VideoMaterial(str(local_frame))
            target = draft_library.Timerange(cursor, duration_us)
            source = draft_library.Timerange(0, duration_us)
            segment = draft_library.VideoSegment(
                material,
                target,
                source_timerange=source,
            )
            script.add_segment(segment, track_name="Arena Scenes")
            cursor += duration_us

        has_voiceover = any(scene.audio_path for scene in project.scenes)
        if has_voiceover:
            script.add_track(draft_library.TrackType.audio, "Voiceover")
            cursor = 0
            for scene, duration_us in zip(project.scenes, durations_us):
                if scene.audio_path is not None:
                    local_audio = _copy_media(
                        scene.audio_path,
                        audio_dir / f"voice-{scene.scene_id}{scene.audio_path.suffix.lower()}",
                    )
                    material = draft_library.AudioMaterial(str(local_audio))
                    clip_duration = min(duration_us, material.duration)
                    if clip_duration <= 0:
                        raise RuntimeError(f"Voiceover duration could not be read: {scene.audio_path}")
                    target = draft_library.Timerange(cursor, clip_duration)
                    source = draft_library.Timerange(0, clip_duration)
                    script.add_segment(
                        draft_library.AudioSegment(
                            material,
                            target,
                            source_timerange=source,
                            volume=1.0,
                        ),
                        track_name="Voiceover",
                    )
                cursor += duration_us

        if project.bgm is not None:
            local_bgm = _copy_media(
                project.bgm.path,
                audio_dir / f"background{project.bgm.path.suffix.lower()}",
            )
            material = draft_library.AudioMaterial(str(local_bgm))
            music_duration = min(sum(durations_us), material.duration)
            if music_duration <= 0:
                raise RuntimeError(f"Background music duration could not be read: {project.bgm.path}")
            script.add_track(draft_library.TrackType.audio, "Background Music")
            script.add_segment(
                draft_library.AudioSegment(
                    material,
                    draft_library.Timerange(0, music_duration),
                    source_timerange=draft_library.Timerange(0, music_duration),
                    volume=project.bgm.volume,
                ),
                track_name="Background Music",
            )

        script.save()
        marker = {
            "format": "Pixelle Arena Video Agent Jianying draft",
            "source_project": str(project.manifest_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": "Captions are rasterized into rendered scene frames; voiceover and BGM remain separate audio clips.",
        }
        (draft_path / "pixelle_arena_draft.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return draft_path
    except Exception:
        # Only remove a directory that was absent before this invocation. This avoids
        # touching an existing user draft, which is rejected above.
        if not created and draft_path.exists():
            shutil.rmtree(draft_path, ignore_errors=True)
        raise


def export_jianying_draft(
    manifest_path: str | Path,
    draft_root: str | Path | None = None,
) -> Path:
    """Render the project's scene cards and create a Jianying draft folder.

    By default the draft is written to ``<project>/output/jianying_drafts/<title>``.
    Pass ``draft_root`` to target a Jianying draft directory on another machine.
    """

    project = load_project(manifest_path, check_assets=True)
    durations = _scene_durations(project)
    draft_library = _load_draft_library()
    target_root = Path(draft_root) if draft_root is not None else project.root / "output" / "jianying_drafts"

    # Render first, so missing browser support fails before a draft folder is created.
    with tempfile.TemporaryDirectory(prefix="pixelle-jianying-frames-") as temp_dir:
        frame_paths = render_frames(project, Path(temp_dir))
        return _build_draft(
            project,
            frame_paths,
            durations,
            target_root,
            draft_library=draft_library,
        )
