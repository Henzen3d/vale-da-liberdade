#!/usr/bin/env python3
"""
Script para testar as 3 chaves do Gemini (.env) e listar os modelos disponíveis no nível gratuito.
"""

import os
import sys
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

# Forçar UTF-8 na saída do console no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Garantir carregamento do .env da raiz do projeto
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

# Tentar importar o SDK oficial google-genai
try:
    from google import genai
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

# Chaves a serem testadas
KEYS_TO_TEST = [
    ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
    ("GEMINI_API_KEY_2", os.getenv("GEMINI_API_KEY_2")),
    ("GEMINI_API_KEY_3", os.getenv("GEMINI_API_KEY_3")),
]


def mask_key(key: str) -> str:
    """Retorna uma versão mascarada da chave para segurança no terminal."""
    if not key:
        return "[NÃO CONFIGURADA]"
    if len(key) <= 10:
        return key[:3] + "..." + key[-3:]
    return key[:6] + "..." + key[-4:]


def list_models_rest(api_key: str):
    """Puxa a lista de modelos diretamente via REST API do Google AI Studio."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            gen_models = []
            for m in models:
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    name = m.get("name", "").replace("models/", "")
                    gen_models.append({
                        "id": name,
                        "displayName": m.get("displayName", name),
                        "inputTokenLimit": m.get("inputTokenLimit"),
                        "outputTokenLimit": m.get("outputTokenLimit"),
                    })
            return True, gen_models, None
        else:
            return False, [], f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, [], str(e)


def test_model_generation(api_key: str, model_id: str):
    """Testa uma geração rápida (ping) para verificar se o modelo responde na cota gratuita."""
    prompt = "Responda apenas com a palavra 'OK'."
    start_time = time.time()

    if HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_id,
                contents=prompt
            )
            elapsed = time.time() - start_time
            text = response.text.strip() if response.text else "Sem texto"
            return True, f"OK ({elapsed:.2f}s) -> '{text}'", elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                return False, f"Cota/Rate Limit Excedido (429)", elapsed
            elif "404" in err_msg or "NOT_FOUND" in err_msg:
                return False, f"Modelo Não Encontrado (404)", elapsed
            elif "403" in err_msg or "PERMISSION_DENIED" in err_msg:
                return False, f"Sem Permissão / Chave Inválida (403)", elapsed
            else:
                clean_err = err_msg.replace("\n", " ")[:100]
                return False, f"Erro: {clean_err}", elapsed
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            response = requests.post(url, json=payload, timeout=15)
            elapsed = time.time() - start_time
            if response.status_code == 200:
                data = response.json()
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception:
                    text = "OK"
                return True, f"OK ({elapsed:.2f}s) -> '{text}'", elapsed
            elif response.status_code == 429:
                return False, f"Cota/Rate Limit Excedido (429)", elapsed
            else:
                return False, f"HTTP {response.status_code}: {response.text[:100]}", elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            return False, f"Erro REST: {str(e)[:100]}", elapsed


def main():
    print("=" * 80)
    print("      DIAGNÓSTICO E TESTE DE CHAVES GEMINI (NÍVEL GRATUITO / FREE TIER)")
    print("=" * 80)
    print(f"SDK 'google-genai': {'Instalado e Ativo' if HAS_GENAI_SDK else 'Não instalado (usando fallback REST)'}")
    print(f"Arquivo de ambiente (.env): {env_path}\n")

    for env_var, api_key in KEYS_TO_TEST:
        print("-" * 80)
        masked = mask_key(api_key)
        print(f"🔑 Testando Chave: {env_var} ({masked})")

        if not api_key:
            print("❌ VARIÁVEL NÃO ENCONTRADA OU VAZIA NO .ENV!\n")
            continue

        # 1. Puxar lista de modelos disponíveis
        success, models, err = list_models_rest(api_key)
        if not success:
            print(f"❌ Falha ao listar modelos para a chave: {err}\n")
            continue

        print(f"✅ Chave VÁLIDA! Encontrados {len(models)} modelos com suporte a geração de conteúdo.\n")
        print("📋 Modelos disponíveis retornados pela API (Nível Gratuito / AI Studio):")
        for idx, m in enumerate(models, 1):
            limit_in = f"{m['inputTokenLimit']:,}" if m['inputTokenLimit'] else "N/A"
            limit_out = f"{m['outputTokenLimit']:,}" if m['outputTokenLimit'] else "N/A"
            print(f"   {idx:02d}. {m['id']:<35} | Input max: {limit_in:>10} tokens | Output max: {limit_out:>7} tokens")

        # 2. Testar na prática os modelos mais relevantes
        print("\n🧪 Testando requisições práticas nos principais modelos:")
        test_candidates = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro",
            "gemini-1.5-pro",
            "gemini-2.5-flash-lite"
        ]

        available_ids = {m["id"] for m in models}
        models_to_test = [m_id for m_id in test_candidates if m_id in available_ids]

        # Se nenhum candidate específico da lista for encontrado, testa os primeiros 5 da lista
        if not models_to_test:
            models_to_test = [m["id"] for m in models[:5]]

        for m_id in models_to_test:
            ok, msg, _ = test_model_generation(api_key, m_id)
            icon = "🟢" if ok else "🔴"
            print(f"   {icon} {m_id:<30} -> {msg}")
            time.sleep(1)

        print()

    print("=" * 80)
    print(" Diagnostic concluído com sucesso! ")
    print("=" * 80)


if __name__ == "__main__":
    main()
