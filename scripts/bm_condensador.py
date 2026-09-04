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
        "Analogias corporativas para política e falha estatal: gestão, fluxo de caixa, falência, cliente que não pode sair — pragmático, não abstrato",
        "Tradutor de narrativas: desmonte eufemismos da imprensa e do jargão institucional e nomeie a intenção real (metalinguagem explícita, autoridade analítica intacta)",
        "Cinismo como lente complementar à indignação: caos institucional também é espetáculo previsível — não suavize a revolta nem copie informalidade de bar",
        "Frases curtas, diretas, às vezes sarcásticas",
        "Voz ativa sempre ('Câmara aprova', não 'É aprovado')",
        "NÃO inventa dados — usa apenas o que está na fonte",
        "NUNCA escreva Turguniev nem variantes: o narrador é Peter Albuquerque; troque essa palavra por Albuquerque",
    ],
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"target_word_count": 830, "min_word_count": 750, "max_word_count": 920, "tags": []}


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

# Quanto da transcrição enviamos ao modelo. 40.000 chars ≈ 6.000-7.000 palavras.
TRANSCRIPT_CHARS = int(os.environ.get("BM_TRANSCRIPT_CHARS", "40000"))
# Nas rodadas de expansão enviamos material de apoio substancial (30.000 chars).
TRANSCRIPT_CHARS_EXPAND = int(os.environ.get("BM_TRANSCRIPT_CHARS_EXPAND", "30000"))


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
    from bm_enrich_sources import domain_of, enrich_episode_sources

    refs, _ = enrich_episode_sources(raw, video_id)
    if not refs:
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
    "gemini-3.8-flash",        # primário: máxima capacidade analítica, nuances, humor, sem truncamento
    "gemini-3.6-flash",        # fallback alta capacidade
    "gemini-3.5-flash-lite",   # fallback rápido
    "gemini-3.1-flash-lite",   # fallback leve
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

def build_prompt(raw: dict, config: dict, skill_text: str, sources_briefing: str = "") -> str:
    target    = config.get("target_word_count", 830)
    min_words = config.get("min_word_count", 750)
    max_words = config.get("max_word_count", 920)
    tags_str  = ", ".join(config.get("tags", []))
    fonte     = (
        f"Fonte original: {raw['source_names'][0]}" if raw.get("source_names")
        else "Fonte: transcrição do canal ANCAPSU"
    )
    guidelines = "\n".join(f"- {g}" for g in PERSONA_PETER["guidelines"])
    briefing_block = (
        f"\n=== BRIEFING DE FONTES EXTRAS PARA APROFUNDAR ===\n{sources_briefing}\n"
        if sources_briefing else ""
    )
    transcript_text = (raw.get("transcript") or "").strip()
    # Quanto da transcrição vai ao modelo. 40.000 chars ≈ 6.000-7.000 palavras.
    transcript_sample = transcript_text[:TRANSCRIPT_CHARS]

    return f"""Você é o roteirista do quadro "Brasil e Mundo" do Webjornal Vale da Liberdade.
Sua tarefa: transformar a transcrição abaixo em um comentário solo de ~4:30 a 5:00 minutos, narrado APENAS pelo Peter Albuquerque.

=== PERSONA PETER — {PERSONA_PETER['style'].upper()} ===
{guidelines}

=== REGRAS DO QUADRO BRASIL E MUNDO (seguir ESTRITAMENTE) ===
1. APENAS Peter fala. SEM menção ao Ricardo. SEM diálogos. SEM turnos de fala.
2. SEM divisão em seções (segurança/saúde/educação/política/mundo). Comentário único e corrido.
3. META E VOLUME DE PALAVRAS (OBRIGATÓRIO PARA VÍDEO DE ~5 MINUTOS):
   - META GERAL: {target} palavras (PISO MÍNIMO ABSOLUTO: {min_words} palavras; MÁXIMO: {max_words} palavras).
   - O roteiro precisa gerar cerca de 4:30 a 5:00 minutos de áudio contínuo. Textos curtos (< {min_words} palavras) QUEBRAM O PIPELINE e são rejeitados.
   - CONDENSAR COM PROFUNDIDADE: Extraia a tese central e 3 a 5 argumentos sólidos com dados, números e fatos da transcrição e do briefing. Desenvolva cada argumento com raciocínio analítico completo.
   - NUNCA crie respostas telegráficas ou tópicos curtos. Peter desenvolve parágrafos completos, articulados, densos e fluídos.
4. DISTRIBUIÇÃO OBRIGATÓRIA DE PALAVRAS POR SEÇÃO (GARANTIA DO PISO DE {min_words} PALAVRAS):
   - "abertura": 2 a 3 falas de contextualização e gancho provocador (~120 a 150 palavras no total).
   - "desenvolvimento": 6 a 9 falas densas e detalhadas. CADA FALA DEVE SER UM PARÁGRAFO COMPLETO de 85 a 125 palavras (~600 a 680 palavras no total da seção), dissecando fatos, mecanismos estatais, interesses em jogo e impactos na liberdade e no bolso do cidadão.
   - "fechamento": 2 falas de síntese ácida e conclusão contundente (~100 a 130 palavras no total).
   - A soma das seções DEVE ficar entre {min_words} e {max_words} palavras.
5. PRESERVAÇÃO DA TESE, RETÓRICA, HUMOR E IRONIA DA FONTE:
   - Mantenha a essência da tese e a linha de raciocínio da matéria original.
   - PRESERVE as perguntas retóricas provocadoras da fonte original (ex.: "Eles acham que o povo não percebe o truque?", "Qual a lógica disso? Nenhuma.") para manter o ouvinte instigado.
   - PRESERVE a ironia mordaz, o sarcasmo e as tiradas de humor ácido típicos do Peter Albuquerque diante da hipocrisia e incompetência estatal. NÃO pasteurize o texto como notícia institucional fria.
6. REGRA CRÍTICA DOS 3 MINUTOS PARA PALAVRÕES / COLOQUIALISMOS FORTES ("merda", etc.):
   - PRIMEIROS 3 MINUTOS DE VÍDEO (toda a "abertura" e as primeiras 4-5 falas de "desenvolvimento" / primeiras ~480 palavras): LINGUAGEM 100% LIMPA. Terminantemente proibido o uso de termos chulos ou palavrões (como "merda"), por exigência estrita das políticas de monetização e algoritmo do YouTube para o início de vídeos.
   - APÓS OS 3 MINUTOS (final do "desenvolvimento" e "fechamento" / acima de 480 palavras): SE E SOMENTE SE o locutor original da transcrição tiver utilizado termos fortes como "merda", "palhaçada" ou desabafos indignados equivalentes, Peter PODE e DEVE refletir essa mesma espontaneidade e indignação de forma orgânica. Se o locutor original não usou tais palavras, NÃO invente nem force termos vulgares.
7. Descartar: enrolação vazia, saudações repetidas e redundâncias da fala falada, mas PRESERVAR toda a riqueza argumentativa, retórica e factual.
8. {fonte}
9. SINCRONIZAÇÃO VISUAL: Ao citar ou comentar a matéria de um veículo, inclua no objeto da fala o campo opcional "fonte_url" com a URL correspondente.
10. NOME DO NARRADOR (INEGOCIÁVEL): o apresentador é Peter Albuquerque. Se a transcrição disser Turguniev / Peter Turguniev / qualquer grafia parecida, SUBSTITUA por Albuquerque. NUNCA transcreva, cite ou deixe essa palavra no JSON, no título, no subtítulo ou nas falas. O áudio também nunca pode pronunciá-la.
{briefing_block}
=== TAGS DISPONÍVEIS (escolha 1-3 para este episódio) ===
{tags_str}

=== TRANSCRIÇÃO DO VÍDEO ({len(transcript_text.split())} palavras) ===
Título original no YouTube: {raw['title']}
Canal: {raw['channel']}
---
{transcript_sample}

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
    {{"speaker": "Peter", "texto": "Fala de abertura...", "fonte_url": "https://..."}},
    {{"speaker": "Peter", "texto": "Contexto inicial..."}}
  ],
  "desenvolvimento": [
    {{"speaker": "Peter", "texto": "Argumento 1...", "fonte_url": "https://..."}},
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


_EARLY_PROFANITY_MAP = {
    "merda": "porcaria",
    "merdas": "porcarias",
    "bosta": "besteira",
    "bostas": "besteiras",
    "caralho": "droga",
    "porra": "droga",
    "putaria": "bagunça",
    "foda": "complicado",
    "foder": "arruinar",
}


def enforce_profanity_3min_rule(data: dict, safe_words_threshold: int = 480) -> dict:
    """Garante que termos chulos/palavrões não apareçam nos primeiros 3 minutos (~480 palavras).

    Até o limiar de ~480 palavras (abertura + primeiros blocos de desenvolvimento),
    termos de baixo calão são convertidos em indignação jornalística suave para preservar
    a monetização e alcance no YouTube.
    Após os 3 minutos (> 480 palavras), termos fortes trazidos da fonte são mantidos.
    """
    cumulative = 0
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in _EARLY_PROFANITY_MAP) + r")\b",
        re.IGNORECASE,
    )

    def _replace_word(m: re.Match) -> str:
        orig = m.group(1)
        sub = _EARLY_PROFANITY_MAP.get(orig.lower(), "absurdo")
        if orig.isupper():
            return sub.upper()
        elif orig.istitle():
            return sub.title()
        return sub

    for section in ("abertura", "desenvolvimento", "fechamento"):
        for item in data.get(section, []):
            texto = item.get("texto", "")
            words_count = len(texto.split())
            if cumulative < safe_words_threshold:
                novo_texto = pattern.sub(_replace_word, texto)
                if novo_texto != texto:
                    print(f"  🛡️ Termo forte sanitizado nos primeiros 3 min ({cumulative} palavras): monetização protegida.")
                    item["texto"] = novo_texto
            cumulative += words_count

    return data


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

def _trim_to_max(data: dict, words: int, target: int, max_words: int) -> tuple[dict, int]:
    """Corta um roteiro acima do teto, mantendo o resultado se o corte falhar."""
    overage = words - target
    print(f"  ⚠️  {words} palavras (máx {max_words}). Pedindo corte de ~{overage} palavras...")
    trim_prompt = (
        f"O roteiro abaixo tem {words} palavras mas o limite é {max_words}.\n"
        f"Corte ~{overage} palavras removendo redundâncias, sem alterar o tom ou perder argumentos principais.\n"
        f"Retorne APENAS o JSON completo corrigido.\n\n"
        f"JSON atual:\n{json.dumps(data, ensure_ascii=False)}"
    )
    try:
        trimmed = extract_json(_call_llm(trim_prompt))
        trimmed_words = count_words_in_roteiro(trimmed)
        print(f"  Após corte: {trimmed_words} palavras")
        # Só aceita se de fato encurtou sem cair abaixo do alvo.
        if trimmed_words < words:
            return trimmed, trimmed_words
    except Exception as exc:
        print(f"  ⚠️  Corte falhou ({exc}); mantém resultado anterior")
    return data, words


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
    target    = config.get("target_word_count", 830)
    min_words = config.get("min_word_count", 750)
    max_words = config.get("max_word_count", 920)

    from bm_enrich_sources import enrich_episode_sources
    enriched_refs, sources_briefing = enrich_episode_sources(raw, video_id)

    print(f"🧠 Condensando transcrição de '{raw['title'][:60]}' ({raw['transcript_words']} palavras → meta ~{target} palavras [{min_words}-{max_words}])...")

    base_prompt = build_prompt(raw, config, skill, sources_briefing=sources_briefing)
    max_rounds = 2
    data       = None
    last_err   = None
    words      = 0

    for attempt in range(1, max_rounds + 1):
        try:
            # Na 2ª tentativa, se a 1ª ficou curta, reforçar o aviso de piso no prompt
            current_prompt = base_prompt
            if attempt > 1 and words > 0 and words < min_words:
                current_prompt += (
                    f"\n\nATENÇÃO MÁXIMA (TENTATIVA {attempt}): O rascunho anterior gerou apenas {words} palavras. "
                    f"O piso inegociável é de {min_words} palavras (meta {target}). "
                    f"Desenvolva cada parágrafo do 'desenvolvimento' com 90 a 130 palavras, com riqueza de fatos, argumentos e ironia."
                )

            response_text = _call_llm(current_prompt)
            data = extract_json(response_text)
            words = count_words_in_roteiro(data)
            print(f"  Tentativa {attempt}: {words} palavras geradas")

            if words > max_words:
                data, words = _trim_to_max(data, words, target, max_words)

            # Sub-loop de expansão: tenta até 2 rodadas dedicadas se estiver abaixo do piso
            if words < min_words:
                underage = target - words
                print(f"  ⚠️  {words} palavras geradas (abaixo do piso de {min_words}). Executando expansão com transcrição integral (+~{underage} palavras)...")
                transcript_ref = (raw.get("transcript") or "")[:TRANSCRIPT_CHARS_EXPAND]
                expand_prompt = (
                    f"ATENÇÃO CRÍTICA: O roteiro gerado abaixo tem apenas {words} palavras, mas a meta OBRIGATÓRIA é de {target} palavras (piso mínimo inegociável de {min_words} palavras para dar ~5 min de áudio).\n\n"
                    f"Sua tarefa: EXPANDIR e APROFUNDAR o roteiro atual adicionando ~{underage} palavras de análise factual e argumentativa.\n"
                    f"- Mantenha o formato JSON exato ('abertura', 'desenvolvimento', 'fechamento').\n"
                    f"- No 'desenvolvimento': expanda cada fala transformando-a em um parágrafo denso e completo de 90 a 130 palavras, explicando em detalhes os dados, mecanismos e consequências citados na transcrição de apoio abaixo.\n"
                    f"- Se necessário, adicione 1 a 2 falas adicionais de desenvolvimento.\n"
                    f"- Mantenha o tom irônico e provocador do Peter. Lembre-se: sem termos chulos nos primeiros 3 minutos (~480 palavras); após isso, apenas se o autor original tiver falado.\n"
                    f"- Retorne APENAS o JSON completo atualizado.\n\n"
                    f"JSON ATUAL ({words} palavras):\n{json.dumps(data, ensure_ascii=False)}\n\n"
                    f"TRANSCRIÇÃO DE APOIO:\n{transcript_ref}"
                )
                if sources_briefing:
                    expand_prompt += f"\n\nBRIEFING DE MATÉRIAS EXTRAS:\n{sources_briefing}"

                try:
                    response_text = _call_llm(expand_prompt)
                    expanded_data = extract_json(response_text)
                    expanded_words = count_words_in_roteiro(expanded_data)
                    print(f"  Após expansão com transcrição: {expanded_words} palavras")
                    if expanded_words >= words:
                        data = expanded_data
                        words = expanded_words
                except Exception as exc:
                    print(f"  ⚠️  Expansão falhou ({exc}); mantém resultado anterior")

                # Segunda rodada de expansão focada caso ainda falte pouco
                if words < min_words:
                    print(f"  ⚠️  Tentando segunda rodada de expansão focada no desenvolvimento...")
                    rescue_prompt = (
                        f"O roteiro ainda tem {words} palavras e PRECISA chegar a pelo menos {min_words} palavras (alvo {target}).\n"
                        f"Amplie imediatamente as falas da seção 'desenvolvimento' adicionando mais detalhes factuais, contextualização e reflexão provocadora do Peter.\n"
                        f"Retorne APENAS o JSON completo atualizado.\n\n"
                        f"JSON ATUAL:\n{json.dumps(data, ensure_ascii=False)}"
                    )
                    try:
                        response_text = _call_llm(rescue_prompt)
                        rescued_data = extract_json(response_text)
                        rescued_words = count_words_in_roteiro(rescued_data)
                        print(f"  Após segunda rodada: {rescued_words} palavras")
                        if rescued_words >= words:
                            data = rescued_data
                            words = rescued_words
                    except Exception as exc:
                        print(f"  ⚠️  Segunda rodada falhou ({exc}); mantém resultado anterior")

                if words > max_words:
                    data, words = _trim_to_max(data, words, target, max_words)

            # Se atingiu o piso (ou superou), temos sucesso nesta tentativa!
            if words >= min_words:
                data.pop("_skip_video_reason", None)
                break
            else:
                print(f"  ⚠️  Tentativa {attempt} terminou com {words} palavras (< piso {min_words}).")
                if attempt < max_rounds:
                    print(f"  🔁 Reiniciando tentativa com prompt ampliado...")
                    time.sleep(2)
                else:
                    print(f"  ⚠️  GATE duração: esgotadas {max_rounds} tentativas. {words} palavras < {min_words} — áudio será gerado, mas vídeo será pulado")
                    data["_skip_video_reason"] = f"duração insuficiente: {words} palavras < {min_words}"

        except Exception as exc:
            print(f"  ❌ Tentativa {attempt} falhou: {exc}")
            last_err = exc
            if attempt < max_rounds:
                time.sleep(2)
            else:
                if data is None:
                    raise RuntimeError(f"Condensador falhou após {max_rounds} tentativas: {last_err}")

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

    from tts_preprocessor import scrub_turguniev_tree
    data = scrub_turguniev_tree(data)
    if not isinstance(data, dict):
        raise RuntimeError("scrub_turguniev_tree devolveu tipo inesperado")

    # Guardrail de monetização YouTube: sanitizar palavrões no trecho < 3 min (< 480 palavras)
    data = enforce_profanity_3min_rule(data)

    # Atribuir referências enriquecidas ao JSON
    data["fonte_referencias"] = enriched_refs
    externas = [r for r in enriched_refs if not r.get("self")]
    from bm_enrich_sources import domain_of
    primaria = next(
        (r for r in externas if "youtube.com" not in domain_of(r.get("url", ""))),
        None,
    ) or (externas[0] if externas else None)
    if primaria:
        data["fonte_veiculo"] = primaria["veiculo"]
    print(
        f"   📎 {len(enriched_refs)} referências registradas "
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
    est_min = words / 175.0
    print(f"✅ Roteiro gerado: {words} palavras (~{est_min:.1f} min)")
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
    est_min = words / 175.0
    print(f"   Palavras: {words} (~{est_min:.1f} min de áudio)")


if __name__ == "__main__":
    main()
