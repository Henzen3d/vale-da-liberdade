#!/usr/bin/env python3
"""Validação de model IDs Gemini contra a API real (não expõe chave).

Testa cada model ID com a chamada mínima:
- texto: generateContent texto puro.
- imagem: generateContent com response_modalities TEXT+IMAGE.
Imprime: model_id -> HTTP status / sucesso / tipo de erro.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def load_key() -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY=") and not line.startswith("GEMINI_API_KEY_"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("GEMINI_API_KEY", "")


def test_text(model: str, key: str) -> dict:
    url = f"{BASE}/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": "Diga apenas: OK"}]}]}
    t0 = time.time()
    try:
        r = requests.post(url, params={"key": key}, json=payload, timeout=60)
    except requests.RequestException as e:
        return {"model": model, "ok": False, "error": f"network: {type(e).__name__}"}
    dt = int((time.time() - t0) * 1000)
    out = {"model": model, "http": r.status_code, "latency_ms": dt}
    if r.status_code == 200:
        body = r.json()
        txt = ""
        try:
            txt = body["candidates"][0]["content"]["parts"][0].get("text", "")
        except (KeyError, IndexError):
            pass
        out["ok"] = bool(txt.strip())
        out["sample"] = txt.strip()[:60]
    else:
        out["ok"] = False
        try:
            out["error"] = r.json()["error"]["message"][:200]
        except Exception:
            out["error"] = r.text[:200]
    return out


def test_image(model: str, key: str) -> dict:
    url = f"{BASE}/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": "A simple editorial test image: an amber square on black background, 16:9."}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    t0 = time.time()
    try:
        r = requests.post(url, params={"key": key}, json=payload, timeout=120)
    except requests.RequestException as e:
        return {"model": model, "ok": False, "error": f"network: {type(e).__name__}"}
    dt = int((time.time() - t0) * 1000)
    out = {"model": model, "http": r.status_code, "latency_ms": dt}
    if r.status_code == 200:
        body = r.json()
        has_img = False
        try:
            for part in body["candidates"][0]["content"]["parts"]:
                if "inlineData" in part or "inline_data" in part:
                    has_img = True
        except (KeyError, IndexError, TypeError):
            pass
        out["ok"] = has_img
        out["has_image"] = has_img
        if not has_img:
            out["note"] = "200 mas sem bloco de imagem"
    else:
        out["ok"] = False
        try:
            out["error"] = r.json()["error"]["message"][:250]
        except Exception:
            out["error"] = r.text[:250]
    return out


def main() -> int:
    key = load_key()
    if not key:
        print("SEM CHAVE GEMINI_API_KEY")
        return 1
    results = []
    # texto
    for m in ["gemini-3.6-flash", "gemini-3.5-flash"]:
        results.append({"kind": "text", **test_text(m, key)})
        time.sleep(1)
    # imagem (variantes com e sem -preview)
    for m in [
        "gemini-3-pro-image",
        "gemini-3-pro-image-preview",
        "gemini-3.1-flash-image",
        "gemini-3.1-flash-image-preview",
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-preview",
    ]:
        results.append({"kind": "image", **test_image(m, key)})
        time.sleep(2)
    print(json.dumps(results, indent=1, ensure_ascii=False))
    out = ROOT / "logs" / "thumbnail_model_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n salvo em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
