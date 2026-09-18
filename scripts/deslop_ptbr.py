#!/usr/bin/env python3
"""Deslop PT-BR no pipeline Vale: bloco de prompt + auditoria (aviso, não bloqueio).

Detector vendored em deslop_detector.py (MIT, Henzen3d/Deslop-ptBR).
Não reescreve o roteiro. Não gasta Gemini. Não vira ❌ — oralidade da casa
(pergunta retórica, "olha só", travessão) fica de fora.
"""
from __future__ import annotations

from typing import Any

# Regras que batem no estilo 7.1 / BM (ironia, eco, pergunta).
HOUSE_SKIP = frozenset({"W12", "W15", "W17", "W21", "W22", "W37"})

PROMPT_BLOCK = """
=== DESLOP PT-BR (perfil jornalístico; não pasteurizar a voz da casa) ===
Proibido: gerundismo de SAC ("vou estar enviando"); ademais/outrossim/destarte;
"no cenário atual" / "vale ressaltar que"; "não é sobre X, é sobre Y";
alavancar / orquestrar / rica tapeçaria; fechamento "o futuro já começou".
Obrigatório preservar: pergunta retórica, ironia, "olha só", "né", "pra",
hesitação, bordão da casa. Não inventar fato, número ou nome.
""".strip()


def audit_text(text: str) -> list[dict[str, Any]]:
    """Violações Alta/Média do detector, sem as regras da casa."""
    if not (text or "").strip():
        return []
    from deslop_detector import analyze_text

    result = analyze_text(text)
    out = []
    for v in result.get("violacoes") or []:
        if v.get("regra_id") in HOUSE_SKIP:
            continue
        if v.get("severidade") not in ("Alta", "Média"):
            continue
        out.append(v)
    return out


def warnings_for_markdown(markdown_text: str) -> list[str]:
    """Linhas ⚠️ para validate_naturalidade / log do BM. Nunca ❌."""
    issues: list[str] = []
    for v in audit_text(markdown_text):
        trecho = (v.get("trecho") or "")[:80]
        rid = v.get("regra_id", "?")
        nome = v.get("regra_nome", "")
        issues.append(f"⚠️ Deslop {rid} ({nome}): \"{trecho}\"")
    return issues


def log_audit(label: str, text: str) -> None:
    hits = warnings_for_markdown(text)
    if not hits:
        print(f"   Deslop PT-BR ({label}): limpo")
        return
    print(f"   Deslop PT-BR ({label}): {len(hits)} aviso(s) — não bloqueia")
    for line in hits[:12]:
        print(f"     {line}")
