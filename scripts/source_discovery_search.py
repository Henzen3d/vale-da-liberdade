#!/usr/bin/env python3
"""
Busca web para o agente Scout (descoberta de fontes do Web Jornal).

Cascata: Tavily (se TAVILY_API_KEY) -> Exa (se EXA_API_KEY) ->
DuckDuckGo (sem chave) -> Wikipedia (fallback sem chave).

Reutiliza o mesmo padrão do Fusion (scripts/web_tools.py) para não
depender do projeto vizinho. As chaves ficam no .env do web-jornal.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
from pathlib import Path

import httpx

log = logging.getLogger("scout.search")

_REQUEST_TIMEOUT = 25
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": max_results, "search_depth": "basic"},
            headers={"Authorization": f"Bearer {key}"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
    except Exception as exc:
        log.warning("✗ Tavily falhou: %s", exc)
        return []


def _exa_search(query: str, max_results: int = 5) -> list[dict]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return []
    try:
        resp = httpx.post(
            "https://api.exa.ai/search",
            json={"query": query, "numResults": max_results, "contents": {"text": True, "highlights": True}},
            headers={"x-api-key": key, "Content-Type": "application/json"},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        out = []
        for r in data.get("results", [])[:max_results]:
            snip = (r.get("text") or "").strip()
            snip = re.sub(r"\s+", " ", snip)[:600]
            if not snip:
                hl = r.get("highlights") or []
                snip = re.sub(r"\s+", " ", " ".join(hl))[:600]
            out.append({"title": r.get("title", ""), "url": r.get("url", ""), "snippet": snip})
        return out
    except Exception as exc:
        log.warning("✗ Exa falhou: %s", exc)
        return []


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        resp = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "br-pt"},
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        log.warning("✗ DuckDuckGo falhou: %s", exc)
        return []
    results = []
    link_re = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    snip_re = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
    links = link_re.findall(html)
    snips = snip_re.findall(html)
    for i, (href, title_html) in enumerate(links[:max_results]):
        real = href
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            real = urllib.parse.unquote(m.group(1))
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snip = ""
        if i < len(snips):
            snip = re.sub(r"<[^>]+>", "", snips[i]).strip()
        if title:
            results.append({"title": title, "url": real, "snippet": snip})
    return results


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Busca em cascata (Tavily -> Exa -> DuckDuckGo -> Wikipedia)."""
    if os.environ.get("TAVILY_API_KEY"):
        r = _tavily_search(query, max_results)
        if r:
            return r
    if os.environ.get("EXA_API_KEY"):
        r = _exa_search(query, max_results)
        if r:
            return r
    results = _ddg_search(query, max_results)
    return results


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    q = sys.argv[1] if len(sys.argv) > 1 else "notícias Blumenau"
    for hit in web_search(q, 5):
        print("-", hit["title"][:60], "|", hit["url"][:50])
