#!/usr/bin/env python3
"""Mapeia roteiro + fontes → timeline.json (sem rede)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
EPS_DAILY = ROOT / "episodes"
EPS_BM = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_BM = ROOT / "output" / "brasil_e_mundo" / "audio"
OUT_ROOT = ROOT / "output" / "videos" / "faceless"

SELF_HOSTS = ("news.mob.tec.br",)
BLOCK_HOST_PARTS = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com")
QUADRO_RE = re.compile(r"^###\s+QUADRO:\s+(.+?)\s*$", re.M)
URL_RE = re.compile(r"\*\*URL\*\*:\s*\[.*?\]\((https?://[^)]+)\)")


@dataclass(frozen=True)
class Story:
    quadro: str
    titulo: str
    url: str
    veiculo: str = ""


@dataclass(frozen=True)
class FaceClip:
    start_ms: int
    end_ms: int
    url: str
    veiculo: str
    quadro: str
    action: str = "scroll"
    quote: str | None = None


def is_usable_url(url: str, *, self_flag: bool = False) -> bool:
    if self_flag or not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if any(host == h or host.endswith("." + h) for h in SELF_HOSTS):
        return False
    if any(part in host for part in BLOCK_HOST_PARTS):
        return False
    return url.startswith("http://") or url.startswith("https://")


def veiculo_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    host = host.removeprefix("www.").removeprefix("www1.")
    return host.split(":")[0]


def parse_raw_md(text: str) -> list[Story]:
    stories: list[Story] = []
    quadro = ""
    titulo = ""
    for line in text.splitlines():
        m = re.match(r"^###\s+QUADRO:\s+(.+?)\s*$", line)
        if m:
            quadro = m.group(1).strip()
            continue
        tm = re.match(r"^####\s+[•*]?\s*(.+)$", line)
        if tm:
            titulo = re.sub(r"^\[BREAKING\]\s*", "", tm.group(1)).strip()
            continue
        um = URL_RE.search(line)
        if um and quadro:
            url = um.group(1).strip()
            stories.append(Story(quadro=quadro, titulo=titulo, url=url, veiculo=veiculo_from_url(url)))
    return stories


def _join_text(blocks) -> str:
    if isinstance(blocks, str):
        return blocks.strip()
    parts: list[str] = []
    for b in blocks or []:
        if isinstance(b, dict):
            t = (b.get("texto") or b.get("text") or "").strip()
            if t:
                parts.append(t)
        elif isinstance(b, str) and b.strip():
            parts.append(b.strip())
    return " ".join(parts)


def _words(text: str) -> int:
    return max(1, len(text.split())) if text.strip() else 0


def _allocate(sections: list[tuple[str, str, str, str]], duration_ms: int) -> list[FaceClip]:
    """sections: (quadro, veiculo, url, text)"""
    usable = [(q, v, u, t) for q, v, u, t in sections if u]
    if not usable:
        return []
    weights = [_words(t) or 1 for *_, t in usable]
    wsum = sum(weights) or 1
    cursor = 0
    clips: list[FaceClip] = []
    for i, ((quadro, veiculo, url, _text), w) in enumerate(zip(usable, weights)):
        dur = int(round(duration_ms * (w / wsum)))
        if i == len(usable) - 1:
            dur = duration_ms - cursor
        dur = max(dur, 1)
        clips.append(
            FaceClip(
                start_ms=cursor,
                end_ms=cursor + dur,
                url=url,
                veiculo=veiculo,
                quadro=quadro,
                action="scroll",
            )
        )
        cursor += dur
    if clips:
        clips[-1] = FaceClip(**{**asdict(clips[-1]), "end_ms": duration_ms})
    return clips


def _pick_url_for_text(text: str, refs: list[Story], used: int) -> Story | None:
    if not refs:
        return None
    low = text.lower()
    for s in refs:
        name = (s.veiculo or "").strip()
        if name and name.lower() in low:
            return s
    return refs[used % len(refs)]


def build_daily_timeline(roteiro: dict, stories: list[Story], duration_ms: int) -> list[FaceClip]:
    usable = [s for s in stories if is_usable_url(s.url)]
    by_quadro: dict[str, list[Story]] = {}
    for s in usable:
        by_quadro.setdefault(s.quadro, []).append(s)

    sections: list[tuple[str, str, str, str]] = []
    fallback = usable[0] if usable else None

    def add_group(quadro: str, blocks) -> None:
        text = _join_text(blocks)
        if not text:
            return
        pool = by_quadro.get(quadro) or usable
        story = _pick_url_for_text(text, pool, len(sections)) if pool else fallback
        if story is None:
            return
        sections.append((quadro, story.veiculo or veiculo_from_url(story.url), story.url, text))

    add_group("INTRODUÇÃO EDITORIAL", roteiro.get("introducao"))
    grouped: dict[str, list] = {}
    for blk in roteiro.get("quadros") or []:
        q = (blk.get("quadro") or "GERAL").strip()
        grouped.setdefault(q, []).append(blk)
    for q, blks in grouped.items():
        add_group(q, blks)
    add_group("FECHAMENTO", roteiro.get("fechamento"))
    return _allocate(sections, duration_ms)


def merge_adjacent(clips: list[FaceClip]) -> list[FaceClip]:
    if not clips:
        return []
    out = [clips[0]]
    for c in clips[1:]:
        prev = out[-1]
        if c.url == prev.url and c.veiculo == prev.veiculo:
            out[-1] = FaceClip(
                start_ms=prev.start_ms,
                end_ms=c.end_ms,
                url=prev.url,
                veiculo=prev.veiculo,
                quadro=prev.quadro,
                action=prev.action,
                quote=prev.quote,
            )
        else:
            out.append(c)
    return out


def build_bm_timeline(especial: dict, duration_ms: int) -> list[FaceClip]:
    refs: list[Story] = []
    seen: set[str] = set()
    for r in especial.get("fonte_referencias") or []:
        url = (r.get("url") or "").strip()
        if not is_usable_url(url, self_flag=bool(r.get("self"))):
            continue
        if url in seen:
            continue
        seen.add(url)
        refs.append(Story(quadro="comentario", titulo="", url=url, veiculo=(r.get("veiculo") or veiculo_from_url(url))))
    if not refs:
        u = (especial.get("fonte_url") or "").strip()
        if is_usable_url(u):
            refs.append(
                Story(
                    quadro="comentario",
                    titulo="",
                    url=u,
                    veiculo=especial.get("fonte_veiculo") or veiculo_from_url(u),
                )
            )

    abertura = _join_text(especial.get("abertura"))
    corpo = _join_text(especial.get("desenvolvimento"))
    fecha = _join_text(especial.get("fechamento"))
    sections: list[tuple[str, str, str, str]] = []
    if abertura and refs:
        s = refs[0]
        sections.append(("abertura", s.veiculo, s.url, abertura))
    if corpo and refs:
        if len(refs) == 1:
            sections.append(("comentario", refs[0].veiculo, refs[0].url, corpo))
        else:
            # fatias iguais do desenvolvimento, uma por fonte (evita flicker)
            chunk_words = max(1, _words(corpo) // len(refs))
            for i, s in enumerate(refs):
                sections.append((f"comentario_{i+1}", s.veiculo, s.url, "x " * chunk_words))
    if fecha and refs:
        s = refs[-1]
        sections.append(("fechamento", s.veiculo, s.url, fecha))
    return merge_adjacent(_allocate(sections, duration_ms))


def ffprobe_ms(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return int(float(r.stdout.strip()) * 1000)
    except ValueError:
        return 0


def write_timeline(episode_id: str, clips: list[FaceClip], audio: Path, extra: dict | None = None) -> Path:
    dest_dir = OUT_ROOT / episode_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "episode_id": episode_id,
        "audio": str(audio),
        "total_duration_ms": clips[-1].end_ms if clips else 0,
        "clips": [asdict(c) for c in clips],
    }
    if extra:
        payload.update(extra)
    dest = dest_dir / "timeline.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def cmd_daily(date: str) -> Path:
    roteiro_path = EPS_DAILY / f"roteiro-{date}.json"
    raw_path = EPS_DAILY / f"raw-{date}.md"
    if not roteiro_path.exists():
        raise SystemExit(f"❌ falta {roteiro_path}")
    audio = ROOT / "public" / "audio" / f"{date}.mp3"
    if not audio.exists():
        audio = ROOT / "audio" / f"{date}-completo.wav"
    if not audio.exists():
        raise SystemExit(f"❌ áudio não encontrado para {date}")
    duration_ms = ffprobe_ms(audio)
    if duration_ms < 1000:
        raise SystemExit(f"❌ duração inválida: {audio}")
    stories = parse_raw_md(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else []
    roteiro = json.loads(roteiro_path.read_text(encoding="utf-8"))
    clips = build_daily_timeline(roteiro, stories, duration_ms)
    dest = write_timeline(date, clips, audio, {"kind": "daily"})
    print(f"✅ {dest}  {len(clips)} clips / {duration_ms/1000:.1f}s")
    return dest


def cmd_bm(video_id: str) -> Path:
    ep_path = EPS_BM / f"especial-{video_id}.json"
    if not ep_path.exists():
        raise SystemExit(f"❌ falta {ep_path}")
    cands = sorted(AUDIO_BM.glob(f"{video_id}_*.mp3"), reverse=True)
    if not cands:
        raise SystemExit(f"❌ áudio BM não encontrado para {video_id}")
    audio = cands[0]
    duration_ms = ffprobe_ms(audio)
    if duration_ms < 1000:
        raise SystemExit(f"❌ duração inválida: {audio}")
    especial = json.loads(ep_path.read_text(encoding="utf-8"))
    clips = build_bm_timeline(especial, duration_ms)
    dest = write_timeline(
        video_id,
        clips,
        audio,
        {"kind": "bm", "titulo": especial.get("titulo") or video_id},
    )
    print(f"✅ {dest}  {len(clips)} clips / {duration_ms/1000:.1f}s")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Timeline faceless (sites das fontes)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="episódio diário YYYY-MM-DD")
    g.add_argument("--video-id", help="id do especial BM")
    args = ap.parse_args()
    if args.date:
        cmd_daily(args.date)
    else:
        cmd_bm(args.video_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
