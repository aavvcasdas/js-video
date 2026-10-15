"""Local FFmpeg assembly for agent-created scene assets.

This module never contacts a model or media provider. It combines rendered PNG frames,
optional scene audio, and optional background music into a single H.264 MP4.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from .manifest import ProjectSpec


def _run(command: list[str], *, label: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFmpeg tools are required. Install FFmpeg and make sure both `ffmpeg` and "
            "`ffprobe` are on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        if len(details) > 3000:
            details = details[-3000:]
        raise RuntimeError(f"{label} failed:\n{details}") from exc

def _probe_duration(audio_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "FFprobe is required to time a scene from audio. Install FFmpeg and make sure "
            "`ffprobe` is on PATH, or set an explicit scene duration."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Could not read audio duration for {audio_path}: {details}") from exc

    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"FFprobe returned an invalid duration for {audio_path}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Audio has an invalid duration: {audio_path}")
    return duration


def _scene_durations(project: ProjectSpec) -> list[float]:
    durations: list[float] = []
    for scene in project.scenes:
        if scene.duration is not None:
            durations.append(scene.duration)
        elif scene.audio_path is not None:
            durations.append(_probe_duration(scene.audio_path))
        else:  # Enforced by manifest validation; keep a defensive guard here.
            raise RuntimeError(f"Scene {scene.scene_id} needs a duration or an audio file")
    return durations


def _concat_file_list(video_paths: list[Path], destination: Path) -> None:
    lines = []
    for video_path in video_paths:
        escaped = video_path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_scene_segment(
    *,
    frame_path: Path,
    audio_path: Path | None,
    duration: float,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-i",
        str(frame_path),
    ]

    if audio_path is None:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        audio_filter: list[str] = []
        audio_input = "1:a:0"
    else:
        command.extend(["-i", str(audio_path)])
        audio_filter = ["-af", f"apad=whole_dur={duration:.3f}"]
        audio_input = "1:a:0"

    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            audio_input,
            "-vf",
            f"scale={width}:{height}:flags=lanczos,fps={fps},setsar=1,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            *audio_filter,
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    _run(command, label=f"Rendering scene segment {output_path.stem}")


def assemble_video(project: ProjectSpec, frame_paths: list[Path], output_path: str | Path) -> Path:
    """Encode and concatenate still frames into an MP4, with optional BGM."""

    if len(frame_paths) != len(project.scenes):
        raise ValueError("There must be exactly one rendered frame for each project scene")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg is not installed or not on PATH. Install FFmpeg before rendering a video."
        )

    final_path = Path(output_path).expanduser().resolve()
    if final_path.suffix.lower() != ".mp4":
        raise ValueError("Video output path must use the .mp4 extension")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    durations = _scene_durations(project)
    total_duration = sum(durations)

    with tempfile.TemporaryDirectory(prefix="pixelle-video-", dir=final_path.parent) as work_dir:
        work = Path(work_dir)
        segments: list[Path] = []
        for index, (scene, frame_path, duration) in enumerate(
            zip(project.scenes, frame_paths, durations), start=1
        ):
            segment = work / f"segment-{index:03d}.mp4"
            _render_scene_segment(
                frame_path=frame_path,
                audio_path=scene.audio_path,
                duration=duration,
                output_path=segment,
                width=project.width,
                height=project.height,
                fps=project.fps,
            )
            segments.append(segment)

        concat_list = work / "segments.txt"
        concatenated = work / "concatenated.mp4"
        _concat_file_list(segments, concat_list)
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(concatenated),
            ],
            label="Concatenating scene segments",
        )

        if project.bgm is None:
            shutil.copy2(concatenated, final_path)
        else:
            volume = project.bgm.volume
            filter_complex = (
                f"[1:a:0]volume={volume:.4f},atrim=duration={total_duration:.3f},"
                "asetpts=PTS-STARTPTS[bgm];"
                "[0:a:0][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
            )
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(concatenated),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(project.bgm.path),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "0:v:0",
                    "-map",
                    "[aout]",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ar",
                    "48000",
                    "-t",
                    f"{total_duration:.3f}",
                    "-movflags",
                    "+faststart",
                    str(final_path),
                ],
                label="Mixing background music",
            )

    return final_path
