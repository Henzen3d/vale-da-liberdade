#!/usr/bin/env python3
"""
Pós-processamento de naturalidade (§7.1) sobre o roteiro JSON.

- Remove aberturas de telejornal
- Remove muletas de transição empilhadas ("Vai daí…", "Olha, vai daí…")
- Injeta chamada de nome com parcimônia (sem "Olha, X:")
- Corta falas com 4+ frases para no máx. 3
- NÃO injeta mais transições mecânicas (isso soava robótico)

Uso:
  python3 scripts/naturalize_roteiro.py --date 2026-07-23
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_script import EPISODES_DIR, RoteiroCompleto, format_script  # noqa: E402
from validate_naturalidade import validate_naturalidade  # noqa: E402

# Muletas que o LLM/polish repetiam demais — strip no início da fala
# Suavizado para preservar interjeições e reações naturais espontâneas (ex.: "Peraí", "Olha só", "Olha isso")
TRANSITION_CRUTCH_RE = re.compile(
    r"^\s*("
    r"(olha[,:]?\s+)?(vai\s+da[ií]\s*[…\.:,-]?\s*)|"
    r"(olha[,:]?\s+)?(agora\s+segura\s+essa\s*[:\-—,]?\s*)|"
    r"(olha[,:]?\s+)?(pois\s+é,?\s+e\s+tem\s+mais\s*[:\-—,]?\s*)"
    r")+",
    re.I,
)

# Stacks ruins no meio: "Olha, Ricardo: vai daí…"
MID_STACK_RE = re.compile(
    r"\b(olha[,:]?\s+)?(peter|ricardo)\s*[:\-—,]?\s*"
    r"(vai\s+da[ií]|agora\s+segura\s+essa|pois\s+é,?\s+e\s+tem\s+mais)\s*[…\.:,-]?\s*",
    re.I,
)

TELEJORNAL_STRIP = re.compile(
    r"^\s*("
    r"Na\s+(segurança|saude|saúde|educação|educacao|política|politica|economia|comunidade|"
    r"mesma\s+\w+)\b[^,.]*[,:]?\s*"
    r"|Ainda\s+(sobre|na|no|em)\b[^,.]*[,:]?\s*"
    r"|E\s+em\s+\w+[^,.]*[,:]?\s*"
    r"|No\s+quadro\b[^,.]*[,:]?\s*"
    r"|Indo\s+para\s+(a\s+)?\w+[^,.]*[,:]?\s*"
    r"|E\s+fechando\b[^,.]*[,:]?\s*"
    r"|E\s+no\s+(esporte|mundo|brasil|lazer)\b[^,.]*[,:]?\s*"
    r"|Vamos\s+(à|a|para)\s+(a\s+)?(segurança|saúde|saude|educação)[^,.]*[,:]?\s*"
    r"|Também\s+em\s+(saúde|saude|educação|segurança)[^,.]*[,:]?\s*"
    r")",
    re.I,
)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _cap_sentences(text: str, max_n: int = 3) -> str:
    sents = _split_sentences(text)
    if len(sents) > max_n:
        kept = sents[:max_n]
        out = " ".join(kept)
        if out and out[-1] not in ".!?…":
            out += "."
        return out
    ends = list(re.finditer(r"[.!?…]+", text))
    if len(ends) > max_n:
        cut = ends[max_n - 1].end()
        return text[:cut].strip()
    return text.strip()


def _strip_telejornal(text: str) -> str:
    t = text.strip()
    for _ in range(2):
        t2 = TELEJORNAL_STRIP.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def _strip_transition_crutches(text: str) -> str:
    """Remove muletas de transição no início e stacks 'Olha + vai daí'."""
    t = text.strip()
    # stacks no meio primeiro
    t = MID_STACK_RE.sub(
        lambda m: (m.group(2).capitalize() + ", ") if m.group(2) else "",
        t,
    )
    # início da fala — tira até 3 camadas
    for _ in range(3):
        t2 = TRANSITION_CRUTCH_RE.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    # "Olha, Ricardo: " no início ok se não empilhar muleta depois — já limpo
    # capitaliza
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    # limpa "Ricardo, ," etc.
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # restos tipo ". Em Rio" ou ": texto" ou "… texto" após strip
    t = re.sub(r"^[\s\.…,:;\-—]+", "", t).strip()
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def _soften_name_commas(text: str) -> str:
    """Remove vírgula ao redor do nome — TTS pausa e fica artificial.

    Ruim:  "falha do Estado, Peter" / "Peter, você viu"
    Bom:   "falha do Estado Peter" / "Peter você viu"
    """
    # ", Peter" / ", Ricardo" / ", Piter"
    text = re.sub(r",\s*(Peter|Ricardo|Piter)\b", r" \1", text)
    # "Peter, " / "Ricardo, " / "Piter, " (vocativo no início/meio)
    text = re.sub(r"\b(Peter|Ricardo|Piter),\s+", r"\1 ", text)
    # limpa espaços duplos
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _has_other_name(text: str, speaker: str) -> bool:
    other = "Ricardo" if speaker == "Peter" else "Peter"
    if other == "Peter":
        return bool(re.search(r"\b(Peter|Piter)\b", text, re.I))
    return bool(re.search(rf"\b{other}\b", text, re.I))


def _inject_name(text: str, speaker: str) -> str:
    """Injeta nome do outro SEM vírgula (evita pausa no TTS).

    Preferência: no fim da 1ª frase curta, senão prefixo sem vírgula.
    """
    if _has_other_name(text, speaker):
        return text
    other = "Ricardo" if speaker == "Peter" else "Peter"
    low = text.lower()
    if low.startswith(other.lower()) or low.startswith("piter"):
        return text

    # Tenta encaixar no fim da primeira frase (padrão natural em PT falado)
    m = re.match(r"^(.+?[.!?…])(\s*)(.*)$", text, re.S)
    if m and len(m.group(1)) <= 160:
        first, sp, rest = m.group(1), m.group(2), m.group(3)
        # "frase. " -> "frase Other."
        core = first.rstrip(".!?…").rstrip()
        punct = first[len(first.rstrip(".!?…")) :] or "."
        first2 = f"{core} {other}{punct}"
        return f"{first2}{sp}{rest}".strip()

    # Prefixo sem vírgula: "Ricardo o impacto..." 
    body = text[0].lower() + text[1:] if text and text[0].isupper() and len(text) > 1 else text
    return f"{other} {body}"


def polish_turns(items: list[dict]) -> list[dict]:
    """Polishes a list of {quadro, speaker, texto}."""
    out = []
    prev_quadro = None
    idx_in_quadro = 0
    turns_since_name = 0

    for it in items:
        quadro = it.get("quadro") or ""
        speaker = (it.get("speaker") or "Peter").strip()
        if speaker not in ("Peter", "Ricardo"):
            speaker = "Peter"
        texto = (it.get("texto") or "").strip()
        if not texto:
            continue

        if quadro != prev_quadro:
            prev_quadro = quadro
            idx_in_quadro = 0
            turns_since_name = 0

        # 1) strip telejornal
        texto = _strip_telejornal(texto)
        # 2) strip transition crutches
        texto = _strip_transition_crutches(texto)
        # 3) cap sentences
        texto = _cap_sentences(texto, 3)
        # 4) vírgula no nome → pausa artificial no TTS
        texto = _soften_name_commas(texto)

        # 5) name injection ~50% menos frequente: a cada 6 falas (antes era 3)
        turns_since_name += 1
        if idx_in_quadro > 0 and turns_since_name >= 6:
            texto = _inject_name(texto, speaker)
            texto = _soften_name_commas(texto)  # garante sem vírgula
            turns_since_name = 0

        out.append({"quadro": quadro, "speaker": speaker, "texto": texto})
        idx_in_quadro += 1

    return out


def _thin_name_mentions(items: list[dict], every_n: int = 2) -> list[dict]:
    """Remove ~50% das menções de nome já existentes (mantém 1 a cada every_n).

    Não mexe no rótulo Peter:/Ricardo: — só no corpo da fala.
    """
    keep_counter = 0
    out = []
    for it in items:
        texto = it.get("texto") or ""
        speaker = it.get("speaker") or "Peter"

        def repl(m: re.Match) -> str:
            nonlocal keep_counter
            keep_counter += 1
            # mantém 1, remove 1, mantém 1...
            if keep_counter % every_n == 0:
                # remove nome + espaço adjacente
                return ""
            return m.group(0)

        # remove menções ao OUTRO (e Piter)
        if speaker == "Peter":
            texto2 = re.sub(r"\bRicardo\b", repl, texto)
        else:
            texto2 = re.sub(r"\b(Peter|Piter)\b", repl, texto)

        texto2 = re.sub(r"\s{2,}", " ", texto2)
        texto2 = re.sub(r"\s+([.?!,;:])", r"\1", texto2)
        texto2 = texto2.strip()
        if texto2 and texto2[0].islower():
            texto2 = texto2[0].upper() + texto2[1:]
        it = {**it, "texto": texto2}
        out.append(it)
    return out


def polish_roteiro_dict(data: dict) -> dict:
    result = {
        "manchetes": list(data.get("manchetes") or []),
        "introducao": polish_turns(list(data.get("introducao") or [])),
        "quadros": polish_turns(list(data.get("quadros") or [])),
        "fechamento": polish_turns(list(data.get("fechamento") or [])),
    }
    # rarefaz nomes já presentes no texto do LLM (~50%)
    result["introducao"] = _thin_name_mentions(result["introducao"], every_n=2)
    result["quadros"] = _thin_name_mentions(result["quadros"], every_n=2)
    result["fechamento"] = _thin_name_mentions(result["fechamento"], every_n=2)
    # re-aplica soften (caso thin deixe sujeira) + cap
    for key in ("introducao", "quadros", "fechamento"):
        fixed = []
        for it in result[key]:
            t = _soften_name_commas(it.get("texto") or "")
            t = _cap_sentences(t, 3)
            fixed.append({**it, "texto": t})
        result[key] = fixed
    RoteiroCompleto(**result)
    return result


def critical_issues(md_text: str) -> list[str]:
    return [i for i in validate_naturalidade(md_text) if i.startswith("❌")]


def polish_file(date: str) -> Path:
    path = EPISODES_DIR / f"roteiro-{date}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    before_md = format_script(date, RoteiroCompleto(**data))
    before_crit = critical_issues(before_md)

    polished = polish_roteiro_dict(data)
    after_md = format_script(date, RoteiroCompleto(**polished))
    after_crit = critical_issues(after_md)

    words_before = len(before_md.split())
    words_after = len(after_md.split())
    if words_before > 500 and words_after < int(words_before * 0.75):
        raise ValueError(
            f"Polimento reduziu drasticamente o roteiro ({words_before} -> {words_after} palavras). Abortado."
        )
    path.write_text(json.dumps(polished, ensure_ascii=False, indent=2), encoding="utf-8")
    # also rewrite md
    md_path = EPISODES_DIR / f"{date}.md"
    md_path.write_text(after_md, encoding="utf-8")

    # count crutches before/after
    def count_crutches(t: str) -> int:
        low = t.lower()
        return sum(
            low.count(p)
            for p in ("vai daí", "vai dai", "segura essa", "pois é, e tem mais", "peraí", "perai")
        )

    print(f"✅ Polido: {path}")
    print(f"   Críticos antes: {len(before_crit)} → depois: {len(after_crit)}")
    print(f"   Muletas transição: {count_crutches(before_md)} → {count_crutches(after_md)}")
    for i in after_crit[:5]:
        print(f"   ainda: {i}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Pós-processa naturalidade no roteiro JSON")
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    try:
        polish_file(args.date)
        return 0
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
