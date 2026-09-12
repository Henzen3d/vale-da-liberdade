#!/usr/bin/env python3
"""
Teste de geração de imagem usando a SDK Oficial google-genai (client.models.generate_images)
em todas as 7 chaves de API do Gemini.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

from google import genai
from google.genai import types

KEYS_TO_TEST = [
    ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
    ("GEMINI_API_KEY_2", os.getenv("GEMINI_API_KEY_2")),
    ("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3")),
    ("GEMINI_API_KEY_4", os.getenv("GEMINI_API_KEY_4")),
    ("GEMINI_API_KEY_5", os.getenv("GEMINI_API_KEY_5")),
    ("GEMINI_API_KEY_6", os.getenv("GEMINI_API_KEY_6")),
    ("GEMINI_API_KEY_7", os.getenv("GEMINI_API_KEY_7")),
]

IMAGEN_MODELS = [
    "imagen-3.0-generate-002",
    "imagen-3.0-fast-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
]

output_dir = Path(__file__).resolve().parents[1] / "output" / "test_images"
output_dir.mkdir(parents=True, exist_ok=True)

def mask_key(key: str) -> str:
    if not key:
        return "[NÃO CONFIGURADA]"
    return key[:6] + "..." + key[-4:] if len(key) > 10 else key[:3] + "..."

print("=" * 85)
print("  TESTANDO IMAGEN VIA SDK OFICIAL GOOGLE GENAI (generate_images)")
print("=" * 85)

for key_name, key in KEYS_TO_TEST:
    print(f"\n🔑 {key_name} ({mask_key(key)})")
    print("-" * 85)
    if not key:
        print("   ❌ Chave não configurada")
        continue

    client = genai.Client(api_key=key)

    for model_id in IMAGEN_MODELS:
        print(f"   🎨 Modelo: {model_id:<32} -> ", end="", flush=True)
        try:
            result = client.models.generate_images(
                model=model_id,
                prompt="A simple red apple icon on white background",
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    output_mime_type="image/jpeg"
                )
            )
            if result.generated_images:
                img_bytes = result.generated_images[0].image.image_bytes
                out_path = output_dir / f"{key_name}_{model_id}.jpg"
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                print(f"✅ SUCESSO! Imagem gerada ({len(img_bytes)} bytes) -> {out_path.name}")
            else:
                print("⚠️ Sem imagens retornadas.")
        except Exception as e:
            err_msg = str(e).replace("\n", " ")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("❌ Erro 429: Cota Excedida (Rate Limit)")
            elif "404" in err_msg or "NOT_FOUND" in err_msg:
                print("❌ Erro 404: Modelo não encontrado nesta chave/região")
            elif "403" in err_msg or "PERMISSION_DENIED" in err_msg:
                print("❌ Erro 403: Permissão negada")
            else:
                print(f"❌ Erro: {err_msg[:120]}")

print("\n" + "=" * 85)
