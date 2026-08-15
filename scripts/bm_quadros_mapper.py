#!/usr/bin/env python3
"""Mapeia especial-{id}.json → quadros-{id}.json (duração pelo áudio real)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
PROTO = ROOT / "references" / "youtube" / "prototype"


def _ffprobe_ms(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return int(float(r.stdout.strip()) * 1000)
    except ValueError:
        return 0


def _join_text(blocks) -> str:
    if isinstance(blocks, str):
        return blocks.strip()
    parts = []
    for b in blocks or []:
        if isinstance(b, dict):
            t = (b.get("texto") or b.get("text") or "").strip()
            if t:
                parts.append(t)
        elif isinstance(b, str) and b.strip():
            parts.append(b.strip())
    return " ".join(parts)


def _words(text: str) -> int:
    return max(1, len(text.split()))


def map_episode(video_id: str, audio: Path | None = None, out: Path | None = None) -> Path:
    ep_path = EPS_DIR / f"especial-{video_id}.json"
    if not ep_path.exists():
        raise SystemExit(f"❌ especial não encontrado: {ep_path}")
    data = json.loads(ep_path.read_text(encoding="utf-8"))
    if audio is None:
        cands = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"), reverse=True)
        audio = cands[0] if cands else None
    if not audio or not Path(audio).exists():
        raise SystemExit(f"❌ áudio não encontrado para {video_id}")
    audio = Path(audio)
    total_ms = _ffprobe_ms(audio)
    if total_ms < 1000:
        raise SystemExit(f"❌ duração inválida: {audio}")

    abertura = _join_text(data.get("abertura"))
    fechamento = _join_text(data.get("fechamento"))
    dev_blocks = data.get("desenvolvimento") or []
    if isinstance(dev_blocks, str):
        dev_blocks = [{"texto": dev_blocks}]
    sections = [("abertura", "Abertura", "abertura", abertura)]
    for i, blk in enumerate(dev_blocks, 1):
        txt = _join_text([blk] if isinstance(blk, dict) else blk)
        if txt:
            sections.append(("brasil-e-mundo", "Comentário", "comentario_materia", txt))
    if fechamento:
        sections.append(("fechamento", "Fechamento", "fechamento", fechamento))

    weights = [_words(s[3]) for s in sections]
    wsum = sum(weights) or 1
    cursor = 0
    quadros = []
    fonte = {
        "fonte_canal": data.get("fonte_canal") or "ANCAPSU",
        "fonte_veiculo": data.get("fonte_veiculo") or "",
        "fonte_url": data.get("fonte_url") or "",
    }
    refs = data.get("fonte_referencias") or []
    primary_url = fonte["fonte_url"] or (refs[0].get("url") if refs else "")
    primary_name = fonte["fonte_veiculo"] or (refs[0].get("veiculo") if refs else "")

    for i, ((section, label, typ, text), w) in enumerate(zip(sections, weights), 1):
        dur = int(round(total_ms * (w / wsum)))
        if i == len(sections):
            dur = total_ms - cursor
        qid = f"q{i:02d}"
        q = {
            "id": qid,
            "order": i,
            "section": section,
            "chapter_label": label,
            "start_ms": cursor,
            "end_ms": cursor + dur,
            "duration_ms": dur,
            "script_text": text,
            "type": typ,
            "avatar_loop": "assets/peter_loop.mp4",
            "audio_narracao": str(audio.relative_to(ROOT)) if str(audio).startswith(str(ROOT)) else str(audio),
            "fonte_nome": primary_name,
            "fonte_url": primary_url,
        }
        quadros.append(q)
        cursor += dur

    payload = {
        "episode_id": f"especial-{video_id}",
        "titulo": data.get("titulo") or video_id,
        "total_duration_ms": total_ms,
        "total_palavras": sum(weights),
        "tags": data.get("tags") or [],
        "fonte_principal": fonte,
        "fonte_referencias": refs,
        "quadros": quadros,
    }
    dest = out or (PROTO / f"quadros-{video_id}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {dest.name}: {len(quadros)} quadros / {total_ms/1000:.1f}s")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Mapper especial JSON → quadros.json")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    vid = args.video_id
    if vid.startswith("-"):
        print("use --video-id-env para IDs que começam com -", file=sys.stderr)
    map_episode(vid, Path(args.audio) if args.audio else None, Path(args.out) if args.out else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
