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


# ── Referências (links das fontes + nosso site) ─────────────────────────────

SITE_URL = os.environ.get("SITE_URL", "https://news.mob.tec.br").rstrip("/")


def _site_referencias(video_id: str) -> list[dict]:
    """Links do PRÓPRIO site: página do episódio + matéria transcrita."""
    return [
        {
            "veiculo": "Vale da Liberdade (site)",
            "url": f"{SITE_URL}/ep/especial-{video_id}.html",
            "self": True,
        },
        {
            "veiculo": "Vale da Liberdade (matéria transcrita)",
            "url": f"{SITE_URL}/episodes/especial-{video_id}.md",
            "self": True,
        },
    ]


def _build_fonte_referencias(raw: dict, video_id: str) -> list[dict]:
    """Monta a lista de referências do episódio:
    1. Raws novos: `sources` já pareado (URL↔veículo) da seção 'Referências:';
    2. Raws antigos: re-extrai a seção 'Referências:' da descrição armazenada
       (fallback: source_urls antigos filtrando autopromoção/redes);
    3. Links do nosso próprio site (página + matéria transcrita).
    """
    from bm_transcript import (
        _PROMO_DOMAINS,
        domain_of,
        extract_referencias,
        veiculo_from_url,
    )

    refs: list[dict] = []
    seen: set[str] = set()

    def _add(url: str, veiculo: str = "") -> None:
        url = url.strip()
        if not url or url in seen:
            return
        seen.add(url)
        refs.append(
            {"veiculo": (veiculo.strip()[:60] or veiculo_from_url(url)), "url": url}
        )

    paired = raw.get("sources")
    if paired:
        for s in paired:
            _add(s.get("url") or "", (s.get("veiculo") or "").strip())
    else:
        # Raws antigos: a descrição armazenada contém a seção "Referências:"
        urls = extract_referencias(raw.get("description") or "")
        if not urls:
            urls = []
            for url in raw.get("source_urls") or []:
                dom = domain_of(url)
                if dom and any(ex in dom for ex in _PROMO_DOMAINS):
                    continue
                urls.append(url)
        for url in urls:
            _add(url)

    refs += _site_referencias(video_id)
    return refs


def enrich_referencias(data: dict, raw: dict, video_id: str) -> bool:
    """Adiciona `fonte_referencias` (se ausente) e corrige `fonte_veiculo`.

    `fonte_veiculo` = primeira referência EXTERNA que não seja YouTube
    (o YouTube Live de origem é referência legítima, mas não deve ser a
    fonte principal quando há veículos de imprensa reais na lista).
    Retorna True se alterou o data."""
    if data.get("fonte_referencias"):
        return False
    from bm_transcript import domain_of

    refs = _build_fonte_referencias(raw, video_id)
    if not refs:
        return False
    data["fonte_referencias"] = refs
    externas = [r for r in refs if not r.get("self")]
    primaria = next(
        (r for r in externas if "youtube.com" not in domain_of(r.get("url", ""))),
        None,
    ) or (externas[0] if externas else None)
    if primaria:
        data["fonte_veiculo"] = primaria["veiculo"]
    return True


def write_referencias_index() -> Path:
    """Consolida as referências de TODOS os especiais em
    output/brasil_e_mundo/referencias.json — base para o pipeline futuro de
    vídeos do YouTube (fundos/imagens de background por episódio)."""
    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "episodes": {},
    }
    for p in sorted(EPS_DIR.glob("especial-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        video_id = p.name[len("especial-"): -len(".json")]
        index["episodes"][f"especial-{video_id}"] = {
            "video_id": video_id,
            "titulo": d.get("titulo"),
            "referencias": d.get("fonte_referencias") or [],
        }
    out = PROJECT_ROOT / "output" / "brasil_e_mundo" / "referencias.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


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
    "gemini-3.5-flash-lite",   # primário: alta cota (500 RPD / 15 RPM), ágil e preciso
    "gemini-3.1-flash-lite",   # secundário leve (500 RPD)
    "gemini-3.6-flash",        # fallback alta capacidade
    "gemini-3-flash-preview",  # fallback alternativo
    "gemma-4-31b-it",          # fallback aberto
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
Título original no YouTube: {raw['title']}
Canal: {raw['channel']}
---
{raw['transcript'][:6000]}

=== REGRAS DO TÍTULO E SUBTÍTULO (OBRIGATÓRIAS) ===
1. TÍTULO ("titulo"): Deve ser BASEADO no título original do YouTube acima, ADAPTADO às regras:
   - 40 a 65 caracteres; NUNCA passar de 80. Entidade/tema nas primeiras palavras.
   - Curiosidade com gap, sem prometer fato que o episódio não entrega.
   - Especificidade numérica se houver (R$, %, anos).
   - PROIBIDO acusação como fato consumado ("roubou", "farsa", "mentira", "propina", "desviou") -> use "no caso", "sob suspeita", "o escândalo de", "a polêmica de".
   - PROIBIDO alarmismo sensacionalista ("pânico", "chocante", "!!!") em tema sensível.
   - MANTENHA a formatação de maiúsculas/minúsculas do título original: palavras-chave destacadas em MAIÚSCULAS e demais em minúsculas (estilo dos títulos do YouTube deste canal).
2. SUBTÍTULO / LINHA FINA ("subtitulo"):
   - Submanchete jornalística de 1 linha (40 a 85 caracteres).
   - Resumo claro e factual do núcleo da notícia que complementa o título.
   - NUNCA coloque falas de abertura, saudações ("Fala pessoal", "Olá") nem o texto que o apresentador vai narrar. Trata-se da linha fina editorial do Lower Third.

=== FORMATO DE SAÍDA (JSON) ===
{{
  "titulo": "Título adaptado do original conforme as regras acima",
  "subtitulo": "Submanchete jornalística concisa de 1 linha complementando o título",
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
    ]
    ref_lines = []
    for r in data.get("fonte_referencias") or []:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        veic = (r.get("veiculo") or "").strip()
        ref_lines.append(f"> - {veic}: {url}" if veic else f"> - {url}")
    if ref_lines:
        lines.append("")
        lines.append("> Referências:")
        lines.extend(ref_lines)
    lines += ["", "---", "", "[QUADRO: BRASIL E MUNDO — Abertura]", ""]
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
        # Auto-cura: especiais antigos (sem fonte_referencias) ganham as
        # referências sem precisar de --force.
        if not data.get("fonte_referencias"):
            try:
                raw = load_raw(video_id)
                if enrich_referencias(data, raw, video_id):
                    json_out.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    md_out.write_text(render_roteiro_md(data, video_id), encoding="utf-8")
                    write_referencias_index()
                    print(
                        f"   📎 Referências retroativas adicionadas "
                        f"({len(data['fonte_referencias'])})"
                    )
            except Exception as exc:
                print(f"   ⚠️  Não foi possível adicionar referências: {exc}")
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

    # Rede de segurança: aplicar regras da skill de otimização ao título final
    # (limpa acusação como fato consumado, alarmismo, CAIXA ALTA, excesso de chars)
    try:
        from title_optimizer import enforce_skill_title, _count
        if data.get("titulo"):
            antes = data["titulo"]
            # preserve_case=True: manter o estilo misto de maiúsculas/minúsculas
            # do título original do YouTube (palavras-chave em caps)
            data["titulo"] = enforce_skill_title(antes, preserve_case=True)
            if data["titulo"] != antes:
                print(f"  🎯 Título ajustado pela skill: {_count(data['titulo'])} chars")
    except Exception as exc:
        print(f"  ⚠️  title_optimizer indisponível p/ limpeza (não bloqueia): {exc}")

    if data is None:
        raise RuntimeError("Condensador terminou sem roteiro (data=None)")

    # Referências: links da seção "Referências:" da descrição do YouTube
    # (pareados URL↔veículo) + links do nosso próprio site (página do episódio
    # e matéria transcrita). Salvo no JSON para o site E para uso futuro como
    # fundo/imagens de background dos vídeos do YouTube.
    if enrich_referencias(data, raw, video_id):
        refs = data["fonte_referencias"]
        externas = [r for r in refs if not r.get("self")]
        print(
            f"   📎 {len(refs)} referências registradas "
            f"({len(externas)} fontes externas)"
        )

    # Salvar JSON
    json_out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Salvar MD
    md_text = render_roteiro_md(data, video_id)
    md_out.write_text(md_text, encoding="utf-8")

    # Índice consolidado de referências (uso futuro: fundos dos vídeos YouTube)
    try:
        idx = write_referencias_index()
        print(f"   🗂️  Índice de referências atualizado: {idx.name}")
    except Exception as exc:
        print(f"   ⚠️  Índice de referências falhou (não bloqueia): {exc}")

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
