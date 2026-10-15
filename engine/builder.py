# -*- coding: utf-8 -*-
"""
通用草稿构建器：对照表 + 图片 + 赛道预设 → 剪映草稿

流程（和 auto-catvideo 的 create_video_final.py 一致，只是把写死的样式改成读赛道预设）：
  片头（引导语配音 + 大字 + 快闪图 + 音效）
  → 把连续几镜合并成一个配音块，一次合成（语气连贯），再按字数把时长分回每一镜和每句字幕
  → 图片铺满 / 居中 + Ken Burns 推拉
  → 顶部系列标题、每镜标签、结尾引导、AI 标识、BGM
  → 保存，补全草稿元信息，校验素材路径
"""

import json
import os
import random
import re
import sys
import time
import uuid
import wave
from typing import Dict, List, Optional, Tuple

from . import draft_paths
from .script_io import Shot, find_image
from .tracks import ROOT, fill_vars, hex_to_rgb

SKILL_ROOT = os.path.join(ROOT, "vendor", "jianying-editor-skill")


def import_skill():
    """导入 vendored skill。必须在 resolve_drafts_root() 之后调用，保证 skill 读到同一个草稿目录。"""
    os.environ.setdefault("JY_SKILL_ROOT", SKILL_ROOT)
    scripts = os.path.join(SKILL_ROOT, "scripts")
    for p in (os.path.join(scripts, "vendor"), scripts):
        if p not in sys.path:
            sys.path.insert(0, p)
    from jy_wrapper import JyProject  # noqa
    import pyJianYingDraft as draft  # noqa
    return JyProject, draft


def fmt(us: int) -> str:
    s = us / 1_000_000
    return f"{int(s // 60)}:{s % 60:04.1f}"


_PUNCT = r'[，。！？、""“”‘’：；…—/\s,.!?;:]'


def plain(t: str) -> str:
    return re.sub(_PUNCT, "", t or "")


def split_subtitles(text: str, max_chars: int = 16) -> List[str]:
    """按标点切成短句字幕；单句太长再按 max_chars 切开。"""
    text = re.sub(r"\s*/\s*", "/", text or "")
    parts = re.split(r"(?<=[，。！？、/；：,!?;])", text)
    out = []
    for p in parts:
        p = p.strip()
        if len(plain(p)) < 1:
            continue
        while len(p) > max_chars + 2:
            out.append(p[:max_chars])
            p = p[max_chars:]
        out.append(p)
    return out or [text]


def alloc(total: int, weights: List[float]) -> List[int]:
    s = sum(weights) or 1
    out, used = [], 0
    for i, w in enumerate(weights):
        if i == len(weights) - 1:
            out.append(total - used)
        else:
            d = int(total * w / s)
            out.append(d)
            used += d
    return out


def write_silent_wav(path: str, seconds: float, rate: int = 16000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = max(1, int(seconds * rate))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)


class DraftBuilder:
    TTS_GROUP_CHARS = 180
    TTS_MAX_CHARS = 300

    def __init__(self, preset: dict, job_dir: str, job: dict, cfg: dict, drafts_root: str,
                 shots: List[Shot], hook: str = "", title: str = "", mock_tts: bool = False,
                 skip_missing: bool = False, seed: Optional[int] = None):
        self.p = preset
        self.job_dir = os.path.abspath(job_dir)
        self.job = job
        self.cfg = cfg
        self.root = drafts_root
        self.shots = shots
        self.hook = (hook or "").strip()
        self.title = title or job.get("title") or ""
        self.mock_tts = mock_tts
        self.skip_missing = skip_missing
        self.rand = random.Random(seed)
        self.JyProject, self.draft = import_skill()
        self.vars = {
            "series": preset.get("series", ""),
            "title": self.title,
            "track": preset.get("name", ""),
            "day": job.get("day", preset.get("day", 1)),
            "topic": job.get("topic", ""),
        }
        self.vars.update({k: v for k, v in (job.get("vars") or {}).items()})
        self.speaker = preset["voice"]["speaker"]
        self.speed = float(preset["voice"].get("speed", 1.0))
        self.TTS_GROUP_CHARS = int(preset["voice"].get("group_chars", self.TTS_GROUP_CHARS))
        self.log_fail: List[Tuple[int, str]] = []

    # ------------------------------------------------------------------ utils
    def _font(self, name: str):
        FontType = self.draft.FontType
        if name and hasattr(FontType, name):
            return getattr(FontType, name)
        return FontType.优设标题黑

    def _text(self, text: str, start: int, dur: int, track: str, style: dict, center: bool = True,
              x: float = 0.0, y: Optional[float] = None, wrap: bool = True, size: Optional[float] = None):
        d = self.draft
        if dur <= 0 or not text:
            return None
        kw = dict(
            font=self._font(style.get("font")),
            style=d.TextStyle(
                size=float(size if size is not None else style.get("size", 8)),
                color=hex_to_rgb(style.get("color", "#FFFFFF")),
                alpha=float(style.get("alpha", 1.0)),
                align=1 if center else 0,
                letter_spacing=int(style.get("letter_spacing", 1)),
                line_spacing=int(style.get("line_spacing", 2)),
                auto_wrapping=wrap,
                max_line_width=float(style.get("max_line_width", 0.86)),
            ),
            clip_settings=d.ClipSettings(transform_x=float(style.get("x", x)),
                                         transform_y=float(style.get("y", 0.0) if y is None else y)),
        )
        bw = float(style.get("border_width", 40))
        if bw > 0:
            kw["border"] = d.TextBorder(color=hex_to_rgb(style.get("border_color", "#000000")),
                                        alpha=float(style.get("border_alpha", 1.0)), width=bw)
        bg = style.get("background")
        if isinstance(bg, dict):
            kw["background"] = d.TextBackground(color=bg.get("color", "#000000"),
                                                alpha=float(bg.get("alpha", 0.5)),
                                                round_radius=float(bg.get("round_radius", 0.3)))
        if style.get("anim_in"):
            kw["anim_in"] = style["anim_in"]
            kw["anim_in_duration"] = min(500_000, dur // 2)
        try:
            return self.project.add_text_simple(text=text, start_time=start, duration=dur, track_name=track, **kw)
        except Exception as e:
            print(f"    ⚠️ 文字失败[{track}] {text[:12]}: {str(e)[:60]}")
            return None

    def _stage(self, path: str, sub: str) -> str:
        return self.stager.stage(path, sub)

    def _rel_asset(self, p: str) -> Optional[str]:
        if not p:
            return None
        for cand in (p, os.path.join(self.job_dir, p), os.path.join(ROOT, p)):
            if os.path.exists(cand):
                return os.path.abspath(cand)
        return None

    # ------------------------------------------------------------------ TTS
    def _tts(self, text: str, start: int, track: str) -> Tuple[Optional[object], int]:
        text = re.sub(r"\s+", "", text.strip())
        text = re.sub(r"。{2,}", "。", text)
        if not text.endswith(("。", "！", "？", "…")):
            text += "。"
        if self.mock_tts:
            secs = max(0.6, len(plain(text)) / 4.5 / self.speed)
            path = os.path.join(self.project.draft_dir, "temp_assets", f"mock_{uuid.uuid4().hex[:8]}.wav")
            write_silent_wav(path, secs)
            seg = self.project.add_audio_safe(path, start, None, track)
            return (seg, seg.target_timerange.duration) if seg else (None, 0)

        from pyJianYingDraft.time_util import Timerange
        for attempt in range(3):
            try:
                seg = self.project.add_tts_intelligent(
                    text=text, speaker=self.speaker, start_time=start, track_name=track,
                    tts_backend="sami", allow_fallback=False)
                if seg:
                    seg.speed.speed = self.speed
                    dur = int(seg.target_timerange.duration / self.speed)
                    seg.target_timerange = Timerange(seg.target_timerange.start, dur)
                    try:
                        seg.add_effect(self.draft.Effects.audio_loudness_normalization, target_loudness=-16.0)
                    except Exception:
                        pass
                    return seg, dur
            except Exception as e:
                print(f"      重试 {attempt + 1}/3 ({str(e)[:40]})")
            time.sleep(1)
        return None, 0

    def _split_for_tts(self, text: str) -> List[str]:
        text = re.sub(r"\s+", "", text or "")
        if len(text) <= self.TTS_MAX_CHARS:
            return [text] if text else []
        units = [u for u in re.split(r"(?<=[。！？；…])", text) if u]
        chunks, buf = [], ""
        for u in units:
            while len(u) > self.TTS_MAX_CHARS:
                chunks.append(u[:self.TTS_MAX_CHARS])
                u = u[self.TTS_MAX_CHARS:]
            if buf and len(buf) + len(u) > self.TTS_MAX_CHARS:
                chunks.append(buf)
                buf = u
            else:
                buf += u
        if buf:
            chunks.append(buf)
        return chunks

    # ------------------------------------------------------------------ 图片
    def _image_seg(self, path: str, start: int, dur: int, track: str, seq: int, ken_burns: bool = True,
                   main: bool = False):
        KP = self.draft.KeyframeProperty
        seg = self.project.add_media_safe(media_path=path, start_time=start, duration=dur, track_name=track)
        if not seg:
            return None
        base = self._fit_scale(path)
        if main and self.p.get("image_fit") == "contain":
            try:
                seg.add_background_filling("color", color=self.p.get("background_color", "#000000") + "FF")
            except Exception:
                pass
        kb = self.p.get("ken_burns", {})
        if ken_burns and kb.get("enabled", True):
            z, pan = float(kb.get("zoom", 1.1)), float(kb.get("pan", 0.04))
            mode = seq % 3
            # 平移只发生在放大的状态下，避免露出画布边缘
            try:
                if mode == 0:  # 慢慢推近 + 向右移
                    seg.add_keyframe(KP.uniform_scale, 0, base)
                    seg.add_keyframe(KP.uniform_scale, dur, base * z)
                    if pan:
                        seg.add_keyframe(KP.position_x, 0, 0.0)
                        seg.add_keyframe(KP.position_x, dur, pan)
                elif mode == 1:  # 从近处慢慢拉远 + 回正
                    seg.add_keyframe(KP.uniform_scale, 0, base * z)
                    seg.add_keyframe(KP.uniform_scale, dur, base)
                    if pan:
                        seg.add_keyframe(KP.position_x, 0, -pan)
                        seg.add_keyframe(KP.position_x, dur, 0.0)
                else:  # 推近 + 向上移
                    seg.add_keyframe(KP.uniform_scale, 0, base)
                    seg.add_keyframe(KP.uniform_scale, dur, base * z)
                    if pan:
                        seg.add_keyframe(KP.position_y, 0, 0.0)
                        seg.add_keyframe(KP.position_y, dur, pan * 0.8)
            except Exception as e:
                print(f"    ⚠️ Ken Burns 失败: {str(e)[:40]}")
        elif base != 1.0:
            seg.add_keyframe(KP.uniform_scale, 0, base)
        return seg

    _size_cache: Dict[str, Tuple[int, int]] = {}

    def _fit_scale(self, path: str) -> float:
        """image_fit=cover 时返回铺满画布需要的放大倍数（剪映默认是完整显示在画布内）。"""
        if self.p.get("image_fit", "cover") != "cover":
            return 1.0
        if path not in self._size_cache:
            w = h = 0
            try:
                from PIL import Image
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                try:
                    m = self.draft.VideoMaterial(path)
                    w, h = m.width, m.height
                except Exception:
                    pass
            self._size_cache[path] = (w, h)
        w, h = self._size_cache[path]
        if not w or not h:
            return 1.0
        cw, ch = self.p["canvas"]
        sx, sy = cw / w, ch / h
        return round(max(sx, sy) / min(sx, sy), 4)

    # ------------------------------------------------------------------ 片头
    def _opening(self, scenes: List[dict]) -> int:
        op = self.p.get("opening", {})
        kind = (op.get("type") or "none").lower()
        if kind == "none" or not self.hook or not scenes:
            return 0
        print(f"\n🎬 片头[{kind}]：{self.hook}")
        seg, lead = self._tts(self.hook, 0, "Voice_Hook")
        if not seg:
            lead = int(max(1.5, len(plain(self.hook)) / 4.5) * 1_000_000)
            print("   ⚠️ 引导语配音失败，按字数估算时长")

        # 主轨第一段：首图（保证主轨从 0 开始连续）
        first = scenes[0]["img_path"]
        self._image_seg(first, 0, lead, "Main", 0, ken_burns=True, main=True)

        if kind == "flash":
            pool = [s["img_path"] for s in scenes]
            n = min(int(op.get("flash_images", 5)), len(pool))
            picks = self.rand.sample(pool, n) if len(pool) >= n else pool
            fps = getattr(self.project.script, "fps", 30) or 30
            frame = int(round(1_000_000 / fps))
            step = int(op.get("flash_frames", 10))
            KP = self.draft.KeyframeProperty
            for i, img in enumerate(picks):
                st = i * (step + 1) * frame
                if st >= lead:
                    break
                s = self.project.add_media_safe(media_path=img, start_time=st, duration=lead - st,
                                                track_name=f"Flash_{i + 1}")
                if s:
                    base = self._fit_scale(img)
                    s.add_keyframe(KP.uniform_scale, 0, base * 1.5)
                    s.add_keyframe(KP.uniform_scale, step * frame, base)
            sfx = self._rel_asset(op.get("sfx"))
            if sfx:
                a = self.project.add_media_safe(media_path=self._stage(sfx, "sfx"), start_time=0,
                                                duration=lead, track_name="SFX")
                if a is not None:
                    a.volume = float(op.get("sfx_volume", 0.8))
        elif op.get("sfx"):
            sfx = self._rel_asset(op.get("sfx"))
            if sfx:
                a = self.project.add_media_safe(media_path=self._stage(sfx, "sfx"), start_time=0,
                                                duration=lead, track_name="SFX")
                if a is not None:
                    a.volume = float(op.get("sfx_volume", 0.8))

        hs = op.get("hook_style", {})
        self._text(self.hook, 0, lead, "Hook", hs, center=True)
        print(f"   ✓ 片头 {fmt(lead)}")
        return lead

    # ------------------------------------------------------------------ 主流程
    def _collect_scenes(self) -> List[dict]:
        img_dir = None
        for cand in ("image", "images", "图片"):
            if os.path.isdir(os.path.join(self.job_dir, cand)):
                img_dir = os.path.join(self.job_dir, cand)
                break
        scenes, missing = [], []
        for s in self.shots:
            path = find_image(img_dir, s.image, s.seq) if img_dir else None
            if not path:
                missing.append(s)
                continue
            if len(plain(s.text)) < 1:
                continue
            scenes.append({"seq": s.seq, "text": s.text, "tag": s.tag, "img": s.image,
                           "img_src": path, "chars": len(plain(s.text))})
        if missing:
            print(f"\n⚠️ 缺 {len(missing)} 张图：" + "、".join(f"{m.seq:02d}({m.image})" for m in missing[:8]))
            if not self.skip_missing:
                raise SystemExit("   把图片放进 image/ 文件夹后重跑；或者加 --skip-missing 跳过缺图的分镜。")
        if not scenes:
            raise SystemExit("❌ 没有可用的分镜（检查对照表和 image/ 文件夹）")
        return scenes

    def build(self) -> Dict:
        d = self.draft
        p = self.p
        cw, ch = p["canvas"]
        scenes = self._collect_scenes()

        name = draft_paths.build_draft_name(
            self.cfg.get("draft_name_template", "{track}_{title}_{datetime}"),
            track=p.get("name", ""), title=self.title or self.job.get("topic", ""),
            series=p.get("series", ""), day=self.vars.get("day"), job=os.path.basename(self.job_dir))
        overwrite = bool(self.cfg.get("overwrite_same_name", True))
        print(f"\n🆕 创建草稿：{name}  ({cw}x{ch})")
        self.project = self.JyProject(project_name=name, width=cw, height=ch,
                                      drafts_root=self.root, overwrite=overwrite)
        name = self.project.name
        draft_dir = getattr(self.project, "draft_dir", None) or os.path.join(self.root, name)
        self.stager = draft_paths.MediaStager(draft_dir, bool(self.cfg.get("copy_media_into_draft", True)))

        # 主轨先建，保证它是最底层轨道
        self.project._ensure_track(d.TrackType.video, "Main")
        for sc in scenes:
            sc["img_path"] = self._stage(sc["img_src"], "images")

        cur = self._opening(scenes)
        opening_end = cur

        # ---- 配音块 ----
        groups, buf, n = [], [], 0
        for sc in scenes:
            if buf and n + sc["chars"] > self.TTS_GROUP_CHARS:
                groups.append(buf)
                buf, n = [], 0
            buf.append(sc)
            n += sc["chars"]
        if buf:
            groups.append(buf)
        print(f"\n🗣️ {len(scenes)} 镜合并为 {len(groups)} 个配音块（音色 {self.speaker}，语速 {self.speed}"
              f"{'，离线静音预览' if self.mock_tts else ''}）")

        sub_style = p.get("subtitle", {})
        hl_first = bool(sub_style.get("highlight_first", True)) and opening_end == 0
        first_done = False
        tag_spans: List[List] = []  # [tag, start, end]
        done = 0

        for gi, group in enumerate(groups):
            gtext = "".join(sc["text"] for sc in group)
            t0 = cur
            ok = 0
            for chunk in self._split_for_tts(gtext):
                seg, dur = self._tts(chunk, cur, "Voice")
                if seg:
                    cur += dur
                    ok += 1
                else:
                    print(f"    ✗ 配音失败：{chunk[:20]}")
            if not ok:
                for sc in group:
                    self.log_fail.append((sc["seq"], "配音失败"))
                continue
            gdur = cur - t0
            print(f"  块{gi + 1}/{len(groups)} [{group[0]['seq']:02d}-{group[-1]['seq']:02d}] {fmt(gdur)}")
            t = t0
            for sc, sdur in zip(group, alloc(gdur, [s["chars"] for s in group])):
                subs = split_subtitles(sc["text"], int(sub_style.get("max_chars", 16)))
                st = t
                for k, (sub, sd) in enumerate(zip(subs, alloc(sdur, [max(1, len(plain(x))) for x in subs]))):
                    clean = re.sub(r"[，。！？、；：,.!?;:]+$", "", sub.strip())
                    clean = clean.replace("/", " ")
                    if hl_first and not first_done:
                        self._text(clean, st, sd, "Subtitles_Hook", p["opening"].get("hook_style", {}), y=0.0)
                        first_done = True
                    else:
                        self._text(clean, st, sd, "Subtitles", sub_style)
                    st += sd
                iseg = self._image_seg(sc["img_path"], t, sdur, "Main", sc["seq"], main=True)
                if sc["tag"]:
                    if tag_spans and tag_spans[-1][0] == sc["tag"] and tag_spans[-1][2] == t:
                        tag_spans[-1][2] = t + sdur
                    else:
                        tag_spans.append([sc["tag"], t, t + sdur])
                if done == 0 and iseg is not None and p.get("first_effects"):
                    self._first_effects(iseg)
                t += sdur
                done += 1

        total = cur
        if done == 0:
            raise SystemExit("❌ 没有成功生成任何分镜（配音全部失败？可以先用 --mock-tts 检查版式）")

        # ---- 全局元素 ----
        hd = p.get("header", {})
        if hd.get("enabled", True):
            htext = fill_vars(hd.get("text", ""), self.vars).strip()
            if htext and "{" not in htext:
                self._text(htext, opening_end, total - opening_end, "Header", hd)
        for tag, s, e in tag_spans:
            self._text(tag, s, e - s, "Tag", p.get("tag", {}))
        ed = p.get("ending", {})
        etext = fill_vars(ed.get("text", ""), self.vars)
        if etext:
            secs = int(float(ed.get("seconds", 2.5)) * 1_000_000)
            self._text(etext, max(opening_end, total - secs), min(secs, total - opening_end), "Ending",
                       dict(ed, anim_in=ed.get("anim_in", "弹入")))
        dc = p.get("disclaimer", {})
        if dc.get("text"):
            self._text(dc["text"], 0, total, "Disclaimer",
                       {"font": dc.get("font", "优设标题黑"), "size": dc.get("size", 4.5),
                        "alpha": dc.get("alpha", 0.75), "x": dc.get("x", -0.62), "y": dc.get("y", 0.9),
                        "border_width": dc.get("border_width", 20), "max_line_width": 0.6}, center=False)
        self._bgm(total)

        # ---- 保存 + 路径一致性处理 ----
        print("\n💾 保存草稿...")
        self.project.save()
        first_img = scenes[0]["img_path"]
        draft_paths.finalize_draft(draft_dir, self.root, name, total, cover_image=first_img)
        report = draft_paths.verify_draft(draft_dir, require_inside=self.stager.enabled)
        ok = draft_paths.print_verify_report(report, require_inside=self.stager.enabled)

        info = {
            "draft_name": name,
            "drafts_root": self.root,
            "draft_dir": draft_dir,
            "track": p.get("name"),
            "title": self.title,
            "duration": round(total / 1_000_000, 2),
            "scenes_ok": done,
            "scenes_failed": self.log_fail,
            "mock_tts": self.mock_tts,
            "paths_ok": ok,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(os.path.join(self.job_dir, "draft.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        return info

    def _first_effects(self, seg):
        """给正片第一张图加特效（名字来自 VideoSceneEffectType，找不到就跳过）。"""
        VSE = self.draft.VideoSceneEffectType
        for name in self.p.get("first_effects", []):
            if hasattr(VSE, name):
                try:
                    seg.add_effect(getattr(VSE, name))
                except Exception as e:
                    print(f"    ⚠️ 特效 {name} 失败: {str(e)[:40]}")
            else:
                print(f"    ⚠️ 没有这个特效：{name}")

    def _bgm(self, total: int):
        bg = self.p.get("bgm", {})
        path = self._rel_asset(self.job.get("bgm") or "")
        if not path:
            d = self._rel_asset(bg.get("dir") or "")
            if d and os.path.isdir(d):
                files = [os.path.join(d, f) for f in sorted(os.listdir(d))
                         if f.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"))]
                if files:
                    path = self.rand.choice(files)
        if not path:
            return
        path = self._stage(path, "bgm")
        vol = float(bg.get("volume", 0.12))
        t, last = 0, None
        while t < total:
            seg = self.project.add_audio_safe(path, t, total - t, "BGM")
            if not seg:
                break
            seg.volume = vol
            last = seg
            t += seg.target_timerange.duration
        if last is not None and bg.get("fade_out"):
            try:
                last.add_fade(0, int(float(bg["fade_out"]) * 1_000_000))
            except Exception:
                pass
        print(f"🎵 BGM：{os.path.basename(path)}（音量 {vol}）")
