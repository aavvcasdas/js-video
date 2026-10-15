# js-video：不露脸图文号 · 多赛道一键出剪映草稿

在 [auto-catvideo](https://github.com/aavvcasdas/auto-catvideo) 的流程上扩展成 **6 个赛道模板**：

| 赛道 | 画面风格 | 版式 | 默认音色 | 片头 |
|---|---|---|---|---|
| 冷知识 | 毛毡微缩风（InsightCut「毛毡风」） | 9:16 满屏 + 黄色系列标题 | 小林科普 `zh_male_iclvop_xiaolinkepu` | 快闪 + 音效 |
| 心理学 | 治愈系概念插画（InsightCut 治愈系 + Pixelle concept） | Pixelle「心理卡片」：黑底 + 1:1 图居中 | `zh_female_inspirational` | 引导语大字 |
| 语录 | 电影胶片意境（InsightCut「电影胶片」） | 9:16 满屏，宋体/毛笔字，出处标签 | 情感男声 `zh_male_iclvop_miaojijsqinggan` | 引导语大字 |
| 自律 | 电影质感高对比（InsightCut「电影质感」） | 9:16 满屏，「自律打卡 Day N」 | 纪录片男声 `ICL_zh_male_jilupianjmh` | 快闪 + 音效 |
| 书单 | 暖光油画阅读风（InsightCut「油彩」+ Pixelle book） | 深色底 + 3:4 图，书名/作者标签 | 纪录片女声 `ICL_zh_female_jilupianxq2` | 引导语大字 |
| 打工人猫 | 3D 盲盒猫打工人（固定橘猫角色） | 9:16 满屏，卡通字体 | 曼波 `ICL_zh_female_manbo_jianying` | 快闪 + 音效 |

文案规则综合了 **InsightCut**（口语化、给 TTS 读、一镜 1–3 句）和 **Pixelle-Video**（像朋友聊天、引用必须真实、开头不许重复、共鸣→观点→解释→启发）的提示词；
画面风格前缀取自两者的风格预设。调研过程见 [docs/冷知识赛道-开源项目调研-2026-10.md](docs/冷知识赛道-开源项目调研-2026-10.md)。

> 不涉及蒙版 / 蒙版关键帧。图片动效只用缩放 + 平移关键帧（Ken Burns），快闪片头也是纯缩放。

---

## 快速开始（Windows / macOS，已安装剪映专业版）

```bash
pip install -r requirements.txt

# 1. 新建一期：生成「发给 AI 的提示词」
python new_job.py 冷知识 "为什么飞机的窗户都是圆的"

# 2. 把 jobs/冷知识/<日期>_<主题>/01_发给AI的提示词.md 全部发给 豆包 / DeepSeek / GPT
#    回复整段粘贴进 02_AI回复.txt，然后解析：
python new_job.py --parse "jobs/冷知识/20261015_为什么飞机的窗户都是圆的"

# 3. 按 03_生图提示词.txt 去即梦出图，存成 image/shot_01.jpg、shot_02.jpg ...

# 4. 生成剪映草稿
python make_video.py "jobs/冷知识/20261015_为什么飞机的窗户都是圆的"
```

打开剪映首页就能看到草稿，检查一下字幕、换 BGM 就可以导出。一条视频的人工操作：发提示词 → 出图 → 运行脚本，约 5 分钟。

### 想更省事：全自动

复制 `config.example.json` 为 `config.json`，填上 `llm`（任意 OpenAI 兼容接口：DeepSeek、豆包/火山方舟、通义、Kimi……）和 `image`（火山方舟 Seedream 等兼容 `/images/generations` 的接口）：

```bash
python new_job.py 打工人猫 "周一早高峰" --auto --images   # 自动写文案 + 自动出图
python make_video.py "jobs/打工人猫/20261015_周一早高峰"
```

### 其他常用命令

```bash
python new_job.py --list                          # 看所有赛道
python new_job.py 自律 "早起的三个小技巧" --day 7   # 自律打卡第 7 天
python new_job.py --placeholder <目录>              # 没有图时用占位图，先看版式
python make_video.py <目录> --mock-tts             # 不调剪映配音，用静音占位，先看版式
python make_video.py "jobs/心理学/*"               # 批量出多个草稿
python make_video.py --where                       # 显示草稿会保存到哪里
# 音色 id 列表：vendor/jianying-editor-skill/data/tts_speakers.csv
```

仓库自带一个完整示例：`jobs/_示例/冷知识_飞机窗户为什么是圆的/`（AI 回复、对照表、生图提示词都有）：

```bash
python new_job.py --placeholder "jobs/_示例/冷知识_飞机窗户为什么是圆的"
python make_video.py "jobs/_示例/冷知识_飞机窗户为什么是圆的" --mock-tts
```

---

## 剪映草稿保存路径（保持一致）

以前常见的问题：脚本写到 A 目录，剪映实际读 B 目录，首页看不到；或者草稿引用了 `image/` 里的原图，移动工程目录后素材全部丢失；
多个草稿 `draft_id` 一样，剪映首页互相覆盖。现在的处理：

1. **只有一个草稿根目录**，按优先级确定，并写回环境变量 `JY_PROJECTS_ROOT`，skill 里的所有模块（包括配音的临时文件）都用它：
   `--drafts-root` > `config.json` 的 `drafts_root` > 环境变量 `JY_PROJECTS_ROOT` > **剪映「全局设置 → 草稿位置」**（自动读取剪映的 `globalSetting` 里的 `currentCustomDraftPath`）> 默认目录
   （Windows：`%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft`；macOS：`~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`）。
   如果你手动指定的目录和剪映设置不一致，会给出提醒。
2. **素材复制进草稿目录**：图片、音效、BGM 复制到 `<草稿>/materials/`，配音在 `<草稿>/temp_assets/`，草稿是自包含的，可以整体拷走。
   （`config.json` 里 `copy_media_into_draft: false` 可以关闭）
3. **补全草稿元信息**：`draft_meta_info.json` 写入真实的 `draft_fold_path` / `draft_root_path` / `draft_name`、唯一的 `draft_id`、时长和封面（第一张图），`draft_info.json` 的 id 也改成唯一值。
4. **保存后自动校验**：检查草稿引用的每个素材都存在、都在草稿目录内，结果写到 `<工作目录>/draft.json`。
5. 草稿名 = `config.json` 的 `draft_name_template`，默认 `{track}_{title}_{datetime}`，不会撞名。

---

## 目录结构

```
make_video.py           对照表 + 图片 → 剪映草稿
new_job.py              新建一期 / 解析 AI 回复 / 自动写文案和出图 / 占位图
config.example.json     草稿目录、命名、LLM、出图接口
tracks/                 赛道预设（版式、字体、音色、动效），_base.json 是公共默认值
prompts/                文案提示词：_通用规则.md + 每个赛道的专属规则
engine/                 构建器、草稿路径处理、对照表解析、AI 接口
assets/sfx/flash.wav    快闪片头音效
assets/bgm/<赛道>/      放你自己的 BGM（随机挑一首；不随仓库附带，注意版权）
vendor/                 jianying-editor-skill（剪映草稿底层库，MIT）
jobs/<赛道>/<日期_主题>/ 每一期的工作目录（不进 git）
```

一期的工作目录：

```
job.json                 track / topic / title / hook / day / bgm / overrides
01_发给AI的提示词.md
02_AI回复.txt
对照表.txt               01 | shot_01.jpg | 口播文案 | 标签(可选)
03_生图提示词.txt
image/shot_01.jpg ...
draft.json               生成结果：草稿名、目录、时长、路径校验
```

`对照表.txt` 兼容 auto-catvideo 的老格式（`01 | shot_01.jpg | 文案`），第 4 列是可选的顶部标签（语录写出处、书单写《书名》作者）。

---

## 自定义

**改某一期**：在 `job.json` 的 `overrides` 里写要覆盖的字段，例如换音色、关掉快闪：

```json
"overrides": {
  "voice": {"speaker": "ICL_zh_female_szrxinxin_jianying", "speed": 1.0},
  "opening": {"type": "hook"},
  "header": {"text": "{series}·第{day}期"}
}
```

**改整个赛道**：直接改 `tracks/<赛道>.json`；文案要求改 `prompts/<赛道>.md`。
**新增赛道**：复制一份 `tracks/冷知识.json` + `prompts/冷知识.md`，改名即可，`new_job.py --list` 会自动出现。

常用字段（完整列表见 `tracks/_base.json`）：

| 字段 | 说明 |
|---|---|
| `image_aspect` / `image_fit` | 出图比例；`cover` 铺满画布，`contain` 完整显示 + `background_color` 底色 |
| `voice.speaker` / `speed` / `group_chars` | 剪映音色 id、语速、多少字合成一段配音（越长语气越连贯） |
| `opening.type` | `flash` 快闪（引导语 + 5 张图依次弹出 + 音效）/ `hook` 引导语大字 / `none` |
| `first_effects` | 正片第一张图的剪映特效名，如 `变清晰`、`震动屏闪`、`幻彩故障` |
| `ken_burns.zoom` / `pan` | 推拉幅度和平移幅度 |
| `subtitle` / `header` / `tag` / `ending` / `disclaimer` | 字体（剪映免费字体名）、字号、颜色、描边、位置（`y`：+0.8 顶部，−0.8 底部） |
| `bgm.dir` / `volume` / `fade_out` | BGM 文件夹、音量、结尾淡出秒数 |

---

## 注意

- **AI 内容标识**：每个赛道默认带一行角落小字（如「内容由AI生成」），按平台规定不要删。
- **名言和数据要核实**：提示词已要求 AI 不得编造出处，但发布前请自己再查一遍（语录、书单、心理学尤其要注意）。
- 心理学内容不要写成诊断或治疗建议。
- 配音使用剪映自带的音色（需要联网），如果某段配音失败会重试 3 次，仍失败会在 `draft.json` 里记下来。
