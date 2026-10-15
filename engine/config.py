# -*- coding: utf-8 -*-
import json
import os

from .tracks import ROOT, deep_merge

DEFAULTS = {
    "drafts_root": "",
    "copy_media_into_draft": True,
    "overwrite_same_name": True,
    "draft_name_template": "{track}_{title}_{datetime}",
    "llm": {},
    "image": {},
}


def load_config(path: str = None) -> dict:
    path = path or os.path.join(ROOT, "config.json")
    cfg = dict(DEFAULTS)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            cfg = deep_merge(cfg, json.load(f))
    return cfg
