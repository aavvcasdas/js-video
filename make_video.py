#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成剪映草稿（第 2 步）

用法：
  python make_video.py jobs/冷知识/20261015_为什么飞机窗户是圆的
  python make_video.py jobs/心理学/*            # 批量：一次生成多个草稿
  python make_video.py <目录> --mock-tts        # 不联网，用静音占位配音先看版式
  python make_video.py --where                  # 只打印草稿会保存到哪个目录
  python make_video.py --list-tracks

草稿目录的优先级：--drafts-root > config.json 的 drafts_root > 环境变量 JY_PROJECTS_ROOT
                  > 剪映「全局设置 → 草稿位置」 > 默认目录
"""

import argparse
import glob
import json
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine import draft_paths  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.script_io import parse_mapping_file  # noqa: E402
from engine.tracks import list_tracks, load_track  # noqa: E402


def build_one(job_dir: str, args, cfg: dict, root: str):
    from engine.builder import DraftBuilder
    import new_job

    job_dir = os.path.abspath(job_dir)
    job = new_job.load_job(job_dir)
    track = args.track or job.get("track")
    mapping = os.path.join(job_dir, "对照表.txt")
    if not os.path.isfile(mapping):
        # 没有对照表，就尝试从 AI 回复里解析一份
        if not new_job.parse_reply(job_dir, quiet=True):
            raise SystemExit(f"❌ {job_dir} 没有 对照表.txt，也没有可解析的 02_AI回复.txt")
        job = new_job.load_job(job_dir)
    shots = parse_mapping_file(mapping)
    preset = load_track(track, job.get("overrides"))
    if job.get("series"):
        preset["series"] = job["series"]

    print("=" * 64)
    print(f"▶ {track} ｜ {job.get('title') or job.get('topic')} ｜ {len(shots)} 镜")
    print("=" * 64)
    b = DraftBuilder(preset, job_dir, job, cfg, root, shots,
                     hook=job.get("hook", ""), title=job.get("title", ""),
                     mock_tts=args.mock_tts, skip_missing=args.skip_missing, seed=args.seed)
    info = b.build()
    print("\n" + "=" * 64)
    print(f"✅ 完成：{info['draft_name']}   时长 {info['duration']} 秒")
    print(f"   草稿位置：{info['draft_dir']}")
    if info["scenes_failed"]:
        print(f"   ⚠️ 失败分镜：{info['scenes_failed']}")
    if info["mock_tts"]:
        print("   (当前是 --mock-tts 静音占位配音，正式出片请去掉这个参数)")
    print("   打开剪映首页就能看到；如果剪映正开着，回到首页或重启剪映刷新一下。")
    return info


def main():
    ap = argparse.ArgumentParser(description="对照表 + 图片 → 剪映草稿（按赛道套用版式）")
    ap.add_argument("jobs", nargs="*", help="工作目录（可以写多个，或者用通配符）")
    ap.add_argument("--track", help="强制使用某个赛道的预设（默认读 job.json）")
    ap.add_argument("--drafts-root", help="临时指定草稿目录（一般不用，默认自动读剪映设置）")
    ap.add_argument("--mock-tts", action="store_true", help="不调用剪映配音，用静音占位（离线看版式）")
    ap.add_argument("--skip-missing", action="store_true", help="跳过缺图的分镜，不中断")
    ap.add_argument("--seed", type=int, help="随机种子（快闪选图 / BGM 选曲），方便复现")
    ap.add_argument("--where", action="store_true", help="只显示草稿保存目录")
    ap.add_argument("--list-tracks", action="store_true")
    args = ap.parse_args()

    if args.list_tracks:
        print("、".join(list_tracks()))
        return
    cfg = load_config()
    root = draft_paths.resolve_drafts_root(args.drafts_root, cfg)
    if args.where:
        return

    dirs = []
    for j in args.jobs:
        dirs += [d for d in (glob.glob(j) or [j]) if os.path.isfile(os.path.join(d, "job.json"))]
    if not dirs:
        ap.print_help()
        print("\n❌ 没有找到工作目录（目录里要有 job.json）。先用 new_job.py 创建。")
        return

    results = []
    for d in dirs:
        try:
            results.append(build_one(d, args, cfg, root))
        except SystemExit as e:
            print(e)
            results.append({"job": d, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            results.append({"job": d, "error": repr(e)})
    if len(dirs) > 1:
        print("\n📋 批量结果：")
        for r in results:
            print("  ✗ " + r["job"] + " → " + r["error"] if "error" in r
                  else f"  ✓ {r['draft_name']}（{r['duration']}s）")


if __name__ == "__main__":
    main()
