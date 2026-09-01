#!/usr/bin/env python3
"""Sincronização de Playlist Dinâmica ("Últimas Notícias / Top da Semana") no YouTube.

Mantém uma playlist rotativa com os últimos N vídeos publicados (padrão: 10).
- Insere o novo vídeo no topo (position 0).
- Remove ocorrências anteriores do mesmo vídeo (idempotência).
- Remove os vídeos excedentes mais antigos (overflow trimming além de max_items).
- Custo de cota: ~101 unidades (1 list + 1 insert + 0-1 delete).
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

CONFIG_PATH = ROOT / "config" / "youtube.json"


def _fold(text: str) -> str:
    raw = unicodedata.normalize("NFD", text or "")
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    return " ".join(raw.lower().split())


def load_playlist_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("dynamic_playlist") or {}
        except Exception:
            return {}
    return {}


def resolve_dynamic_playlist_id(yt, configured_id: str | None = None, title: str | None = None) -> str | None:
    """Valida o playlist_id configurado ou localiza a playlist pelo título no canal."""
    # 1. Se tem ID configurado e não é chave de template/placeholder
    if configured_id and not configured_id.startswith("PL_") and len(configured_id) >= 12:
        try:
            resp = yt.playlists().list(part="id,snippet", id=configured_id, maxResults=1).execute()
            if resp.get("items"):
                return configured_id
        except Exception:
            pass

    # 2. Busca pelo título exato ou aproximado no canal
    target_title = title or "Últimas Notícias — Vale da Liberdade"
    target_fold = _fold(target_title)
    try:
        resp = yt.playlists().list(part="id,snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items") or []:
            sn_title = (item.get("snippet") or {}).get("title") or ""
            if _fold(sn_title) == target_fold or "ultimas noticias" in _fold(sn_title):
                return item["id"]
    except Exception:
        pass

    return None


def sync_dynamic_playlist(
    yt,
    video_id: str,
    playlist_id: str | None = None,
    max_items: int | None = None,
) -> dict:
    """Insere video_id na posição 0 da playlist dinâmica e remove excedentes."""
    cfg = load_playlist_config()
    if cfg.get("enabled") is False:
        return {"skipped": True, "reason": "disabled_in_config"}

    limit = max_items if max_items is not None else cfg.get("max_items", 10)
    p_id = playlist_id or cfg.get("playlist_id")
    p_title = cfg.get("title", "Últimas Notícias — Vale da Liberdade")

    resolved_pid = resolve_dynamic_playlist_id(yt, p_id, p_title)
    if not resolved_pid:
        return {"skipped": True, "reason": f"playlist não encontrada no canal ({p_title})"}

    # 1. Lê os itens atuais da playlist (ordem natural do índice 0 ao fim)
    resp = yt.playlistItems().list(part="id,snippet", playlistId=resolved_pid, maxResults=50).execute()
    items = resp.get("items") or []

    # 2. Verifica se o vídeo já está no topo (posição 0)
    if items:
        top_vid = (items[0].get("snippet") or {}).get("resourceId", {}).get("videoId")
        if top_vid == video_id:
            return {
                "added": False,
                "already_top": True,
                "playlist_id": resolved_pid,
                "total_items": len(items),
            }

    # 3. Insere o novo vídeo na posição 0
    insert_body = {
        "snippet": {
            "playlistId": resolved_pid,
            "position": 0,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        }
    }
    inserted = yt.playlistItems().insert(part="snippet", body=insert_body).execute()

    # 4. Remove ocorrências antigas do mesmo vídeo se já existia na playlist
    removed_ids: list[str] = []
    active_items: list[dict] = [inserted]
    for it in items:
        it_vid = (it.get("snippet") or {}).get("resourceId", {}).get("videoId")
        if it_vid == video_id:
            try:
                yt.playlistItems().delete(id=it["id"]).execute()
                removed_ids.append(it["id"])
            except Exception:
                pass
        else:
            active_items.append(it)

    # 5. Trim de overflow: remove os mais antigos que excederem o limite max_items
    while len(active_items) > limit:
        oldest = active_items.pop()
        try:
            yt.playlistItems().delete(id=oldest["id"]).execute()
            removed_ids.append(oldest["id"])
        except Exception:
            pass

    return {
        "added": True,
        "playlist_id": resolved_pid,
        "video_id": video_id,
        "position": 0,
        "removed": removed_ids,
        "total_items": len(active_items),
    }


def sync_dynamic_playlist_standalone(
    video_id: str,
    playlist_id: str | None = None,
    max_items: int | None = None,
) -> int:
    import youtube_uploader as ytu

    def _run():
        yt = ytu._yt()
        report = sync_dynamic_playlist(yt, video_id, playlist_id=playlist_id, max_items=max_items)
        if report.get("skipped"):
            print(f"  ⏭️  playlist dinâmica pulada: {report.get('reason')}")
            return 0
        if report.get("already_top"):
            print(f"  ℹ️  vídeo {video_id} já é o mais recente na playlist {report.get('playlist_id')}")
            return 0
        print(
            f"  ✅ playlist dinâmica sincronizada: {report.get('playlist_id')} "
            f"(vídeo {video_id} no topo, {len(report.get('removed', []))} removido(s), "
            f"total: {report.get('total_items')})"
        )
        return 0

    return ytu.run_with_slots("dynamic-playlist", _run)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza vídeo na playlist dinâmica rotativa")
    ap.add_argument("--video-id", required=True, help="ID do vídeo no YouTube")
    ap.add_argument("--playlist-id", default=None, help="ID opcional da playlist")
    ap.add_argument("--max-items", type=int, default=None, help="Limite máximo de vídeos na playlist (padrão: 10)")
    args = ap.parse_args()
    return sync_dynamic_playlist_standalone(args.video_id, args.playlist_id, args.max_items)


if __name__ == "__main__":
    raise SystemExit(main())
