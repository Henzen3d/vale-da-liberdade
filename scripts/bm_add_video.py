#!/usr/bin/env python3
"""
Entrada manual de vídeo — Pipeline Brasil e Mundo.

Empilha qualquer URL de vídeo do YouTube na mesma fila usada
pelo bm_monitor.py. Aceita vídeos de qualquer canal.

Uso:
    python scripts/bm_add_video.py --url "https://youtube.com/watch?v=XXXXX"
    python scripts/bm_add_video.py --url "https://youtu.be/XXXXX"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PIPELINE_DIR = PROJECT_ROOT / "pipelines" / "brasil_e_mundo"
QUEUE_PATH = PIPELINE_DIR / "queue.json"
SEEN_PATH = PIPELINE_DIR / "seen_videos.json"


def extract_video_id(url: str) -> str | None:
    """Extrai video_id de vários formatos de URL do YouTube."""
    patterns = [
        r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)"
        r"([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # ID puro
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def load_queue() -> list[dict]:
    if QUEUE_PATH.exists():
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data.get("queue", [])
    return []


def save_queue(queue: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(
        json.dumps({"queue": queue}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    return {"videos": {}}


def main():
    parser = argparse.ArgumentParser(
        description="Adicionar vídeo manualmente à fila Brasil e Mundo"
    )
    parser.add_argument("--url", required=True, help="URL do vídeo do YouTube")
    parser.add_argument("--title", default="", help="Título (opcional, preenchido depois)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Força adição mesmo se já processado",
    )
    args = parser.parse_args()

    video_id = extract_video_id(args.url)
    if not video_id:
        print(f"❌ Não foi possível extrair video_id de: {args.url}")
        sys.exit(1)

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"

    # Verificar se já está na fila ou já foi processado
    queue = load_queue()
    seen = load_seen()

    if not args.force:
        if video_id in seen.get("videos", {}):
            print(f"⚠️  Vídeo {video_id} já foi processado. Use --force para reprocessar.")
            sys.exit(0)
        if any(item["video_id"] == video_id for item in queue):
            print(f"⚠️  Vídeo {video_id} já está na fila.")
            sys.exit(0)

    # Remover entrada anterior se --force
    if args.force:
        queue = [item for item in queue if item["video_id"] != video_id]

    queue.append(
        {
            "video_id": video_id,
            "url": canonical_url,
            "title": args.title or f"(manual) {video_id}",
            "channel": "(manual)",
            "published": "",
            "source": "manual",
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
    )

    save_queue(queue)
    print(f"✅ Vídeo {video_id} adicionado à fila")
    print(f"   URL: {canonical_url}")
    print(f"   Fila: {QUEUE_PATH} ({len(queue)} item(s))")
    print(f"\n   Para processar: python scripts/bm_pipeline.py process-queue")


if __name__ == "__main__":
    main()
