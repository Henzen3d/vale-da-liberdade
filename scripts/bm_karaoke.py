#!/usr/bin/env python3
"""Gera words karaoke (timestamps por palavra) para cada quadro de QUALQUER episódio.

Corta o áudio completo do episódio nos intervalos de cada quadro (start_ms/end_ms
do quadros-<ID>.json) e transcreve cada trecho com faster-whisper, produzindo
references/youtube/prototype/generated/<qid>_words.json com [{word, start, end}]
timestamps RELATIVOS ao trecho.

Uso:
    python3 scripts/bm_karaoke.py --video-id <ID> [--audio <mp3 opcional>] [--force]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERMES_PY = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
QUADROS_DIR = ROOT / "references/youtube/prototype"
AUDIO_DIR = ROOT / "output/brasil_e_mundo/audio"
GEN = ROOT / "references/youtube/prototype/generated"
TMP = Path("/tmp/bm_karaoke")

# Fix 2026-08-13 (Gemini 3.7): encoder delay do MP3 (~2112 samples @44.1kHz)
# causa drift acumulado entre áudio e karaoke sobre 225s de vídeo.
ENCODER_DELAY_MS = 50
# Quantization pro timeline GSAP (~30 FPS = 33.33ms steps)
FPS_MS = 33.33


def resolve_audio(video_id: str) -> Path:
    """Retorna o MP3 mais recente de output/brasil_e_mundo/audio/{video_id}_*.mp3."""
    files = sorted(
        AUDIO_DIR.glob(f"{video_id}_*.mp3"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in files:
        if p.stat().st_size > 200_000:
            return p
    if files:
        return files[0]
    raise FileNotFoundError(f"áudio não encontrado: {AUDIO_DIR}/{video_id}_*.mp3")


def cut(audio: Path, quadro_id: str, start_ms: int, end_ms: int) -> Path:
    """Corta áudio porém compensa o MP3 encoder delay (~2112 samples @44.1kHz).

    Fix 2026-08-13 (Gemini 3.7 identificou risco de drift MP3↔karaoke):
    o MP3 tem encoder delay/padding (~2.3ms/sample) que faz o -ss do ffmpeg
    não alinhar perfeitamente com o início real. Aplicamos um *pre-roll* de
    encoder delay (~50ms) no início do corte e, na transcrição, os timestamps
    são re-offsetados pro start_ms global pra não acumular drift.
    """
    TMP.mkdir(parents=True, exist_ok=True)
    out = TMP / f"{quadro_id}.mp3"
    start_s = max(0, (start_ms - ENCODER_DELAY_MS) / 1000.0)
    pre_skip_s = (start_ms - max(0, start_ms - ENCODER_DELAY_MS)) / 1000.0
    dur_s = (end_ms - start_ms) / 1000.0 + ENCODER_DELAY_MS / 1000.0
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start_s:.3f}", "-i", str(audio),
         "-t", f"{dur_s:.3f}", "-ac", "1", "-ar", "16000", str(out)],
        capture_output=True, check=True)
    return out


def transcribe(audio_path: Path, global_start_ms: int = 0) -> list[dict]:
    """Transcreve com timestamps re-offsetados pro start_ms do quadro global.

    O faster-whisper retorna timestamps RELATIVOS ao trecho cortado.
    Nós adicionamos `global_start_ms` (menos o encoder delay) pros que o
    karaoke sincronize com a timeline GSAP do HyperFrames (~30FPS = 33.33ms
    steps).
    """
    code = f"""
import json, sys
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe({str(audio_path)!r}, language="pt", word_timestamps=True)
words = []
for seg in segments:
    for w in (seg.words or []):
        words.append({{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}})
print(json.dumps(words, ensure_ascii=False))
"""
    r = subprocess.run([str(HERMES_PY), "-c", code], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"whisper falhou: {r.stderr[-500:]}")
    out = r.stdout.strip().splitlines()[-1]
    words = json.loads(out)
    if global_start_ms > 0:
        base_s = global_start_ms / 1000.0
        for w in words:
            w["start"] = round(w["start"] + base_s - ENCODER_DELAY_MS/1000.0, 3)
            w["end"] = round(w["end"] + base_s - ENCODER_DELAY_MS/1000.0, 3)
    return words


def main() -> int:
    ap = argparse.ArgumentParser(description="Karaoke (words) por quadro — episódio BM qualquer")
    ap.add_argument("--video-id", required=True, help="ID do episódio (ex: EwZxO3DKHoQ)")
    ap.add_argument("--audio", default=None, help="Path do MP3 (default: mais recente em output/brasil_e_mundo/audio)")
    ap.add_argument("--force", action="store_true", help="Regenera words existentes")
    args = ap.parse_args()

    quadros_path = QUADROS_DIR / f"quadros-{args.video_id}.json"
    if not quadros_path.exists():
        print(f"❌ quadros não encontrado: {quadros_path}")
        print("   Rode antes: bm_quadros_mapper.py --video-id <ID> --audio <mp3>")
        return 1

    audio = Path(args.audio) if args.audio else resolve_audio(args.video_id)
    print(f"🎙️  Áudio: {audio.name}")
    quadros = json.load(open(quadros_path))["quadros"]
    # ISOLAMENTO POR EPISÓDIO (fix 2026-08-12): cada vídeo tem sua própria
    # subpasta em generated/<video_id>/ — antes os words.json eram
    # compartilhados (q01_words.json sem ID), então o último episódio
    # processado sobrescrevia e contaminava a legenda dos demais.
    gen_ep = GEN / args.video_id
    gen_ep.mkdir(parents=True, exist_ok=True)

    ok, fail = 0, 0
    for q in quadros:
        qid = q["id"]
        out_path = gen_ep / f"{qid}_words.json"
        if out_path.exists() and not args.force:
            print(f"⏭️  {qid} já existe (--force para regerar)")
            ok += 1
            continue
        try:
            seg = cut(audio, qid, q["start_ms"], q["end_ms"])
            print(f"🎙️  {qid} ({q['end_ms']-q['start_ms']}ms) → transcrevendo...", flush=True)
            words = transcribe(seg, global_start_ms=q["start_ms"])
        except Exception as e:
            print(f"   ❌ {qid}: {e}")
            fail += 1
            continue
        out_path.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   ✅ {qid}: {len(words)} palavras → {out_path.name}")
        ok += 1

    print(f"\n✅ karaoke: {ok} quadros OK, {fail} falhas")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
