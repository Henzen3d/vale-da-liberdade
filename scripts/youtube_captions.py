#!/usr/bin/env python3
"""Legendas SRT (pt com tempo + en) e localização EN no YouTube.

Whisper no MP3 do episódio → SRT pt-BR. Gemini traduz cues/título/descrição.
Não bloqueia o upload se falhar.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"
AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"
CAPTIONS_DIR = ROOT / "output" / "brasil_e_mundo" / "captions"
STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"

TITLE_MAX = 100


@dataclass
class Cue:
    start: float
    end: float
    text: str


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def cues_to_srt(cues: list[Cue]) -> str:
    blocks: list[str] = []
    for i, c in enumerate(cues, 1):
        text = re.sub(r"\s+", " ", (c.text or "").strip())
        if not text:
            continue
        end = c.end if c.end > c.start else c.start + 0.4
        blocks.append(
            f"{i}\n{srt_timestamp(c.start)} --> {srt_timestamp(end)}\n{text}\n"
        )
    return "\n".join(blocks).rstrip() + ("\n" if blocks else "")


def parse_srt(srt: str) -> list[Cue]:
    cues: list[Cue] = []
    chunks = re.split(r"\n\s*\n", srt.strip())
    ts_re = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    )

    def to_s(h, m, s, ms) -> float:
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    for chunk in chunks:
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        m = ts_re.search("\n".join(lines[:3]))
        if not m:
            continue
        text_lines = []
        seen_ts = False
        for ln in lines:
            if ts_re.search(ln):
                seen_ts = True
                continue
            if not seen_ts and ln.strip().isdigit():
                continue
            text_lines.append(ln.strip())
        text = " ".join(text_lines).strip()
        if text:
            cues.append(
                Cue(to_s(*m.group(1, 2, 3, 4)), to_s(*m.group(5, 6, 7, 8)), text)
            )
    return cues


def merge_short_cues(cues: list[Cue], min_s: float = 1.4, max_s: float = 8.0) -> list[Cue]:
    out: list[Cue] = []
    for c in cues:
        text = re.sub(r"\s+", " ", (c.text or "").strip())
        if not text:
            continue
        if out:
            prev = out[-1]
            gap = c.start - prev.end
            span = c.end - prev.start
            prev_dur = prev.end - prev.start
            cur_dur = c.end - c.start
            if (prev_dur < min_s or cur_dur < min_s) and gap < 0.45 and span <= max_s:
                out[-1] = Cue(prev.start, max(prev.end, c.end), f"{prev.text} {text}")
                continue
        out.append(Cue(c.start, c.end, text))
    return out


def clamp_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    if len(t) <= TITLE_MAX:
        return t
    cut = t[: TITLE_MAX - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut or t[:TITLE_MAX]).strip()


def parse_en_cues_json(raw: str) -> dict[int, str]:
    text = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    arr = json.loads(text)
    out: dict[int, str] = {}
    if isinstance(arr, dict) and "cues" in arr:
        arr = arr["cues"]
    if not isinstance(arr, list):
        raise ValueError("JSON de tradução não é lista")
    for item in arr:
        if not isinstance(item, dict):
            continue
        i = item.get("i") or item.get("n") or item.get("index")
        en = item.get("en") or item.get("text") or item.get("translation")
        if i is None or not en:
            continue
        out[int(i)] = re.sub(r"\s+", " ", str(en)).strip()
    return out


def transcribe_cues(audio_path: Path) -> list[Cue]:
    from faster_whisper import WhisperModel

    print(f"  🎙️  Whisper SRT ← {audio_path.name}")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        language="pt",
        vad_filter=True,
        beam_size=1,
    )
    cues = [
        Cue(float(seg.start), float(seg.end), (seg.text or "").strip())
        for seg in segments
        if (seg.text or "").strip()
    ]
    return merge_short_cues(cues)


def _gemini_client():
    from gemini_client import GeminiClient, GeminiMultiClient

    keys: list[str] = []
    seen: set[str] = set()
    for name, val in os.environ.items():
        if name == "GEMINI_API_KEY" or (
            name.startswith("GEMINI_API_KEY_") and name.split("_")[-1].isdigit()
        ):
            v = (val or "").strip()
            if v and "***" not in v and v not in seen:
                seen.add(v)
                keys.append(v)
    if not keys:
        raise RuntimeError("sem GEMINI_API_KEY")
    return GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])


def _gemini_text(prompt: str) -> str:
    client = _gemini_client()
    last = None
    for model in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview", "gemma-4-31b-it"):
        try:
            resp = client.generate_content(model, prompt)
            text = (getattr(resp, "text", None) or "").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise RuntimeError(f"Gemini falhou na tradução: {last}")


def translate_cues_en(cues: list[Cue]) -> list[Cue]:
    if not cues:
        return []
    out = list(cues)
    batch = 35
    for start in range(0, len(cues), batch):
        chunk = cues[start : start + batch]
        payload = [{"i": start + i + 1, "pt": c.text} for i, c in enumerate(chunk)]
        prompt = (
            "Translate each Portuguese YouTube caption to natural English. "
            "Keep meaning, tone (direct, journalistic, Brazilian libertarian commentary). "
            "Do not add quotes. Do not merge or split items. URLs stay unchanged.\n"
            "Reply ONLY with a JSON array of {\"i\": n, \"en\": \"...\"}.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        mapped = parse_en_cues_json(_gemini_text(prompt))
        for i, c in enumerate(chunk):
            en = mapped.get(start + i + 1)
            if en:
                out[start + i] = Cue(c.start, c.end, en)
    return out


def translate_title_desc_en(title: str, description: str) -> tuple[str, str]:
    prompt = (
        "Translate this YouTube video title and description from Brazilian Portuguese "
        "to natural English. Keep all URLs, hashtags that are brand names, and line breaks. "
        "Title max 100 characters. Do not mention YouTube or ANCAPSU.\n"
        "Reply ONLY JSON: {\"title\": \"...\", \"description\": \"...\"}\n\n"
        + json.dumps({"title": title, "description": description}, ensure_ascii=False)
    )
    raw = _gemini_text(prompt)
    m = re.search(r"\{[\s\S]*\}", raw)
    data = json.loads(m.group(0) if m else raw)
    en_title = clamp_title(str(data.get("title") or title))
    en_desc = str(data.get("description") or description).strip()
    return en_title, en_desc


def resolve_audio(video_id: str) -> Path | None:
    files = sorted(AUDIO_DIR.glob(f"{video_id}_*.mp3"))
    return files[-1] if files else None


def write_srts(video_id: str, pt: list[Cue], en: list[Cue]) -> tuple[Path, Path]:
    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    pt_path = CAPTIONS_DIR / f"{video_id}.pt.srt"
    en_path = CAPTIONS_DIR / f"{video_id}.en.srt"
    pt_path.write_text(cues_to_srt(pt), encoding="utf-8")
    en_path.write_text(cues_to_srt(en), encoding="utf-8")
    return pt_path, en_path


def attach_captions_and_en(
    video_id: str,
    yt_id: str,
    audio: Path | None,
    title_pt: str,
    desc_pt: str,
) -> dict:
    """Gera SRT pt/en, sobe legendas e localização EN. Falha isolada."""
    import youtube_uploader as ytu

    audio = audio or resolve_audio(video_id)
    if not audio or not audio.is_file():
        raise FileNotFoundError(f"MP3 ausente para SRT: {video_id}")

    pt_cues = transcribe_cues(audio)
    if len(pt_cues) < 3:
        raise RuntimeError(f"Whisper gerou só {len(pt_cues)} cues")
    en_cues = translate_cues_en(pt_cues)
    pt_path, en_path = write_srts(video_id, pt_cues, en_cues)
    print(f"  ✅ SRT pt {pt_path.name} ({len(pt_cues)} cues)")
    print(f"  ✅ SRT en {en_path.name}")

    ytu.upload_caption(yt_id, str(pt_path), language="pt-BR", name="Português")
    print("  ✅ caption pt-BR")
    ytu.upload_caption(yt_id, str(en_path), language="en", name="English")
    print("  ✅ caption en")

    en_title, en_desc = translate_title_desc_en(title_pt, desc_pt)
    ytu.set_english_localization(yt_id, en_title, en_desc)
    print(f"  ✅ localization en: {en_title[:70]}")
    return {
        "pt_srt": str(pt_path),
        "en_srt": str(en_path),
        "en_title": en_title,
        "cues": len(pt_cues),
    }


def _load_published(video_id: str) -> str:
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    info = (data.get("videos") or {}).get(video_id) or {}
    yt = info.get("yt_id") or ""
    if not yt:
        raise SystemExit(f"sem yt_id publicado para {video_id}")
    return yt


def _title_desc_from_episode(video_id: str) -> tuple[str, str]:
    from bm_mockup_video import build_metadata, resolve_audio as ra

    ep_path = EPS_DIR / f"especial-{video_id}.json"
    ep = json.loads(ep_path.read_text(encoding="utf-8")) if ep_path.exists() else {}
    audio = ra(video_id) or resolve_audio(video_id)
    if not audio:
        raise SystemExit("sem áudio")
    title, desc, _tags = build_metadata(video_id, ep, audio)
    return title, desc


def main() -> int:
    ap = argparse.ArgumentParser(description="SRT pt/en + localização EN no YouTube")
    ap.add_argument("--video-id", required=True, help="ID do especial BM")
    ap.add_argument("--yt-id", help="ID do vídeo no YouTube (senão lê videos_published.json)")
    args = ap.parse_args()
    yt_id = args.yt_id or _load_published(args.video_id)
    title, desc = _title_desc_from_episode(args.video_id)
    attach_captions_and_en(args.video_id, yt_id, resolve_audio(args.video_id), title, desc)
    print(f"https://youtu.be/{yt_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
