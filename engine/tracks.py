# -*- coding: utf-8 -*-
"""赛道预设加载 + 文案提示词拼装"""

import copy
import json
import os
import re
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS_DIR = os.path.join(ROOT, "tracks")
PROMPTS_DIR = os.path.join(ROOT, "prompts")


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def list_tracks() -> List[str]:
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(TRACKS_DIR)
        if f.endswith(".json") and not f.startswith("_")
    )


def load_track(name: str, overrides: Optional[dict] = None) -> dict:
    path = os.path.join(TRACKS_DIR, f"{name}.json")
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 没有这个赛道：{name}\n   可选：{'、'.join(list_tracks())}")
    preset = deep_merge(_load_json(os.path.join(TRACKS_DIR, "_base.json")), _load_json(path))
    if overrides:
        preset = deep_merge(preset, overrides)
    return preset


def parse_range(v, default=(10, 14)):
    """'10-14' / 12 / [10,14] → (lo, hi)"""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return int(v[0]), int(v[1])
    if isinstance(v, (int, float)):
        return int(v), int(v)
    m = re.match(r"\s*(\d+)\s*[-~～到]\s*(\d+)\s*", str(v or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    return default


def hex_to_rgb(h) -> tuple:
    if isinstance(h, (list, tuple)):
        return tuple(float(x) for x in h[:3])
    h = str(h or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def fill_vars(text: str, variables: Dict) -> str:
    """把 {series} {title} {day} 这类占位符替换成实际值，未知的占位符原样保留。"""
    if not text:
        return ""
    return re.sub(r"\{(\w+)\}", lambda m: str(variables.get(m.group(1), m.group(0))), str(text))


# ----------------------------------------------------------------------------
# 文案提示词
# ----------------------------------------------------------------------------
_TAG_EXAMPLES = {
    "语录": " | ——作者",
    "书单": " | 《书名》",
}


def build_copy_prompt(track: str, topic: str, preset: dict, extra: str = "") -> str:
    """把 _通用规则.md + <赛道>.md 拼成一份完整的提示词，可以直接发给豆包 / DeepSeek / GPT。"""
    common = open(os.path.join(PROMPTS_DIR, "_通用规则.md"), encoding="utf-8").read()
    track_md_path = os.path.join(PROMPTS_DIR, f"{track}.md")
    track_md = open(track_md_path, encoding="utf-8").read() if os.path.isfile(track_md_path) else ""

    lo, hi = parse_range(preset.get("shots", {}).get("count"), (10, 14))
    t_lo, t_hi = parse_range(preset.get("shots", {}).get("total_chars"), (260, 380))
    speed = float(preset.get("voice", {}).get("speed", 1.0))
    sec_lo, sec_hi = int(t_lo / 4.5 / speed), int(t_hi / 4.5 / speed)  # 中文 TTS 约 4.5 字/秒

    character = preset.get("character", "")
    style = preset.get("image_style", {})
    v = {
        "track": track,
        "topic": topic,
        "series": preset.get("series", "") or track,
        "copy_style": preset.get("copy_style", ""),
        "shots": f"{lo}-{hi}" if lo != hi else str(lo),
        "chars_per_shot": preset.get("shots", {}).get("chars_per_shot", "18-35"),
        "total_chars": f"{t_lo}-{t_hi}",
        "seconds": f"{sec_lo}-{sec_hi}",
        "aspect": preset.get("image_aspect", "9:16"),
        "style_jimeng": style.get("jimeng", ""),
        "style_mj": style.get("mj", ""),
        "character": character,
        "face_rule": "这是不露脸账号：画面里不出现真人正脸，人物只能是背影、剪影、手部特写或卡通形象。",
        "character_rule": f"- 角色锁定：每一张图都要带上角色锚定句「{character}」，保证每一镜都是同一个角色。" if character else "",
        "tag_example": _TAG_EXAMPLES.get(track, ""),
        "comment_extra": "，以及本期书单汇总（书名 + 作者）" if track == "书单" else (
            "，以及本期语录的出处" if track == "语录" else ""),
        "extra_info": (f"- 补充要求：{extra}" if extra else ""),
    }
    body = fill_vars(common, v)
    if track_md:
        body = body.replace("# 通用生图规则", fill_vars(track_md, v).strip() + "\n\n# 通用生图规则", 1)
    return body.strip() + f"\n\n现在请为主题「{topic}」创作。\n"
