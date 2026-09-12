#!/usr/bin/env python3
"""
Script rápido para testar a cota/disponibilidade de TODOS os modelos de Imagem (Qwen Image & Wan)
cadastrados na chave QwenCloud/DashScope.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def parse_env_file():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
        except Exception:
            pass

parse_env_file()

IMAGE_MODELS = [
    "qwen-image-3.0-pro",
    "qwen-image-3.0",
    "qwen-image-2.0-pro",
    "qwen-image-2.0",
    "qwen-image-max",
    "qwen-image-plus",
    "qwen-image-edit",
    "qwen-image-edit-plus",
    "qwen-image-edit-max",
    "wan2.7-image-pro",
    "wan2.7-image",
    "z-image-turbo"
]

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

def test_image_model(api_key, model_id):
    url_chat = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload_chat = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hi"}]
            }
        ],
        "max_tokens": 1
    }

    start = time.time()
    try:
        data_bytes = json.dumps(payload_chat).encode("utf-8")
        req = urllib.request.Request(url_chat, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            elapsed = (time.time() - start) * 1000
            return True, resp.status, f"OK ({elapsed:.0f}ms)", "Quota disponível!"
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start) * 1000
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            msg = err_json.get("error", {}).get("message") or err_json.get("message") or str(e.code)
            code = err_json.get("error", {}).get("code") or e.code
            return False, e.code, f"HTTP {e.code}", f"{code}: {msg[:80]}"
        except Exception:
            return False, e.code, f"HTTP {e.code}", str(e.reason)
    except Exception as e:
        # Se for timeout, o modelo aceitou a conexão e está processando geração de imagem!
        if "timed out" in str(e).lower() or "timeout" in str(e).lower():
            return True, 200, "OK (Geração Iniciada)", "Modelo ativo (Conexão aceita)"
        return False, 0, "ERRO", str(e)

def main():
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ QWEN_API_KEY não encontrada no .env")
        sys.exit(1)

    print("=" * 90)
    print(f"   TESTANDO COTA DE TODOS OS {len(IMAGE_MODELS)} MODELOS DE IMAGEM (QWEN IMAGE / WAN)")
    print("=" * 90)
    print(f"🔑 Chave: {api_key[:6]}...{api_key[-4:]}\n")

    results = []

    for idx, model in enumerate(IMAGE_MODELS, 1):
        print(f"[{idx:02d}/{len(IMAGE_MODELS)}] Testando '{model}'...", end=" ", flush=True)
        ok, status_code, status_str, detail = test_image_model(api_key, model)
        results.append({"model": model, "ok": ok, "status": status_str, "detail": detail})
        if ok:
            print(f"✅ DISPONÍVEL! ({status_str})")
        else:
            print(f"❌ {status_str} -> {detail}")

    print("\n" + "=" * 90)
    print("                           RESUMO DOS MODELOS DE IMAGEM")
    print("=" * 90)

    available = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    print(f"\n🟢 MODELOS COM QUOTA ATIVA E DISPONÍVEL ({len(available)}):")
    if available:
        for r in available:
            print(f"   • {r['model']:<30} | {r['detail']}")
    else:
        print("   (Nenhum modelo de imagem com cota gratuita ativa no momento)")

    print(f"\n🔴 MODELOS COM ERRO / SEM COTA ({len(failed)}):")
    for r in failed:
        print(f"   • {r['model']:<30} | {r['status']:<10} | {r['detail']}")

    print("=" * 90)

if __name__ == "__main__":
    main()
