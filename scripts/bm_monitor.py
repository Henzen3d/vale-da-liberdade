#!/usr/bin/env python3
"""
Monitor RSS do canal ANCAPSU — Pipeline Brasil e Mundo.

Faz polling do feed Atom do YouTube, compara video_id contra
seen_videos.json, filtra por duração/tipo, e enfileira novos
vídeos em queue.json para processamento pelo bm_pipeline.py.

Uso:
    python scripts/bm_monitor.py              # polling normal
    python scripts/bm_monitor.py --dry-run    # lista sem enfileirar
    python scripts/bm_monitor.py --backfill 5 # enfileira os últimos N

Cron sugerido (servidor):
    */60 * * * * cd /path/to/webjornal && python scripts/bm_monitor.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PIPELINE_DIR = PROJECT_ROOT / "pipelines" / "brasil_e_mundo"
CONFIG_PATH = PIPELINE_DIR / "config.json"
SEEN_PATH = PIPELINE_DIR / "seen_videos.json"
QUEUE_PATH = PIPELINE_DIR / "queue.json"

# YouTube Atom feed namespaces
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERRO: config não encontrado: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return {"videos": {}}


def save_seen(seen: dict) -> None:
    SEEN_PATH.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_queue() -> list[dict]:
    if QUEUE_PATH.exists():
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data.get("queue", [])
    return []


def save_queue(queue: list[dict]) -> None:
    QUEUE_PATH.write_text(
        json.dumps({"queue": queue}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_feed(rss_url: str) -> list[dict]:
    """Faz fetch do feed Atom do YouTube e extrai entradas."""
    req = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "Mozilla/5.0 (WebjornalBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_bytes = resp.read()
    except urllib.error.URLError as e:
        print(f"ERRO ao buscar feed: {e}")
        return []

    root = ET.fromstring(xml_bytes)
    entries = []

    for entry in root.findall("atom:entry", NS):
        video_id_el = entry.find("yt:videoId", NS)
        title_el = entry.find("atom:title", NS)
        published_el = entry.find("atom:published", NS)
        updated_el = entry.find("atom:updated", NS)
        link_el = entry.find("atom:link", NS)
        author_el = entry.find("atom:author/atom:name", NS)

        # Media group for description/thumbnail
        media_group = entry.find("media:group", NS)
        description = ""
        if media_group is not None:
            desc_el = media_group.find("media:description", NS)
            if desc_el is not None and desc_el.text:
                description = desc_el.text

        if video_id_el is None or video_id_el.text is None:
            continue

        video_id = video_id_el.text.strip()
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        published = (
            published_el.text.strip()
            if published_el is not None and published_el.text
            else ""
        )
        url = (
            link_el.get("href", f"https://www.youtube.com/watch?v={video_id}")
            if link_el is not None
            else f"https://www.youtube.com/watch?v={video_id}"
        )
        channel_name = (
            author_el.text.strip()
            if author_el is not None and author_el.text
            else "Desconhecido"
        )

        entries.append(
            {
                "video_id": video_id,
                "title": title,
                "url": url,
                "published": published,
                "channel": channel_name,
                "description": description[:500],
            }
        )

    return entries


def is_short_or_live(title: str, url: str) -> bool:
    """Heurística para detectar Shorts e lives pelo título ou URL."""
    low = title.lower()
    if "/shorts/" in url.lower():
        return True
    # Shorts geralmente têm #shorts no título
    if "#shorts" in low or "#short" in low:
        return True
    # Lives cruas
    if re.search(r"\b(live|ao vivo|transmiss[aã]o)\b", low):
        return True
    return False


def is_interview(title: str) -> bool:
    """Entrevistas do ANCAPSU (ex.: 'PETER ENTREVISTA: ALTIVO DUARTE — Deputado').

    Formato do canal: <APRESENTADOR> ENTREVISTA: <Convidado> ou 'ENTREVISTA COM …'.
    Mesmo tratamento dos stories: ignorar — a pauta é notícia, não conversa.
    """
    low = title.lower()
    # "PETER ENTREVISTA: ...", "ENTREVISTA: ...", "ENTREVISTA COM ..."
    if re.search(r"\bentrevista\s*:", low):
        return True
    if re.search(r"\bentrevista\s+com\b", low):
        return True
    return False


def enqueue_video(
    queue: list[dict],
    seen: dict,
    video: dict,
    source: str = "monitor",
) -> bool:
    """Adiciona vídeo à fila se não for duplicata."""
    vid = video["video_id"]

    # Já visto?
    if vid in seen.get("videos", {}):
        return False

    # Já na fila?
    if any(item["video_id"] == vid for item in queue):
        return False

    queue.append(
        {
            "video_id": vid,
            "url": video["url"],
            "title": video["title"],
            "channel": video.get("channel", ""),
            "published": video.get("published", ""),
            "source": source,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Monitor RSS — Brasil e Mundo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista vídeos novos sem enfileirar",
    )
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Enfileira os últimos N vídeos (ignora seen)",
    )
    args = parser.parse_args()

    config = load_config()
    seen = load_seen()
    queue = load_queue()

    total_new = 0

    for channel in config.get("channels", []):
        rss_url = channel.get("rss_url")
        channel_name = channel.get("name", "?")
        if not rss_url:
            continue

        print(f"📡 Verificando feed de {channel_name}...")
        entries = fetch_feed(rss_url)
        print(f"   {len(entries)} entradas no feed")

        for i, entry in enumerate(entries):
            # Backfill: pegar os últimos N independente do seen
            if args.backfill > 0 and i >= args.backfill:
                break

            # Filtrar Shorts/lives
            if is_short_or_live(entry["title"], entry["url"]):
                print(f"   ⏭️  Ignorando (Short/Live): {entry['title'][:60]}")
                continue

            # Filtrar entrevistas (formato ANCAPSU "PETER ENTREVISTA: …")
            if is_interview(entry["title"]):
                print(f"   ⏭️  Ignorando (Entrevista): {entry['title'][:60]}")
                continue

            vid = entry["video_id"]

            if args.backfill > 0:
                # No backfill, ignora seen
                pass
            elif vid in seen.get("videos", {}):
                continue

            if args.dry_run:
                print(f"   🆕 [DRY-RUN] {entry['title'][:70]}")
                print(f"      URL: {entry['url']}")
                total_new += 1
                continue

            added = enqueue_video(queue, seen if args.backfill == 0 else {"videos": {}}, entry, source="monitor")
            if added:
                print(f"   ✅ Enfileirado: {entry['title'][:70]}")
                total_new += 1

    if not args.dry_run and total_new > 0:
        save_queue(queue)
        print(f"\n📋 {total_new} vídeo(s) adicionado(s) à fila ({QUEUE_PATH})")
    elif total_new == 0:
        print("   Nenhum vídeo novo encontrado.")
    else:
        print(f"\n📋 [DRY-RUN] {total_new} vídeo(s) seriam enfileirados")


if __name__ == "__main__":
    main()
