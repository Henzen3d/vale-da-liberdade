#!/usr/bin/env python3
"""
Digest semanal de evolução de persona — Pipeline Brasil e Mundo (Fase 5).

Consolida todas as análises de estilo brutas da semana em um único
arquivo de revisão legível para aprovação manual.

Filtros aplicados antes de gerar sugestões:
  - Reforço vs. novidade: padrões já em peter_style_evolution.json são descartados
  - Conflitos: sinaliza contradições com traços já estabelecidos

NÃO altera o pipeline diário nem o SOUL.md automaticamente.
Revisão e aprovação são SEMPRE manuais.

Uso:
    python scripts/bm_persona_digest.py
    python scripts/bm_persona_digest.py --dry-run   # não move para processed/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
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

SUBS_DIR   = PROJECT_ROOT / "persona_suggestions" / "raw"
PROC_DIR   = SUBS_DIR / "processed"
DIGEST_DIR = PROJECT_ROOT / "persona_suggestions"
EVOLUTION_PATH = PROJECT_ROOT / "presenters" / "peter_style_evolution.json"

DIGEST_PROMPT = """Você é um consultor de desenvolvimento de personagem de podcast.

Abaixo estão N análises de estilo do apresentador do canal ANCAPSU, coletadas ao longo de uma semana.
Seu trabalho: identificar padrões NOVOS e CONSISTENTES que poderiam enriquecer a persona do Peter Albuquerque
(um locutor de podcast com perfil libertário/anarcocapitalista similar).

=== PERSONA ATUAL DO PETER ===
{peter_current}

=== ANÁLISES DA SEMANA ({n_videos} vídeos) ===
{analyses}

=== REGRAS PARA AS SUGESTÕES ===
1. APENAS padrões que aparecem em pelo menos 3 vídeos diferentes (consistência)
2. DESCARTAR padrões que já estão na persona atual do Peter (sem reforços)
3. SINALIZAR conflitos com a persona atual com ⚠️
4. NUNCA copiar frases ou catchphrases literais — descreva o PADRÃO
5. Foco em: estrutura argumentativa, vocabulário, tom, cadência
6. NÃO incluir opiniões ou posições políticas específicas — só ESTILO

Retorne APENAS este JSON:
{{
  "periodo": "{period}",
  "videos_analisados": {n_videos},
  "sugestoes": [
    {{
      "categoria": "vocabulario|estrutura|tom|cadencia",
      "padrao_observado": "descrição objetiva do padrão",
      "frequencia": "X de N vídeos",
      "video_ids": ["id1", "id2", "id3"],
      "sugestao_para_soul_md": "texto proposto para adicionar ao SOUL.md do Peter",
      "conflito_com_atual": "descrição do conflito se houver, ou null"
    }}
  ],
  "nota_guardrail": "observação geral sobre risco de overfitting no estilo do ANCAPSU"
}}

Se não houver padrões novos suficientes (< 3 vídeos), retorne sugestoes como lista vazia."""


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


def _call_gemini(prompt: str) -> str:
    keys = _candidate_keys("GEMINI_API_KEY")
    if not keys:
        raise RuntimeError("GEMINI_API_KEY ausente")
    from gemini_client import GeminiClient, GeminiMultiClient
    client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
    for model in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview", "gemma-4-31b-it"]:
        try:
            resp = client.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": 0.3, "max_output_tokens": 4096,
                        "response_mime_type": "application/json"},
            )
            text = getattr(resp, "text", None) or ""
            if text.strip():
                return text
        except Exception as exc:
            print(f"  ⚠ {model}: {exc}")
            time.sleep(2)
    raise RuntimeError("Digest LLM falhou")


def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{"); end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text[start:end+1])
            return json.loads(cleaned)
    raise ValueError("Nenhum JSON encontrado")


def load_evolution() -> dict:
    if EVOLUTION_PATH.exists():
        return json.loads(EVOLUTION_PATH.read_text(encoding="utf-8"))
    return {}


def load_week_analyses() -> list[dict]:
    """Carrega todos os arquivos de análise bruta não processados."""
    SUBS_DIR.mkdir(parents=True, exist_ok=True)
    analyses = []
    for f in sorted(SUBS_DIR.glob("*.json")):
        if f.name == "processed":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            analyses.append(data)
        except Exception as exc:
            print(f"⚠️  Ignorando {f.name}: {exc}")
    return analyses


def format_digest_md(digest_data: dict, analyses: list[dict]) -> str:
    """Formata o digest como Markdown legível para revisão humana."""
    today = datetime.now().strftime("%Y-%m-%d")
    n = digest_data.get("videos_analisados", len(analyses))
    period = digest_data.get("periodo", today)
    sugestoes = digest_data.get("sugestoes", [])

    lines = [
        f"# Digest Semanal de Persona — Peter Albuquerque",
        f"**Período:** {period}  ",
        f"**Vídeos analisados:** {n}  ",
        f"**Gerado em:** {today}  ",
        "",
        "> [!WARNING]",
        "> Esta é uma sugestão para REVISÃO MANUAL. NENHUMA mudança é aplicada automaticamente.",
        "> Copie apenas o que fizer sentido para o `presenters/peter_style_evolution.json`.",
        "",
        "---",
        "",
    ]

    if not sugestoes:
        lines += [
            "## Resultado",
            "",
            "✅ Nenhum padrão novo suficientemente consistente identificado esta semana.",
            "Os padrões observados já estão cobertos pela persona atual ou aparecem em menos de 3 vídeos.",
            "",
        ]
    else:
        lines += [f"## {len(sugestoes)} Sugestão(ões) de Atualização", ""]

        for i, sug in enumerate(sugestoes, 1):
            conflito = sug.get("conflito_com_atual")
            lines += [
                f"### Sugestão {i} — {sug.get('categoria', '').upper()}",
                "",
                f"**Padrão observado:** {sug.get('padrao_observado', '')}",
                f"**Frequência:** {sug.get('frequencia', '')}",
                f"**Vídeos de origem:** `{', '.join(sug.get('video_ids', []))}`",
                "",
                "**Sugestão para `peter_style_evolution.json`:**",
                "```",
                sug.get("sugestao_para_soul_md", ""),
                "```",
            ]
            if conflito:
                lines += [
                    "",
                    f"> ⚠️ **Conflito com persona atual:** {conflito}",
                ]
            lines += ["", "---", ""]

    nota = digest_data.get("nota_guardrail", "")
    if nota:
        lines += [
            "## 🛡️ Guardrail",
            "",
            nota,
            "",
            "> Recomendação: revisar o `peter_style_evolution.json` completo mensalmente",
            "> para checar se o Peter ainda soa como o personagem original,",
            "> não uma cópia progressiva do apresentador do ANCAPSU.",
            "",
        ]

    lines += [
        "---",
        "",
        "## Vídeos desta Semana",
        "",
    ]
    for a in analyses:
        lines.append(f"- [{a.get('title', a['video_id'])[:70]}]({a.get('url', '')})  ")
        lines.append(f"  `{a.get('video_id', '')}` — {a.get('analyzed_at', '')[:10]}")

    return "\n".join(lines)


def run_digest(dry_run: bool = False) -> None:
    analyses = load_week_analyses()
    if not analyses:
        print("ℹ️  Nenhuma análise bruta encontrada. Execute bm_persona_watch.py primeiro.")
        return

    print(f"📊 Gerando digest com {len(analyses)} análise(s)...")

    evolution = load_evolution()
    peter_current = json.dumps({
        k: v for k, v in evolution.items()
        if k not in ("videos_processados", "ultima_atualizacao", "changelog")
    }, ensure_ascii=False, indent=2)

    # Montar resumo das análises para o LLM
    analyses_text = ""
    for i, a in enumerate(analyses[:30], 1):  # Limitar a 30 para não exceder contexto
        style = a.get("style_analysis", {})
        analyses_text += f"\n--- Vídeo {i}: {a.get('title', a['video_id'])[:60]} ---\n"
        analyses_text += f"video_id: {a['video_id']}\n"
        for key, val in style.items():
            if isinstance(val, list):
                analyses_text += f"{key}: {', '.join(str(x) for x in val[:5])}\n"
            else:
                analyses_text += f"{key}: {str(val)[:150]}\n"

    # Definir período
    now = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    period = f"{week_start} a {now.strftime('%Y-%m-%d')}"

    prompt = DIGEST_PROMPT.format(
        peter_current=peter_current,
        analyses=analyses_text,
        n_videos=len(analyses),
        period=period,
    )

    try:
        response = _call_gemini(prompt)
        digest_data = extract_json(response)
    except Exception as exc:
        print(f"❌ Digest LLM falhou: {exc}")
        # Criar digest mínimo sem LLM
        digest_data = {
            "periodo": period,
            "videos_analisados": len(analyses),
            "sugestoes": [],
            "nota_guardrail": "Análise LLM falhou. Revise os arquivos raw manualmente.",
        }

    # Gerar MD
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    digest_path = DIGEST_DIR / f"digest_{today}.md"
    md_content = format_digest_md(digest_data, analyses)
    digest_path.write_text(md_content, encoding="utf-8")
    print(f"✅ Digest gerado: {digest_path}")

    # Também salvar JSON para referência
    json_path = DIGEST_DIR / f"digest_{today}.json"
    json_path.write_text(json.dumps(digest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Mover arquivos raw processados (a menos que --dry-run)
    if not dry_run:
        PROC_DIR.mkdir(parents=True, exist_ok=True)
        moved = 0
        for a in analyses:
            src = SUBS_DIR / f"{a['video_id']}.json"
            if src.exists():
                dst = PROC_DIR / f"{a['video_id']}.json"
                src.rename(dst)
                moved += 1
        print(f"📦 {moved} arquivo(s) movido(s) para processed/")
    else:
        print("ℹ️  [dry-run] Arquivos raw NÃO foram movidos")

    # Resumo
    sugestoes = digest_data.get("sugestoes", [])
    print(f"\n📋 Resumo do digest:")
    print(f"   Vídeos: {len(analyses)}")
    print(f"   Sugestões novas: {len(sugestoes)}")
    if sugestoes:
        print(f"\n   Para revisar:")
        print(f"   → {digest_path}")
        print(f"\n   ⚠️  NENHUMA mudança foi aplicada automaticamente.")
        print(f"   Copie manualmente o que fizer sentido para peter_style_evolution.json")


def main():
    parser = argparse.ArgumentParser(description="Digest semanal de persona — Brasil e Mundo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gera o digest mas não move arquivos para processed/",
    )
    args = parser.parse_args()
    run_digest(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
