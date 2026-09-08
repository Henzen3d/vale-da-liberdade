#!/usr/bin/env python3
"""
Testador de Quota e Validação de Gemini TTS 3.1 para as Chaves de API do Vale da Liberdade.
"""
import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

keys = [
    ("GEMINI_API_KEY (Chave 1)", os.environ.get("GEMINI_API_KEY", "").strip()),
    ("GEMINI_API_KEY_2 (Chave 2)", os.environ.get("GEMINI_API_KEY_2", "").strip()),
    ("GEMINI_API_KEY_3 (Chave 3)", os.environ.get("GEMINI_API_KEY_3", "").strip()),
    ("GEMINI_API_KEY_4 (Chave 4)", os.environ.get("GEMINI_API_KEY_4", "").strip()),
    ("GEMINI_API_KEY_5 (Chave 5)", os.environ.get("GEMINI_API_KEY_5", "").strip()),
    ("GEMINI_API_KEY_6 (Chave 6)", os.environ.get("GEMINI_API_KEY_6", "").strip()),
    ("GEMINI_API_KEY_7 (Chave 7)", os.environ.get("GEMINI_API_KEY_7", "").strip()),
]

MODEL = "gemini-3.1-flash-tts-preview"
URL_TEMPLATE = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={{key}}"

print("=" * 95, flush=True)
print(f"RELATÓRIO DE QUOTAS GEMINI TTS: {MODEL}", flush=True)
print("=" * 95, flush=True)

payload = {
    "contents": [{"parts": [{"text": "Vale da Liberdade, jornalismo diário."}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": "Charon"}
            }
        }
    }
}
data_bytes = json.dumps(payload).encode("utf-8")
headers = {"Content-Type": "application/json"}

results = []

for label, key in keys:
    if not key:
        results.append((label, "N/A", "❌ NÃO CONFIGURADA", "N/A"))
        continue

    key_prev = f"{key[:8]}...{key[-6:]}"
    url = URL_TEMPLATE.format(key=key)
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            elapsed = time.time() - t0
            raw = json.loads(resp.read().decode("utf-8"))
            parts = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            has_audio = bool(parts and "inlineData" in parts[0])
            if has_audio:
                status = f"✅ ATIVA (Quota 100% OK)"
            else:
                status = f"⚠️ Resposta Sem Áudio"
            results.append((label, key_prev, status, f"{elapsed:.2f}s"))
    except urllib.error.HTTPError as he:
        elapsed = time.time() - t0
        err_body = he.read().decode("utf-8", errors="ignore")
        if he.code == 429:
            status = "🚫 QUOTA ESGOTADA (429 Rate Limit)"
        elif he.code == 401:
            status = "❌ CHAVE REVOGADA/EXPIRADA (401)"
        elif he.code == 403:
            status = "❌ SEM PERMISSÃO (403)"
        else:
            status = f"❌ HTTP {he.code}"
        results.append((label, key_prev, status, f"{elapsed:.2f}s"))
    except Exception as e:
        elapsed = time.time() - t0
        results.append((label, key_prev, f"❌ ERRO ({str(e)[:30]})", f"{elapsed:.2f}s"))

print(f"{'CHAVE':<28} | {'PREVIEW':<18} | {'STATUS DA QUOTA':<32} | {'LATÊNCIA'}", flush=True)
print("-" * 95, flush=True)
for label, key_prev, status, latency in results:
    print(f"{label:<28} | {key_prev:<18} | {status:<32} | {latency}", flush=True)
print("=" * 95, flush=True)
