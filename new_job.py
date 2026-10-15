#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新建一条视频的工作目录（第 1 步）

用法：
  python new_job.py 冷知识 "为什么飞机的窗户都是圆的"
  python new_job.py 自律 "早起的三个小技巧" --day 7
  python new_job.py 书单 "精神内耗的人必看的5本书" --auto            # 配了 llm：自动写文案
  python new_job.py 打工人猫 "周一早高峰" --auto --images           # 再配了 image：自动出图
  python new_job.py --parse jobs/冷知识/20261015_xxx                 # 手动粘贴 AI 回复后解析
  python new_job.py --images jobs/冷知识/20261015_xxx                # 只补出图
  python new_job.py --placeholder jobs/冷知识/20261015_xxx           # 用占位图先看版式

会生成：
  jobs/<赛道>/<日期>_<主题>/
    job.json                 本条视频的参数（标题、Day、BGM、样式覆盖）
    01_发给AI的提示词.md      复制给 豆包 / DeepSeek / GPT
    02_AI回复.txt            把 AI 的回复整段粘贴进来（--auto 时自动写入）
    对照表.txt               解析出来的「镜号 | 图片 | 文案 | 标签」
    03_生图提示词.txt        每镜一条，复制到即梦 / MJ，或者用 --images 自动出图
    image/                   放 shot_01.jpg、shot_02.jpg ...
"""

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine import ai_api  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.draft_paths import sanitize_name  # noqa: E402
from engine.script_io import parse_llm_reply, write_mapping_file, parse_mapping_file  # noqa: E402
from engine.tracks import build_copy_prompt, list_tracks, load_track  # noqa: E402

REPLY_FILE = "02_AI回复.txt"
PROMPT_FILE = "01_发给AI的提示词.md"
IMG_PROMPT_FILE = "03_生图提示词.txt"
REPLY_PLACEHOLDER = "# 把 AI 的完整回复粘贴到这里（覆盖这一行），然后运行：python new_job.py --parse <本目录>\n"


def load_job(job_dir: str) -> dict:
    f = os.path.join(job_dir, "job.json")
    if not os.path.isfile(f):
        raise SystemExit(f"❌ {job_dir} 里没有 job.json，请先用 new_job.py 创建")
    return json.load(open(f, encoding="utf-8-sig"))


def save_job(job_dir: str, job: dict):
    with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def parse_reply(job_dir: str, quiet: bool = False) -> bool:
    """解析 02_AI回复.txt → 对照表.txt + 03_生图提示词.txt，并把标题和引导语写回 job.json"""
    reply_path = os.path.join(job_dir, REPLY_FILE)
    if not os.path.isfile(reply_path):
        return False
    text = open(reply_path, encoding="utf-8-sig").read()
    if not text.strip() or text.strip().startswith("# 把 AI"):
        if not quiet:
            print(f"⚠️ {REPLY_FILE} 还是空的：先把 AI 回复粘贴进去")
        return False
    r = parse_llm_reply(text)
    if not r["shots"]:
        print("❌ 没解析到【对照表】，检查 AI 回复的格式（每行：01 | shot_01.jpg | 文案）")
        return False
    job = load_job(job_dir)
    job["title"] = job.get("title") or r["title"]
    job["hook"] = job.get("hook") or r["hook"]
    if r["cover"]:
        job["cover"] = r["cover"]
    save_job(job_dir, job)
    write_mapping_file(os.path.join(job_dir, "对照表.txt"), r["shots"], job.get("title", ""))

    preset = load_track(job["track"], job.get("overrides"))
    style = preset.get("image_style", {}).get("jimeng", "")
    lines = [f"# 风格前缀（每张都带上）：{style}", f"# 比例：{preset.get('image_aspect', '9:16')}", ""]
    for s in r["shots"]:
        pr = r["image_prompts"].get(s.seq, "")
        if pr and style and style[:8] not in pr:
            pr = f"{style}，{pr}"  # AI 忘了带风格前缀就自动补上
        lines.append(f"{s.seq:02d} | {s.image} | {pr}")
    with open(os.path.join(job_dir, IMG_PROMPT_FILE), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if not quiet:
        print(f"✅ 解析完成：{len(r['shots'])} 镜")
        print(f"   标题：{job.get('title')}")
        print(f"   引导语：{job.get('hook')}")
        print(f"   → 对照表.txt / {IMG_PROMPT_FILE}")
    return True


def read_image_prompts(job_dir: str) -> dict:
    out = {}
    f = os.path.join(job_dir, IMG_PROMPT_FILE)
    if not os.path.isfile(f):
        return out
    for line in open(f, encoding="utf-8-sig"):
        m = re.match(r"^\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.+)$", line.strip())
        if m:
            out[int(m.group(1))] = (m.group(2).strip(), m.group(3).strip())
    return out


def gen_images(job_dir: str, cfg: dict, force: bool = False):
    img_cfg = dict(cfg.get("image") or {})
    if not ai_api.configured(img_cfg):
        raise SystemExit("❌ config.json 的 image 段没配好（base_url / api_key / model）")
    job = load_job(job_dir)
    preset = load_track(job["track"], job.get("overrides"))
    aspect = preset.get("image_aspect", "9:16")
    size = (img_cfg.get("size_by_aspect") or {}).get(aspect)
    if size:
        img_cfg["size"] = size
    prompts = read_image_prompts(job_dir)
    if not prompts:
        raise SystemExit(f"❌ 没有 {IMG_PROMPT_FILE}，先 --parse")
    img_dir = os.path.join(job_dir, "image")
    os.makedirs(img_dir, exist_ok=True)
    for seq, (fname, pr) in sorted(prompts.items()):
        out = os.path.join(img_dir, os.path.splitext(fname)[0] + ".jpg")
        if os.path.exists(out) and not force:
            print(f"  · {seq:02d} 已存在，跳过")
            continue
        print(f"  🎨 {seq:02d} 出图中... {pr[:40]}")
        try:
            ai_api.generate_image(img_cfg, f"{pr}，竖版构图，比例{aspect}", out)
        except Exception as e:
            print(f"     ✗ {e}")
    print("✅ 出图结束（失败的可以重跑，已存在的会跳过）")


def placeholder_images(job_dir: str):
    """用纯色占位图补齐缺的图，方便先在剪映里看版式。"""
    from PIL import Image, ImageDraw
    job = load_job(job_dir)
    preset = load_track(job["track"], job.get("overrides"))
    aw, ah = [int(x) for x in preset.get("image_aspect", "9:16").split(":")]
    w = 1080
    h = int(w * ah / aw)
    shots = parse_mapping_file(os.path.join(job_dir, "对照表.txt"))
    img_dir = os.path.join(job_dir, "image")
    os.makedirs(img_dir, exist_ok=True)
    palette = [(242, 196, 120), (150, 196, 230), (190, 160, 220), (160, 210, 170), (240, 160, 150), (120, 140, 170)]
    n = 0
    for s in shots:
        out = os.path.join(img_dir, s.image)
        if any(os.path.exists(os.path.join(img_dir, os.path.splitext(s.image)[0] + e))
               for e in (".jpg", ".jpeg", ".png", ".webp")):
            continue
        im = Image.new("RGB", (w, h), palette[s.seq % len(palette)])
        dr = ImageDraw.Draw(im)
        for i in range(0, w + h, 60):  # 斜线纹理，方便看 Ken Burns 动没动
            dr.line([(i, 0), (i - h, h)], fill=tuple(max(0, c - 18) for c in palette[s.seq % len(palette)]), width=6)
        dr.rectangle([w * 0.3, h * 0.42, w * 0.7, h * 0.58], outline=(255, 255, 255), width=8)
        dr.text((w * 0.47, h * 0.49), f"{s.seq:02d}", fill=(255, 255, 255))
        im.save(out if out.lower().endswith((".jpg", ".jpeg")) else os.path.splitext(out)[0] + ".jpg", quality=88)
        n += 1
    print(f"✅ 生成占位图 {n} 张（{w}x{h}，{preset.get('image_aspect')}）")


def create(track: str, topic: str, args, cfg: dict) -> str:
    preset = load_track(track)
    date = time.strftime("%Y%m%d")
    job_dir = os.path.join(ROOT, "jobs", track, f"{date}_{sanitize_name(topic, 30)}")
    if os.path.exists(os.path.join(job_dir, "job.json")) and not args.force:
        print(f"⚠️ 已存在：{job_dir}（加 --force 覆盖提示词）")
    os.makedirs(os.path.join(job_dir, "image"), exist_ok=True)
    job = {"track": track, "topic": topic, "title": "", "hook": "",
           "day": args.day if args.day is not None else preset.get("day", 1),
           "bgm": "", "vars": {}, "overrides": {}}
    if os.path.exists(os.path.join(job_dir, "job.json")):
        old = load_job(job_dir)
        old.update({k: v for k, v in job.items() if k in ("track", "topic")})
        job = old
    save_job(job_dir, job)

    prompt = build_copy_prompt(track, topic, preset, extra=args.extra or "")
    with open(os.path.join(job_dir, PROMPT_FILE), "w", encoding="utf-8") as f:
        f.write(prompt)
    reply = os.path.join(job_dir, REPLY_FILE)
    if not os.path.exists(reply):
        with open(reply, "w", encoding="utf-8") as f:
            f.write(REPLY_PLACEHOLDER)

    rel = os.path.relpath(job_dir, ROOT)
    print(f"✅ 已创建：{rel}")
    print(f"   赛道：{track} ｜ 画面：{preset['image_style'].get('name')} ｜ 比例 {preset.get('image_aspect')}"
          f" ｜ 音色 {preset['voice']['speaker']}")

    if args.auto:
        llm = cfg.get("llm") or {}
        if not ai_api.configured(llm):
            print("⚠️ config.json 的 llm 段没配置，跳过自动写文案。请手动复制提示词给 AI。")
        else:
            print(f"🤖 调用 {llm.get('model')} 写文案...")
            text = ai_api.chat(llm, prompt)
            with open(reply, "w", encoding="utf-8") as f:
                f.write(text)
            parse_reply(job_dir)
            if args.images:
                gen_images(job_dir, cfg)
    if not args.auto:
        print("\n下一步：")
        print(f"  1) 把 {rel}/{PROMPT_FILE} 的全部内容发给 豆包 / DeepSeek / GPT")
        print(f"  2) 把回复粘贴进 {rel}/{REPLY_FILE}，运行  python new_job.py --parse \"{rel}\"")
        print(f"  3) 按 {IMG_PROMPT_FILE} 出图，存成 image/shot_01.jpg ...（或者用 --images 自动出图）")
        print(f"  4) python make_video.py \"{rel}\"")
    else:
        print(f"\n下一步：确认 image/ 里的图都齐了 → python make_video.py \"{rel}\"")
    return job_dir


def main():
    ap = argparse.ArgumentParser(description="新建 / 解析 一条视频的工作目录")
    ap.add_argument("track", nargs="?", help="赛道：" + "、".join(list_tracks()))
    ap.add_argument("topic", nargs="?", help="本期主题")
    ap.add_argument("--day", type=int, help="自律打卡的天数（显示在标题 Day N）")
    ap.add_argument("--extra", help="给 AI 的补充要求，例如“结尾提到我的系列名”")
    ap.add_argument("--auto", action="store_true", help="用 config.json 的 llm 自动写文案")
    ap.add_argument("--images", nargs="?", const=True, default=False, metavar="JOB_DIR",
                    help="用 config.json 的 image 自动出图（可单独跟一个已有目录）")
    ap.add_argument("--parse", metavar="JOB_DIR", help="解析已粘贴好的 02_AI回复.txt")
    ap.add_argument("--placeholder", metavar="JOB_DIR", help="用占位图补齐缺图（先看版式用）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true", help="列出所有赛道")
    args = ap.parse_args()
    cfg = load_config()

    if args.list:
        for t in list_tracks():
            p = load_track(t)
            print(f"  {t:<6} {p['image_style'].get('name', '')} ｜ {p.get('image_aspect')} ｜ {p['voice']['speaker']}")
        return
    if args.parse:
        parse_reply(args.parse)
        return
    if args.placeholder:
        placeholder_images(args.placeholder)
        return
    if isinstance(args.images, str) and not args.track:
        gen_images(args.images, cfg, force=args.force)
        return
    if not args.track or not args.topic:
        ap.print_help()
        print("\n可选赛道：" + "、".join(list_tracks()))
        return
    create(args.track, args.topic, args, cfg)


if __name__ == "__main__":
    main()
