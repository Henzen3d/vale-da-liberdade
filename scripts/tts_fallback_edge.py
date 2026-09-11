#!/usr/bin/env python3
"""Fallback Edge TTS (HERMES_PY): 1 processo, Semaphore(3), vozes distintas.

Peter = pt-BR-AntonioNeural
Ricardo = pt-BR-FranciscaNeural
Sem FX librosa/pyworld nesta onda. Concat + cadeia FFmpeg v2 de generate_gemini_tts_multi.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

HERMES_PY = Path(os.environ.get("HERMES_PY", "/home/osmar/.hermes/hermes-agent/venv/bin/python3"))
EDGE_VOICES = {
    "peter": os.environ.get("EDGE_TTS_VOICE_PETER", "pt-BR-AntonioNeural"),
    "ricardo": os.environ.get("EDGE_TTS_VOICE_RICARDO", "pt-BR-FranciscaNeural"),
}
MIN_CHUNK_BYTES = int(os.environ.get("MIN_CHUNK_BYTES", "15000"))
MIN_FINAL_BYTES = int(os.environ.get("MIN_FINAL_BYTES", "1000000"))
EDGE_CONCURRENCY = int(os.environ.get("VALE_EDGE_CONCURRENCY", "3"))
SHM_CAP_BYTES = 512 * 1024 * 1024
SWAP_CAP_BYTES = int(2.5 * 1024 * 1024 * 1024)

_LINE_PETER = re.compile(r"^[Pp]eter:\s*(.*)$")
_LINE_RICARDO = re.compile(r"^[Rr]icardo:\s*(.*)$")
_PAUSE = re.compile(r"\[PAUSA(?:_CURTA)?\]")


def _swap_used() -> int:
    total = free = 0
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("SwapTotal:"):
                total = int(line.split()[1]) * 1024
            elif line.startswith("SwapFree:"):
                free = int(line.split()[1]) * 1024
        return max(0, total - free)
    except Exception:
        return 0


def _shm_free() -> int:
    try:
        usage = shutil.disk_usage("/dev/shm")
        return int(usage.free)
    except Exception:
        return 0


def pick_tmpdir(date: str) -> Path:
    if _shm_free() > SHM_CAP_BYTES and _swap_used() < SWAP_CAP_BYTES:
        p = Path("/dev/shm") / f"valeliberdade-edge-{date}"
    else:
        p = PROJECT_ROOT / "audio" / "tmp" / date
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_tts_lines(text: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        speaker = "ricardo"
        m = _LINE_PETER.match(line)
        if m:
            speaker = "peter"
            transcript = m.group(1)
        else:
            m = _LINE_RICARDO.match(line)
            if m:
                speaker = "ricardo"
                transcript = m.group(1)
            else:
                transcript = line
        transcript = _PAUSE.sub(" ", transcript).strip()
        if len(transcript.split()) < 3:
            continue
        chunks.append((speaker, transcript))
    return chunks


async def _synth_one(sem: asyncio.Semaphore, text: str, voice: str, dest: Path) -> bool:
    import edge_tts

    async with sem:
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(dest))
        except Exception as exc:
            print(f"AVISO: falha edge_tts {dest.name}: {exc}", file=sys.stderr)
            return False
    return dest.exists() and dest.stat().st_size >= MIN_CHUNK_BYTES


async def synth_all(chunks: list[tuple[str, str]], tmp: Path) -> list[Path]:
    try:
        import uvloop  # type: ignore

        uvloop.install()
    except ImportError:
        pass
    sem = asyncio.Semaphore(max(1, min(EDGE_CONCURRENCY, 3)))
    tasks = []
    dests: list[Path] = []
    for i, (speaker, text) in enumerate(chunks, 1):
        dest = tmp / f"{speaker}-{i:03d}.mp3"
        dests.append(dest)
        voice = EDGE_VOICES[speaker]
        tasks.append(_synth_one(sem, text, voice, dest))
    ok = await asyncio.gather(*tasks)
    kept = [d for d, good in zip(dests, ok) if good]
    return kept


def concat_and_normalize(chunks: list[Path], final_mp3: Path) -> None:
    from generate_gemini_tts_multi import run_ffmpeg_chain_2pass

    concat_wav = Path(tempfile.mkstemp(suffix="-edge-concat.wav")[1])
    filelist = Path(tempfile.mkstemp(suffix="-edge-list.txt")[1])
    try:
        filelist.write_text("".join(f"file '{p}'\n" for p in chunks), encoding="utf-8")
        import subprocess

        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist), "-ar", "44100", "-ac", "1", str(concat_wav)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg concat falhou: {(r.stderr or '')[-400:]}")
        run_ffmpeg_chain_2pass(concat_wav, final_mp3, tempo=1.0, peter_eq=False)
    finally:
        concat_wav.unlink(missing_ok=True)
        filelist.unlink(missing_ok=True)


def run(date: str) -> int:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    episodes = PROJECT_ROOT / "episodes"
    audio = PROJECT_ROOT / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    tts_txt = episodes / f"{date}-tts.txt"
    md = episodes / f"{date}.md"
    if not tts_txt.exists() and md.exists():
        from tts_preprocessor import preprocess_for_tts

        tts_txt.write_text(preprocess_for_tts(md.read_text(encoding="utf-8")), encoding="utf-8")
    if not tts_txt.exists():
        print(f"FALHA: não há {tts_txt} nem {md}", file=sys.stderr)
        return 2
    chunks = parse_tts_lines(tts_txt.read_text(encoding="utf-8"))
    if len(chunks) < 5:
        print(f"FALHA: poucos chunks úteis ({len(chunks)}). Abortando.", file=sys.stderr)
        return 3
    tmp = pick_tmpdir(date)
    try:
        kept = asyncio.run(synth_all(chunks, tmp))
        print(f"chunks kept={len(kept)} skipped={len(chunks) - len(kept)}")
        if len(kept) < 5:
            print(f"FALHA: poucos chunks úteis ({len(kept)}). Abortando concat.", file=sys.stderr)
            return 3
        final = audio / f"{date}.mp3"
        concat_and_normalize(kept, final)
        size = final.stat().st_size if final.exists() else 0
        if size < MIN_FINAL_BYTES:
            print(f"FALHA: MP3 final pequeno demais ({size}B < {MIN_FINAL_BYTES})", file=sys.stderr)
            return 3
        named = audio / f"{date}-vale-da-liberdade.mp3"
        named.unlink(missing_ok=True)
        print(f"✅ Fallback Edge OK: {final} ({size} bytes)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("date", nargs="?", default=None)
    p.add_argument("--date", dest="date_opt", default=None)
    args = p.parse_args()
    from datetime import date as _date

    date = args.date_opt or args.date or _date.today().isoformat()
    return run(date)


if __name__ == "__main__":
    raise SystemExit(main())
