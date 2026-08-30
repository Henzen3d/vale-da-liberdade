#!/usr/bin/env python3
"""
Analisador de estilo — Pipeline Brasil e Mundo (Fase 5).

Após cada vídeo processado, analisa a transcrição ORIGINAL do canal
ANCAPSU em 4 camadas de estilo e grava observações brutas em
persona_suggestions/raw/{video_id}.json.

NÃO analisa o roteiro condensado — analisa sempre o apresentador original.
NÃO altera o pipeline diário nem o SOUL.md.

Uso:
    python scripts/bm_persona_watch.py --video-id "abc123"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

RAW_DIR  = PROJECT_ROOT / "output" / "brasil_e_mundo" / "raw"
SUBS_DIR = PROJECT_ROOT / "persona_suggestions" / "raw"
EVOLUTION_PATH = PROJECT_ROOT / "presenters" / "peter_style_evolution.json"

ANALYSIS_PROMPT = """Você é um analista de estilo de comunicação. Analise o texto de transcrição abaixo
e identifique padrões de ESTILO do apresentador (nunca opiniões ou conteúdo).

Foque em 4 camadas:
1. ESTRUTURA ARGUMENTATIVA: como o apresentador monta o argumento (abertura, desenvolvimento, fechamento, uso de analogias)
2. VOCABULÁRIO: expressões recorrentes, vocabulário favorito, nível de formalidade
3. TOM: sarcasmo, ironia, agressividade, humor, provocação (escala e forma)
4. CADÊNCIA: frases curtas vs longas, ritmo de fala, pausas dramáticas, perguntas retóricas

REGRAS IMPORTANTES:
- Descreva PADRÕES, não conteúdo/opiniões específicas
- NÃO copie frases literais do apresentador
- Use exemplos apenas para ilustrar o PADRÃO, não como transcrição
- Foco em elementos que poderiam enriquecer a persona de um locutor similar

Transcrição (primeiros ~2000 palavras):
---
{transcript}
---

Retorne APENAS este JSON:
{{
  "estrutura_argumentativa": "descrição objetiva de como ele monta argumentos",
  "vocabulario_frequente": ["palavra1", "palavra2", "..."],
  "expressoes_recorrentes": ["padrão de expressão 1", "padrão de expressão 2"],
  "tom_registro": "descrição do tom dominante e variações",
  "cadencia": "frases curtas/longas, ritmo, uso de pausas e perguntas retóricas",
  "abertura_tipica": "como ele costuma abrir um comentário/notícia",
  "fechamento_tipico": "como ele costuma fechar",
  "nivel_provocacao": "baixo/médio/alto com justificativa",
  "notas_extras": "qualquer padrão interessante não coberto acima"
}}"""


def _candidate_keys(env_name: str) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for k, v in os.environ.items():
        base = env_name
        if k == base or (k.startswith(base + "_") and k[len(base)+1:].isdigit()):
            v = v.strip()
            if v and "***" not in v and v not in seen:
                seen.add(v); keys.append(v)
    for env_path in (PROJECT_ROOT / ".env", Path.home() / ".hermes" / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            base = env_name
            if k == base or (k.startswith(base + "_") and k[len(base)+1:].isdigit()):
                if v and "***" not in v and v not in seen:
                    seen.add(v); keys.append(v)
    return keys


def _call_gemini_lite(prompt: str) -> str:
    """Chamada leve — usa modelo flash-lite para análise de estilo."""
    keys = _candidate_keys("GEMINI_API_KEY")
    if not keys:
        raise RuntimeError("GEMINI_API_KEY ausente")
    from gemini_client import GeminiClient, GeminiMultiClient
    client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
    for model in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemma-4-31b-it"]:
        try:
            resp = client.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": 0.3, "max_output_tokens": 2048,
                        "response_mime_type": "application/json"},
            )
            text = getattr(resp, "text", None) or ""
            if text.strip():
                return text
        except Exception as exc:
            print(f"  ⚠ {model}: {exc}")
            time.sleep(1)
    raise RuntimeError("Análise de estilo falhou (todos os modelos)")


def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            import re as re2
            cleaned = re2.sub(r",\s*([}\]])", r"\1", text[start:end+1])
            return json.loads(cleaned)
    raise ValueError("Nenhum JSON encontrado")


import re


def analyze_video(video_id: str, force: bool = False) -> dict | None:
    SUBS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SUBS_DIR / f"{video_id}.json"

    if out_path.exists() and not force:
        print(f"ℹ️  Análise já existe: {out_path}")
        return json.loads(out_path.read_text(encoding="utf-8"))

    raw_path = RAW_DIR / f"{video_id}.json"
    if not raw_path.exists():
        print(f"⚠️  Transcrição não encontrada: {raw_path}")
        return None

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    transcript = raw.get("transcript", "")
    if not transcript or len(transcript.split()) < 50:
        print(f"⚠️  Transcrição muito curta para análise")
        return None

    # Usar apenas os primeiros ~2000 palavras para a análise (suficiente para padrões)
    words = transcript.split()
    sample = " ".join(words[:2000])

    print(f"🔍 Analisando estilo de '{raw.get('title', video_id)[:60]}'...")

    prompt = ANALYSIS_PROMPT.format(transcript=sample)
    try:
        response = _call_gemini_lite(prompt)
        analysis = extract_json(response)
    except Exception as exc:
        print(f"  ❌ Análise falhou: {exc}")
        return None

    result = {
        "video_id": video_id,
        "title": raw.get("title", ""),
        "channel": raw.get("channel", ""),
        "url": raw.get("url", ""),
        "published": raw.get("published", ""),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "transcript_words": len(words),
        "style_analysis": analysis,
    }

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Análise salva: {out_path}")

    # Incrementar contador no peter_style_evolution.json
    if EVOLUTION_PATH.exists():
        evo = json.loads(EVOLUTION_PATH.read_text(encoding="utf-8"))
        evo["videos_processados"] = evo.get("videos_processados", 0) + 1
        evo["ultima_atualizacao"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        EVOLUTION_PATH.write_text(json.dumps(evo, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def main():
    parser = argparse.ArgumentParser(description="Persona Watch — análise de estilo por vídeo")
    parser.add_argument("--video-id", required=True, help="ID do vídeo do YouTube")
    parser.add_argument("--force", action="store_true", help="Reanalisar mesmo se já existir")
    args = parser.parse_args()

    result = analyze_video(args.video_id, force=args.force)
    if result:
        analysis = result.get("style_analysis", {})
        print(f"\n📊 Resumo da análise:")
        print(f"   Tom: {analysis.get('tom_registro', '—')[:80]}")
        print(f"   Provocação: {analysis.get('nivel_provocacao', '—')}")
        print(f"   Vocabulário: {', '.join(analysis.get('vocabulario_frequente', [])[:6])}")


if __name__ == "__main__":
    main()
