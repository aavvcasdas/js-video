# -*- coding: utf-8 -*-
"""
对照表 / AI 回复解析

对照表格式和 auto-catvideo 完全兼容，并新增了可选的第 4 列「标签」：

    01 | shot_01.jpg | 文案内容
    01 | shot_01.jpg | 文案内容 | 《认知觉醒》      ← 第 4 列：这一镜的顶部标签（书名 / Day 3 / 作者 …）
    01  文案内容                                     ← 简写，图片默认 shot_01.jpg

AI 回复（按 prompts/ 里的模板生成）由若干【小节】组成：
    【标题】【封面文案】【引导语】【对照表】【生图提示词】【标签】
"""

import os
import re
from typing import Dict, List, Optional

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


class Shot:
    __slots__ = ("seq", "text", "image", "tag")

    def __init__(self, seq: int, text: str, image: str, tag: str = ""):
        self.seq, self.text, self.image, self.tag = seq, text, image, tag

    def __repr__(self):
        return f"Shot({self.seq:02d}, {self.image}, {self.text[:16]!r}, tag={self.tag!r})"


_PIPE = re.compile(r"^\s*(?:分镜|镜头)?\s*(\d+)\s*[|｜]\s*([^|｜]+?)\s*[|｜]\s*([^|｜]*?)\s*(?:[|｜]\s*(.*?))?\s*$")
_SIMPLE = re.compile(r"^\s*(\d+)[\s.．、:：]+(.+)$")


def parse_mapping_text(content: str) -> List[Shot]:
    shots: List[Shot] = []
    for line in content.splitlines():
        line = line.strip().strip("`")
        if not line or line.startswith(("#", "---", "格式", "【")) or "镜头字幕对照表" in line:
            continue
        m = _PIPE.match(line)
        if m:
            seq = int(m.group(1))
            img = m.group(2).strip()
            text = (m.group(3) or "").strip()
            tag = (m.group(4) or "").strip()
            if "无配套字幕" in text:
                continue
            if not img.lower().endswith(IMAGE_EXTS):
                # 第二列不是文件名（比如有人把文案写在第二列），按 文案|标签 理解
                text, tag, img = img, text, f"shot_{seq:02d}.jpg"
            shots.append(Shot(seq, text, img, tag))
            continue
        m = _SIMPLE.match(line)
        if m:
            seq = int(m.group(1))
            shots.append(Shot(seq, m.group(2).strip(), f"shot_{seq:02d}.jpg"))
    return shots


def parse_mapping_file(path: str) -> List[Shot]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return parse_mapping_text(f.read())


def find_image(image_dir: str, filename: str, seq: Optional[int] = None) -> Optional[str]:
    """兼容 jpg/png/webp 互换、shot_1 / shot_01 / scene_01 等写法。"""
    if not image_dir or not os.path.isdir(image_dir):
        return None
    names = []
    base, _ = os.path.splitext(filename)
    names.append(filename)
    names += [base + e for e in IMAGE_EXTS]
    if seq is not None:
        for stem in (f"shot_{seq:02d}", f"shot_{seq}", f"scene_{seq:02d}", f"{seq:02d}", f"{seq}"):
            names += [stem + e for e in IMAGE_EXTS]
    lower = {n.lower(): n for n in os.listdir(image_dir)}
    for n in names:
        real = lower.get(n.lower())
        if real:
            return os.path.join(image_dir, real)
    return None


# ----------------------------------------------------------------------------
# AI 回复解析
# ----------------------------------------------------------------------------
_SECTION = re.compile(r"^\s*[#>*\s]*【([^】]+)】\s*[:：]?\s*(.*)$")


def split_sections(text: str) -> Dict[str, str]:
    """把 AI 回复按【小节】切开，返回 {小节名: 内容}。"""
    sections: Dict[str, List[str]] = {}
    current = None
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, [])
            if m.group(2).strip():
                sections[current].append(m.group(2).strip())
            continue
        if current is not None:
            sections[current].append(line.rstrip())
    out = {}
    for k, lines in sections.items():
        body = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()
        out[k] = body
    return out


def parse_llm_reply(text: str) -> Dict:
    """
    解析按 prompts/ 模板生成的 AI 回复。

    Returns:
        {"title", "cover", "hook", "mapping_text", "shots", "image_prompts": {seq: prompt}, "extra": {...}}
    """
    sec = split_sections(text)
    mapping_text = sec.get("对照表", "")
    shots = parse_mapping_text(mapping_text) if mapping_text else parse_mapping_text(text)
    prompts: Dict[int, str] = {}
    for line in sec.get("生图提示词", "").splitlines():
        m = re.match(r"^\s*(?:分镜|镜头)?\s*(\d+)\s*[|｜.．、:：]\s*(?:shot_\d+\.\w+\s*[|｜]\s*)?(.+)$", line.strip())
        if m:
            prompts[int(m.group(1))] = m.group(2).strip()
    first_line = lambda s: (s or "").strip().splitlines()[0].strip() if (s or "").strip() else ""
    known = {"标题", "封面文案", "引导语", "对照表", "生图提示词"}
    return {
        "title": first_line(sec.get("标题")),
        "cover": sec.get("封面文案", "").strip(),
        "hook": first_line(sec.get("引导语")),
        "mapping_text": mapping_text,
        "shots": shots,
        "image_prompts": prompts,
        "extra": {k: v for k, v in sec.items() if k not in known},
    }


def write_mapping_file(path: str, shots: List[Shot], title: str = ""):
    lines = [f"# {title}" if title else "# 镜头字幕对照表",
             "# 格式：镜头编号 | 图片文件名 | 字幕/口播文案 | 顶部标签(可选)", ""]
    for s in shots:
        row = f"{s.seq:02d} | {s.image} | {s.text}"
        if s.tag:
            row += f" | {s.tag}"
        lines.append(row)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
