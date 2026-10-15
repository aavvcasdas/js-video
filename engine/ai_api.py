# -*- coding: utf-8 -*-
"""
可选：调用 OpenAI 兼容接口，自动写文案、自动出图。
只用到标准库 urllib，不需要额外安装依赖。

  文案：DeepSeek / 豆包(火山方舟) / 通义 / Kimi / OpenAI …… 只要兼容 /chat/completions
  出图：火山方舟 Seedream、硅基流动、OpenAI 这类兼容 /images/generations 的接口
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional


def _post(url: str, payload: dict, api_key: str, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def configured(section: Optional[dict]) -> bool:
    return bool(section and section.get("api_key") and section.get("base_url") and section.get("model"))


def chat(llm: dict, prompt: str, temperature: float = 0.8) -> str:
    url = llm["base_url"].rstrip("/") + "/chat/completions"
    data = _post(url, {
        "model": llm["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(llm.get("temperature", temperature)),
    }, llm["api_key"])
    return data["choices"][0]["message"]["content"]


def generate_image(img: dict, prompt: str, out_path: str, retries: int = 2) -> str:
    url = img["base_url"].rstrip("/") + "/images/generations"
    payload = {"model": img["model"], "prompt": prompt, "n": 1}
    if img.get("size"):
        payload["size"] = img["size"]
    payload.update(img.get("extra") or {})
    last = None
    for i in range(retries + 1):
        try:
            data = _post(url, payload, img["api_key"], timeout=300)
            item = (data.get("data") or data.get("images") or [{}])[0]
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            if item.get("b64_json"):
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=120) as r, open(out_path, "wb") as f:
                    f.write(r.read())
            else:
                raise RuntimeError(f"返回里没有图片: {str(data)[:200]}")
            return out_path
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"出图失败: {last}")
