#!/usr/bin/env python3
"""
Gera a DESCRIÇÃO OTIMIZADA do episódio do Vale da Liberdade para o YouTube,
seguindo a skill "descricoes-vale-liberdade":

  - Primeiras 2-3 linhas: gancho decisivo + tema central antes do "mostrar mais"
  - Contexto e destaques das principais notícias (sem keyword stuffing)
  - Análise sob a ótica libertária (incentivos, impacto no bolso, coerção estatal)
  - Pergunta provocativa final para engajamento nos comentários
  - Link canônico do app PWA: https://news.mob.tec.br
  - Compliance: PROIBIDO qualquer link/URL do canal ANCAPSU (@ancap_su, ancap.su)
  - Limite: 350 a 700 caracteres no corpo (máx ~1.000 com links e rodapé)
  - 0 a 3 hashtags relevantes

Suporta:
  - Episódio Diário (--date YYYY-MM-DD): lê título + roteiro JSON (ou raw)
  - Especial Brasil & Mundo (--video-id ID): lê especial-{id}.json

Prioridade de backend:
  1) Gemini (GEMINI_API_KEY) via GeminiClient/GeminiMultiClient
  2) OpenRouter (OPENROUTER_API_KEY) com modelos free
Fallback: geração determinística contextual de alta qualidade.

Saída:
  - Grava em episodes/{date}-description.txt (episódio diário)
  - Atualiza especial-{id}.json ou stdout (BM)

Uso:
  python3 scripts/description_optimizer.py --date 2026-08-07
  python3 scripts/description_optimizer.py --date 2026-08-07 --dry-run
  python3 scripts/description_optimizer.py --date 2026-08-07 --force
  python3 scripts/description_optimizer.py --video-id ID
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

EPISODES_DIR = PROJECT_ROOT / "episodes"
BM_EPISODES_DIR = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes"

APP_CANONICAL_URL = "https://news.mob.tec.br"

# Regex de URLs proibidas (Regra ANCAPSU inegociável)
ANCAPSU_URL_PATTERNS = [
    r"https?://(?:www\.)?youtube\.com/@ancap_su[^\s]*",
    r"https?://(?:www\.)?youtube\.com/c/ANCAPSU[^\s]*",
    r"https?://(?:www\.)?youtube\.com/channel/UC[a-zA-Z0-9_-]+ancap[^\s]*",
    r"https?://(?:www\.)?ancap\.su[^\s]*",
    r"https?://ancap_su[^\s]*",
]

GEMINI_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemma-4-31b-it",
]

OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-m.1:free",
]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ---------------------------------------------------------------------------
# Leitura de Chaves de API
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
            if (k == prefix or (k.startswith(prefix + "_") and k[len(prefix) + 1:].isdigit())) and v and "***" not in v:
                out[k] = v
    except Exception:
        pass
    return out


def _candidate_keys(env_name: str) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for k, v in os.environ.items():
        if k == env_name or (k.startswith(env_name + "_") and k[len(env_name) + 1:].isdigit()):
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


# ---------------------------------------------------------------------------
# Filtros de Compliance e Limpeza Determinística
# ---------------------------------------------------------------------------
def strip_forbidden_urls(text: str) -> str:
    """Remove qualquer menção a URLs do canal ANCAPSU."""
    res = text
    for pattern in ANCAPSU_URL_PATTERNS:
        res = re.sub(pattern, "", res, flags=re.IGNORECASE)
    # Linhas que sobraram vazias ou apenas marcadores
    lines = [line for line in res.splitlines() if line.strip()]
    return "\n".join(lines)


def clean_youtube_description(
    raw_desc: str,
    sources: list[str] | None = None,
    hashtags: list[str] | None = None,
    is_bm: bool = False,
) -> str:
    """Higieniza o texto gerado e monta o formato institucional padronizado."""
    body = _html.unescape(raw_desc).strip()

    # Remove títulos markdown repetidos gerados por LLM
    body = re.sub(r"^###\s*DESCRIÇÃO\s*", "", body, flags=re.IGNORECASE).strip()
    body = re.sub(r"###\s*HASHTAGS[\s\S]*$", "", body, flags=re.IGNORECASE).strip()

    # Remove URLs proibidas do ANCAPSU
    body = strip_forbidden_urls(body)

    # Remove saudações proibidas no início
    cliche_pattern = r"^(?:olá pessoal|sejam bem-vindos(?: ao canal)?|no vídeo de hoje(?: vamos falar)?|fala galera|bom dia|boa tarde|boa noite)[,!.\s-]*"
    while re.match(cliche_pattern, body, flags=re.IGNORECASE):
        body = re.sub(cliche_pattern, "", body, count=1, flags=re.IGNORECASE).strip()

    # Normaliza espaçamento entre parágrafos
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    cleaned_body = "\n\n".join(paragraphs)

    # Rodapé institucional com link canônico
    app_line = f"📱 Ouça a edição completa no app: {APP_CANONICAL_URL}"

    # Fontes legítimas
    valid_sources = []
    if sources:
        for s in sources:
            s_clean = strip_forbidden_urls(s).strip()
            if s_clean and s_clean.startswith("http"):
                valid_sources.append(f"- {s_clean}")
            elif s_clean and not s_clean.startswith("http") and "ancap" not in s_clean.lower():
                valid_sources.append(f"- {s_clean}")

    # Hashtags (máximo 3)
    clean_tags: list[str] = []
    default_tags = ["#BrasilEMundo", "#Economia", "#Liberdade"] if is_bm else ["#Webjornal", "#ValedaLiberdade", "#Noticias"]
    tag_pool = hashtags or default_tags
    for tag in tag_pool:
        t = tag.strip()
        if not t.startswith("#"):
            t = f"#{t.replace(' ', '')}"
        if t and t.lower() not in [x.lower() for x in clean_tags]:
            clean_tags.append(t)
        if len(clean_tags) >= 3:
            break

    blocks = [cleaned_body, app_line]
    if valid_sources:
        blocks.append("Fontes:\n" + "\n".join(valid_sources[:4]))
    if clean_tags:
        blocks.append(" ".join(clean_tags))

    return "\n\n".join(blocks).strip()


# ---------------------------------------------------------------------------
# Extração de Dados dos Episódios
# ---------------------------------------------------------------------------
def load_daily_episode_context(date: str) -> dict[str, Any]:
    """Recupera título, manchetes e resumo dos quadros do episódio diário."""
    # 1. Título
    title = ""
    title_file = EPISODES_DIR / f"{date}-title.txt"
    if title_file.exists():
        title = title_file.read_text(encoding="utf-8").strip()

    # 2. Manchetes e Roteiro JSON
    manchetes: list[str] = []
    quadros_resumo: list[dict[str, str]] = []
    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            manchetes = [m.strip() for m in data.get("manchetes", []) if m.strip()]
            for q in data.get("quadros", []):
                q_nome = q.get("nome") or q.get("quadro") or ""
                # pegar fala inicial da notícia
                falas = q.get("falas", [])
                resumo_q = ""
                for f in falas[:2]:
                    txt = f.get("texto", "").strip()
                    if txt:
                        resumo_q += txt + " "
                if q_nome:
                    quadros_resumo.append({"quadro": q_nome, "destaque": resumo_q.strip()[:200]})
        except Exception:
            pass

    # 3. Fallback para manchetes.txt, {date}.md ou raw-{date}.md
    if not manchetes:
        m_txt = EPISODES_DIR / f"{date}-manchetes.txt"
        if m_txt.exists():
            for line in m_txt.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("•-–— ").strip()
                if line and "manchetes" not in line.lower() and line != "-":
                    manchetes.append(line)

    if not manchetes:
        md_file = EPISODES_DIR / f"{date}.md"
        if md_file.exists():
            try:
                from tts_preprocessor import extract_manchetes
                m_extracted = extract_manchetes(md_file.read_text(encoding="utf-8"))
                for line in m_extracted.splitlines():
                    line = line.strip().lstrip("•-–— ").strip()
                    if line and "manchetes" not in line.lower():
                        manchetes.append(line)
            except Exception:
                pass

    if not manchetes:
        raw_file = EPISODES_DIR / f"raw-{date}.md"
        if raw_file.exists():
            for line in raw_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"^####\s*•\s*(.+)$", line.strip())
                if m:
                    manchetes.append(m.group(1).strip())

    if not title:
        title = f"Webjornal Vale da Liberdade — {date}"

    return {
        "date": date,
        "title": title,
        "manchetes": manchetes,
        "quadros": quadros_resumo,
        "is_bm": False,
    }


def load_bm_episode_context(video_id: str) -> dict[str, Any]:
    """Recupera título, transcrição/resumo e referências do especial BM."""
    json_path = BM_EPISODES_DIR / f"especial-{video_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Especial BM não encontrado: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    title = data.get("titulo") or f"Brasil & Mundo — Comentário ({video_id})"

    # Resumo das seções
    trechos: list[str] = []
    for sec in ("abertura", "desenvolvimento", "fechamento"):
        for item in data.get(sec, []):
            txt = (item.get("texto") or "").strip()
            if txt:
                trechos.append(txt)

    resumo = " ".join(trechos)[:1200]
    refs = []
    for r in data.get("fonte_referencias", []):
        u = r.get("url")
        if u and not any(re.search(pat, u, re.I) for pat in ANCAPSU_URL_PATTERNS):
            refs.append(u)

    tags = data.get("tags") or ["BrasilEMundo", "Economia", "Liberdade"]

    return {
        "video_id": video_id,
        "title": title,
        "resumo": resumo,
        "refs": refs,
        "tags": tags,
        "is_bm": True,
    }


def extract_json_object(text: str) -> dict:
    if not text:
        raise ValueError("resposta vazia do modelo")
    text = text.strip()
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
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


# ---------------------------------------------------------------------------
# Prompts Canônicos para o Hermes Agent / LLMs
# ---------------------------------------------------------------------------
def build_description_prompt(context: dict[str, Any]) -> str:
    """
    Constrói o prompt canônico seguindo a skill descricoes-vale-liberdade.
    Exposto para uso do Hermes Agent e dos backends LLM.
    """
    is_bm = context.get("is_bm", False)
    title = context.get("title", "")

    if is_bm:
        resumo = context.get("resumo", "")
        return f"""Você é o redator do canal YouTube "Vale da Liberdade" (viés libertário/anarcocapitalista).
Sua tarefa é escrever a DESCRIÇÃO para o vídeo especial de análise do Peter Albuquerque.

=== DADOS DO VÍDEO ===
TÍTULO: {title}
RESUMO DO COMENTÁRIO:
{resumo}

=== REGRAS DE REDAÇÃO (OBRIGATÓRIO) ===
1. GANCHO INICIAL (2-3 linhas): comece direto no conflito central e impacto do tema. Sem saudações clichês ("Olá pessoal", "Sejam bem-vindos").
2. CONTEXTO: apresente o que aconteceu e quem está envolvido de forma clara e imparcial.
3. ANÁLISE LIBERTÁRIA: Peter analisa os incentivos, custos ocultos para o cidadão e a ineficiência ou coerção estatal envolvida. Tom direto, crítico e inteligente (sarcasmo nível 2-3 de 5).
4. ENCERRAMENTO: termine com uma pergunta instigante convidando a responder nos comentários.
5. TAMANHO: 350 a 600 caracteres de texto principal.
6. REGRA RÍGIDA: NUNCA mencione nem inclua links do canal ANCAPSU.
7. Português do Brasil, voz ativa, sem prolixidade.

Responda APENAS com um JSON válido, sem markdown:
{{"descricao": "texto da descrição em 3 ou 4 parágrafos curtos", "hashtags": ["#BrasilEMundo", "#Economia", "#Liberdade"]}}"""

    # Contexto do Diário
    manchetes = "\n".join(f"- {m}" for m in context.get("manchetes", [])[:6])
    quadros_txt = ""
    for q in context.get("quadros", []):
        quadros_txt += f"* {q['quadro']}: {q['destaque']}\n"

    return f"""Você é o redator do podcast e canal YouTube "Webjornal Vale da Liberdade" (viés libertário/anarcocapitalista).
Sua tarefa é escrever a DESCRIÇÃO do episódio diário apresentado por Peter Albuquerque e Ricardo Souto.

=== DADOS DO EPISÓDIO ===
TÍTULO: {title}
MANCHETES DO DIA:
{manchetes}

DESTAQUES DOS QUADROS:
{quadros_txt}

=== REGRAS DE REDAÇÃO (OBRIGATÓRIO) ===
1. GANCHO INICIAL (2-3 linhas): comece direto no fato mais impactante ou na contradição estatal do dia. Sem saudações ("Olá pessoal", "Bom dia", "Fala galera").
2. CONTEXTO DO EPISÓDIO: sintetize as principais pautas discutidas por Peter e Ricardo (notícias locais de SC, contas públicas, liberdade e economia) sem copiar a lista de manchetes verbatim.
3. ANÁLISE LIBERTÁRIA: destaque o impacto no bolso do cidadão, a ineficiência burocrática e a visão crítica do canal.
4. ENCERRAMENTO: faça uma pergunta provocativa e sincera sobre uma das decisões públicas do dia para movimentar os comentários.
5. TAMANHO: 400 a 700 caracteres de texto principal.
6. REGRA RÍGIDA: NUNCA mencione nem inclua links do canal ANCAPSU. O apresentador é Peter Albuquerque.
7. Português do Brasil, direto e instigante.

Responda APENAS com um JSON válido, sem markdown:
{{"descricao": "texto da descrição em 3 ou 4 parágrafos curtos", "hashtags": ["#Webjornal", "#ValedaLiberdade", "#Noticias"]}}"""


# ---------------------------------------------------------------------------
# Chamadas LLM (Gemini e OpenRouter)
# ---------------------------------------------------------------------------
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
                    "temperature": 0.6,
                    "max_output_tokens": 1024,
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
                return text.strip()
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
                                "Você é o redator do canal de notícias YouTube Vale da Liberdade. "
                                "Escreva em português do Brasil com viés libertário, direto e analítico. "
                                "Retorne apenas um objeto JSON com as chaves 'descricao' e 'hashtags'."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.6,
                    "max_tokens": 1024,
                    "response_format": {"type": "json_object"},
                }
                resp = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://news.mob.tec.br",
                        "X-Title": "Web Jornal Pipeline (descriptions)",
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
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as exc:
                last_err = exc
    raise RuntimeError(f"OpenRouter falhou: {last_err}")


def generate_description_via_llm(context: dict[str, Any]) -> tuple[str, list[str]] | None:
    prompt = build_description_prompt(context)
    for name, fn in (("Gemini", _call_gemini), ("OpenRouter", _call_openrouter)):
        try:
            raw = fn(prompt)
            if raw:
                try:
                    data = extract_json_object(raw)
                    desc = str(data.get("descricao") or data.get("description") or "").strip()
                    tags = data.get("hashtags") or data.get("tags") or []
                    if desc and len(desc) > 80:
                        return desc, tags
                except Exception:
                    # fallback se não veio JSON válido mas veio texto
                    clean_txt = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
                    if len(clean_txt) > 80 and not clean_txt.startswith("{"):
                        return clean_txt, []
        except Exception as exc:
            print(f"  ⚠ {name} falhou p/ descrição: {exc}")
    return None


# ---------------------------------------------------------------------------
# Fallback Determinístico de Alta Qualidade
# ---------------------------------------------------------------------------
def deterministic_description(context: dict[str, Any]) -> str:
    """Gera uma descrição contextual rica e bem pontuada sem requisições de rede."""
    is_bm = context.get("is_bm", False)
    title = context.get("title", "")

    if is_bm:
        resumo = context.get("resumo", "")
        p1 = f"Em mais uma análise contundente, Peter Albuquerque disseca os bastidores e os impactos reais de: {title}."
        p2 = "Discutimos como as decisões estatais, arranjos de poder e o avanço regulatório atingem a liberdade individual e a economia de mercado. Porque quando o governo intervém, a conta sempre termina nas costas do cidadão comum."
        p3 = "Qual é a sua visão sobre esse desdobramento? Acredita que haverá alguma reversão prática? Participe nos comentários."
        return f"{p1}\n\n{p2}\n\n{p3}"

    manchetes = context.get("manchetes", [])
    m_top = manchetes[:3] if manchetes else ["os principais acontecimentos de Santa Catarina e do Brasil"]
    m_text = "; ".join(m_top)

    p1 = f"Mais uma edição do Webjornal Vale da Liberdade com as notícias que movimentam Santa Catarina e o país, analisadas sem os filtros da imprensa tradicional."
    p2 = f"Hoje, Peter Albuquerque e Ricardo Souto debatem os principais temas do dia: {m_text}. Avaliamos os mecanismos fiscais, os atrasos de infraestrutura e como cada nova medida estatal interfere diretamente na sua vida prática."
    p3 = "Diante de tudo isso: o pagador de impostos ainda tem fôlego para bancar essa estrutura? Deixe sua opinião sincera nos comentários."
    return f"{p1}\n\n{p2}\n\n{p3}"


# ---------------------------------------------------------------------------
# Geradores Principais
# ---------------------------------------------------------------------------
def generate_daily_description(date: str, force: bool = False, dry_run: bool = False) -> tuple[str, Path]:
    """Gera e grava episodes/{date}-description.txt."""
    out_path = EPISODES_DIR / f"{date}-description.txt"
    if out_path.exists() and not force and not dry_run:
        print(f"ℹ️  Descrição já existe: {out_path}")
        return out_path.read_text(encoding="utf-8").strip(), out_path

    context = load_daily_episode_context(date)
    print(f"🎯 Otimizando descrição para {date}")
    print(f"   Título de referência: {context['title']}")

    raw_body = None
    llm_tags: list[str] = []
    if not dry_run:
        print("  → tentando LLM (Gemini/OpenRouter)...")
        llm_res = generate_description_via_llm(context)
        if llm_res:
            raw_body, llm_tags = llm_res
            print("  ✓ LLM respondeu com sucesso")
        else:
            print("  ⚠ LLM indisponível — usando fallback determinístico")

    if not raw_body:
        raw_body = deterministic_description(context)

    final_desc = clean_youtube_description(
        raw_body,
        sources=None,
        hashtags=llm_tags or ["#Webjornal", "#ValedaLiberdade", "#Noticias"],
        is_bm=False,
    )

    if not dry_run:
        out_path.write_text(final_desc + "\n", encoding="utf-8")
        print(f"✅ Descrição gravada em: {out_path} ({len(final_desc)} caracteres)")

    return final_desc, out_path


def generate_bm_description(video_id: str, dry_run: bool = False) -> str:
    """Gera descrição para especial Brasil & Mundo."""
    context = load_bm_episode_context(video_id)
    print(f"🎯 Otimizando descrição BM para {video_id}: {context['title']}")

    raw_body = None
    llm_tags: list[str] = []
    if not dry_run:
        print("  → tentando LLM (Gemini/OpenRouter)...")
        llm_res = generate_description_via_llm(context)
        if llm_res:
            raw_body, llm_tags = llm_res
            print("  ✓ LLM respondeu com sucesso")
        else:
            print("  ⚠ LLM indisponível — usando fallback determinístico")

    if not raw_body:
        raw_body = deterministic_description(context)

    tags_pool = llm_tags or [f"#{t}" for t in context.get("tags", ["BrasilEMundo", "Economia", "Liberdade"])]
    final_desc = clean_youtube_description(
        raw_body,
        sources=context.get("refs"),
        hashtags=tags_pool,
        is_bm=True,
    )

    return final_desc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", help="Data do episódio diário (YYYY-MM-DD)")
    group.add_argument("--video-id", help="ID do vídeo do especial Brasil & Mundo")

    ap.add_argument("--dry-run", action="store_true", help="Apenas imprime a descrição, sem gravar")
    ap.add_argument("--force", action="store_true", help="Reescreve mesmo se o arquivo já existir")
    ap.add_argument("--print-prompt", action="store_true", help="Imprime o prompt canônico para o Hermes Agent")

    args = ap.parse_args()

    if args.date:
        if args.print_prompt:
            ctx = load_daily_episode_context(args.date)
            print(build_description_prompt(ctx))
            return 0

        desc, path = generate_daily_description(args.date, force=args.force, dry_run=args.dry_run)
        print("\n--- DESCRIÇÃO FINAL GERADA ---")
        print(desc)
        print("------------------------------")
        return 0

    if args.video_id:
        if args.print_prompt:
            ctx = load_bm_episode_context(args.video_id)
            print(build_description_prompt(ctx))
            return 0

        desc = generate_bm_description(args.video_id, dry_run=args.dry_run)
        print("\n--- DESCRIÇÃO FINAL BM GERADA ---")
        print(desc)
        print("---------------------------------")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
