#!/usr/bin/env python3
"""
Condensador LLM — Pipeline Brasil e Mundo.

Transforma a transcrição bruta de um vídeo do YouTube em um roteiro
de ~5 min narrado exclusivamente pelo Peter Albuquerque.

Regras do quadro (SKILL_BRASIL_E_MUNDO.md):
  - Apenas Peter (sem Ricardo, sem diálogos)
  - Sem seções fixas — comentário único e corrido
  - Meta: 750-900 palavras (~5 min)
  - RESUMIR, nunca expandir

Uso:
    python scripts/bm_condensador.py --video-id "abc123"
    python scripts/bm_condensador.py --video-id "abc123" --force
"""
from __future__ import annotations

import argparse
import json
import os
import re
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

RAW_DIR    = PROJECT_ROOT / "output" / "brasil_e_mundo" / "raw"
EPS_DIR    = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"
SKILL_PATH = PROJECT_ROOT / "pipelines" / "brasil_e_mundo" / "SKILL_BRASIL_E_MUNDO.md"
CONFIG_PATH = PROJECT_ROOT / "pipelines" / "brasil_e_mundo" / "config.json"

# ── Persona Peter (copiada de generate_script.py) ──────────────────────────
PERSONA_PETER = {
    "style": "anarcocapitalista provocador",
    "voice": "Charon",
    "guidelines": [
        "Anti-estado: rejeita soluções estatais, destaca coerção, questiona burocracia",
        "Defende mercado livre, liberdade individual, descentralização; imposto é roubo",
        "Nunca elogia eficiência do Estado; expõe custos ocultos e incentivos perversos",
        "Tom irônico, cético, provocador — como quem desafia o status quo",
        "Foca no indivíduo, na liberdade, na responsabilidade pessoal",
        "Usa metáforas libertárias: 'monopólio da violência', 'imposto é roubo'",
        "Frases curtas, diretas, às vezes sarcásticas",
        "Voz ativa sempre ('Câmara aprova', não 'É aprovado')",
        "NÃO inventa dados — usa apenas o que está na fonte",
    ],
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"target_word_count": 850, "max_word_count": 950, "tags": []}


def load_skill() -> str:
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return ""


def load_raw(video_id: str) -> dict:
    raw_path = RAW_DIR / f"{video_id}.json"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Transcrição não encontrada: {raw_path}\n"
            f"Execute: python scripts/bm_transcript.py --video-id {video_id}"
        )
    return json.loads(raw_path.read_text(encoding="utf-8"))


# ── Backends LLM ─────────────────────────────────────────────────────────────

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
            if (k == base or (k.startswith(base + "_") and k[len(base)+1:].isdigit())):
                if v and "***" not in v and v not in seen:
                    seen.add(v); keys.append(v)
    return keys


GEMINI_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]
OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
]


def _call_gemini(prompt: str) -> str:
    keys = _candidate_keys("GEMINI_API_KEY")
    if not keys:
        raise RuntimeError("GEMINI_API_KEY ausente")
    from gemini_client import GeminiClient, GeminiMultiClient
    client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
    last_err = None
    for model in GEMINI_MODELS:
        try:
            print(f"  → Gemini: {model}")
            resp = client.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": 0.65, "max_output_tokens": 8192,
                        "response_mime_type": "application/json"},
            )
            text = getattr(resp, "text", None) or ""
            if not text:
                candidates = getattr(resp, "candidates", []) or []
                parts = []
                for c in candidates:
                    content = getattr(c, "content", None)
                    cparts = getattr(content, "parts", None) if content else None
                    if cparts:
                        for p in cparts:
                            t = getattr(p, "text", None)
                            if t: parts.append(t)
                text = "\n".join(parts)
            if text.strip():
                print(f"  ✓ {model}: {len(text)} chars")
                return text
            last_err = RuntimeError(f"{model}: resposta vazia")
        except Exception as exc:
            print(f"  ⚠ Gemini {model}: {exc}")
            last_err = exc
            msg = str(exc).lower()
            if any(k in msg for k in ("429", "quota", "rate", "resource_exhausted")):
                time.sleep(2)
                continue
            if any(k in msg for k in ("api key", "401", "403")):
                break
        time.sleep(1.5)
    raise RuntimeError(f"Gemini falhou: {last_err}")


def _call_openrouter(prompt: str) -> str:
    import urllib.request, urllib.error
    keys = _candidate_keys("OPENROUTER_API_KEY")
    if not keys:
        raise RuntimeError("OPENROUTER_API_KEY ausente")
    last_err = None
    for key in keys:
        for model in OPENROUTER_MODELS:
            try:
                print(f"  → OpenRouter: {model}")
                body = json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system",
                         "content": ("Você é um roteirista de podcast. "
                                     "Retorne APENAS o objeto JSON solicitado. "
                                     "Sem markdown, sem explicações.")},
                        {"role": "user", "content": prompt + "\n\nRESPONDA APENAS COM O JSON."},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 6000,
                    "response_format": {"type": "json_object"},
                }).encode()
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://webjornal.mob.tec.br",
                        "X-Title": "Brasil e Mundo Pipeline",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read())
                text = (data.get("choices", [{}])[0].get("message") or {}).get("content", "")
                if text.strip():
                    return text
            except Exception as exc:
                print(f"  ⚠ OpenRouter {model}: {exc}")
                last_err = exc
    raise RuntimeError(f"OpenRouter falhou: {last_err}")


def _call_llm(prompt: str) -> str:
    for backend, fn in (("gemini", _call_gemini), ("openrouter", _call_openrouter)):
        try:
            return fn(prompt)
        except Exception as exc:
            print(f"⚠️  Backend {backend} indisponível: {exc}")
    raise RuntimeError("Todos os backends LLM falharam")


# ── Extração JSON ────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    if start < 0:
        raise ValueError("Nenhum JSON encontrado na resposta")
    depth = 0; in_str = False; esc = False; last_ok = None
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") if not esc else False
            if not esc and ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: last_ok = text[start:i+1]; break
    if not last_ok:
        end = text.rfind("}")
        if end > start: last_ok = text[start:end+1]
        else: raise ValueError("JSON incompleto")
    try:
        return json.loads(last_ok)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", last_ok)
        return json.loads(cleaned)


# ── Prompt ───────────────────────────────────────────────────────────────────

def build_prompt(raw: dict, config: dict, skill_text: str) -> str:
    target   = config.get("target_word_count", 850)
    tags_str = ", ".join(config.get("tags", []))
    fonte    = (
        f"Fonte original: {raw['source_names'][0]}" if raw.get("source_names")
        else "Fonte: transcrição do canal ANCAPSU"
    )
    guidelines = "\n".join(f"- {g}" for g in PERSONA_PETER["guidelines"])

    return f"""Você é o roteirista do quadro "Brasil e Mundo" do Webjornal Vale da Liberdade.
Sua tarefa: transformar a transcrição abaixo em um comentário solo de ~5 minutos, narrado APENAS pelo Peter Albuquerque.

=== PERSONA PETER — {PERSONA_PETER['style'].upper()} ===
{guidelines}

=== REGRAS DO QUADRO BRASIL E MUNDO (seguir ESTRITAMENTE) ===
1. APENAS Peter fala. SEM menção ao Ricardo. SEM diálogos. SEM turnos de fala.
2. SEM divisão em seções (segurança/saúde/educação/política/mundo). Comentário único e corrido.
3. META DE PALAVRAS: {target} palavras (máximo {int(target * 1.15)}).
   RESUMIR e CONDENSAR — o vídeo original é esticado para SEO. Você CORTA.
4. Extrair: tese central + 2-4 argumentos fortes + gancho final.
5. Descartar: repetições, digressões, enrolação, exemplos redundantes.
6. Preservar naturalidade do apresentador original, mas na VOZ do Peter.
7. {fonte}
8. NÃO invente dados. Use apenas o que está na transcrição.

=== ESTRUTURA DO ROTEIRO ===
- abertura: 2-3 falas curtas (gancho de impacto, ~30s)
- desenvolvimento: 5-8 falas (corpo da análise, ~3-4 min)
- fechamento: 1-2 falas (provocação/CTA, ~30s)

=== TAGS DISPONÍVEIS (escolha 1-3 para este episódio) ===
{tags_str}

=== TRANSCRIÇÃO DO VÍDEO ({len(raw['transcript'].split())} palavras) ===
Título: {raw['title']}
Canal: {raw['channel']}
---
{raw['transcript'][:6000]}

=== FORMATO DE SAÍDA (JSON) ===
{{
  "titulo": "Título curto e impactante para o episódio (diferente do vídeo original)",
  "fonte_url": "{raw['url']}",
  "fonte_canal": "{raw['channel']}",
  "fonte_veiculo": "{raw.get('source_names', [''])[0] if raw.get('source_names') else ''}",
  "tags": ["tag1", "tag2"],
  "abertura": [
    {{"speaker": "Peter", "texto": "Fala de abertura..."}},
    {{"speaker": "Peter", "texto": "Contexto inicial..."}}
  ],
  "desenvolvimento": [
    {{"speaker": "Peter", "texto": "Argumento 1..."}},
    {{"speaker": "Peter", "texto": "Argumento 2..."}}
  ],
  "fechamento": [
    {{"speaker": "Peter", "texto": "Provocação final / CTA..."}}
  ]
}}

IMPORTANTE: O campo "speaker" SEMPRE deve ser "Peter". Retorne APENAS o JSON, sem markdown."""


def count_words_in_roteiro(data: dict) -> int:
    total = 0
    for section in ("abertura", "desenvolvimento", "fechamento"):
        for item in data.get(section, []):
            total += len(item.get("texto", "").split())
    return total


# ── Renderer MD ──────────────────────────────────────────────────────────────

def render_roteiro_md(data: dict, video_id: str) -> str:
    lines = [
        "# BRASIL E MUNDO — Web Jornal Vale da Liberdade",
        f"## {data.get('titulo', 'Episódio Especial')}",
        "",
        f"> Fonte: {data.get('fonte_veiculo') or data.get('fonte_canal', '')}",
        f"> URL do vídeo: {data.get('fonte_url', '')}",
        f"> Tags: {', '.join(data.get('tags', []))}",
        f"> video_id: {video_id}",
        "",
        "---",
        "",
        "[QUADRO: BRASIL E MUNDO — Abertura]",
        "",
    ]
    for item in data.get("abertura", []):
        lines.append(f"Peter: {item['texto']}")
        lines.append("")

    lines += ["", "[QUADRO: BRASIL E MUNDO — Desenvolvimento]", ""]
    for item in data.get("desenvolvimento", []):
        lines.append(f"Peter: {item['texto']}")
        lines.append("")

    lines += ["", "[QUADRO: BRASIL E MUNDO — Fechamento]", ""]
    for item in data.get("fechamento", []):
        lines.append(f"Peter: {item['texto']}")
        lines.append("")

    return "\n".join(lines)


# ── Pipeline principal ───────────────────────────────────────────────────────

def condense(video_id: str, force: bool = False) -> dict:
    EPS_DIR.mkdir(parents=True, exist_ok=True)
    json_out = EPS_DIR / f"especial-{video_id}.json"
    md_out   = EPS_DIR / f"especial-{video_id}.md"

    if json_out.exists() and not force:
        data = json.loads(json_out.read_text(encoding="utf-8"))
        words = count_words_in_roteiro(data)
        print(f"ℹ️  Roteiro já existe ({words} palavras): {json_out}")
        return data

    config    = load_config()
    skill     = load_skill()
    raw       = load_raw(video_id)
    target    = config.get("target_word_count", 850)
    max_words = config.get("max_word_count", int(target * 1.15))

    print(f"🧠 Condensando transcrição de '{raw['title'][:60]}' ({raw['transcript_words']} palavras → ~{target} palavras)...")

    prompt    = build_prompt(raw, config, skill)
    max_rounds = 2
    data      = None
    last_err  = None

    for attempt in range(1, max_rounds + 2):
        try:
            response_text = _call_llm(prompt)
            data = extract_json(response_text)
            words = count_words_in_roteiro(data)
            print(f"  Tentativa {attempt}: {words} palavras geradas")

            if words > max_words:
                overage = words - target
                print(f"  ⚠️  {words} palavras (máx {max_words}). Pedindo corte de ~{overage} palavras...")
                trim_prompt = (
                    f"O roteiro abaixo tem {words} palavras mas o limite é {max_words}.\n"
                    f"Corte ~{overage} palavras removendo redundâncias, sem alterar o tom ou perder argumentos principais.\n"
                    f"Retorne APENAS o JSON completo corrigido.\n\n"
                    f"JSON atual:\n{json.dumps(data, ensure_ascii=False)}"
                )
                response_text = _call_llm(trim_prompt)
                data = extract_json(response_text)
                words = count_words_in_roteiro(data)
                print(f"  Após corte: {words} palavras")

            break
        except Exception as exc:
            print(f"  ❌ Tentativa {attempt} falhou: {exc}")
            last_err = exc
            if attempt <= max_rounds:
                time.sleep(2)
            else:
                raise RuntimeError(f"Condensador falhou após {max_rounds+1} tentativas: {last_err}")

    # Salvar JSON
    json_out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Salvar MD
    md_text = render_roteiro_md(data, video_id)
    md_out.write_text(md_text, encoding="utf-8")

    words = count_words_in_roteiro(data)
    print(f"✅ Roteiro gerado: {words} palavras (~{words//150} min)")
    print(f"   JSON: {json_out}")
    print(f"   MD:   {md_out}")

    return data


def main():
    parser = argparse.ArgumentParser(description="Condensador LLM — Brasil e Mundo")
    parser.add_argument("--video-id", help="ID do vídeo do YouTube")
    parser.add_argument("--video-id-env", action="store_true", help="Ler video_id da variável BM_VIDEO_ID")
    parser.add_argument("--force", action="store_true", help="Regenerar mesmo se já existir")
    args = parser.parse_args()

    video_id = args.video_id or os.environ.get("BM_VIDEO_ID")
    if not video_id:
        parser.error("--video-id ou BM_VIDEO_ID é obrigatório")

    data = condense(video_id, force=args.force)
    print(f"\n📻 Título: {data.get('titulo', '—')}")
    print(f"   Tags: {', '.join(data.get('tags', []))}")
    words = count_words_in_roteiro(data)
    print(f"   Palavras: {words} (~{words//150} min de áudio)")


if __name__ == "__main__":
    main()
