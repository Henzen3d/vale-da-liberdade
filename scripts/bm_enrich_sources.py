#!/usr/bin/env python3
"""
Enriquecedor de Fontes — Pipeline Brasil e Mundo.

Adiciona fontes externas legítimas (veículos de imprensa) para dar suporte
ao aprofundamento do roteiro e alimentar as cenas visuais do mockup.

Estratégia (para quando tiver 6–10 fontes externas úteis):
1. Fontes da descrição do YouTube (já pareadas URL↔veículo);
2. Feeds RSS ativos do projeto (`sources/sources.json`);
3. Se < 6 fontes externas: chamada leve ao gemini-3.5-flash-lite (500 RPD)
   pedindo 3–5 URLs de notícias de veículos de referência sobre o mesmo fato.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

SOURCES_JSON_PATH = PROJECT_ROOT / "sources" / "sources.json"
SITE_URL = os.environ.get("SITE_URL", "https://news.mob.tec.br").rstrip("/")

# Idade máxima de item de RSS aceito como fonte de uma pauta atual.
RSS_MAX_AGE_DAYS = int(os.environ.get("BM_RSS_MAX_AGE_DAYS", "7"))
# Mínimo de palavras-chave discriminantes em comum para casar uma matéria preliminarmente.
RSS_MIN_KEYWORD_HITS = int(os.environ.get("BM_RSS_MIN_KEYWORD_HITS", "2"))

# Verbos/termos jornalísticos genéricos: aparecem em QUALQUER manchete e não
# identificam pauta. Casar por eles produzia fontes totalmente fora do tema.
GENERIC_TITLE_WORDS = {
    "mostra", "mostram", "aguarda", "aguardam", "aponta", "apontam", "revela",
    "revelam", "afirma", "afirmam", "declara", "diz", "dizem", "confira",
    "veja", "saiba", "entenda", "assista", "anuncia", "anunciam", "promete",
    "prometem", "temem", "teme", "quer", "querem", "pode", "podem", "deve", "devem",
    "após", "apos", "ainda", "assim", "outro", "outra", "outros", "outras",
    "primeiro", "primeira", "última", "ultima", "último", "ultimo", "grande",
    "melhor", "pior", "hoje", "ontem", "amanhã", "amanha", "ano", "anos",
    "dias", "meses", "vezes", "caso", "casos", "gente", "coisa", "coisas",
    "tudo", "nada", "pessoa", "pessoas", "parte", "forma", "fazer", "faz",
    "vídeo", "video", "fotos", "foto", "veja", "alerta", "urgente",
}

# Stopwords estruturais (preposições, dêiticos, termos do próprio canal).
_STRUCTURAL_STOPS = {
    "para", "com", "por", "que", "como", "mais", "sobre", "este", "esta",
    "canal", "vídeo", "video", "especial", "brasil", "mundo", "pelo", "pela",
    "entre", "depois", "antes", "contra", "agora", "quando", "muito", "novo",
    "nova", "todos", "todas", "qual", "quais", "onde", "quem", "isso", "aquilo",
    "esse", "essa", "esses", "essas", "daquele", "daquela", "nestes", "nestas",
}

BLOCKED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "ancapsu",
    "news.mob.tec.br",
    "instagram.com/accounts/login",
    "twitter.com/login",
    "x.com/login",
    "nytimes.com",
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def is_blocked_source(url: str) -> bool:
    low = (url or "").strip().lower()
    if not low.startswith("http://") and not low.startswith("https://"):
        return True
    return any(tok in low for tok in BLOCKED_DOMAINS)


def domain_of(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def clean_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    try:
        parts = urllib.parse.urlsplit(u)
        qs = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
        ]
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(qs), parts.fragment)
        )
    except Exception:
        return u


def veiculo_from_url(url: str) -> str:
    dom = domain_of(url)
    if not dom:
        return "Fonte Externa"
    name_map = {
        "g1.globo.com": "G1",
        "oglobo.globo.com": "O Globo",
        "folha.uol.com.br": "Folha de S.Paulo",
        "www1.folha.uol.com.br": "Folha de S.Paulo",
        "uol.com.br": "UOL",
        "noticias.uol.com.br": "UOL",
        "estadao.com.br": "Estadão",
        "cnnbrasil.com.br": "CNN Brasil",
        "bbc.com": "BBC News",
        "feeds.bbci.co.uk": "BBC News",
        "metropoles.com": "Metrópoles",
        "poder360.com.br": "Poder360",
        "gazetadopovo.com.br": "Gazeta do Povo",
        "veja.abril.com.br": "Veja",
        "exame.com": "Exame",
        "valor.globo.com": "Valor Econômico",
        "agenciabrasil.ebc.com.br": "Agência Brasil",
        "jovempan.com.br": "Jovem Pan",
        "ndmais.com.br": "ND+",
        "scc10.com.br": "SCC10",
        "reuters.com": "Reuters",
        "bloomberg.com": "Bloomberg",
        "infomoney.com.br": "InfoMoney",
        "revistaoeste.com": "Revista Oeste",
        "instagram.com": "Instagram",
        "x.com": "X",
        "twitter.com": "X",
    }
    for k, v in name_map.items():
        if dom == k or dom.endswith("." + k):
            return v
    # Formatação amigável: parte antes do primeiro ponto ou TLD
    part = dom.split(".")[0]
    return part.capitalize() if part else "Fonte Externa"


def site_referencias(video_id: str) -> list[dict]:
    return [
        {
            "veiculo": "Vale da Liberdade (site)",
            "url": f"{SITE_URL}/ep/especial-{video_id}.html",
            "self": True,
            "role": "visual",
            "origin": "site",
        },
        {
            "veiculo": "Vale da Liberdade (matéria transcrita)",
            "url": f"{SITE_URL}/episodes/especial-{video_id}.md",
            "self": True,
            "role": "visual",
            "origin": "site",
        },
    ]


def extract_keywords_from_title(title: str) -> list[str]:
    """Extrai palavras-chave relevantes (>3 caracteres, sem stopwords)."""
    words = re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛãõÃÕçÇ0-9]{4,}\b", (title or "").lower())
    return [w for w in words if w not in _STRUCTURAL_STOPS]


def strong_keywords_from_title(title: str) -> list[str]:
    """Só palavras-chave discriminantes: fora stopwords E verbos genéricos.

    São essas que caracterizam a pauta (nomes próprios, siglas, termos discriminantes).
    """
    return [w for w in extract_keywords_from_title(title) if w not in GENERIC_TITLE_WORDS]


def _rss_item_is_recent(item: ET.Element, max_age_days: int = RSS_MAX_AGE_DAYS) -> bool:
    """Rejeita item de RSS sem data ou publicado há mais de `max_age_days`."""
    raw_date = ""
    for tag in ("pubDate", "{http://www.w3.org/2005/Atom}updated",
                "{http://www.w3.org/2005/Atom}published",
                "{http://purl.org/dc/elements/1.1/}date"):
        el = item.find(tag)
        if el is not None and (el.text or "").strip():
            raw_date = el.text.strip()
            break
    if not raw_date:
        return False

    dt = None
    try:
        dt = parsedate_to_datetime(raw_date)
    except Exception:
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except Exception:
            return False
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt
    return age <= timedelta(days=max_age_days)


# Palavras temáticas comuns que sozinhas não identificam uma pauta única
COMMON_TOPIC_WORDS = {
    "governo", "brasil", "presidente", "política", "politica", "nacional",
    "país", "pais", "estado", "ministro", "tribunal", "justiça", "justica",
    "câmara", "camara", "senado", "congresso", "dia", "dias", "semana",
    "mês", "ano", "anos", "tempo", "água", "agua", "lama", "novo", "nova",
    "plano", "projeto", "lei", "reforma", "eleições", "eleicoes", "campanha",
}


def judge_source_relevance(pauta_title: str, candidate_title: str, candidate_summary: str = "") -> bool:
    """Juiz Semântico: valida se a matéria candidata trata especificamente do mesmo fato da pauta."""
    pauta_kws = strong_keywords_from_title(pauta_title)
    if len(pauta_kws) < RSS_MIN_KEYWORD_HITS:
        return False

    cand_low = (candidate_title or "").lower()
    hits = [kw for kw in pauta_kws if kw in cand_low]
    if len(hits) < RSS_MIN_KEYWORD_HITS:
        return False

    # Se há 4 ou mais termos discriminantes em comum, é o mesmo fato
    if len(hits) >= 4:
        return True

    # Entidades nomeadas (pessoa, órgão) ligam o tema. Não deixar o LLM vetar isso.
    high_value_hits = [kw for kw in hits if kw not in COMMON_TOPIC_WORDS]
    if len(high_value_hits) >= 2:
        return True

    # Checagem semântica com LLM leve para homônimos / 1 entidade + termo genérico
    try:
        from bm_condensador import _candidate_keys
        keys = _candidate_keys("GEMINI_API_KEY")
        if keys:
            from gemini_client import GeminiClient
            client = GeminiClient(api_key=keys[0])
            prompt = (
                "Você é um editor sênior de checagem jornalística.\n"
                f"Pauta em produção: \"{pauta_title}\"\n"
                f"Matéria encontrada: \"{candidate_title}\" {candidate_summary[:150]}\n\n"
                "Pergunta: A matéria encontrada cobre estritamente o mesmo acontecimento/fato da pauta?\n"
                "(Responda NÃO se for apenas um assunto diferente que compartilha palavras soltas como governo, polícia, lama, imposto).\n"
                "Responda ESTRITAMENTE 'SIM' ou 'NAO'."
            )
            resp = client.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={"temperature": 0.0, "max_output_tokens": 5},
            )
            ans = (getattr(resp, "text", "") or "").strip().upper()
            return "SIM" in ans
    except Exception:
        pass

    # Fallback: 2 hits no total e ao menos 1 entidade específica
    if len(hits) >= 2 and len(high_value_hits) >= 1:
        return True

    return False


def search_local_rss_sources(title: str, max_items: int = 3) -> list[dict]:
    """Busca itens relevantes em feeds RSS nacionais/gerais cadastrados em sources.json com validação estrita."""
    if not SOURCES_JSON_PATH.exists():
        return []
    try:
        data = json.loads(SOURCES_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    keywords = strong_keywords_from_title(title)
    if len(keywords) < RSS_MIN_KEYWORD_HITS:
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    sources = [
        s for s in data.get("sources", [])
        if s.get("enabled") and s.get("method") == "rss" and s.get("scope") in {"nacional", "internacional"}
    ]

    for src in sources[:8]:
        feed_url = src.get("url")
        if not feed_url:
            continue
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml"},
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items:
                t_el = item.find("title")
                if t_el is None:
                    t_el = item.find("{http://www.w3.org/2005/Atom}title")
                l_el = item.find("link")
                if l_el is None:
                    l_el = item.find("{http://www.w3.org/2005/Atom}link")
                item_title = (t_el.text or "").strip() if t_el is not None else ""
                item_url = ""
                if l_el is not None:
                    item_url = l_el.attrib.get("href") or (l_el.text or "").strip()
                item_url = clean_url(item_url)
                if not item_url or item_url in seen_urls or is_blocked_source(item_url):
                    continue

                # 1. Filtro de Idade: descarta notícias com mais de 7 dias
                if not _rss_item_is_recent(item):
                    continue

                # 2. Juiz de Relevância: descarta coincidências acidentais de palavras isoladas
                if not judge_source_relevance(title, item_title):
                    continue

                seen_urls.add(item_url)
                results.append({
                    "veiculo": src.get("name") or veiculo_from_url(item_url),
                    "url": item_url,
                    "title": item_title,
                    "role": "supporting",
                    "origin": "rss",
                    "self": False,
                })
                if len(results) >= max_items:
                    return results
        except Exception:
            continue

    return results


def search_web_sources(title: str, existing_urls: set[str], max_items: int = 3) -> list[dict]:
    """Busca fontes web reais via Tavily API (sem alucinar URLs) com validação semântica."""
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if not tavily_key:
        return []

    try:
        body = json.dumps({
            "api_key": tavily_key,
            "query": f"{title} noticia",
            "topic": "news",
            "search_depth": "basic",
            "max_results": max(4, max_items * 2),
            "include_domains": [
                "g1.globo.com", "folha.uol.com.br", "cnnbrasil.com.br",
                "estadao.com.br", "metropoles.com", "poder360.com.br",
                "oglobo.globo.com", "veja.abril.com.br", "gazetadopovo.com.br",
                "infomoney.com.br", "valor.globo.com", "bbc.com", "ndmais.com.br",
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        out: list[dict] = []
        for r in data.get("results", []):
            url = clean_url(r.get("url") or "")
            if not url or url in existing_urls or is_blocked_source(url):
                continue
            item_title = (r.get("title") or "").strip()
            item_snippet = (r.get("content") or "").strip()

            # Valida pertinência com a pauta antes de incluir
            if not judge_source_relevance(title, item_title, item_snippet):
                continue

            existing_urls.add(url)
            out.append({
                "veiculo": veiculo_from_url(url),
                "url": url,
                "title": item_title,
                "role": "supporting",
                "origin": "web_search",
                "self": False,
            })
            if len(out) >= max_items:
                break
        return out
    except Exception as exc:
        print(f"  ⚠️  Busca web Tavily falhou: {exc}")
        return []


def search_gemini_lite_sources(title: str, existing_urls: set[str], max_items: int = 4) -> list[dict]:
    """Fallback mantido para compatibilidade com assinaturas anteriores."""
    return search_web_sources(title, existing_urls, max_items)


def enrich_episode_sources(raw: dict, video_id: str, max_external: int = 8) -> tuple[list[dict], str]:
    """Monta lista completa de fontes (6–10 no total) e gera briefing em texto."""
    refs: list[dict] = []
    seen_urls: set[str] = set()

    # 1. Fontes da descrição YouTube
    from bm_transcript import (
        _PROMO_DOMAINS,
        extract_referencias,
    )

    paired = raw.get("sources")
    if paired:
        for idx, s in enumerate(paired):
            u = clean_url(s.get("url") or "")
            if u and u not in seen_urls and not is_blocked_source(u):
                seen_urls.add(u)
                refs.append({
                    "veiculo": (s.get("veiculo") or "").strip() or veiculo_from_url(u),
                    "url": u,
                    "self": False,
                    "role": "primary" if idx == 0 else "supporting",
                    "origin": "youtube_description",
                })
    else:
        urls = extract_referencias(raw.get("description") or "")
        if not urls:
            urls = []
            for u in raw.get("source_urls") or []:
                dom = domain_of(u)
                if dom and any(ex in dom for ex in _PROMO_DOMAINS):
                    continue
                urls.append(u)
        for idx, u in enumerate(urls):
            cu = clean_url(u)
            if cu and cu not in seen_urls and not is_blocked_source(cu):
                seen_urls.add(cu)
                refs.append({
                    "veiculo": veiculo_from_url(cu),
                    "url": cu,
                    "self": False,
                    "role": "primary" if idx == 0 else "supporting",
                    "origin": "youtube_description",
                })

    title = raw.get("title") or ""

    # REGRA DE SUFICIÊNCIA:
    # Se a descrição do YouTube já trouxe >= 2 fontes externas legítimas,
    # NÃO forçar busca aleatória em RSS ou web. Essas fontes originais são a base autêntica.
    # Só buscamos se tivermos menos de 2 fontes externas legítimas.
    MIN_SUFFICIENT_SOURCES = int(os.environ.get("BM_MIN_SUFFICIENT_SOURCES", "2"))
    TARGET_EXTERNAL_SOURCES = int(os.environ.get("BM_TARGET_EXTERNAL_SOURCES", "4"))

    # 2. RSS Local se ainda temos menos que o mínimo de fontes confiáveis
    if len(refs) < MIN_SUFFICIENT_SOURCES and title:
        needed = TARGET_EXTERNAL_SOURCES - len(refs)
        rss_hits = search_local_rss_sources(title, max_items=needed)
        for hit in rss_hits:
            u = hit["url"]
            if u not in seen_urls:
                seen_urls.add(u)
                refs.append(hit)

    # 3. Busca Web real se ainda faltarem fontes para o mínimo
    if len(refs) < MIN_SUFFICIENT_SOURCES and title:
        needed = TARGET_EXTERNAL_SOURCES - len(refs)
        web_hits = search_web_sources(title, seen_urls, max_items=needed)
        for hit in web_hits:
            refs.append(hit)

    # Limitar fontes externas ao teto configurado
    externas = refs[:max_external]

    # 4. Adicionar links self do site ao final
    todas = list(externas) + site_referencias(video_id)

    # 5. Montar briefing de texto para injeção no prompt do condensador
    # Tenta resolver títulos reais para fontes que só têm a URL crua
    try:
        from recover_page import recover_page
    except ImportError:
        try:
            from scripts.recover_page import recover_page
        except ImportError:
            recover_page = None

    briefing_lines = []
    for r in externas:
        veic = r.get("veiculo") or "Veículo"
        t = r.get("title")
        prov = r.get("provenance")
        url_target = r.get("url") or ""

        # Se não tiver título amigável, tentar recuperar via recover_page
        if (not t or t == url_target) and recover_page and url_target:
            try:
                rec = recover_page(url_target, timeout=6.0, try_direct_first=True)
                if rec.success:
                    t = rec.title or t
                    r["title"] = t
                    if rec.snapshot_date:
                        r["snapshot_date"] = rec.snapshot_date
                        r["provenance"] = rec.provenance
                        prov = rec.provenance
            except Exception:
                pass

        label_title = t or url_target
        if prov and "Arquivado" in prov:
            briefing_lines.append(f"- {veic} ({prov}): {label_title}")
        else:
            briefing_lines.append(f"- {veic}: {label_title}")

    briefing_text = ""
    if briefing_lines:
        briefing_text = "FONTES EXTRA (use para aprofundar; cite o veículo, não leia URL):\n" + "\n".join(briefing_lines)

    return todas, briefing_text
