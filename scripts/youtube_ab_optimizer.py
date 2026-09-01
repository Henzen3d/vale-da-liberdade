#!/usr/bin/env python3
"""Otimizador A/B de Títulos para YouTube (Web Jornal Vale da Liberdade).

Audita vídeos publicados que tiveram desempenho abaixo do esperado (views < 60%
da mediana dos últimos N dias) e gera novos títulos de alto CTR com IA (Gemini).
Permite aplicar a alteração via API (videos.update = 50 unidades de cota).

Uso:
  # 1. Auditoria de vídeos com baixo desempenho nos últimos 7 dias:
  python scripts/youtube_ab_optimizer.py --audit --days 7

  # 2. Sugestão de títulos para um vídeo específico:
  python scripts/youtube_ab_optimizer.py --suggest --video-id <YT_ID>

  # 3. Aplicação manual de um novo título no YouTube:
  python scripts/youtube_ab_optimizer.py --apply --video-id <YT_ID> --title "Novo Título"

  # 4. Modo automático (audita, sugere e opcionalmente aplica):
  python scripts/youtube_ab_optimizer.py --auto --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    from datetime import timezone, timedelta as _td
    TZ = timezone(_td(hours=-3))

PUBLISHED_STATE = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"
EPISODES_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AB_HISTORY_FILE = ROOT / "output" / "brasil_e_mundo" / "ab_title_history.json"

from title_optimizer import clean_youtube_title, generate_title_via_llm


def load_ab_history() -> dict:
    if AB_HISTORY_FILE.exists():
        try:
            return json.loads(AB_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"history": {}}
    return {"history": {}}


def save_ab_history(data: dict) -> None:
    AB_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AB_HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(AB_HISTORY_FILE)


def was_already_optimized(yt_id: str) -> bool:
    hist = load_ab_history().get("history") or {}
    return yt_id in hist


def record_optimization(
    yt_id: str,
    old_title: str,
    new_title: str,
    views_before: int = 0,
    median_views: float = 0.0,
    reason: str = "",
) -> None:
    data = load_ab_history()
    hist = data.setdefault("history", {})
    hist[yt_id] = {
        "yt_id": yt_id,
        "old_title": old_title,
        "new_title": new_title,
        "views_before": views_before,
        "median_views": median_views,
        "applied_at": datetime.now(TZ).isoformat(),
        "reason": reason,
    }
    save_ab_history(data)


def load_recent_published_candidates(days: int = 7, min_age_hours: float = 12.0) -> list[dict]:
    """Lê vídeos publicados em videos_published.json dentro da janela."""
    if not PUBLISHED_STATE.exists():
        return []
    try:
        data = json.loads(PUBLISHED_STATE.read_text(encoding="utf-8"))
    except Exception:
        return []

    videos = data.get("videos") or {}
    now = datetime.now(TZ)
    cutoff = now - timedelta(days=days)
    min_age_cutoff = now - timedelta(hours=min_age_hours)

    candidates: list[dict] = []
    for vid, meta in videos.items():
        yt_id = meta.get("yt_id")
        if not yt_id:
            continue
        pub_str = meta.get("published_at") or meta.get("data")
        if not pub_str:
            continue
        try:
            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=TZ)
            else:
                pub_dt = pub_dt.astimezone(TZ)
        except Exception:
            continue

        if cutoff <= pub_dt <= min_age_cutoff:
            candidates.append({
                "video_id": vid,
                "yt_id": yt_id,
                "title": meta.get("title", ""),
                "published_at": pub_dt.isoformat(),
            })

    return candidates


def audit_underperformers(
    yt,
    days: int = 7,
    threshold_pct: float = 0.60,
    min_age_hours: float = 12.0,
) -> tuple[list[dict], float]:
    """Identifica vídeos com views abaixo de threshold_pct da mediana.

    Retorna (underperformers, median_views).
    """
    candidates = load_recent_published_candidates(days=days, min_age_hours=min_age_hours)
    if not candidates:
        return [], 0.0

    yt_ids = [c["yt_id"] for c in candidates]
    # Busca statistics em batches de até 50 (custo: 1 unidade por batch)
    stats_map: dict[str, dict] = {}
    for i in range(0, len(yt_ids), 50):
        chunk = yt_ids[i : i + 50]
        resp = yt.videos().list(part="snippet,statistics", id=",".join(chunk)).execute()
        for item in resp.get("items") or []:
            vid = item["id"]
            sn = item.get("snippet") or {}
            st = item.get("statistics") or {}
            stats_map[vid] = {
                "title": sn.get("title") or "",
                "description": sn.get("description") or "",
                "views": int(st.get("viewCount") or 0),
                "likes": int(st.get("likeCount") or 0),
                "published_at": sn.get("publishedAt") or "",
            }

    all_views = [stats_map[vid]["views"] for vid in yt_ids if vid in stats_map]
    if not all_views:
        return [], 0.0

    median_views = statistics.median(all_views)
    cutoff_views = median_views * threshold_pct

    underperformers: list[dict] = []
    for cand in candidates:
        yid = cand["yt_id"]
        if yid not in stats_map:
            continue
        info = stats_map[yid]
        v = info["views"]
        if v <= cutoff_views and not was_already_optimized(yid):
            ratio = v / max(median_views, 1.0)
            underperformers.append({
                "video_id": cand["video_id"],
                "yt_id": yid,
                "title": info["title"],
                "description": info["description"],
                "views": v,
                "median_views": median_views,
                "ratio": ratio,
                "deficit_pct": round((1.0 - ratio) * 100, 1),
                "published_at": info["published_at"],
            })

    underperformers.sort(key=lambda x: x["views"])
    return underperformers, median_views


def suggest_alternative_titles(
    title: str,
    description: str = "",
    episode_id: str | None = None,
) -> list[str]:
    """Gera 3 a 5 variações de títulos com alta taxa de clique (CTR)."""
    manchetes: list[str] = []
    if episode_id:
        ep_file = EPISODES_DIR / f"especial-{episode_id}.json"
        if ep_file.exists():
            try:
                ep_data = json.loads(ep_file.read_text(encoding="utf-8"))
                for k in ("titulo", "fonte_titulo", "sintese", "lead"):
                    val = ep_data.get(k)
                    if val and isinstance(val, str):
                        manchetes.append(val.strip())
            except Exception:
                pass

    if not manchetes:
        manchetes = [title]
        if description:
            first_line = description.split("\n\n")[0].strip()
            if first_line and first_line != title:
                manchetes.append(first_line[:140])

    llm_res = generate_title_via_llm(manchetes)
    suggestions: list[str] = []
    if llm_res:
        rec = llm_res.get("recomendado")
        if rec and rec != title:
            suggestions.append(clean_youtube_title(rec))
        for op in llm_res.get("opcoes") or []:
            c = clean_youtube_title(op)
            if c and c != title and c not in suggestions:
                suggestions.append(c)

    if not suggestions:
        # Fallback de reformulação heurística
        suggestions.append(clean_youtube_title(f"A verdade sobre: {title}"))
        suggestions.append(clean_youtube_title(f"Entenda o caso: {title}"))

    return suggestions[:4]


def apply_new_title(
    yt,
    yt_id: str,
    new_title: str,
    views_before: int = 0,
    median_views: float = 0.0,
    reason: str = "ab_optimization",
) -> dict:
    """Atualiza o título do vídeo via YouTube Data API v3 (custo: 50 unidades)."""
    cleaned = clean_youtube_title(new_title)
    got = yt.videos().list(part="snippet,status,recordingDetails", id=yt_id).execute()
    items = got.get("items") or []
    if not items:
        raise RuntimeError(f"vídeo YouTube {yt_id} não encontrado")

    item = items[0]
    sn = item.get("snippet") or {}
    old_title = sn.get("title") or ""

    sn["title"] = cleaned
    body = {
        "id": yt_id,
        "snippet": sn,
        "status": item.get("status") or {},
        "recordingDetails": item.get("recordingDetails") or {},
    }

    yt.videos().update(part="snippet,status,recordingDetails", body=body).execute()
    record_optimization(
        yt_id=yt_id,
        old_title=old_title,
        new_title=cleaned,
        views_before=views_before,
        median_views=median_views,
        reason=reason,
    )
    return {
        "yt_id": yt_id,
        "old_title": old_title,
        "new_title": cleaned,
        "applied": True,
    }


def cmd_audit(days: int = 7, threshold_pct: float = 0.60) -> int:
    import youtube_uploader as ytu

    def _run():
        yt = ytu._yt()
        under, med = audit_underperformers(yt, days=days, threshold_pct=threshold_pct)
        print(f"\n📊 Auditoria de Desempenho (Últimos {days} dias — Mediana: {med:.0f} views):")
        if not under:
            print("  ✅ Nenhum vídeo com baixo desempenho crítico encontrado (todos ≥ 60% da mediana).")
            return 0
        print(f"  🔍 {len(under)} vídeo(s) com views abaixo de {threshold_pct*100:.0f}% da mediana ({med*threshold_pct:.0f} views):")
        for u in under:
            print(f"  • [{u['yt_id']}] {u['views']} views (-{u['deficit_pct']}%) — {u['title'][:70]}")
        return 0

    return ytu.run_with_slots("whoami", _run)


def cmd_suggest(yt_id: str) -> int:
    import youtube_uploader as ytu

    def _run():
        yt = ytu._yt()
        resp = yt.videos().list(part="snippet", id=yt_id).execute()
        items = resp.get("items") or []
        if not items:
            print(f"❌ Vídeo {yt_id} não encontrado")
            return 1
        sn = items[0]["snippet"]
        current_title = sn.get("title", "")
        desc = sn.get("description", "")
        print(f"\n🎯 Título Atual: {current_title}")
        print("💡 Gerando sugestões otimizadas para taxa de clique (CTR)...")
        suggestions = suggest_alternative_titles(current_title, desc)
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s} ({len(s)} chars)")
        return 0

    return ytu.run_with_slots("whoami", _run)


def cmd_apply(yt_id: str, new_title: str) -> int:
    import youtube_uploader as ytu

    def _run():
        yt = ytu._yt()
        res = apply_new_title(yt, yt_id, new_title)
        print(f"✅ Título atualizado com sucesso!")
        print(f"   De:   {res['old_title']}")
        print(f"   Para: {res['new_title']}")
        return 0

    return ytu.run_with_slots("apply-policy", _run)


def cmd_auto(days: int = 7, threshold_pct: float = 0.60, dry_run: bool = True) -> int:
    import youtube_uploader as ytu

    def _run():
        yt = ytu._yt()
        under, med = audit_underperformers(yt, days=days, threshold_pct=threshold_pct)
        if not under:
            print("✅ Nenhum vídeo com baixo desempenho precisa de otimização.")
            return 0
        target = under[0]  # Pior sob-performer
        print(f"\n🔍 Pior desempenho detectado: [{target['yt_id']}] ({target['views']} views vs mediana {med:.0f})")
        print(f"   Título atual: {target['title']}")
        suggestions = suggest_alternative_titles(target['title'], target.get('description', ''), target.get('video_id'))
        if not suggestions:
            print("⚠️ Nenhuma sugestão gerada.")
            return 0
        best_title = suggestions[0]
        print(f"💡 Novo título sugerido: {best_title}")
        if dry_run:
            print("ℹ️  [DRY-RUN] Nenhuma alteração aplicada na API do YouTube.")
            return 0
        res = apply_new_title(yt, target['yt_id'], best_title, views_before=target['views'], median_views=med)
        print(f"✅ [APLICADO] Título atualizado para: {res['new_title']}")
        return 0

    return ytu.run_with_slots("apply-policy" if not dry_run else "whoami", _run)


def main() -> int:
    ap = argparse.ArgumentParser(description="Otimizador A/B de Títulos no YouTube")
    ap.add_argument("--audit", action="store_true", help="Audita vídeos abaixo da mediana de views")
    ap.add_argument("--suggest", action="store_true", help="Gera títulos alternativos com alto CTR")
    ap.add_argument("--apply", action="store_true", help="Aplica novo título no YouTube (50 un)")
    ap.add_argument("--auto", action="store_true", help="Otimiza automaticamente o pior sob-performer")
    ap.add_argument("--video-id", help="ID do vídeo no YouTube")
    ap.add_argument("--title", help="Novo título a ser aplicado")
    ap.add_argument("--days", type=int, default=7, help="Janela de dias para auditoria (padrão: 7)")
    ap.add_argument("--threshold", type=float, default=0.60, help="Fator de corte da mediana (padrão: 0.60)")
    ap.add_argument("--dry-run", action="store_true", help="Modo simulação sem chamada de escrita")
    args = ap.parse_args()

    if args.audit:
        return cmd_audit(days=args.days, threshold_pct=args.threshold)
    if args.suggest:
        if not args.video_id:
            print("❌ --video-id é obrigatório para --suggest", file=sys.stderr)
            return 2
        return cmd_suggest(args.video_id)
    if args.apply:
        if not args.video_id or not args.title:
            print("❌ --video-id e --title são obrigatórios para --apply", file=sys.stderr)
            return 2
        return cmd_apply(args.video_id, args.title)
    if args.auto:
        return cmd_auto(days=args.days, threshold_pct=args.threshold, dry_run=args.dry_run)

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
