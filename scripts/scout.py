#!/usr/bin/env python3
"""
Agente Scout — descoberta contínua de fontes para o Web Jornal Vale da Liberdade.

Roda semanalmente (via cron Hermes) e descobre candidatas por 3 vias:
  1. Busca direta ("notícias Blumenau", "portal Vale do Itajaí") via web_search().
  2. Mineração de citações: quando uma fonte ativa linka/outra veículo no
     conteúdo coletado (raw-{date}.md dos últimos dias), vira sinal de candidata.
  3. Contas X retuitadas/citadas por fontes confiáveis (lê X_USERNAME do .env;
     se não houver coletor X funcional, pula silenciosamente).

As candidatas são cruzadas contra o sources_registry.json (descarta as já
existentes) e salvas em sources/sources_candidates.json para o Judge avaliar.

Uso:
  python3 scripts/scout.py --weeks 1 --max-candidates 20
  python3 scripts/scout.py --dry-run        # não salva, só imprime
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Carrega .env do projeto
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
load_dotenv(PROJECT_ROOT / ".env")

from source_discovery_search import web_search  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scout")

REGISTRY = PROJECT_ROOT / "sources" / "sources_registry.json"
CANDIDATES = PROJECT_ROOT / "sources" / "sources_candidates.json"
EPISODES_DIR = PROJECT_ROOT / "episodes"

# Termos de busca geográficos (via 1)
SEARCH_QUERIES = [
    "notícias Blumenau hoje",
    "portal de notícias Vale do Itajaí",
    "jornal Blumenau Santa Catarina",
    "notícias Alto Vale SC",
    "veículo de comunicação Santa Catarina",
    "blog notícias Blumenau",
]

# Padrões de URL de veículos de notícia (para mineração de citações, via 2)
_NEWS_DOMAIN_RE = re.compile(
    r"https?://([a-z0-9.-]+\.(?:com|com\.br|net|org|news|blog|jor|diario|portal)[a-z0-9./-]*)",
    re.I,
)
# domínios que são nossas próprias fontes ou agregadores não-veículo
_IGNORE_DOMAINS = {
    "youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com",
    "twitter.com", "x.com", "t.co", "whatsapp.com", "wa.me", "t.me", "gov.br",
    "wikipedia.org", "google.com", "gstatic.com", "feeds.feedburner.com",
}


def _load_registry() -> dict:
    if not REGISTRY.exists():
        return {"sources": []}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _known_urls(registry: dict) -> set[str]:
    known = set()
    for s in registry.get("sources", []):
        for key in ("url", "feed_url"):
            u = (s.get(key) or "").strip().lower()
            if u:
                known.add(u)
                # também a raiz do domínio
                m = re.match(r"https?://([^/]+)", u)
                if m:
                    known.add(m.group(1))
    return known


def _domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def _discover_via_search(max_per_query: int = 5) -> list[dict]:
    """Via 1: busca direta por termos geográficos."""
    found: list[dict] = []
    for q in SEARCH_QUERIES:
        try:
            hits = web_search(q, max_per_query)
        except Exception as exc:
            log.warning("busca '%s' falhou: %s", q, exc)
            continue
        for h in hits:
            url = h.get("url", "")
            if not url:
                continue
            found.append({
                "name": h.get("title", "")[:120],
                "url": url,
                "discovery": {"via": "search", "query": q, "snippet": (h.get("snippet") or "")[:300]},
            })
    return found


def _discover_via_citations(days: int = 14) -> list[dict]:
    """Via 2: minera links de outros veículos dentro dos raw-{date}.md recentes."""
    found: list[dict] = []
    cutoff = datetime.now() - timedelta(days=days)
    if not EPISODES_DIR.exists():
        return found
    for raw in sorted(EPISODES_DIR.glob("raw-*.md"), reverse=True):
        try:
            m = re.search(r"raw-(\d{4}-\d{2}-\d{2})", raw.name)
            if m and datetime.strptime(m.group(1), "%Y-%m-%d") < cutoff:
                continue
        except Exception:
            pass
        text = raw.read_text(encoding="utf-8", errors="ignore")
        for dom in _NEWS_DOMAIN_RE.findall(text):
            d = dom.lower().rstrip("/")
            if any(d.endswith(ig) or ig in d for ig in _IGNORE_DOMAINS):
                continue
            m = re.match(r"https?://([^/]+)", "https://" + d)
            host = m.group(1) if m else d
            # tenta achar o título da notícia citada próximo ao link
            found.append({
                "name": host,
                "url": "https://" + d,
                "discovery": {"via": "citation", "from_raw": raw.name},
            })
    return found


def _discover_via_x() -> list[dict]:
    """Via 3: contas X citadas por fontes confiáveis.

    Sem coletor X funcional disponível no momento, retorna lista vazia.
    (Hook mantido para integração futura com x_collector.py.)
    """
    # TODO: quando x_collector estiver coletando, extrair handles retuitados
    # por fontes de status 'ativa' e transformar em candidatas x_scrape.
    return []


def _merge_and_dedupe(candidates: list[dict], known: set[str]) -> list[dict]:
    """Remove duplicatas (mesmo domínio) e fontes já no registry."""
    seen_domains: set[str] = set()
    out: list[dict] = []
    for c in candidates:
        url = c.get("url", "")
        dom = _domain_of(url)
        if not dom or dom in seen_domains:
            continue
        # descarta se a raiz do domínio já está no registry
        if any(dom == k or dom.endswith("." + k) or k.endswith("." + dom) for k in known):
            continue
        seen_domains.add(dom)
        out.append(c)
    return out


def run(weeks: int = 1, max_candidates: int = 30, dry_run: bool = False) -> list[dict]:
    registry = _load_registry()
    known = _known_urls(registry)
    log.info("Registry: %d fontes conhecidas. Buscando candidatas...", len(registry.get("sources", [])))

    raw: list[dict] = []
    raw += _discover_via_search()
    raw += _discover_via_citations(days=weeks * 7)
    raw += _discover_via_x()
    log.info("Descobertas brutas: %d (search+citações+x)", len(raw))

    candidates = _merge_and_dedupe(raw, known)
    log.info("Candidatas após cruzar com registry: %d", len(candidates))
    candidates = candidates[:max_candidates]

    if dry_run:
        for c in candidates:
            print(f"  • {c['name']}  <{c['url']}>  via={c['discovery']['via']}")
        return candidates

    # Salva acumulando com candidatas anteriores (sem perder histórico)
    existing: list[dict] = []
    if CANDIDATES.exists():
        try:
            existing = json.loads(CANDIDATES.read_text(encoding="utf-8")).get("candidates", [])
        except Exception:
            existing = []
    existing_doms = {_domain_of(c.get("url", "")) for c in existing}
    for c in candidates:
        if _domain_of(c.get("url", "")) in existing_doms:
            continue
        c["discovered_at"] = datetime.now(timezone.utc).isoformat()
        c["status"] = "candidata"
        existing.append(c)

    CANDIDATES.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "candidates": existing},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Salvo em %s (%d candidatas no total)", CANDIDATES, len(existing))
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description="Scout — descoberta de fontes")
    ap.add_argument("--weeks", type=int, default=1)
    ap.add_argument("--max-candidates", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(weeks=args.weeks, max_candidates=args.max_candidates, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
