# -*- coding: utf-8 -*-
"""
剪映草稿保存路径统一管理
================================================

为什么需要这个模块
------------------
以前用 auto-catvideo 生成草稿时，经常遇到「脚本说保存成功，打开剪映却看不到草稿」或者「草稿打开后素材丢失」。原因主要有三个：

1. **草稿目录不一致**：skill 只会去猜默认目录
   `%LOCALAPPDATA%/JianyingPro/User Data/Projects/com.lveditor.draft`。
   如果你在剪映「全局设置 → 草稿位置」里改过目录（比如改到 D 盘），
   草稿就写到了一个剪映根本不扫描的地方。
2. **素材分散**：配音写在 `<草稿>/temp_assets`，图片却引用工程目录里的原图。
   工程目录一旦移动或改名，草稿里的素材就全部丢失。
3. **draft_meta_info.json 字段为空**：pyJianYingDraft 的模板里
   `draft_fold_path / draft_root_path / draft_name` 都是空字符串，
   `draft_id` 也是固定值，所有草稿都共用同一个 ID。

本模块的做法：
* 按「命令行 > config.json > 环境变量 JY_PROJECTS_ROOT > 剪映 globalSetting 里的
  currentCustomDraftPath > 默认目录」的优先级确定**唯一**的草稿根目录，
  再写回环境变量，让 skill 里所有模块（TTS 临时文件、draft_inspector、
  auto_exporter）都用同一个目录。
* 把图片、音效、BGM 复制到 `<草稿根目录>/<草稿名>/materials/` 下，
  草稿只引用自己文件夹里的文件。
* 保存后补全 draft_meta_info.json，并给每个草稿生成唯一的 draft_id 和内容 id。
* 最后逐个检查草稿里引用的素材路径，有问题直接报出来。
"""

import json
import os
import re
import shutil
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

ENV_KEY = "JY_PROJECTS_ROOT"


# ----------------------------------------------------------------------------
# 1. 读取剪映自己的「草稿位置」设置
# ----------------------------------------------------------------------------
def _global_setting_candidates() -> List[str]:
    """剪映 / CapCut 的 globalSetting 文件可能所在的位置。"""
    home = os.path.expanduser("~")
    out = []
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        out += [
            os.path.join(local, "JianyingPro", "User Data", "Config", "globalSetting"),
            os.path.join(local, "CapCut", "User Data", "Config", "globalSetting"),
        ]
    elif sys.platform == "darwin":
        out += [
            os.path.join(home, "Movies", "JianyingPro", "User Data", "Config", "globalSetting"),
            os.path.join(home, "Library", "Containers", "com.lemon.lvpro", "Data", "Movies",
                         "JianyingPro", "User Data", "Config", "globalSetting"),
            os.path.join(home, "Library", "Application Support", "JianyingPro", "User Data",
                         "Config", "globalSetting"),
            os.path.join(home, "Movies", "CapCut", "User Data", "Config", "globalSetting"),
        ]
    return out


def _unescape_qt_ini(value: str) -> str:
    """Qt QSettings(ini) 的值转义：去引号、\\\\ → \\、\\xHHHH → 对应字符。"""
    v = value.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
    v = re.sub(r"\\x([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), v)
    v = v.replace("\\\\", "\\")
    return v.strip()


def read_jianying_setting_path(setting_file: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    从剪映 globalSetting 读取 currentCustomDraftPath。

    Returns:
        (草稿目录, 读取的 globalSetting 文件路径)，读取不到就返回 (None, None)
    """
    files = [setting_file] if setting_file else _global_setting_candidates()
    for f in files:
        if not f or not os.path.isfile(f):
            continue
        raw = open(f, "rb").read()
        text = None
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("currentCustomDraftPath="):
                v = _unescape_qt_ini(line.split("=", 1)[1])
                if v:
                    return os.path.normpath(v), f
    return None, None


def _skill_default_root() -> str:
    """和 skill 的默认探测逻辑保持一致的兜底目录。"""
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(local, "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
    if sys.platform == "darwin":
        return os.path.join(home, "Movies", "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
    # Linux 等非剪映平台：只用于离线测试 / 预览草稿结构
    return os.path.join(home, "JianyingPro Drafts")


def resolve_drafts_root(cli_root: Optional[str] = None, config: Optional[dict] = None,
                        verbose: bool = True) -> str:
    """
    确定唯一的草稿根目录，并写回环境变量 JY_PROJECTS_ROOT。

    优先级：命令行 --drafts-root > config.json 的 drafts_root > 环境变量
            > 剪映「全局设置 → 草稿位置」 > 默认目录
    """
    config = config or {}
    source = ""
    root = None
    if cli_root:
        root, source = cli_root, "命令行 --drafts-root"
    elif (config.get("drafts_root") or "").strip():
        root, source = config["drafts_root"].strip(), "config.json → drafts_root"
    elif os.environ.get(ENV_KEY, "").strip():
        root, source = os.environ[ENV_KEY].strip(), f"环境变量 {ENV_KEY}"
    else:
        jy_root, setting_file = read_jianying_setting_path()
        if jy_root:
            root, source = jy_root, f"剪映设置 ({setting_file})"
        else:
            root, source = _skill_default_root(), "默认目录"

    root = os.path.abspath(os.path.expanduser(root))
    os.makedirs(root, exist_ok=True)
    os.environ[ENV_KEY] = root  # 让 skill 内所有模块使用同一个目录

    if verbose:
        print(f"📁 剪映草稿目录: {root}")
        print(f"   来源: {source}")
        # 手动指定的目录和剪映实际设置不一致时给出提醒
        jy_root, _ = read_jianying_setting_path()
        if jy_root and os.path.normcase(os.path.abspath(jy_root)) != os.path.normcase(root):
            print(f"   ⚠️ 注意：剪映「草稿位置」设置的是 {jy_root}")
            print("      两者不一致时，剪映首页里会看不到这个草稿。请改 config.json，或者改剪映设置。")
    return root


# ----------------------------------------------------------------------------
# 2. 草稿命名
# ----------------------------------------------------------------------------
def sanitize_name(name: str, max_len: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name)).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned or "未命名")[:max_len]


def build_draft_name(template: str, **kw) -> str:
    """按 config 里的 draft_name_template 生成草稿名，例如 {track}_{title}_{date}"""
    now = time.localtime()
    values = {
        "date": time.strftime("%Y%m%d", now),
        "time": time.strftime("%H%M%S", now),
        "datetime": time.strftime("%Y%m%d_%H%M%S", now),
    }
    values.update({k: v for k, v in kw.items() if v is not None})
    try:
        name = template.format(**values)
    except KeyError as e:
        print(f"⚠️ draft_name_template 里有未知字段 {e}，改用默认命名")
        name = "{track}_{title}_{datetime}".format(**values)
    return sanitize_name(name)


# ----------------------------------------------------------------------------
# 3. 素材复制到草稿目录内
# ----------------------------------------------------------------------------
class MediaStager:
    """把素材复制到 <草稿目录>/materials/<子目录>/，保证草稿自包含。"""

    def __init__(self, draft_dir: str, enabled: bool = True):
        self.draft_dir = draft_dir
        self.enabled = enabled
        self._cache: Dict[Tuple[str, str], str] = {}

    def stage(self, src: str, sub: str = "images") -> str:
        if not src:
            return src
        src = os.path.abspath(src)
        if not self.enabled or not os.path.isfile(src):
            return src
        if os.path.normcase(src).startswith(os.path.normcase(os.path.abspath(self.draft_dir)) + os.sep):
            return src  # 已经在草稿目录里了
        key = (src, sub)
        if key in self._cache:
            return self._cache[key]
        dst_dir = os.path.join(self.draft_dir, "materials", sub)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(src))
        base, ext = os.path.splitext(dst)
        i = 1
        # 同名但内容不同的文件，自动改名避免覆盖
        while os.path.exists(dst) and os.path.getsize(dst) != os.path.getsize(src):
            dst = f"{base}_{i}{ext}"
            i += 1
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        self._cache[key] = dst
        return dst


# ----------------------------------------------------------------------------
# 4. 保存后补全元信息 + 校验
# ----------------------------------------------------------------------------
def _jy_path(p: str) -> str:
    """剪映（Qt）在 Windows 上写路径时用正斜杠。"""
    p = os.path.abspath(p)
    return p.replace("\\", "/") if sys.platform.startswith("win") else p


def _content_file(draft_dir: str) -> Optional[str]:
    for fn in ("draft_info.json", "draft_content.json"):
        f = os.path.join(draft_dir, fn)
        if os.path.isfile(f):
            return f
    return None


def finalize_draft(draft_dir: str, drafts_root: str, draft_name: str,
                   duration_us: int = 0, cover_image: Optional[str] = None) -> Dict:
    """
    补全 draft_meta_info.json（路径、名称、唯一 ID、时间戳），
    并把 draft_info.json 的 id 改成唯一值。
    """
    now_us = int(time.time() * 1_000_000)
    draft_id = str(uuid.uuid4()).upper()

    meta_file = os.path.join(draft_dir, "draft_meta_info.json")
    meta = {}
    if os.path.isfile(meta_file):
        try:
            meta = json.load(open(meta_file, encoding="utf-8"))
        except Exception:
            meta = {}
    meta.update({
        "draft_id": draft_id,
        "draft_name": draft_name,
        "draft_fold_path": _jy_path(draft_dir),
        "draft_root_path": _jy_path(drafts_root),
        "tm_draft_create": meta.get("tm_draft_create") or now_us,
        "tm_draft_modified": now_us,
        "tm_duration": int(duration_us or meta.get("tm_duration") or 0),
    })
    # 封面：复制第一张图作为 draft_cover.jpg，剪映首页缩略图会显示它
    if cover_image and os.path.isfile(cover_image):
        try:
            cover_dst = os.path.join(draft_dir, "draft_cover.jpg")
            _save_cover(cover_image, cover_dst)
            meta["draft_cover"] = "draft_cover.jpg"
        except Exception as e:
            print(f"   (封面生成跳过: {e})")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    content_file = _content_file(draft_dir)
    if content_file:
        try:
            content = json.load(open(content_file, encoding="utf-8"))
            content["id"] = str(uuid.uuid4()).upper()
            with open(content_file, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False)
        except Exception as e:
            print(f"   ⚠️ 无法更新草稿内容 id: {e}")

    os.utime(draft_dir, None)
    return {"draft_id": draft_id, "meta_file": meta_file}


def _save_cover(src: str, dst: str):
    try:
        from PIL import Image  # 可选依赖
        im = Image.open(src).convert("RGB")
        im.thumbnail((720, 720))
        im.save(dst, "JPEG", quality=85)
    except ImportError:
        if src.lower().endswith((".jpg", ".jpeg")):
            shutil.copy2(src, dst)
        else:
            raise RuntimeError("未安装 Pillow，PNG 封面无法转换")


def verify_draft(draft_dir: str, require_inside: bool = True) -> Dict:
    """
    检查草稿引用的所有本地素材：文件是否存在、是否都在草稿目录内。
    """
    content_file = _content_file(draft_dir)
    report = {"content_file": content_file, "total": 0, "missing": [], "outside": []}
    if not content_file:
        report["missing"].append("(找不到 draft_info.json / draft_content.json)")
        return report
    data = json.load(open(content_file, encoding="utf-8"))
    mats = data.get("materials", {})
    dd = os.path.normcase(os.path.abspath(draft_dir))
    for kind in ("videos", "audios"):
        for m in mats.get(kind, []) or []:
            p = m.get("path") or ""
            if not p or p.startswith("##_") or "draftpath_placeholder" in p:
                continue  # 云素材 / 占位
            report["total"] += 1
            ap = os.path.normcase(os.path.abspath(p))
            if not os.path.exists(p):
                report["missing"].append(p)
            elif require_inside and not ap.startswith(dd + os.sep):
                report["outside"].append(p)
    return report


def print_verify_report(report: Dict, require_inside: bool = True) -> bool:
    ok = not report["missing"] and (not require_inside or not report["outside"])
    print(f"\n🔍 路径校验: 共 {report['total']} 个本地素材", end="")
    if ok:
        print(" —— 全部存在" + ("，并且都在草稿目录内 ✅" if require_inside else " ✅"))
        return True
    print()
    for p in report["missing"][:10]:
        print(f"   ❌ 缺失: {p}")
    if require_inside:
        for p in report["outside"][:10]:
            print(f"   ⚠️ 在草稿目录外（移动工程目录后会丢失）: {p}")
    return ok
