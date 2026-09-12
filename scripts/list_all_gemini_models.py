#!/usr/bin/env python3
"""
Script para listar todos os modelos disponíveis na API do Gemini,
destacando especialmente os modelos de TTS (Text-to-Speech / Áudio).
"""

import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ GEMINI_API_KEY não encontrada no .env")
    sys.exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
response = requests.get(url, timeout=12)

if response.status_code != 200:
    print(f"❌ Erro HTTP {response.status_code}: {response.text}")
    sys.exit(1)

data = response.json()
all_models = data.get("models", [])

tts_models = []
text_models = []
image_models = []
embedding_models = []
other_models = []

for m in all_models:
    name = m.get("name", "").replace("models/", "")
    display = m.get("displayName", name)
    methods = m.get("supportedGenerationMethods", [])
    in_limit = m.get("inputTokenLimit")
    out_limit = m.get("outputTokenLimit")
    
    item = {
        "id": name,
        "display": display,
        "methods": methods,
        "input_max": f"{in_limit:,}" if in_limit else "N/A",
        "output_max": f"{out_limit:,}" if out_limit else "N/A"
    }

    if "tts" in name.lower() or "lyria" in name.lower() or "audio" in name.lower() or "speech" in name.lower():
        tts_models.append(item)
    elif "image" in name.lower() or "imagen" in name.lower() or "banana" in name.lower() or "veo" in name.lower():
        image_models.append(item)
    elif "embed" in name.lower():
        embedding_models.append(item)
    elif "generateContent" in methods:
        text_models.append(item)
    else:
        other_models.append(item)

print("=" * 90)
print(f"       LISTA COMPLETA DE MODELOS GEMINI DISPONÍVEIS NA SUA CHAVE ({len(all_models)} TOTAL)")
print("=" * 90)

print("\n🎙️ 1. MODELOS DE TTS / ÁUDIO (Text-to-Speech & Músicas):")
print("-" * 90)
for idx, m in enumerate(tts_models, 1):
    print(f"   {idx:02d}. ID: {m['id']:<38} | Nome: {m['display']:<32}")
    print(f"       Input Max: {m['input_max']:>10} tokens | Output Max: {m['output_max']:>7} tokens | Métodos: {', '.join(m['methods'])}")

print("\n🖼️ 2. MODELOS DE IMAGEM & VÍDEO (Imagen / Veo / Vision):")
print("-" * 90)
for idx, m in enumerate(image_models, 1):
    print(f"   {idx:02d}. ID: {m['id']:<38} | Nome: {m['display']}")

print("\n📝 3. MODELOS PRINCIPAIS DE TEXTO & MULTIMODAL (LLMs):")
print("-" * 90)
for idx, m in enumerate(text_models, 1):
    print(f"   {idx:02d}. ID: {m['id']:<38} | Input: {m['input_max']:>10} | Output: {m['output_max']:>7} | {m['display']}")

print("\n🔍 4. MODELOS DE EMBEDDING & OUTROS:")
print("-" * 90)
for idx, m in enumerate(embedding_models + other_models, 1):
    print(f"   {idx:02d}. ID: {m['id']:<38} | {m['display']}")

print("\n" + "=" * 90)
