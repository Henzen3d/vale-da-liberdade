#!/usr/bin/env python3
"""
Script para testar a geração de imagem com o modelo gemini-2.5-flash-image (e outros)
em TODAS as 7 chaves do Gemini configuradas no .env.
"""

import os
import sys
import json
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

KEYS_TO_TEST = [
    ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
    ("GEMINI_API_KEY_2", os.getenv("GEMINI_API_KEY_2")),
    ("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3")),
    ("GEMINI_API_KEY_4", os.getenv("GEMINI_API_KEY_4")),
    ("GEMINI_API_KEY_5", os.getenv("GEMINI_API_KEY_5")),
    ("GEMINI_API_KEY_6", os.getenv("GEMINI_API_KEY_6")),
    ("GEMINI_API_KEY_7", os.getenv("GEMINI_API_KEY_7")),
]

IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image",
    "nano-banana-pro-preview"
]

output_dir = Path(__file__).resolve().parents[1] / "output" / "test_images"
output_dir.mkdir(parents=True, exist_ok=True)

def mask_key(key: str) -> str:
    if not key:
        return "[NÃO CONFIGURADA]"
    return key[:6] + "..." + key[-4:] if len(key) > 10 else key[:3] + "..."

def test_gemini_content_image(api_key: str, model_id: str, key_name: str):
    """Testa geração via generateContent para modelos multimodo tipo gemini-2.5-flash-image."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {"parts": [{"text": "Generate a simple icon of a small red circle on white background"}]}
        ]
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            data = res.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            found_img = False
            for p in parts:
                if "inlineData" in p:
                    img_b64 = p["inlineData"].get("data", "")
                    mime = p["inlineData"].get("mimeType", "image/jpeg")
                    ext = "png" if "png" in mime else "jpg"
                    img_data = base64.b64decode(img_b64)
                    out_path = output_dir / f"{key_name}_{model_id.replace(':', '_')}.{ext}"
                    with open(out_path, "wb") as f:
                        f.write(img_data)
                    found_img = True
                    return True, f"✅ SUCESSO! Imagem salva ({len(img_data)} bytes) -> {out_path.name}"
            if not found_img:
                text_resp = "".join([p.get("text", "") for p in parts])
                return False, f"⚠️ Respondeu texto em vez de imagem: '{text_resp[:100]}'"
        else:
            err_text = res.text[:200].replace("\n", " ")
            return False, f"❌ HTTP {res.status_code}: {err_text}"
    except Exception as e:
        return False, f"💥 Exceção: {str(e)[:150]}"

print("=" * 85)
print("     TESTANDO TODAS AS 7 CHAVES COM OS MODELOS DE IMAGEM GEMINI")
print("=" * 85)

success_count = 0
total_tested = 0

for key_name, key in KEYS_TO_TEST:
    print(f"\n🔑 {key_name} ({mask_key(key)})")
    print("-" * 85)
    if not key:
        print("   ❌ Chave não configurada no .env")
        continue

    for model in IMAGE_MODELS:
        total_tested += 1
        print(f"   🎨 Modelo: {model:<30} -> ", end="", flush=True)
        ok, msg = test_gemini_content_image(key, model, key_name)
        if ok:
            success_count += 1
        print(msg)

print("\n" + "=" * 85)
print(f"RESULTADO FINAL: {success_count}/{total_tested} testes bem-sucedidos.")
print("=" * 85)
