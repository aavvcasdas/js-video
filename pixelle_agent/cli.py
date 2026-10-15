"""Command line entrypoint for validation and local rendering."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from . import __version__
from .manifest import ManifestError, load_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pixelle-video",
        description="Validate, render, or create a Jianying draft from an Arena-agent project.",
    )
    parser.add_argument("--version", action="version", version=f"pixelle-video {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a project JSON manifest")
    validate.add_argument("project", type=Path, help="path to project.json")
    validate.add_argument(
        "--check-assets",
        action="store_true",
        help="also require all referenced image/audio files to exist",
    )

    render = commands.add_parser("render", help="render a project to an MP4 file")
    render.add_argument("project", type=Path, help="path to project.json")
    render.add_argument(
        "--output",
        type=Path,
        help="output MP4 path (relative to the current directory, overrides video.output)",
    )

    draft = commands.add_parser("draft", help="create a Jianying project draft")
    draft.add_argument("project", type=Path, help="path to project.json")
    draft.add_argument(
        "--draft-root",
        type=Path,
        help="Jianying draft root folder; defaults to <project>/output/jianying_drafts",
    )
    return parser


def _render(project_path: Path, output_override: Path | None) -> Path:
    project = load_project(project_path, check_assets=True)
    from .renderer import render_frames
    from .video import assemble_video

    output = output_override
    if output is None:
        output = project.root / project.output
    elif not output.is_absolute():
        output = Path.cwd() / output

    print(f"Rendering {len(project.scenes)} scene(s) for {project.title!r} …")
    with tempfile.TemporaryDirectory(prefix="pixelle-frames-") as frame_dir:
        frames = render_frames(project, Path(frame_dir))
        final_path = assemble_video(project, frames, output)
    return final_path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            project = load_project(args.project, check_assets=args.check_assets)
            mode = "manifest and assets" if args.check_assets else "manifest"
            print(
                f"Valid {mode}: {project.title!r} — {len(project.scenes)} scene(s), "
                f"{project.width}x{project.height} at {project.fps} fps, "
                f"template {project.template}"
            )
            if not args.check_assets:
                print("Run with --check-assets before rendering to verify generated media files.")
            return 0

        if args.command == "draft":
            from .jianying import export_jianying_draft

            draft_path = export_jianying_draft(args.project, args.draft_root)
            print(f"Jianying draft created at: {draft_path}")
            print("Open/copy this draft folder with the Jianying desktop app; MP4 export is manual.")
            return 0

        final_path = _render(args.project, args.output)
        print(f"Video written to: {final_path}")
        return 0
    except (ManifestError, RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
