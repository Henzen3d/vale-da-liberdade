#!/usr/bin/env python3
"""
Governança de fontes — probatório + relatório semanal human-in-loop.

Fluxo de estados:
  descoberta(Scout) → candidata → probatória (N matérias) → ativa
                                                       ↓ falha
                                                    banida

Este módulo NÃO promove nem bane automaticamente. Ele:
  1. Atualiza métricas de fontes em probatória a partir do cache de coleta.
  2. Quando uma fonte probatória atinge probation_min_articles E
     usage_rate/duplicate_rate dentro do aceitável, gera uma PROPOSTA de
     promoção (status continua 'probatória' até aprovação humana).
  3. Quando score do Judge < ban_threshold recorrente, gera PROPOSTA de banimento.
  4. Escreve sources/sources_weekly_report.json (pendente de aprovação) e
     imprime o relatório legível.

A aprovação é feita por humano (Hermes pergunta ao usuário) e só então
governance_apply.py (ou função apply()) efetiva a mudança no registry e no
sources.json operacional.

Uso:
  python3 scripts/source_governance.py            # gera relatório semanal
  python3 scripts/source_governance.py --apply    # (após aprovação) efetiva propostas
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("governance")

REGISTRY = PROJECT_ROOT / "sources" / "sources_registry.json"
CANDIDATES = PROJECT_ROOT / "sources" / "sources_candidates.json"
SOURCES_JSON = PROJECT_ROOT / "sources" / "sources.json"
REPORT = PROJECT_ROOT / "sources" / "sources_weekly_report.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_probation_metrics(registry: dict) -> None:
    """Atualiza articles_collected_in_probation a partir do cache de coleta (source_stats)."""
    cache = _load(PROJECT_ROOT / "sources" / "cache.json")
    stats = cache.get("source_stats", {})
    for s in registry.get("sources", []):
        if s.get("status") != "probatória" or not s.get("probation"):
            continue
        sid = s["id"]
        st = stats.get(sid)
        if st:
            s["probation"]["articles_collected_in_probation"] = st.get("total_fetches", 0)
            # usa últimas métricas se houver
            if "articles_collected" in st:
                s["metrics"]["articles_collected"] = st["articles_collected"]


def build_report(registry: dict, candidates: dict) -> dict:
    gov = registry.get("governance", {})
    min_art = gov.get("probation_min_articles", 15)
    ban_th = gov.get("judge_score_ban_threshold", 5.0)
    promote_th = gov.get("judge_score_promote_threshold", 7.0)

    proposals_promote = []
    proposals_ban = []

    # Candidatas já julgadas: promover para probatória ou banir conforme veredicto
    for c in candidates.get("candidates", []):
        sc = c.get("judge_score")
        if not sc:
            continue
        sf = float(sc.get("score_final", 0))
        if sf >= promote_th and c.get("status") == "candidata":
            proposals_promote.append({
                "id": c.get("id") or f"cand_{c.get('url','')[-12:]}",
                "name": c.get("name"), "url": c.get("url"),
                "action": "criar_probatória",
                "score": sf, "motivo": sc.get("motivo", ""),
            })
        elif sf < ban_th:
            proposals_ban.append({
                "id": c.get("id") or f"cand_{c.get('url','')[-12:]}",
                "name": c.get("name"), "url": c.get("url"),
                "action": "banir_candidata", "score": sf, "motivo": sc.get("motivo", ""),
            })

    # Fontes probatórias que atingiram o período: propor promoção a ativa
    for s in registry.get("sources", []):
        if s.get("status") != "probatória":
            continue
        pb = s.get("probation") or {}
        collected = pb.get("articles_collected_in_probation", 0)
        m = s.get("metrics", {})
        usage = m.get("usage_rate")
        dup = m.get("duplicate_rate")
        ok = (collected >= min_art) and (usage is None or usage >= 0.20) and (dup is None or dup <= 0.30)
        if ok:
            proposals_promote.append({
                "id": s["id"], "name": s.get("name"), "url": s.get("url"),
                "action": "promover_ativa",
                "collected_in_probation": collected, "usage_rate": usage, "duplicate_rate": dup,
                "motivo": "período probatório concluído com métricas dentro do aceitável",
            })
        else:
            proposals_ban.append({
                "id": s["id"], "name": s.get("name"), "url": s.get("url"),
                "action": "banir_probatória",
                "collected_in_probation": collected, "usage_rate": usage, "duplicate_rate": dup,
                "motivo": "não atingiu critérios do período probatório",
            })

    return {
        "generated_at": _now(),
        "pending_approval": True,
        "auto_promote": gov.get("auto_promote", False),
        "auto_ban": gov.get("auto_ban", False),
        "proposals_promote": proposals_promote,
        "proposals_ban": proposals_ban,
        "note": "Nenhuma mudança foi aplicada. Aprovação humana requerida (Hermes pergunta ao usuário).",
    }


def apply_proposals(registry: dict, candidates: dict, report: dict) -> None:
    """Efetiva propostas (APÓS aprovação humana)."""
    id_map = {s["id"]: s for s in registry.get("sources", [])}
    # promoções
    for p in report.get("proposals_promote", []):
        sid = p["id"]
        if p["action"] == "criar_probatória" and sid not in id_map:
            now = _now()
            registry["sources"].append({
                "id": sid, "name": p["name"], "url": p["url"], "feed_url": "",
                "access_type": "scraping_html", "category": ["sc"], "topic_tags": [],
                "status": "probatória",
                "added_at": now, "promoted_at": None,
                "metrics": {"articles_collected": 0, "articles_used_in_episode": 0,
                            "usage_rate": None, "scrape_error_rate": None,
                            "duplicate_rate": None, "avg_editorial_score": None, "last_scored_at": now},
                "bias_notes": p.get("motivo"), "banned_reason": None,
                "probation": {"started_at": now, "min_articles_required": registry.get("governance", {}).get("probation_min_articles", 15),
                              "articles_collected_in_probation": 0, "review_at": ""},
            })
            id_map[sid] = registry["sources"][-1]
        elif p["action"] == "promover_ativa" and sid in id_map:
            id_map[sid]["status"] = "ativa"
            id_map[sid]["promoted_at"] = _now()
            id_map[sid]["probation"] = None
    # banimentos
    for p in report.get("proposals_ban", []):
        sid = p["id"]
        if sid in id_map:
            id_map[sid]["status"] = "banida"
            id_map[sid]["banned_reason"] = p.get("motivo", "proposta de governança")
            id_map[sid]["probation"] = None
    registry["last_updated"] = _now()
    # sincroniza sources.json operacional (adiciona fontes probatórias/ativas)
    _sync_sources_json(registry)


def _sync_sources_json(registry: dict) -> None:
    """Adiciona ao sources.json as fontes que o collector precisa coletar."""
    src = _load(SOURCES_JSON)
    existing_urls = {s.get("url", "").rstrip("/") for s in src.get("sources", [])}
    changed = False
    for s in registry.get("sources", []):
        if s.get("status") in ("ativa", "probatória") and s.get("url", "").rstrip("/") not in existing_urls:
            method = {"rss": "rss", "scraping_html": "scraping", "browser_js": "browser"}.get(s.get("access_type"), "scraping")
            src.setdefault("sources", []).append({
                "id": s["id"], "name": s["name"], "url": s["url"],
                "method": method, "enabled": True,
            })
            existing_urls.add(s["url"].rstrip("/"))
            changed = True
    if changed:
        SOURCES_JSON.write_text(json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("sources.json operacional atualizado.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Governança de fontes")
    ap.add_argument("--apply", action="store_true", help="efetiva propostas (após aprovação)")
    args = ap.parse_args()

    registry = _load(REGISTRY) or {"sources": [], "governance": {}}
    candidates = _load(CANDIDATES) or {"candidates": []}
    update_probation_metrics(registry)

    if args.apply:
        if not REPORT.exists():
            log.error("Nenhum relatório pendente. Rode sem --apply primeiro.")
            return 3
        report = _load(REPORT)
        apply_proposals(registry, candidates, report)
        REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT.write_text(json.dumps({**report, "pending_approval": False, "applied_at": _now()}, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Propostas aplicadas e registry atualizado.")
        return 0

    report = build_report(registry, candidates)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    # imprime relatório legível
    print("\n" + "=" * 70)
    print("RELATÓRIO SEMANAL DE FONTES — pendente de aprovação humana")
    print("=" * 70)
    print(f"Promoções propostas: {len(report['proposals_promote'])}")
    for p in report["proposals_promote"]:
        print(f"  ↑ {p['action']}: {p['name']}  (score={p.get('score','-')})")
    print(f"Banimentos propostos: {len(report['proposals_ban'])}")
    for p in report["proposals_ban"]:
        print(f"  ↓ {p['action']}: {p['name']}  (score={p.get('score','-')})")
    print("-" * 70)
    print("Salvo em:", REPORT)
    print("Nenhuma mudança aplicada automaticamente (governança human-in-loop).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
