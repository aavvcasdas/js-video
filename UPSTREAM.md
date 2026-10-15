# Upstream provenance

This adaptation starts from **[ATH-MaaS/Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video)**, fetched on 2026-10-15 at source commit `848b054e4fae40dabc62ec58e960b573e83793ac` (shallow clone of the upstream `main` branch).

## Retained

- Static HTML image-card templates under `templates/`, based on upstream files. Google Fonts links were removed for offline/deterministic rendering; the cartoon template's remote decorative background was replaced with a CSS gradient. Each modified HTML file carries an adaptation comment.
- The upstream Apache `LICENSE` and relevant attribution notices; the original NOTICE entries for unused UI/API dependencies were omitted.

## Replaced or intentionally omitted

- The Streamlit web interface, FastAPI service/API, provider clients, ComfyUI/RunningHub workflows, API credentials/configuration, and remote LLM/image-generation integrations are not included.
- `pixelle_agent/` is a small local renderer and manifest validator written for this adaptation. It consumes local scene assets created/provided by the Agent or user; image generation is performed by the current Arena agent's native tool, not by an undocumented HTTP endpoint.
- Project instructions and the agent workflow are in `AGENTS.md` and `.agents/skills/arena-video/SKILL.md`.

## Optional Jianying draft support

The `vendor/pyJianYingDraft/` package is adapted from the vendored copy at [`aavvcasdas/auto-catvideo/jianying-editor-skill-main/scripts/vendor/pyJianYingDraft`](https://github.com/aavvcasdas/auto-catvideo/tree/main/jianying-editor-skill-main/scripts/vendor/pyJianYingDraft), fetched at parent repository commit `fc8fc7fc2329150694e314f2debab34b42215769`. Its MIT license is retained at `vendor/pyJianYingDraft/LICENSE`. The Windows-only editor UI controller and auto-export code are deliberately omitted; this project only uses the portable JSON draft-writing classes and does not copy the referenced Skill's broader UI automation or cloud APIs.

For source history and license terms, see the upstream repositories and the included `LICENSE`, `NOTICE`, and `vendor/pyJianYingDraft/LICENSE` files.
