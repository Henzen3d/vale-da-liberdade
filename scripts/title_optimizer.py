#!/usr/bin/env python3
"""
Gera o TÍTULO OTIMIZADO do episódio do Webjornal Vale da Liberdade a partir do
roteiro JSON (manchetes do dia), seguindo a skill "youtube-journalistic-title-
optimizer":

  - 40-60 caracteres (70 = teto absoluto), informação decisiva nos 40 primeiros
  - palavra-chave/entidade no início (nome, órgão, tema)
  - tensão/contraste, especificidade numérica, tradução de jargão
  - compliance: sem acusação como fato consumado, sem clickbait enganoso,
    sem alarmismo em eventos sensíveis, sem CAIXA ALTA/!!!, sem pilha de emojis

Prioridade de backend:
  1) Gemini (GEMINI_API_KEY) via GeminiClient
  2) OpenRouter (OPENROUTER_API_KEY) com modelos free
Fallback: seleção determinística + limpeza da melhor manchete.

Saída:
  - Stdout: lista de opções com risco + a recomendada
  - Grava em episodes/{date}-title.txt a linha final (título otimizado)

Uso:
  python3 scripts/title_optimizer.py --date 2026-08-07
  python3 scripts/title_optimizer.py --date 2026-08-07 --dry-run   # não grava
  python3 scripts/title_optimizer.py --date 2026-08-07 --force     # reescreve
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

EPISODES_DIR = PROJECT_ROOT / "episodes"

# --- limpeza monolítica -----------------------------------------------------
TITLE_MIN = 40
TITLE_TARGET = 60
TITLE_MAX = 70

# Verbos/juízo que afirmam culpa como fato consumado (risco de difamação).
ACCUSATION_WORDS = [
    "roubou", "farsa", "fraudou", "desviou", "corrompeu", "mentiu",
    "enganou", "golpista", "estelionatário", "ladrão", "ladrao",
]
# Substituições seguras para manter a curiosidade sem afirmar veredito.
ACCUSATION_SAFE = {
    "roubou": "no escândalo",
    "desviou": "sob suspeita",
    "fraudou": "no caso",
    "corrompeu": "no escândalo",
    "mentira": "controvérsia",
    "farsa": "polêmica",
    "farça": "polêmica",
    "farçado": "questionado",
    "enganou": "no caso",
    "propina": "das suspeitas",
    "pânico": "a pressão",
    "panico": "a pressão",
    "parasitas": "beneficiários do Estado",
    "manipulou": "no caso",
}
ALARM_WORDS = [
    "chocante", "chocante!", "atenção!!!", "atenção!", "pior já visto",
    "espetacular", "inacreditável!!!!", "!!!",
]


def _read_roteiro_manchetes(date: str) -> list[str]:
    """Lê manchetes do roteiro JSON (fonte primária)."""
    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            manchetes = [m.strip() for m in (data.get("manchetes") or []) if m.strip()]
            if manchetes:
                return manchetes
        except Exception:
            pass
    # Fallback: arquivo de manchetes derivado do MD
    txt_path = EPISODES_DIR / f"{date}-manchetes.txt"
    if txt_path.exists():
        out = []
        for line in txt_path.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("•-–— ").strip()
            if line and "manchetes" not in line.lower() and line != "-":
                out.append(line)
        if out:
            return out
    return []


def _read_raw_headlines(date: str) -> list[str]:
    """Fallback final: extrai títulos de notícias do raw-{date}.md."""
    raw = EPISODES_DIR / f"raw-{date}.md"
    if not raw.exists():
        return []
    out = []
    for line in raw.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        m = re.match(r"^####\s*•\s*(.+)$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def clean_youtube_title(raw: str, preserve_case: bool = False) -> str:
    """Aplica as regras determinísticas de compliance + length.

    preserve_case=True preserva a formatação mista de maiúsculas/minúsculas
    (usado nos títulos dos especiais BM, que mantêm o estilo do vídeo original:
    palavras-chave em MAIÚSCULAS + resto em minúsculas).
    """
    t = raw.strip()
    # wiki de acusação -> forma investigativa
    for k, v in ACCUSATION_SAFE.items():
        t = re.sub(rf"\b{k}\b", v, t, flags=re.IGNORECASE)
    # remover mau caveat "---" ou resíduos
    t = re.sub(r"\s*[-\u2013\u2014]\s*$", "", t).strip()
    # remover [!] repetido e "!!!" (aparência de spam)
    t = re.sub(r"!{2,}", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # se algo ficar gritando em MAIÚSCULAS inteiro, normalizar para Title Case
    # (exceto quando preserve_case — título estilo YouTube com destaque em caps)
    if not preserve_case and len(t) > 3 and t == t.upper() and " " in t:
        t = t.title()
    # truncar por palavra no teto
    if len(t) > TITLE_MAX:
        cut = t[: TITLE_MAX + 1]
        sp = cut.rfind(" ")
        t = cut[: sp] if sp > TITLE_MIN else t[:TITLE_MAX].rstrip()
        t = t.rstrip(" ,;:") + "…"
    return t.strip()


_clean_title = clean_youtube_title


def _sanitize_accent(text: str) -> str:
    """Remove acentos para contagem segura de caracteres (exibição)."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def enforce_skill_title(title: str, preserve_case: bool = False) -> str:
    """Aplica as regras da skill de otimização de títulos a um título dado.

    Usado como rede de segurança pós-LLM (ex.: títulos dos especiais BM gerados
    pelo bm_condensador): limpa acusação como fato consumado, alarmismo, CAIXA
    ALTA e corta o excesso de caracteres, seguindo as mesmas regras de
    _clean_title. Retorna o título limpo (sem truncar o significado).

    preserve_case=True mantém o estilo misto de maiúsculas/minúsculas do título
    original (títulos estilo YouTube dos especiais BM).
    """
    return _clean_title(title, preserve_case=preserve_case)


def _count(text: str) -> int:
    return len(_sanitize_accent(text))


def _risk_for(title: str, source_manchetes: list[str]) -> tuple[str, str]:
    low = title.lower()
    risk = "🟢 Baixo"
    notes = []
    if any(w in low for w in ALARM_WORDS) or "!" in title:
        risk = "🟡 Médio"
        notes.append("alarme/sensação em evento sensível")
    if any(acc in low for acc in ACCUSATION_WORDS):
        risk = "🟡 Médio"
        notes.append("afirmação de culpa como fato consumado")
    if _count(title) > TITLE_MAX:
        risk = "🚨 Acima do teto"
        notes.append(f"{_count(title)} chars > {TITLE_MAX}")
    if not notes:
        notes.append("sem flag de compliance detectada")
    return risk, "; ".join(notes)


# ---------------------------------------------------------------------------
# Backends de LLM (reutiliza o padrão do generate_roteiro_llm)
# ---------------------------------------------------------------------------
def _read_env_file_keys(path: Path, prefix: str = "GEMINI_API_KEY") -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == prefix or (
                k.startswith(prefix + "_") and k[len(prefix) + 1 :].isdigit()
            ) and v and "***" not in v:
                out[k] = v
    except Exception:
        pass
    return out


def _candidate_keys(env_name: str) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for k, v in os.environ.items():
        if k == env_name or (
            k.startswith(env_name + "_") and k[len(env_name) + 1 :].isdigit()
        ):
            if v and v.strip() and "***" not in v and v.strip() not in seen:
                seen.add(v.strip())
                keys.append(v.strip())
    for path in (PROJECT_ROOT / ".env", Path.home() / ".hermes" / ".env"):
        d = _read_env_file_keys(path, env_name)
        for kk in d.values():
            if kk and "***" not in kk and kk not in seen:
                seen.add(kk)
                keys.append(kk)
    return keys


GEMINI_MODELS = [
    "gemini-3.5-flash-lite",   # primário: 500 RPD / 15 RPM, rápido e ideal para títulos curtos
    "gemini-3.1-flash-lite",   # secundário: 500 RPD
    "gemini-3.6-flash",        # fallback alta capacidade
    "gemini-3-flash-preview",  # fallback alternativo
    "gemma-4-31b-it",          # backup aberto
]
OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-m.1:free",
]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TITLE_PROMPT = """Você é o otimizador de títulos do webjornal "Vale da Liberdade" (canais de notícias locais/SC, economia, mundo).

Regras OBRIGATÓRIAS:
1. Comprimento: 40 a 60 caracteres (sem acentos ~1:1 com com acento). NUNCA passar de 70.
2. Palavra-chave/entidade no INÍCIO (nome, órgão, tema, cidade). Informação decisiva nos 40 primeiros caracteres.
3. Gerar curiosidade com gap (não entregue o desfecho) — mas NUNCA prometa fato/twist que o episódio não entrega.
4. Especificidade numérica quando houver (R$, %, anos, valores).
5. PROIBIDO: acusação como fato consumado (roubou, farsa, desviou) -> use "no caso", "sob suspeita", "o escândalo de...".
6. PROIBIDO alarmismo em evento sensível (guerra, tragédia, catástrofe): tom informativo, não sensacionalista.
7. PROIBIDO CAIXA ALTA no título inteiro, "!!!", e emojis empilhados (máx. 1 opcional).
8. Português do Brasil. Sem aspas desnecessárias. Voz ativa.

Manchetes do episódio de hoje (use estes fatos como matéria-prima, NÃO copie verbatim):
{manchetes}

Responda APENAS com um JSON válido, sem markdown:
{{"recomendado": "título recomendado", "opcoes": ["opção 1", "opção 2", "opção 3", "opção 4"], "porque": "1 frase curta de por que o recomendado funciona"}}
"""


def extract_json_object(text: str) -> dict:
    if not text:
        raise ValueError("resposta vazia do modelo")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    if start < 0:
        raise ValueError("nenhum objeto JSON encontrado")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("JSON incompleto na resposta")


def _call_gemini(prompt: str) -> str:
    keys = _candidate_keys("GEMINI_API_KEY")
    if not keys:
        raise RuntimeError("GEMINI_API_KEY ausente ou mascarada")
    from gemini_client import GeminiClient, GeminiMultiClient
    import time as _time

    last_err: Exception | None = None
    client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
    for model in GEMINI_MODELS:
        try:
            resp = client.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": 0.5,
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                },
            )
            text = getattr(resp, "text", None) or ""
            candidates = getattr(resp, "candidates", None) or []
            if not text and candidates:
                parts = []
                for c in candidates:
                    content = getattr(c, "content", None)
                    cparts = getattr(content, "parts", None) if content else None
                    if cparts:
                        for p in cparts:
                            t_ = getattr(p, "text", None)
                            if t_:
                                parts.append(t_)
                text = "\n".join(parts)
            if text and text.strip():
                return text
            last_err = RuntimeError(f"{model}: resposta vazia")
        except Exception as exc:
            last_err = exc
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "rate" in msg or "resource_exhausted" in msg:
                _time.sleep(1.5)
                continue
            if "api key" in msg or "invalid" in msg or "401" in msg or "403" in msg:
                break
        _time.sleep(1.5)
    raise RuntimeError(f"Gemini falhou: {last_err}")


def _call_openrouter(prompt: str) -> str:
    import requests

    keys = _candidate_keys("OPENROUTER_API_KEY")
    if not keys:
        raise RuntimeError("OPENROUTER_API_KEY ausente ou mascarada")
    last_err: Exception | None = None
    for api_key in keys:
        for model in OPENROUTER_MODELS:
            try:
                body = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a JSON API that writes Brazilian Portuguese "
                                "news titles. Output ONLY a single valid JSON object. "
                                "No markdown, no commentary. Start with { and end with }."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 1024,
                    "response_format": {"type": "json_object"},
                }
                resp = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                        "X-Title": "Web Jornal Pipeline (titles)",
                    },
                    json=body,
                    timeout=120,
                )
                if resp.status_code >= 400:
                    if resp.status_code in (401, 403):
                        last_err = RuntimeError(f"HTTP {resp.status_code}")
                        break
                    body.pop("response_format", None)
                    resp = requests.post(
                        OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                        timeout=120,
                    )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:
                last_err = exc
    raise RuntimeError(f"OpenRouter falhou: {last_err}")


def generate_title_via_llm(manchetes: list[str]) -> dict | None:
    bullet = "\n".join(f"- {m}" for m in manchetes)
    prompt = TITLE_PROMPT.format(manchetes=bullet)
    for name, fn in (("Gemini", _call_gemini), ("OpenRouter", _call_openrouter)):
        try:
            raw = fn(prompt)
            data = extract_json_object(raw)
            if data.get("recomendado") or data.get("opcoes"):
                return data
        except Exception as exc:
            print(f"  ⚠ {name} falhou p/ título: {exc}")
    return None


_generate_via_llm = generate_title_via_llm


def _deterministic_title(manchetes: list[str]) -> str:
    """Seleciona a manchete mais adequada e limpa segundo as regras."""
    if not manchetes:
        return "Vale da Liberdade — o webjornal do dia"
    # Preferir manchetes com número, cidade, órgão; menor risco de alarmismo.
    def score(m: str) -> int:
        s = 0
        if re.search(r"R\$|milh|bilh|mil |%|\d{4}|\d+ anos", m, re.IGNORECASE):
            s += 3
        if re.search(r"\b(em|de|no|na)\s+[A-ZÁÉÍÓÚÂÊÔ]" , m, re.IGNORECASE):
            s += 2
        for k in ("SUS", "Câmara", "Câmara", "Prefeitura", "Ideb", "BR-", "SC-"):
            if k in m:
                s += 2
        for a in ALARM_WORDS:
            if a in m.lower():
                s -= 5
        s -= abs(len(m) - TITLE_TARGET) // 10
        return s

    best = max(manchetes, key=score)
    cleaned = _clean_title(best)
    # Se ficou muito curto ou perdeu sentido, tentar via não-verbatim resumo
    if _count(cleaned) < TITLE_MIN:
        cleaned = f"O que muda em Santa Catarina: {_clean_title(best)}"[:TITLE_MAX]
    return cleaned


def _build_result(manchetes: list[str], llm: dict | None) -> tuple[str, list[dict], str]:
    opts: list[dict] = []
    rec = llm.get("recomendado") if llm else None
    candidatos = []
    if llm and llm.get("opcoes"):
        candidatos = [o for o in llm.get("opcoes", []) if isinstance(o, str) and o.strip()]
    if rec:
        candidatos.insert(0, rec)

    for c in candidatos:
        cleaned = _clean_title(c)
        if cleaned:
            risk, note = _risk_for(cleaned, manchetes)
            opts.append({"title": cleaned, "risk": risk, "note": note})

    # Recommendation: first clean && within range && low risk preferred
    def order_key(o: dict):
        risk_low = 0 if "Baixo" in o["risk"] else (1 if "Médio" in o["risk"] else 2)
        dist = abs(_count(o["title"]) - TITLE_TARGET)
        return (risk_low, dist)

    if opts:
        opts.sort(key=order_key)
    else:
        rec = _deterministic_title(manchetes)
        opts.append({"title": rec, "risk": _risk_for(rec, manchetes)[0], "note": "fallback determinístico"})

    final = opts[0]["title"]
    return final, opts, (llm.get("porque", "") if llm else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="Data YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="só mostra, não grava")
    ap.add_argument("--force", action="store_true", help="reescreve o arquivo de título")
    args = ap.parse_args()

    date = args.date
    manchetes = _read_roteiro_manchetes(date) or _read_raw_headlines(date)
    if not manchetes:
        print(f"❌ Nenhuma manchete/notícia encontrada para {date}. Abortando.")
        return 3

    out_path = EPISODES_DIR / f"{date}-title.txt"
    if out_path.exists() and not args.force and not args.dry_run:
        print(f"ℹ️  Título já existe: {out_path}")
        print(f"   → {out_path.read_text(encoding='utf-8').strip()}")
        print("   (use --force para regenerar)")
        return 0

    print(f"🎯 Otimizando título para {date}")
    print(f"   {len(manchetes)} manchete(s) de matéria-prima")

    llm = None
    if not args.dry_run:
        print("  → tentando LLM (Gemini/OpenRouter)...")
        llm = _generate_via_llm(manchetes)
        if llm:
            print("  ✓ LLM respondeu")
        else:
            print("  ⚠ LLM indisponível — usando fallback determinístico")

    final, opts, porque = _build_result(manchetes, llm)

    print("\nOpções otimizadas:")
    for i, o in enumerate(opts, 1):
        mark = " ★" if o["title"] == final else ""
        print(f"  {i}. [{o['risk']}] {o['title']} ({_count(o['title'])} chars){mark}")
        if o.get("note"):
            print(f"      - {o['note']}")
    if porque:
        print(f"\nPor que o recomendado funciona: {porque}")

    print(f"\n✅ Título final recomendado: {final}")

    if not args.dry_run:
        out_path.write_text(final + "\n", encoding="utf-8")
        print(f"   Gravado em: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
