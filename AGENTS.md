# Agent instructions

When asked to make a video from a topic or script, follow `.agents/skills/arena-video/SKILL.md` and produce project files and/or a rendered video rather than returning only a plan.

## Non-negotiable boundaries

- Use the Arena agent's native image-generation tool for scene images. Save each result as a local file under the active project and put that exact relative path in `project.json`.
- Do **not** invent an Arena HTTP endpoint, call third-party image-generation APIs, add model API keys, or restore Pixelle's ComfyUI/RunningHub/provider adapters.
- Do not add Streamlit, FastAPI, web UI, remote task servers, or background polling services. This project is a tool-using Agent workflow plus a local renderer.
- Use only documented sources for factual claims. Preserve source URLs in `sources`; distinguish sourced facts from creative narration.
- Do not claim a video or generated asset exists until the file is present and validated.
- Keep user content and generated media in `projects/<slug>/`; large outputs are ignored by Git.

## Before delivery

1. Validate the project with `python -m pixelle_agent validate <project.json> --check-assets`.
2. If dependencies and browser binaries are installed, render with `python -m pixelle_agent render <project.json>` and verify the output file exists and is non-empty.
3. Only when the user requests Jianying, optionally create a draft with `python -m pixelle_agent draft <project.json>`; explain that captions are baked into scene frames and final MP4 export is manual in the desktop editor.
4. If rendering cannot run because FFmpeg/Chromium is unavailable, state the exact missing dependency and leave a valid project manifest and local assets; never claim the MP4 was produced.
5. Run `python -m unittest discover -s tests -v` after changing project code.
