# Pixelle Arena Video Agent

把 **ATH-MaaS/Pixelle-Video** 改造成面向 Arena Agent 的短视频制作项目：Agent 负责调研、脚本、分镜与 Arena 原生图片生成；本仓库只负责校验项目清单、渲染 Pixelle HTML 模板并用本机 FFmpeg 合成 MP4。

## 改造边界

- **Arena 生成图片：**图片生成通过 Agent 当前会话可用的 Arena 原生图像工具完成，按镜头保存到项目目录；这里不伪造一个未公开的 Arena REST endpoint，也不要求第三方生图 API key。
- **本地确定性渲染：**命令行只读取本地图片/音频和 `project.json`，不调用 LLM、图片模型、ComfyUI、RunningHub 或媒体供应商 API。
- **无 UI / Web 服务：**没有 Streamlit、FastAPI、浏览器控制面板或后台任务服务。Agent 的流程说明放在 `AGENTS.md` 与 `.agents/skills/arena-video/SKILL.md`。
- **旁白：**可以使用 Arena 当前会话提供的语音工具生成本地音频，也可以放入用户提供的音频。没有音频时，按分镜时长渲染为静音视频。

> Arena 图像生成功能在这里作为 Agent 工具使用，而非 Python 程序可直接调用的公共 API。若在非 Arena 环境运行 CLI，须先自行提供场景图片。

## 安装

需要 Python 3.11+、FFmpeg（含 `ffprobe`）和 Chromium；Linux 上建议另外安装 Noto CJK 字体（例如 Debian/Ubuntu 的 `fonts-noto-cjk`），否则模板会退回系统默认字体：

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e '.[render]'
playwright install chromium

# 若还需要输出剪映草稿（可选；在同一个 venv 中）
python -m pip install -e '.[render,draft]'
```

FFmpeg 请按操作系统安装并确认 `ffmpeg`、`ffprobe` 均在 `PATH` 中。安装后可运行纯标准库测试：

```bash
python -m unittest discover -s tests -v
```

## Agent 工作流

1. 将主题/脚本、语言、平台、画幅、时长和事实来源要求交给 Arena Agent；默认可采用中文、竖屏 9:16、约 30–60 秒。
2. Agent 按 skill 研究事实、整理来源并写出 `project.json`，把每个镜头的旁白、屏幕字幕、图片提示词、图片路径和时长放在同一条记录中。
3. Agent 使用 Arena **原生**图片生成工具逐镜头生成图片，保存到项目目录中的 `assets/scenes/`，而不是调用外部生图 API。若用户需要配音，使用当前会话可用的原生语音工具，或使用用户提供的音频文件。
4. 校验本地素材并渲染：

```bash
python -m pixelle_agent validate projects/my-video/project.json
python -m pixelle_agent validate projects/my-video/project.json --check-assets
python -m pixelle_agent render projects/my-video/project.json
```

### 可选：导出剪映草稿

安装 `.[render,draft]` 并执行 `playwright install chromium` 后，可以生成一份可由剪映桌面版打开的草稿目录：

```bash
python -m pixelle_agent draft projects/my-video/project.json
# 如要直接写入剪映草稿目录，可显式指定路径（请先确认路径）
python -m pixelle_agent draft projects/my-video/project.json --draft-root "/path/to/com.lveditor.draft"
```

草稿包含逐场景画面片段、独立旁白轨和可选 BGM 轨；字幕已经合成在场景卡片图片里，不是可编辑文字图层。BGM 不会自动循环；如果源音频短于视频，会提前结束。此功能只生成草稿，不会操作剪映 UI 或自动导出 MP4；需在剪映中打开、检查素材路径并手动导出。它面向中国大陆桌面版剪映草稿，不适用于 CapCut 国际版或手机端；Windows 优先，macOS/具体版本兼容性未验证。本仓库没有运行剪映桌面程序做端到端验证；覆盖已有草稿会被拒绝，请使用新的项目标题或草稿根目录。

也可安装命令行入口后使用 `pixelle-video` 替代 `python -m pixelle_agent`。MP4 默认输出路径来自 `video.output`；也可覆盖：

```bash
python -m pixelle_agent render projects/my-video/project.json --output output/my-video.mp4
```

## 项目清单

`project.schema.json` 是 JSON Schema，`examples/starter/project.json` 是可复制的起始范例。创建项目后，将示例里的占位提示词和素材路径换成真实内容：

```bash
mkdir -p projects/my-video/assets/scenes
cp examples/starter/project.json projects/my-video/project.json
```

每个场景至少需要 `id`、`narration`、本地图片 `image`，以及 `duration` 或可探测时长的 `audio`。路径相对于 `project.json`，禁止用 `..` 越出项目目录。渲染器会拒绝缺失素材、重复场景 ID、与模板不匹配的画幅和越出项目目录的素材路径；它本身不发起任何模型请求。

可选的 `sources` 用来记录 Agent 的事实来源；素材路径只接受 PNG、JPEG、WebP 与常见音频格式。多行 `caption` 会安全地转为换行显示，用户文本会在插入 HTML 模板前进行转义。

## Pixelle 模板

保留了上游的静态图片卡片模板（竖屏 `1080x1920`、横屏 `1920x1080`、方形 `1080x1080`），包括 `image_default`、`image_book`、`image_healing`、`image_film` 等风格；模板源文件在 `templates/`。为离线、确定性渲染，移除了 Google Fonts 网络请求，并把 `image_cartoon` 的远程装饰背景替换为本地 CSS 渐变；字幕与图像均来自项目内素材。渲染时按项目元数据覆盖模板中的品牌字段，不携带 Pixelle 的 Web UI、API 服务、模型客户端或工作流配置。

## 目录

- `AGENTS.md` — 仓库级 Agent 约定。
- `.agents/skills/arena-video/SKILL.md` — 选题到成片的详细 Agent 技能流程。
- `pixelle_agent/` — 清单校验、HTML 帧渲染与 FFmpeg 合成 CLI。
- `templates/` — 从 Pixelle-Video 复用的静态卡片模板。
- `UPSTREAM.md`、`LICENSE`、`NOTICE` — 上游来源和许可说明。
