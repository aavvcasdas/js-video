---
name: arena-video
description: Create research-grounded short videos with Arena-native image generation and Pixelle-Video templates.
---

# Arena Video Production Skill

Use this skill when the user asks to turn a topic, outline, or script into a short video. The Arena Agent owns creative decisions and native tool calls; the Python CLI is only a deterministic local renderer.

## 1. Clarify only what blocks production

Use the user's brief as the source of truth. If unspecified, default to Chinese, vertical 9:16, a concise 30–60 second video, and 5–8 scenes. Ask a compact set of questions only when audience, platform/format, factual risk, or approval requirements materially change the result. Do not ask about details already supplied.

## 2. Research and write the script

- For factual or current topics, browse with the tools available in the current Arena session. Prefer primary sources, record URLs and access dates, and do not add a claim that the sources do not support.
- For creative topics, do not invent research citations; leave `sources` empty unless sources were actually consulted.
- Write a strong opening, one idea per scene, concise spoken narration, short on-screen captions, and a clear ending. Keep essential nuance; do not turn uncertain claims into certainties.
- Create a project folder at `projects/<short-slug>/`, copy `examples/starter/project.json`, then fill in the manifest. Use `project.schema.json` as the schema reference.
- Each scene needs a unique ID, narration, a short caption, an image prompt, a project-relative image path under `assets/scenes/`, and either a duration or an audio path. Prefer durations matching speech; if both duration and audio are present, the duration is the target.
- Keep captions readable on mobile: one short phrase or at most two brief lines. Do not put dense narration paragraphs on screen.

## 3. Generate scene images with Arena

- Use the **native image-generation capability exposed by the current Arena agent session**. This is an agent tool call, not a Python/HTTP API. Never guess an endpoint, create an API key, use an external provider SDK, or silently substitute a different image service.
- Generate **one standalone image per scene**. Do not ask for a contact sheet, grid, collage, or storyboard sheet. Since images are assets inside a larger video project, do not request user-facing image options unless the user explicitly asks for alternatives.
- Save each generated image directly to the path in the manifest, for example `projects/<slug>/assets/scenes/scene-01.png`, and set `scenes[i].image` to that exact relative path. Use PNG, JPEG, or WebP.
- Keep one visual style, palette, lighting, and recurring character/subject across the full video. Prompts should specify the intended composition and leave clean space for captions.
- Ask for no lettering, captions, logos, or watermarks inside generated images; captions are rendered separately from the manifest.
- If the current session does not expose an image-generation tool, stop at a truthful prompt pack and ask the user to provide assets or run the project in an Arena-enabled session. Do not pretend a prompt or API response is a generated image.

## 4. Narration audio (optional)

If the user wants voiceover and a native Arena speech tool is available, use that tool rather than adding an external TTS provider. Follow its voice-selection flow when required, then save each scene's speech to `projects/<slug>/assets/audio/scene-01.mp3` (or another supported audio extension) and use the same selected voice throughout. Respect per-call text limits. User-provided audio is also valid. If neither is available, keep `audio` absent, set a reasonable `duration`, and tell the user that the render will be silent; do not imply that duration alone creates speech.

## 5. Validate, render, and inspect

1. Write `project.json`, adding research citations under `sources` and keeping media paths relative to that project folder.
2. Run `python -m pixelle_agent validate projects/<slug>/project.json` while the project is still being prepared.
3. Once all generated images/audio are saved, run `python -m pixelle_agent validate projects/<slug>/project.json --check-assets`.
4. If FFmpeg, FFprobe, Playwright, and Chromium are installed, run `python -m pixelle_agent render projects/<slug>/project.json`.
5. Verify that the output MP4 exists and has non-zero size. Inspect the rendered result when video/image inspection tools are available: check crop, continuity, legibility, scene order, audio timing, and factual captions. Correct and rerender if needed.
6. Only if the user asks for a Jianying draft, install the `render,draft` extras and run `python -m pixelle_agent draft projects/<slug>/project.json`. Treat this as best-effort: the draft contains editable scene clips and audio tracks, but captions are baked into the scene images; open and verify it in the user's Jianying desktop app. Do not claim app compatibility or MP4 export was verified in this environment.
7. Report the actual project/asset/video/draft paths and disclose any dependency or tool limitation. Do not claim an MP4 was rendered unless the file was verified.

## Manifest example

```json
{
  "schema_version": 1,
  "project": { "title": "Example", "language": "zh-CN", "author": "" },
  "video": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "template": "1080x1920/image_default.html",
    "output": "output/example.mp4"
  },
  "scenes": [
    {
      "id": "scene-01",
      "title": "Example",
      "narration": "One concise spoken sentence.",
      "caption": "Short on-screen line",
      "image_prompt": "Vertical 9:16 editorial image, no text or watermark.",
      "image": "assets/scenes/scene-01.png",
      "duration": 4.5
    }
  ],
  "sources": []
}
```
