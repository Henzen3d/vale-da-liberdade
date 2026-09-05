#!/usr/bin/env python3
"""
B-Roll Fetcher & Cataloger — Pipeline Brasil e Mundo.

Busca e baixa clipes de vídeo curtos (b-roll de 2 a 5 segundos, sem áudio, 1080p)
utilizando as APIs públicas de Pexels e Pixabay com as chaves configuradas em .env.
Registra os clipes baixados no manifesto `references/youtube/broll/_index.json`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BROLL_DIR = PROJECT_ROOT / "references" / "youtube" / "broll"
BROLL_INDEX = BROLL_DIR / "_index.json"

# Carregar variáveis do .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Mapeamento de termos pt_BR -> termos de busca en_US para maior precisão em stock footage
TOPIC_TRANSLATIONS = {
    "trânsito": "traffic highway cars",
    "transito": "traffic highway cars",
    "carros": "cars road traffic",
    "impostos": "money tax counting cash",
    "imposto": "money tax counting cash",
    "ipva": "cars highway road",
    "economia": "stock market chart currency",
    "bolsa": "stock market trading chart",
    "dólar": "us dollar cash money",
    "dolar": "us dollar cash money",
    "dinheiro": "cash currency counting money",
    "justiça": "court gavel judge scales justice",
    "justica": "court gavel judge scales justice",
    "stf": "courthouse judge gavel",
    "tribunal": "courtroom judge gavel legal",
    "polícia": "police car emergency siren",
    "policia": "police car emergency siren",
    "saúde": "hospital doctor medical healthcare",
    "saude": "hospital doctor medical healthcare",
    "corrupção": "handcuffs prison interrogation dark office",
    "corrupcao": "handcuffs prison interrogation dark office",
    "tecnologia": "computer keyboard data server",
    "cidade": "city aerial buildings skyline",
}


def load_index() -> dict:
    if not BROLL_INDEX.is_file():
        return {"clips": []}
    try:
        return json.loads(BROLL_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"clips": []}


def save_index(data: dict) -> None:
    BROLL_DIR.mkdir(parents=True, exist_ok=True)
    BROLL_INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def probe_clip_duration_s(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(file_path)
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 3.0


def search_pexels_videos(query: str, max_items: int = 2) -> list[dict]:
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return []

    q_en = TOPIC_TRANSLATIONS.get(query.lower(), query)
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(q_en)}&per_page={max_items}&orientation=landscape"
    req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": UA})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = []
        for vid in data.get("videos", []):
            files = vid.get("video_files") or []
            # Preferência para 1080p ou 720p em formato MP4
            chosen = None
            for f in sorted(files, key=lambda x: x.get("width") or 0, reverse=True):
                if f.get("file_type") == "video/mp4" and (f.get("width") or 0) <= 1920:
                    chosen = f
                    break
            if not chosen and files:
                chosen = files[0]
            if chosen and chosen.get("link"):
                results.append({
                    "id": f"pexels-{vid.get('id')}",
                    "url": chosen["link"],
                    "width": chosen.get("width"),
                    "height": chosen.get("height"),
                    "provider": "pexels",
                })
        return results
    except Exception as exc:
        print(f"  ⚠️  Pexels video search falhou ({query}): {exc}")
        return []


def search_pixabay_videos(query: str, max_items: int = 2) -> list[dict]:
    api_key = os.environ.get("PIXABAY_API_KEY")
    if not api_key:
        return []

    q_en = TOPIC_TRANSLATIONS.get(query.lower(), query)
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={urllib.parse.quote(q_en)}&video_type=film&per_page={max_items}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = []
        for hit in data.get("hits", []):
            vids = hit.get("videos") or {}
            target = vids.get("large") or vids.get("medium") or vids.get("small")
            if target and target.get("url"):
                results.append({
                    "id": f"pixabay-{hit.get('id')}",
                    "url": target["url"],
                    "width": target.get("width"),
                    "height": target.get("height"),
                    "provider": "pixabay",
                })
        return results
    except Exception as exc:
        print(f"  ⚠️  Pixabay video search falhou ({query}): {exc}")
        return []


def download_and_normalize_broll(clip_info: dict, tag: str, max_duration_s: float = 3.5) -> Path | None:
    """Baixa e recorta clipe para o tamanho padrão de transição (1080p, mudo, ~3s)."""
    BROLL_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "", clip_info["id"])
    target_file = BROLL_DIR / f"broll-{slug}.mp4"
    raw_tmp = BROLL_DIR / f"tmp-{slug}.mp4"

    if target_file.is_file() and target_file.stat().st_size > 50000:
        return target_file

    try:
        req = urllib.request.Request(clip_info["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as resp, open(raw_tmp, "wb") as f:
            shutil.copyfileobj(resp, f)

        # Normalizar com ffmpeg: escalar para 1920x1080, sem áudio, recortar primeiros X segundos
        cmd = [
            "ffmpeg", "-y", "-i", str(raw_tmp),
            "-t", str(max_duration_s),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22",
            str(target_file)
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        raw_tmp.unlink(missing_ok=True)

        if target_file.is_file() and target_file.stat().st_size > 30000:
            dur = probe_clip_duration_s(target_file)
            index_data = load_index()
            existing = [c for c in index_data.get("clips", []) if c.get("file") == target_file.name]
            if not existing:
                index_data.setdefault("clips", []).append({
                    "id": f"broll-{slug}",
                    "file": target_file.name,
                    "tags": [tag.lower()],
                    "dur_s": round(dur, 2),
                    "provider": clip_info.get("provider", "stock"),
                })
                save_index(index_data)
            print(f"  🎬 B-roll pronto: {target_file.name} ({dur:.1f}s, tag='{tag}')")
            return target_file
    except Exception as exc:
        raw_tmp.unlink(missing_ok=True)
        print(f"  ⚠️  Falha ao baixar/normalizar b-roll {clip_info['id']}: {exc}")
    return None


def fetch_brolls_for_tags(tags: list[str], max_per_tag: int = 1) -> list[Path]:
    """Garante que existam clipes de b-roll para as tags fornecidas."""
    ready: list[Path] = []
    index_data = load_index()

    for tag in tags:
        clean_tag = tag.strip().lower()
        if not clean_tag:
            continue

        already_has = any(clean_tag in c.get("tags", []) for c in index_data.get("clips", []))
        if already_has:
            continue

        print(f"🔍 Buscando b-roll para tema '{clean_tag}'...")
        cands = search_pexels_videos(clean_tag, max_items=max_per_tag)
        if not cands:
            cands = search_pixabay_videos(clean_tag, max_items=max_per_tag)

        for c in cands[:max_per_tag]:
            p = download_and_normalize_broll(c, clean_tag)
            if p:
                ready.append(p)

    return ready


def main() -> None:
    ap = argparse.ArgumentParser(description="Baixa e cataloga clipes de b-roll")
    ap.add_argument("--tags", nargs="+", default=["transito", "economia", "justica"], help="Tags a baixar")
    args = ap.parse_args()

    print(f"🎬 Verificando b-rolls para tags: {args.tags}")
    out = fetch_brolls_for_tags(args.tags)
    print(f"✨ Concluído. {len(out)} novos clipes prontos.")


if __name__ == "__main__":
    main()
