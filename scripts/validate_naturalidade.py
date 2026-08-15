#!/usr/bin/env python3
"""
Validador de naturalidade / dinâmica conversacional (SKILL §7.1).

Usado por tts_preprocessor.validate_episode() e pode rodar standalone:

  python3 scripts/validate_naturalidade.py episodes/2026-07-22.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SPEAKER_RE = re.compile(r"^(Peter|Ricardo):\s*(.+)$", re.M)

# Aberturas de telejornal / apresentador formal (início da fala)
TELEJORNAL_RE = re.compile(
    r"^\s*("
    r"Na\s+(segurança|saude|saúde|educação|educacao|política|politica|economia|comunidade)\b"
    r"|Ainda\s+(sobre|na|no|em)\b"
    r"|E\s+em\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç]"
    r"|No\s+quadro\b"
    r"|Indo\s+para\s+(a\s+)?"
    r"|Na\s+mesma\s+"
    r"|E\s+fechando\b"
    r"|E\s+no\s+(esporte|mundo|brasil|lazer)\b"
    r"|Vamos\s+(à|a|para)\s+(a\s+)?(segurança|saúde|saude|educação)"
    r"|Também\s+em\s+(saúde|saude|educação|segurança)"
    r")",
    re.I,
)

REACTION_OPENERS = re.compile(
    r"^\s*("
    r"espera|peraí|peraí|pois é|vai daí|isso|exato|exato\.|sério|sério\?"
    r"|você (disse|falou|mencionou)|ricardo,|peter,"
    r"|olha|olha só|agora segura|e tem mais|e por falar|ainda nessa"
    r"|setenta|dez horas|duas toneladas|três anos"  # eco de números comuns
    r")",
    re.I,
)

TRANSITION_PHRASES = [
    "vai daí",
    "agora segura essa",
    "pois é, e tem mais",
    "espera, deixa eu entender",
    "isso aí é sério",
    "peraí",
    "e por falar nisso",
    "ainda nessa área",
    "saindo desse ponto",
    "e tem mais",
    "ricardo, espera",
    "peter, olha",
]

STOPWORDS = {
    "a", "o", "os", "as", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "que", "com", "por", "para", "se",
    "ao", "à", "às", "é", "foi", "ser", "são", "não", "mais", "já", "como",
    "mas", "ou", "também", "isso", "esse", "essa", "este", "esta", "pelo", "pela",
    "seu", "sua", "ele", "ela", "eles", "elas", "lhe", "me", "te", "nos",
}


def _extract_turns(markdown_text: str) -> list[tuple[str, str]]:
    """Lista (speaker, texto) na ordem do roteiro."""
    return [(m.group(1), m.group(2).strip()) for m in SPEAKER_RE.finditer(markdown_text)]


def _sentence_count(text: str) -> int:
    parts = re.split(r"[.!?]+", text.strip())
    return max(1, len([p for p in parts if p.strip()]))


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def _quadro_boundaries(markdown_text: str) -> list[int]:
    """Índices de linha onde começa um novo quadro / intro / fechamento."""
    lines = markdown_text.splitlines()
    starts = []
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if (
            s.startswith("### ")
            or s.startswith("[quadro:")
            or "introdução editorial" in s
            or "fechamento editorial" in s
            or re.match(r"^#{1,3}\s*quadro", s)
        ):
            starts.append(i)
    return starts


def validate_naturalidade(markdown_text: str) -> list[str]:
    """
    Retorna issues no mesmo formato do validate_episode:
    '❌ …' = crítico, '⚠️ …' = aviso.
    """
    issues: list[str] = []
    turns = _extract_turns(markdown_text)
    if len(turns) < 6:
        issues.append("❌ Naturalidade: poucas falas de locutor para avaliar dinâmica (< 6)")
        return issues

    # --- 0) Equilíbrio entre locutores ---
    peter_turns = sum(1 for sp, _ in turns if sp == "Peter")
    ricardo_turns = sum(1 for sp, _ in turns if sp == "Ricardo")
    if peter_turns == 0 or ricardo_turns == 0:
        issues.append("❌ Naturalidade: diálogo unilateral — um dos locutores tem 0 falas no episódio")
    elif min(peter_turns, ricardo_turns) / len(turns) < 0.20:
        issues.append(
            f"❌ Naturalidade: desequilíbrio crítico entre apresentadores "
            f"(Peter: {peter_turns}, Ricardo: {ricardo_turns})"
        )

    # --- 1) Aberturas de telejornal ---
    telejornal_hits: list[str] = []
    for speaker, text in turns:
        if TELEJORNAL_RE.search(text):
            snippet = text[:70].replace("\n", " ")
            telejornal_hits.append(f"{speaker}: {snippet}…")
    if len(telejornal_hits) >= 2:
        issues.append(
            f"❌ Naturalidade: {len(telejornal_hits)} aberturas em formato de telejornal "
            f"(ex.: {telejornal_hits[0]})"
        )
    elif len(telejornal_hits) == 1:
        issues.append(
            f"⚠️ Naturalidade: abertura de telejornal detectada ({telejornal_hits[0]})"
        )

    # --- 2) Fala longa (frases) — regra 3: nunca 4+ ---
    long_strict = []  # 4+ frases = crítico
    long_warn = []  # 3 frases mas muito longas (chars)
    for speaker, text in turns:
        sc = _sentence_count(text)
        if sc >= 4:
            long_strict.append((speaker, sc, len(text)))
        elif sc == 3 and len(text) > 380:
            long_warn.append((speaker, sc, len(text)))
        elif sc <= 2 and len(text) > 280:
            long_warn.append((speaker, sc, len(text)))

    if long_strict:
        sp, sc, n = long_strict[0]
        issues.append(
            f"❌ Naturalidade: fala com {sc} frases ({sp}, {n} chars) — "
            f"limite rígido 2–3 frases, nunca 4+"
        )
        if len(long_strict) > 1:
            issues.append(
                f"⚠️ Naturalidade: {len(long_strict)} falas com 4+ frases"
            )
    if long_warn:
        sp, sc, n = long_warn[0]
        issues.append(
            f"⚠️ Naturalidade: fala densa ({sp}: {sc} frases, {n} chars) — "
            f"prefira frases mais curtas"
        )

    # --- 3) Reação à fala anterior (heurística) ---
    # Agrupa por "blocos" separados por cabeçalhos de quadro
    lines = markdown_text.splitlines()
    first_turn_in_block = True
    no_reaction = 0
    checked = 0
    prev_words: set[str] = set()
    prev_speaker = None

    def is_block_header(line: str) -> bool:
        s = line.strip().lower()
        return (
            s.startswith("###")
            or s.startswith("[quadro")
            or s.startswith("---")
            or "introdução editorial" in s
            or "fechamento" in s
            or bool(re.match(r"^#{1,3}\s*quadro", s))
        )

    for line in lines:
        if is_block_header(line):
            first_turn_in_block = True
            prev_words = set()
            prev_speaker = None
            continue
        m = re.match(r"^(Peter|Ricardo):\s*(.+)$", line.strip())
        if not m:
            continue
        speaker, text = m.group(1), m.group(2)
        if first_turn_in_block or prev_speaker is None:
            first_turn_in_block = False
            prev_words = _content_words(text)
            prev_speaker = speaker
            continue
        checked += 1
        words = _content_words(text)
        overlap = words & prev_words
        reacts = bool(REACTION_OPENERS.search(text)) or len(overlap) >= 1
        # chamar o outro pelo nome conta como reação
        other = "ricardo" if speaker == "Peter" else "peter"
        if other in text.lower():
            reacts = True
        if not reacts:
            no_reaction += 1
        prev_words = words
        prev_speaker = speaker

    if checked >= 8 and no_reaction / max(checked, 1) >= 0.45:
        issues.append(
            f"⚠️ Naturalidade: ~{no_reaction}/{checked} falas não ecoam a anterior "
            f"(falta reação antes do novo ponto)"
        )

    # --- 4) Expressões de transição ---
    lower = markdown_text.lower()
    crutch_patterns = (
        "vai daí", "vai dai", "segura essa", "pois é, e tem mais",
        "peraí", "perai", "isso aí é sério",
    )
    trans_hits = sum(lower.count(p) for p in crutch_patterns)
    n_turns = max(len(turns), 1)
    # Excesso: mais de 1 muleta a cada 4 falas, ou >8 no episódio
    if trans_hits >= max(8, n_turns // 3):
        issues.append(
            f"❌ Naturalidade: excesso de muletas de transição ({trans_hits} em {n_turns} falas) — "
            f"corte 'Vai daí/segura essa/pois é e tem mais/peraí'; prefira ecoar fato/número"
        )
    elif trans_hits >= max(5, n_turns // 4):
        issues.append(
            f"⚠️ Naturalidade: muitas muletas de transição ({trans_hits}) — "
            f"varie com reação ao conteúdo, não com bordão"
        )
    # zero ok agora — reação ao conteúdo basta; não exigir muleta

    # --- 5) Chamar o outro pelo nome (no corpo da fala) ---
    name_mentions = 0
    comma_name = 0
    for speaker, text in turns:
        other = "Ricardo" if speaker == "Peter" else "Peter"
        if re.search(rf"\b{other}\b", text, re.I) or (
            other == "Peter" and re.search(r"\bPiter\b", text, re.I)
        ):
            name_mentions += 1
        if re.search(r",\s*(Peter|Ricardo|Piter)\b", text) or re.search(
            r"\b(Peter|Ricardo|Piter),\s+", text
        ):
            comma_name += 1
    # meta baixa: ~1 a cada 6 falas (antes era ~1/6 mínimo alto demais)
    if name_mentions < max(2, len(turns) // 10):
        issues.append(
            f"⚠️ Naturalidade: poucos chamados pelo nome ({name_mentions} em {len(turns)} falas)"
        )
    if comma_name >= 3:
        issues.append(
            f"⚠️ Naturalidade: {comma_name} nomes com vírgula (causa pausa no TTS) — "
            f"use \"estado Peter\" / \"Peter você\", sem vírgula"
        )

    # --- 6) Fórmula repetida do Peter (fato → Estado) ---
    peter_estado = 0
    peter_total = 0
    for speaker, text in turns:
        if speaker != "Peter":
            continue
        peter_total += 1
        tl = text.lower()
        if "estado" in tl and any(
            k in tl for k in ("monopólio", "burocracia", "imposto", "público", "contribuint", "fiscaliz")
        ):
            peter_estado += 1
    if peter_total >= 6 and peter_estado / peter_total >= 0.75:
        issues.append(
            f"⚠️ Naturalidade: Peter em loop anti-Estado em {peter_estado}/{peter_total} falas "
            f"— variar pergunta/ironia/concordância parcial"
        )

    # --- 7) Conectores genéricos proibidos ---
    banned = ["e para detalhar", "isso mesmo", "exatamente,", "exatamente."]
    for b in banned:
        if b in lower:
            issues.append(f"❌ Naturalidade: conector genérico proibido: \"{b.strip()}\"")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida naturalidade §7.1 de um episódio")
    parser.add_argument("path", help="Caminho do .md do episódio")
    args = parser.parse_args()
    text = Path(args.path).read_text(encoding="utf-8")
    issues = validate_naturalidade(text)
    if not issues:
        print("✅ Naturalidade OK")
        return 0
    print(f"Naturalidade: {len(issues)} issue(s)\n")
    for i in issues:
        print(f"  {i}")
    # exit 1 se houver crítico
    if any(i.startswith("❌") for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
