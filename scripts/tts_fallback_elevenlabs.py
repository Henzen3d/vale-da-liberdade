#!/usr/bin/env python3
"""
Fallback TTS — ElevenLabs multilingual (pt-BR) com 2 vozes.

Cadeia preferida (cmd_audio):
  1) Gemini multi
  2) ElevenLabs (se ELEVENLABS_API_KEY)  ← este script
  3) MOSS-TTS-Nano (clone)
  4) Edge + FX Ricardo

Uso:
  python3 scripts/tts_fallback_elevenlabs.py --date 2026-07-22
  python3 scripts/tts_fallback_elevenlabs.py --text "Olá" --speaker Peter --out /tmp/p.mp3
  python3 scripts/tts_fallback_elevenlabs.py --list-voices

Env:
  ELEVENLABS_API_KEY ou XI_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CFG = ROOT / "config" / "elevenlabs_tts.yaml"


def load_dotenv_files() -> None:
    for p in (ROOT / ".env", Path.home() / ".hermes" / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def load_cfg(path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "enabled": True,
        "model_id": "eleven_multilingual_v2",
        "voices": {
            "Peter": {
                "voice_id": "TX3LPaxmHKxFdv7VOQHJ",
                "stability": 0.45,
                "similarity_boost": 0.75,
                "style": 0.35,
                "use_speaker_boost": True,
            },
            "Ricardo": {
                "voice_id": "bIHbv24MWmeRgasZH58o",
                "stability": 0.55,
                "similarity_boost": 0.75,
                "style": 0.20,
                "use_speaker_boost": True,
            },
        },
        "api_base": "https://api.elevenlabs.io/v1",
        "output_format": "mp3_44100_128",
        "min_words": 3,
        "min_chunk_bytes": 8000,
        "min_final_bytes": 1_000_000,
        "max_chars_per_chunk": 400,
        "timeout_s": 90,
    }
    if not path.exists():
        return defaults
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    cfg = defaults.copy()
    for k, v in data.items():
        if k == "voices" and isinstance(v, dict):
            merged = dict(defaults["voices"])
            for sp, opts in v.items():
                base = dict(merged.get(sp) or {})
                if isinstance(opts, dict):
                    base.update(opts)
                merged[sp] = base
            cfg["voices"] = merged
        else:
            cfg[k] = v
    return cfg


def api_key() -> str:
    load_dotenv_files()
    k = (os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY") or "").strip()
    if not k or "***" in k:
        raise RuntimeError(
            "ELEVENLABS_API_KEY ausente. Coloque no .env do projeto ou ~/.hermes/.env"
        )
    return k


def tts_request(
    *,
    text: str,
    voice_id: str,
    model_id: str,
    api_base: str,
    output_format: str,
    voice_settings: dict[str, Any],
    timeout_s: int,
    out_path: Path,
) -> Path:
    key = api_key()
    url = f"{api_base.rstrip('/')}/text-to-speech/{voice_id}?output_format={output_format}"
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": float(voice_settings.get("stability", 0.5)),
            "similarity_boost": float(voice_settings.get("similarity_boost", 0.75)),
            "style": float(voice_settings.get("style", 0.0)),
            "use_speaker_boost": bool(voice_settings.get("use_speaker_boost", True)),
        },
    }
    # language hint helps pt-BR on multilingual models
    payload["language_code"] = "pt"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {body}") from e
    if len(audio) < 1000:
        raise RuntimeError(f"Áudio ElevenLabs muito curto ({len(audio)} bytes)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio)
    return out_path


def parse_tts_lines(path: Path, min_words: int = 3) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        speaker, text = "Ricardo", line
        m = re.match(r"^(Peter|Ricardo)\s*:\s*(.*)$", line, re.I)
        if m:
            speaker = "Peter" if m.group(1).lower() == "peter" else "Ricardo"
            text = m.group(2).strip()
        text = re.sub(r"\[PAUSA(?:_CURTA)?\]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text.split()) < min_words:
            continue
        turns.append((speaker, text))
    return turns


def split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    buf = ""
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if not s:
            continue
        if len(buf) + len(s) + 1 <= max_chars:
            buf = f"{buf} {s}".strip()
        else:
            if buf:
                parts.append(buf)
            if len(s) <= max_chars:
                buf = s
            else:
                for i in range(0, len(s), max_chars):
                    c = s[i : i + max_chars].strip()
                    if c:
                        parts.append(c)
                buf = ""
    if buf:
        parts.append(buf)
    return parts or [text[:max_chars]]


def concat_mp3s(paths: list[Path], out_mp3: Path) -> None:
    lst = out_mp3.with_suffix(".filelist.txt")
    lst.write_text("\n".join(f"file '{p.resolve()}'" for p in paths) + "\n", encoding="utf-8")
    tmp = out_mp3.with_suffix(".concat.mp3")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(tmp)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat: {proc.stderr.decode()[:250]}")
    proc2 = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(tmp),
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "192k", str(out_mp3),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    tmp.unlink(missing_ok=True)
    if proc2.returncode != 0 or not out_mp3.exists():
        raise RuntimeError(f"ffmpeg loudnorm: {proc2.stderr.decode()[:250]}")


def run_episode(date: str, cfg: dict, limit: int | None = None) -> Path:
    if not cfg.get("enabled", True):
        raise RuntimeError("ElevenLabs fallback desabilitado")
    # fail fast on missing key
    api_key()

    episodes = ROOT / "episodes"
    audio_dir = ROOT / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts_txt = episodes / f"{date}-tts.txt"
    md = episodes / f"{date}.md"
    if not tts_txt.exists() and md.exists():
        hermes = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
        if hermes.exists():
            subprocess.run(
                [str(hermes), str(ROOT / "scripts/tts_preprocessor.py"),
                 "--input", str(md), "--output", str(tts_txt)],
                check=False,
            )
    if not tts_txt.exists():
        raise FileNotFoundError(tts_txt)

    turns = parse_tts_lines(tts_txt, min_words=int(cfg.get("min_words", 3)))
    if limit:
        turns = turns[:limit]
    if not turns:
        raise RuntimeError("Nenhuma fala útil")

    voices = cfg["voices"]
    model_id = cfg.get("model_id") or "eleven_multilingual_v2"
    api_base = cfg.get("api_base") or "https://api.elevenlabs.io/v1"
    out_fmt = cfg.get("output_format") or "mp3_44100_128"
    max_chars = int(cfg.get("max_chars_per_chunk", 400))
    min_bytes = int(cfg.get("min_chunk_bytes", 8000))
    timeout_s = int(cfg.get("timeout_s", 90))

    kept: list[Path] = []
    idx = 0
    for speaker, text in turns:
        vopts = voices.get(speaker) or voices.get("Ricardo") or {}
        voice_id = vopts.get("voice_id")
        if not voice_id:
            raise RuntimeError(f"voice_id ausente para {speaker}")
        for part in split_long_text(text, max_chars):
            idx += 1
            mp3 = audio_dir / f"{date}-el-{speaker.lower()}-{idx:03d}.mp3"
            print(f"[eleven] {idx} {speaker}/{voice_id[:6]}…: {part[:70]}")
            t0 = time.time()
            try:
                tts_request(
                    text=part,
                    voice_id=voice_id,
                    model_id=model_id,
                    api_base=api_base,
                    output_format=out_fmt,
                    voice_settings=vopts,
                    timeout_s=timeout_s,
                    out_path=mp3,
                )
                size = mp3.stat().st_size
                if size < min_bytes:
                    print(f"  ⚠ pequeno ({size}B) skip")
                    continue
                kept.append(mp3)
                print(f"  ✓ {size}B · {time.time()-t0:.1f}s")
            except Exception as exc:
                print(f"  ✗ {exc}")

    if len(kept) < 3 and not limit:
        raise RuntimeError(f"Poucos chunks ElevenLabs ({len(kept)})")
    if not kept:
        raise RuntimeError("Nenhum chunk ElevenLabs")

    named = audio_dir / f"{date}-vale-da-liberdade.mp3"
    final = audio_dir / f"{date}.mp3"
    print(f"[eleven] Concat {len(kept)} → {named}")
    concat_mp3s(kept, named)
    nbytes = named.stat().st_size
    if nbytes < int(cfg.get("min_final_bytes", 1_000_000)) and not limit:
        raise RuntimeError(f"MP3 final pequeno: {nbytes}B")
    final.write_bytes(named.read_bytes())
    print(f"✅ ElevenLabs OK: {final} ({nbytes} bytes)")
    return final


def list_ptbr_voices() -> None:
    """Lista vozes do catálogo público com locale pt-BR verificado."""
    url = "https://api.elevenlabs.io/v1/voices"
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    print("Vozes premade com preview pt-BR (ElevenLabs):\n")
    for v in data.get("voices") or []:
        for item in v.get("verified_languages") or []:
            if not isinstance(item, dict):
                continue
            if item.get("locale") == "pt-BR" or (
                item.get("language") == "pt" and "BR" in str(item.get("locale") or "BR")
            ):
                labels = v.get("labels") or {}
                print(
                    f"- {v.get('name')}\n"
                    f"  id: {v.get('voice_id')}\n"
                    f"  gender: {labels.get('gender')} · accent: {labels.get('accent')}\n"
                    f"  pt-BR preview: {item.get('preview_url')}\n"
                )
                break


def main() -> int:
    ap = argparse.ArgumentParser(description="Fallback ElevenLabs pt-BR 2 vozes")
    ap.add_argument("--date")
    ap.add_argument("--config", default=str(DEFAULT_CFG))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--text")
    ap.add_argument("--speaker", default="Peter", choices=["Peter", "Ricardo"])
    ap.add_argument("--out", default="/tmp/eleven_smoke.mp3")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()
    cfg = load_cfg(Path(args.config))

    if args.list_voices:
        list_ptbr_voices()
        return 0

    if args.text:
        vopts = cfg["voices"][args.speaker]
        tts_request(
            text=args.text,
            voice_id=vopts["voice_id"],
            model_id=cfg.get("model_id") or "eleven_multilingual_v2",
            api_base=cfg.get("api_base") or "https://api.elevenlabs.io/v1",
            output_format=cfg.get("output_format") or "mp3_44100_128",
            voice_settings=vopts,
            timeout_s=int(cfg.get("timeout_s", 90)),
            out_path=Path(args.out),
        )
        print(f"✅ {args.out}")
        return 0

    if not args.date:
        ap.error("--date, --text ou --list-voices")
    try:
        run_episode(args.date, cfg, limit=args.limit or None)
        return 0
    except Exception as exc:
        print(f"❌ ElevenLabs fallback falhou: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
