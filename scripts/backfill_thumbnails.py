#!/usr/bin/env python3
"""Backfill: gera thumbnails dos especiais sem cover_url, usando a data do áudio."""
import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/osmar/web-jornal-vale-da-liberdade")
sys.path.insert(0, str(ROOT / "scripts"))

from thumbnail_generator import generate_thumbnail_safe  # noqa: E402

EPS_DIR = ROOT / "output/brasil_e_mundo/episodes"
AUDIO_DIR = ROOT / "output/brasil_e_mundo/audio"

# Especiais sem thumbnail no catálogo atual
eps = json.load(open(ROOT / "public/data/episodes.json"))
lst = eps.get("episodes", eps) if isinstance(eps, dict) else eps
faltando = [e for e in lst if e.get("type") == "especial" and not e.get("cover_url")]

print(f"{len(faltando)} especiais sem thumbnail")
ok = 0
falhas = []
for e in faltando:
    vid = str(e.get("id", "")).replace("especial-", "")
    # data da fonte de verdade: nome do áudio
    date_str = None
    mp3s = sorted(AUDIO_DIR.glob(f"{vid}_*.mp3"))
    if mp3s:
        m = re.search(r"_(\d{4}-\d{2}-\d{2})\.mp3$", mp3s[0].name)
        if m:
            date_str = m.group(1)
    if not date_str:
        date_str = str(e.get("date") or "")

    # título/resumo do JSON do especial
    jp = EPS_DIR / f"especial-{vid}.json"
    h, s = e.get("title") or vid, ""
    d = {}
    if jp.exists():
        d = json.loads(jp.read_text(encoding="utf-8"))
        h = d.get("titulo") or d.get("title") or h
        s = d.get("resumo") or d.get("summary") or ""
    if not s:
        # monta resumo das seções
        partes = []
        for sec in ("abertura", "desenvolvimento", "fechamento"):
            for item in d.get(sec, []):
                partes.append(item.get("texto", ""))
        s = " ".join(partes)[:600]

    try:
        thumb = generate_thumbnail_safe(
            date=date_str,
            episode_id=f"bm_{vid}",
            headline=str(h),
            summary=str(s)[:600],
        )
        if thumb.get("path"):
            ok += 1
            print(f"  OK {vid} ({date_str}) [{thumb.get('image_model_used')}]")
        else:
            falhas.append((vid, str(thumb.get("error", "?"))[:120]))
            print(f"  FALHA {vid}: {thumb.get('error', '?')[:120]}")
    except Exception as exc:
        falhas.append((vid, str(exc)[:120]))
        print(f"  ERRO {vid}: {exc}")

print(f"\nOK: {ok} | falhas: {len(falhas)}")
for f in falhas:
    print(f"  - {f[0]}: {f[1]}")
