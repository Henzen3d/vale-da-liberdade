#!/usr/bin/env python3
"""
Script interativo para listar modelos do Qwen (Alibaba Cloud DashScope / QwenCloud)
e testar cota / disponibilidade de saldo no modelo escolhido.
Sem dependências externas de terceiros (usa apenas biblioteca padrão do Python).

Uso:
  python scripts/check_qwen_models.py                  (modo interativo)
  python scripts/check_qwen_models.py qwen-image-2.0   (passando modelo por argumento)
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

# Ajusta codificação UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def parse_env_file():
    """ Tenta carregar variáveis de ambiente do arquivo .env manualmente """
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'").strip('"')
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

parse_env_file()

# Lista curada de modelos conhecidos do Qwen / DashScope
CATALOG_MODELS = [
    {"id": "qwen-max", "desc": "Qwen Flagship (Mais avançado / raciocínio elevado)"},
    {"id": "qwen-plus", "desc": "Qwen Plus (Equilibrado entre velocidade e inteligência)"},
    {"id": "qwen-turbo", "desc": "Qwen Turbo (Alta velocidade e baixo custo)"},
    {"id": "qwen-long", "desc": "Qwen Long (Suporte a contexto ultra-longo)"},
    {"id": "qwen-image-2.0", "desc": "Qwen Image 2.0 (Geração/Edição de imagens)"},
    {"id": "qwen-image-max", "desc": "Qwen Image Max"},
    {"id": "qwen-image-plus", "desc": "Qwen Image Plus"},
    {"id": "qwen2.5-72b-instruct", "desc": "Qwen 2.5 72B Instruct"},
    {"id": "qwen2.5-coder-32b-instruct", "desc": "Qwen 2.5 Coder 32B (Especializado em código)"},
    {"id": "qwen2.5-vl-72b-instruct", "desc": "Qwen 2.5 Vision-Language 72B (Multimodal / Visão)"},
    {"id": "qwen3.8-max", "desc": "Qwen 3.8 Max (Lançamento recente)"},
]

ENDPOINTS = [
    {"name": "DashScope International", "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"},
    {"name": "DashScope China Mainland", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
]

def get_api_key():
    key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        print("🔑 Nenhuma chave QWEN_API_KEY ou DASHSCOPE_API_KEY encontrada no arquivo .env.")
        key = input("👉 Insira sua API Key do QwenCloud / DashScope: ").strip()
    else:
        print(f"🔑 Chave detectada no .env: {key[:6]}...{key[-4:]}")
    
    if not key:
        print("❌ Chave API é obrigatória para continuar.")
        sys.exit(1)
    return key

def fetch_live_models(api_key, base_url):
    """ Tenta consultar o endpoint /models da API OpenAI compatible do DashScope """
    url = f"{base_url}/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                models_list = data.get("data", [])
                return [m.get("id") for m in models_list if m.get("id")]
    except Exception:
        pass
    return []

def main():
    print("=" * 80)
    print("      QWEN CLOUD / DASHSCOPE - LISTAGEM DE MODELOS & TESTE DE QUOTA")
    print("=" * 80)

    api_key = get_api_key()

    print("\n🔍 Buscando modelos disponíveis via API...")
    live_models = []
    active_base_url = ENDPOINTS[0]["base_url"]

    for ep in ENDPOINTS:
        found = fetch_live_models(api_key, ep["base_url"])
        if found:
            live_models = found
            active_base_url = ep["base_url"]
            print(f"✅ Conectado com sucesso ao endpoint: {ep['name']} ({len(found)} modelos encontrados)")
            break

    # Unifica modelos encontrados dinamicamente com o catálogo
    all_models = []
    seen_ids = set()

    if live_models:
        for m_id in live_models:
            all_models.append({"id": m_id, "desc": "Modelo retornado pela API live"})
            seen_ids.add(m_id)

    for item in CATALOG_MODELS:
        if item["id"] not in seen_ids:
            all_models.append(item)
            seen_ids.add(item["id"])

    selected_model_id = ""
    if len(sys.argv) > 1:
        arg_val = sys.argv[1].strip()
        if arg_val.isdigit():
            c_num = int(arg_val)
            if 1 <= c_num <= len(all_models):
                selected_model_id = all_models[c_num - 1]["id"]
        else:
            selected_model_id = arg_val

    if not selected_model_id:
        print("\n📋 MODELOS DISPONÍVEIS / SUPORTADOS:")
        print("-" * 80)
        for idx, m in enumerate(all_models, 1):
            print(f" [{idx:3d}] ID: {m['id']:<42} | {m['desc']}")

        print("\n [  0] Informar outro modelo customizado (ex: qwen-vl-max)")
        print("-" * 80)

        choice = input("\n👉 Digite o número do modelo que deseja testar: ").strip()

        if choice == "0":
            selected_model_id = input("👉 Digite o ID exato do modelo: ").strip()
        else:
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(all_models):
                    selected_model_id = all_models[choice_num - 1]["id"]
                else:
                    print("❌ Opção inválida!")
                    sys.exit(1)
            except ValueError:
                print("❌ Entrada inválida! Digite um número válido.")
                sys.exit(1)

    print(f"\n🧪 Testando cota e disponibilidade para o modelo: '{selected_model_id}'...")
    print(f"🌐 Base URL: {active_base_url}")
    print("-" * 80)

    # Executa a requisição de teste para validar a quota
    test_model_quota(api_key, active_base_url, selected_model_id)

def test_model_quota(api_key, base_url, model_id):
    # Se for modelo de geração de imagem (ex: qwen-image-2.0, qwen-image-max, etc.)
    if "image" in model_id.lower() and not "vl" in model_id.lower():
        test_images_generations(api_key, base_url, model_id)
    else:
        test_chat_completion(api_key, base_url, model_id)

def test_chat_completion(api_key, base_url, model_id):
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Suporta formato estruturado compatível com texto e multimodal
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Olá, responda apenas 'OK'."}]
            }
        ],
        "max_tokens": 10
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = (time.time() - start_time) * 1000
            print(f"⏱️ Tempo de resposta: {elapsed:.2f} ms")
            print(f"📊 Status HTTP: {resp.status}")

            body = resp.read().decode("utf-8")
            data = json.loads(body)
            choices = data.get("choices", [])
            content = ""
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
            usage = data.get("usage", {})

            print("\n✅ TESTE BEM-SUCEDIDO! QUOTA DISPONÍVEL NA SUA CHAVE!")
            print(f"💬 Resposta do modelo: {str(content).strip()}")
            if usage:
                print(f"📈 Consumo de tokens: Prompt={usage.get('prompt_tokens', 0)}, Completion={usage.get('completion_tokens', 0)}, Total={usage.get('total_tokens', 0)}")

    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"⏱️ Tempo de resposta: {elapsed:.2f} ms")
        print(f"📊 Status HTTP: {e.code}")
        print("\n❌ FALHA NO TESTE / QUOTA INDISPONÍVEL:")

        try:
            err_body = e.read().decode("utf-8")
            err_data = json.loads(err_body)
            error_obj = err_data.get("error", {})
            code = error_obj.get("code") or e.code
            message = error_obj.get("message") or err_body
            print(f"   • Código do erro: {code}")
            print(f"   • Mensagem: {message}")

            if "InsufficientBalance" in str(message) or "quota" in str(message).lower():
                print("\n💡 Diagnóstico: Saldo insuficiente ou cota excedida na chave QwenCloud/DashScope.")
            elif "InvalidApiKey" in str(message) or "auth" in str(message).lower():
                print("\n💡 Diagnóstico: A chave API informada é inválida ou não possui permissão.")
            elif "Model" in str(message) and "not found" in str(message).lower():
                print(f"\n💡 Diagnóstico: O modelo '{model_id}' não está habilitado para esta conta/chave.")
        except Exception:
            print(f"   • Detalhes do erro: {e.reason}")

    except urllib.error.URLError as e:
        print(f"\n❌ Erro na comunicação de rede com a API: {e.reason}")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")

def test_images_generations(api_key, base_url, model_id):
    """ Teste para modelos de geração/edição de imagem (images/generations) """
    url = f"{base_url}/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "prompt": "A small blue circle on white background",
        "n": 1,
        "size": "1024*1024"
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed = (time.time() - start_time) * 1000
            print(f"⏱️ Tempo de resposta: {elapsed:.2f} ms")
            print(f"📊 Status HTTP: {resp.status}")

            body = resp.read().decode("utf-8")
            data = json.loads(body)
            data_items = data.get("data", [])
            img_url = data_items[0].get("url") if data_items else "(imagem gerada com sucesso)"

            print("\n✅ TESTE BEM-SUCEDIDO! QUOTA DE IMAGEM DISPONÍVEL NA SUA CHAVE!")
            print(f"🖼️ Resultado da geração: {img_url}")

    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"⏱️ Tempo de resposta: {elapsed:.2f} ms")
        print(f"📊 Status HTTP: {e.code}")
        print("\n❌ FALHA NO TESTE / QUOTA INDISPONÍVEL:")

        try:
            err_body = e.read().decode("utf-8")
            err_data = json.loads(err_body)
            error_obj = err_data.get("error", {})
            code = error_obj.get("code") or e.code
            message = error_obj.get("message") or err_body
            print(f"   • Código do erro: {code}")
            print(f"   • Mensagem: {message}")

            if "InsufficientBalance" in str(message) or "quota" in str(message).lower() or "Arrears" in str(message):
                print("\n💡 Diagnóstico: Saldo insuficiente ou cota excedida na chave QwenCloud/DashScope.")
            elif "InvalidApiKey" in str(message) or "auth" in str(message).lower():
                print("\n💡 Diagnóstico: A chave API informada é inválida ou não possui permissão.")
        except Exception:
            print(f"   • Detalhes do erro: {e.reason}")

    except urllib.error.URLError as e:
        print(f"\n❌ Erro na comunicação de rede com a API: {e.reason}")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")

if __name__ == "__main__":
    main()
