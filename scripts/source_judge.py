#!/usr/bin/env python3
"""
Source Judge — scoring por LLM de fontes candidatas (padrão Fusion).

Cada candidata recebe notas 0–10 em 6 eixos, com pesos:
  - relevancia_geo_tematica   25%
  - qualidade_editorial       25%
  - frequencia_regularidade   15%
  - confiabilidade_tecnica    15%
  - ineditismo                10%
  - transparencia_vies        10%

Score final >= 7.0  -> promove a "candidata testável" (vai para probatória)
Score <  5.0 (recorrente) -> "banida" com motivo.

Se a LLM não estiver disponível, aplica um score heurístico local (fallback)
para não bloquear o pipeline. O Judge NÃO promove nem bane sozinho: ele só
emite o veredito; a governança (source_governance.py) gera o relatório
semanal para aprovação humana.

Uso:
  python3 scripts/source_judge.py --candidates sources/sources_candidates.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("source_judge")

AXES = {
    "relevancia_geo_tematica": 0.25,
    "qualidade_editorial": 0.25,
    "frequencia_regularidade": 0.15,
    "confiabilidade_tecnica": 0.15,
    "ineditismo": 0.10,
    "transparencia_vies": 0.10,
}
PROMOTE = 7.0
BAN = 5.0

JUDGE_SYSTEM = (
    "Você é um editor-chefe que avalia fontes de notícia para um web jornal "
    "hiperlocal de Blumenau / Vale do Itajaí / Santa Catarina. "
    "Receberá dados de uma fonte candidata (nome, URL, trecho de descoberta, "
    "citações de fontes ativas que a mencionam). "
    "Responda APENAS um JSON válido com as chaves abaixo, sem comentários.\n"
    "Esquema OBRIGATÓRIO:\n"
    "{\n"
    '  "relevancia_geo_tematica": <0-10>,\n'
    '  "qualidade_editorial": <0-10>,\n'
    '  "frequencia_regularidade": <0-10>,\n'
    '  "confiabilidade_tecnica": <0-10>,\n'
    '  "ineditismo": <0-10>,\n'
    '  "transparencia_vies": <0-10>,\n'
    '  "score_final": <média ponderada 0-10>,\n'
    '  "veredicto": "promover" | "observar" | "banir",\n'
    '  "motivo": "<texto curto PT-BR>"\n'
    "}\n"
    "Critérios: relevancia=geo/tema útil ao público; qualidade=distigue fato de "
    "opinião, evita clickbait, cita fontes; frequencia=cadência previsível; "
    "confiabilidade=RSS estável > scraping frágil; ineditismo=traz pauta que as "
    "fontes atuais não cobrem; transparencia=se opinativo, é explícito. "
    "score_final = média ponderada pelos pesos (0.25/0.25/0.15/0.15/0.10/0.10)."
)


def _call_openrouter(prompt: str) -> str | None:
    try:
        import requests
    except Exception:
        return None
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    models = [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "openai/gpt-oss-20b:free",
        "poolside/laguna-m.1:free",
    ]
    for model in models:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                          "HTTP-Referer": "https://hermes-agent.nousresearch.com", "X-Title": "WebJornal SourceJudge"},
                json={"model": model, "messages": [
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": prompt},
                ], "temperature": 0.2, "max_tokens": 800},
                timeout=45,
            )
            if resp.status_code >= 400:
                continue
            data = resp.json()
            return (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        except Exception as exc:
            log.warning("OpenRouter %s falhou: %s", model, exc)
    return None


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    blob = fence.group(1) if fence else text
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(blob[start:end + 1])
    except Exception:
        return None


def _heuristic_fallback(c: dict) -> dict:
    """Score local quando a LLM não está disponível (nunca bloqueia o pipeline)."""
    via = c.get("discovery", {}).get("via", "")
    # citation é sinal forte; search é neutro; x é fraco sem conteúdo
    base = {"search": 6.0, "citation": 7.5, "x": 5.5}.get(via, 6.0)
    score = {
        "relevancia_geo_tematica": base,
        "qualidade_editorial": base - 0.5,
        "frequencia_regularidade": base - 1.0,
        "confiabilidade_tecnica": 7.0 if via == "citation" else 6.0,
        "ineditismo": base,
        "transparencia_vies": base,
        "score_final": round(base, 2),
        "veredicto": "promover" if base >= PROMOTE else "observar",
        "motivo": f"score heurístico (LLM indisponível); via={via}",
    }
    return score


def judge_candidate(c: dict) -> dict:
    name = c.get("name", "")
    url = c.get("url", "")
    disc = c.get("discovery", {})
    prompt = (
        f"FONTE CANDIDATA\nNome: {name}\nURL: {url}\n"
        f"Descoberta: via={disc.get('via')} query='{disc.get('query','')}' "
        f"snippet='{(disc.get('snippet') or '')[:300]}'\n"
        f"Citada por: {disc.get('from_raw','')}\n\n"
        "Avalie esta fonte para o web jornal (Blumenau/Vale do Itajaí/SC)."
    )
    text = _call_openrouter(prompt)
    score = _extract_json(text) if text else None
    if not score or "score_final" not in score:
        log.warning("Judge LLM indisponível para %s — usando fallback heurístico", name)
        score = _heuristic_fallback(c)
    # garante pesos e normalização
    for axis in AXES:
        score.setdefault(axis, 5.0)
    try:
        weighted = sum(float(score.get(a, 5.0)) * w for a, w in AXES.items())
    except Exception:
        weighted = float(score.get("score_final", 5.0))
    score["score_final"] = round(weighted, 2)
    if score.get("score_final", 0) >= PROMOTE:
        score["veredicto"] = "promover"
    elif score.get("score_final", 10) < BAN:
        score["veredicto"] = "banir"
    else:
        score["veredicto"] = score.get("veredicto") or "observar"
    return score


def run(candidates_path: Path) -> list[dict]:
    if not candidates_path.exists():
        log.error("Arquivo de candidatas não existe: %s", candidates_path)
        return []
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    cands = data.get("candidates", [])
    log.info("Julgando %d candidatas...", len(cands))
    scored = []
    for c in cands:
        if c.get("judged_at"):
            scored.append(c)
            continue
        sc = judge_candidate(c)
        c["judged_at"] = datetime.now(timezone.utc).isoformat()
        c["judge_score"] = sc
        scored.append(c)
        log.info("  • %s — score=%.2f veredicto=%s", c.get("name"), sc["score_final"], sc["veredicto"])
    candidates_path.write_text(json.dumps({**data, "candidates": scored}, ensure_ascii=False, indent=2), encoding="utf-8")
    return scored


def main() -> int:
    ap = argparse.ArgumentParser(description="Source Judge")
    ap.add_argument("--candidates", default=str(SCRIPT_DIR.parent / "sources" / "sources_candidates.json"))
    args = ap.parse_args()
    run(Path(args.candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
