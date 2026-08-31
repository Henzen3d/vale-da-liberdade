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
# Mínimo de palavras-chave discriminantes em comum para casar uma matéria.
RSS_MIN_KEYWORD_HITS = int(os.environ.get("BM_RSS_MIN_KEYWORD_HITS", "2"))

BLOCKED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "ancapsu",
    "news.mob.tec.br",
    "instagram.com/accounts/login",
    "twitter.com/login",
    "x.com/login",
    "nytimes.com",  # PerimeterX challenge
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


# Verbos/termos jornalísticos genéricos: aparecem em QUALQUER manchete e não
# identificam pauta. Casar por eles produzia fontes totalmente fora do tema
# (ex.: "mostra" casando "Levantamento do G1 mostra variação de preço...").
GENERIC_TITLE_WORDS = {
    "mostra", "mostram", "aguarda", "aguardam", "aponta", "apontam", "revela",
    "revelam", "afirma", "afirmam", "declara", "diz", "dizem", "confira",
    "veja", "saiba", "entenda", "assista", "anuncia", "anuncia", "anunciam",
    "temem", "teme", "quer", "querem", "pode", "podem", "deve", "devem",
    "após", "apos", "ainda", "assim", "outro", "outra", "outros", "outras",
    "primeiro", "primeira", "última", "ultima", "último", "ultimo", "grande",
    "melhor", "pior", "hoje", "ontem", "amanhã", "amanha", "ano", "anos",
    "dias", "meses", "vezes", "caso", "casos", "gente", "coisa", "coisas",
    "tudo", "nada", "pessoa", "pessoas", "parte", "forma", "fazer", "faz",
}

# Stopwords estruturais (preposições, dêiticos, termos do próprio canal).
_STRUCTURAL_STOPS = {
    "para", "com", "por", "que", "como", "mais", "sobre", "este", "esta",
    "canal", "vídeo", "video", "especial", "brasil", "mundo", "pelo", "pela",
    "entre", "depois", "antes", "contra", "agora", "quando", "muito", "novo",
    "nova", "todos", "todas", "qual", "quais", "onde", "quem", "isso", "aquilo",
}


def extract_keywords_from_title(title: str) -> list[str]:
    """Extrai palavras-chave relevantes (>3 caracteres, sem stopwords)."""
    words = re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛãõÃÕçÇ0-9]{4,}\b", title.lower())
    return [w for w in words if w not in _STRUCTURAL_STOPS]


def strong_keywords_from_title(title: str) -> list[str]:
    """Só palavras-chave discriminantes: fora stopwords E verbos genéricos.

    São essas que caracterizam a pauta (nomes próprios, siglas, temas).
    """
    return [w for w in extract_keywords_from_title(title) if w not in GENERIC_TITLE_WORDS]


def _rss_item_is_recent(item: "ET.Element", max_age_days: int = RSS_MAX_AGE_DAYS) -> bool:
    """Rejeita item de RSS sem data ou publicado há mais de `max_age_days`.

    Feeds regionais do G1 devolviam matérias de 2018 no mesmo XML; sem esse
    filtro elas entravam como 'fonte' de uma pauta de 2026.
    """
    raw_date = ""
    for tag in ("pubDate", "{http://www.w3.org/2005/Atom}updated",
                "{http://www.w3.org/2005/Atom}published",
                "{http://purl.org/dc/elements/1.1/}date"):
        el = item.find(tag)
        if el is not None and (el.text or "").strip():
            raw_date = el.text.strip()
            break
    if not raw_date:
        return False  # sem data confiável => não usa

    dt = None
    try:
        dt = parsedate_to_datetime(raw_date)
    except Exception:  # noqa: BLE001
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return False
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - dt
    return age <= timedelta(days=max_age_days)


def search_local_rss_sources(title: str, max_items: int = 3) -> list[dict]:
    """Busca itens relevantes em feeds RSS nacionais/gerais cadastrados em sources.json."""
    if not SOURCES_JSON_PATH.exists():
        return []
    try:
        data = json.loads(SOURCES_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    keywords = strong_keywords_from_title(title)
    if len(keywords) < RSS_MIN_KEYWORD_HITS:
        # Sem termos discriminantes suficientes, qualquer match seria ruído.
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
            with urllib.request.urlopen(req, timeout=8) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            # RSS 2.0 channel/item ou Atom feed/entry
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

                # Rejeita matéria antiga (feeds regionais devolvem arquivo de anos atrás)
                if not _rss_item_is_recent(item):
                    continue

                # Exige >= RSS_MIN_KEYWORD_HITS palavras discriminantes em comum.
                title_low = item_title.lower()
                hits = [kw for kw in keywords if kw in title_low]
                if len(hits) >= RSS_MIN_KEYWORD_HITS:
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


def search_gemini_lite_sources(title: str, existing_urls: set[str], max_items: int = 4) -> list[dict]:
    """Usa gemini-3.5-flash-lite para sugerir 3–5 URLs de reportagens de veículos conhecidos."""
    try:
        from bm_condensador import _candidate_keys
        keys = _candidate_keys("GEMINI_API_KEY")
        if not keys:
            return []
        from gemini_client import GeminiClient, GeminiMultiClient
        client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])

        prompt = f"""Você é um pesquisador de imprensa para o jornal Vale da Liberdade.
Para o fato jornalístico abaixo, indique de 3 a 5 URLs reais ou típicas de reportagens dos principais portais de notícias (Folha, G1, CNN Brasil, Estadão, Metrópoles, Poder360, BBC Brasil, UOL) que cobrem esse acontecimento.

Tema/Título: {title}

Retorne ESTRITAMENTE um JSON no seguinte formato:
{{
  "fontes": [
    {{"veiculo": "Folha de S.Paulo", "url": "https://www1.folha.uol.com.br/...", "resumo": "Uma linha sobre o fato"}},
    {{"veiculo": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/...", "resumo": "Uma linha sobre o fato"}}
  ]
}}
NÃO invente domínios inexistentes. Use apenas veículos conhecidos."""

        resp = client.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 1024, "response_mime_type": "application/json"},
        )
        text = getattr(resp, "text", "") or ""
        if not text:
            return []
        data = json.loads(text)
        out: list[dict] = []
        for item in data.get("fontes", []):
            url = clean_url(item.get("url", ""))
            if not url or url in existing_urls or is_blocked_source(url):
                continue
            veic = item.get("veiculo") or veiculo_from_url(url)
            out.append({
                "veiculo": veic,
                "url": url,
                "title": item.get("resumo", ""),
                "role": "supporting",
                "origin": "search",
                "self": False,
            })
            existing_urls.add(url)
            if len(out) >= max_items:
                break
        return out
    except Exception as exc:
        print(f"  ⚠️  Busca gemini-lite de fontes falhou: {exc}")
        return []


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

    # 2. RSS Local se ainda temos poucas fontes externas (< 6)
    if len(refs) < 6 and title:
        rss_hits = search_local_rss_sources(title, max_items=max(0, 6 - len(refs)))
        for hit in rss_hits:
            u = hit["url"]
            if u not in seen_urls:
                seen_urls.add(u)
                refs.append(hit)

    # 3. Gemini Lite se ainda < 6 fontes externas
    if len(refs) < 6 and title:
        lite_hits = search_gemini_lite_sources(title, seen_urls, max_items=max(0, 6 - len(refs)))
        for hit in lite_hits:
            refs.append(hit)

    # Limitar fontes externas ao teto configurado
    externas = refs[:max_external]

    # 4. Adicionar links self do site ao final
    todas = list(externas) + site_referencias(video_id)

    # 5. Montar briefing de texto para injeção no prompt do condensador
    briefing_lines = []
    for r in externas:
        veic = r.get("veiculo") or "Veículo"
        t = r.get("title") or r.get("url")
        briefing_lines.append(f"- {veic}: {t}")

    briefing_text = ""
    if briefing_lines:
        briefing_text = "FONTES EXTRA (use para aprofundar; cite o veículo, não leia URL):\n" + "\n".join(briefing_lines)

    return todas, briefing_text
