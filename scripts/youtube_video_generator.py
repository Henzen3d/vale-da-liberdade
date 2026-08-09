#!/usr/bin/env python3
"""
Gera o vídeo para YouTube do episódio diário do Vale da Liberdade.

Pipeline:
  [branding/intro.mp4  (se existir)]  +
  [thumbnail + waveform animado + áudio do episódio]  +
  [branding/outro.mp4  (se existir)]
  = vídeo final pronto para upload.

A abertura e o fechamento são criados pelo dono (Osmar) e ficam em
`branding/` — o script apenas REUTILIZA: se o arquivo existe, concatena;
se não existe, gera o vídeo só com o episódio (nunca quebra o dia).

Uso:
  python3 scripts/youtube_video_generator.py --date 2026-08-07 [--out video.mp4]
  python3 scripts/youtube_video_generator.py --audio X.mp3 --thumbnail Y.webp [--out video.mp4]

Requisitos de branding (1280x720, 30fps recomendado, libx264 + AAC):
  branding/intro.mp4   — abertura (ex.: 6s com logo e vinheta)
  branding/outro.mp4   — fechamento (ex.: 8s com "até amanhã")
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANDING_DIR = ROOT / "branding"
INTRO = BRANDING_DIR / "intro.mp4"
OUTRO = BRANDING_DIR / "outro.mp4"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

W, H, FPS = 1280, 720, 30


def run(cmd: list, tag: str) -> None:
    print(f"[youtube-video] {tag}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"[youtube-video] FALHOU em: {tag}")


def resolve_assets(date: str):
    """Resolve áudio + thumbnail + título do episódio diário."""
    audio = ROOT / "public" / "audio" / f"{date}.mp3"
    if not audio.exists():
        # tenta o WAV completo como fallback
        wav = ROOT / "audio" / f"{date}-completo.wav"
        if wav.exists():
            audio = wav
        else:
            raise SystemExit(f"[youtube-video] Áudio não encontrado para {date}: {audio}")

    thumb_candidates = [
        ROOT / "public" / "thumbnails" / date / f"ep_{date}.webp",
        ROOT / "public" / "thumbnails" / date / f"ep_{date}.jpg",
    ]
    thumb = next((p for p in thumb_candidates if p.exists()), None)
    if thumb is None:
        # fallback: capa padrão
        thumb = ROOT / "public" / "assets" / "cover.jpg"
    if not thumb.exists():
        raise SystemExit(f"[youtube-video] Thumbnail não encontrada para {date}")

    # título otimizado (title_optimizer.py escreve episodes/{date}-title.txt)
    title = ""
    tpath = ROOT / "episodes" / f"{date}-title.txt"
    if tpath.exists():
        title = tpath.read_text(encoding="utf-8").strip()
    if not title:
        # fallback: lê do episodes.json
        eps_json = ROOT / "public" / "data" / "episodes.json"
        try:
            data = json.loads(eps_json.read_text(encoding="utf-8"))
            eps = data.get("episodes", data) if isinstance(data, dict) else data
            for ep in eps:
                if str(ep.get("date")) == date and ep.get("type") != "especial":
                    title = ep.get("title") or ""
                    break
        except Exception:
            pass
    if not title:
        title = f"Vale da Liberdade — Edição de {date}"

    return audio, thumb, title


def build_episode_segment(audio, thumb, out_mp4: Path) -> None:
    """Gera o segmento do episódio: thumbnail escurecida + waveform animado + áudio."""
    # duração do áudio
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(audio)],
        capture_output=True, text=True,
    )
    dur = float(r.stdout.strip() or 0) or 30

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(thumb),
        "-i", str(audio),
        "-filter_complex",
        (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},eq=brightness=-0.25:saturation=1.1[bg];"
            f"[1:a]showwaves=s={W-180}x300:mode=cline:colors=0xffc06c|0xe8a23d"
            f":rate={FPS}:scale=sqrt[wave];"
            f"[bg][wave]overlay=(W-w)/2:(H-h)/2+10[out]"
        ),
        "-map", "[out]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-t", str(dur),
        "-shortest",
        str(out_mp4),
    ]
    run(cmd, f"gerando episódio ({dur:.0f}s)")


def normalize_segment(src, dst: Path) -> None:
    """Re-encode um segmento para o padrão único (1280x720/30fps/H.264 + AAC 44.1kHz stereo).
    Necessário porque o concat exige streams idênticos entre os arquivos (sample rate,
    canais, codec). O intro/outro do dono podem vir em qualquer formato."""
    run(
        ["ffmpeg", "-y", "-i", str(src),
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
         "-r", str(FPS),
         "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
         "-video_track_timescale", "15360",
         str(dst)],
        "normalizando segmento",
    )


def concat_segments(segments, out_mp4: Path) -> None:
    """Normaliza cada segmento para o padrão único e concatena com -c copy."""
    with tempfile.TemporaryDirectory(prefix="vld_yt_norm_") as tmpdir:
        norm = []
        for i, seg in enumerate(segments):
            n = Path(tmpdir) / f"seg_{i}.mp4"
            normalize_segment(seg, n)
            norm.append(str(n))
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            for n in norm:
                f.write(f"file '{n}'\n")
            concat_file = f.name
        try:
            run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                 "-c", "copy",
                 str(out_mp4)],
                "concatenando (intro + episódio + outro)",
            )
        finally:
            os.unlink(concat_file)


def main():
    ap = argparse.ArgumentParser(description="Gera vídeo do episódio para YouTube")
    ap.add_argument("--date", help="Data do diário (YYYY-MM-DD)")
    ap.add_argument("--audio", help="Caminho do áudio (alternativo a --date)")
    ap.add_argument("--thumbnail", help="Caminho da thumbnail (alternativo a --date)")
    ap.add_argument("--out", default=None, help="Arquivo de saída (default: /tmp/vld_yt_{date}.mp4)")
    args = ap.parse_args()

    if args.date:
        audio, thumb, title = resolve_assets(args.date)
        out = args.out or f"/tmp/vld_yt_{args.date}.mp4"
    else:
        if not args.audio or not args.thumbnail:
            raise SystemExit("[youtube-video] Use --date OU --audio+--thumbnail")
        audio, thumb = Path(args.audio), Path(args.thumbnail)
        title = ""
        out = args.out or "/tmp/vld_yt_episodio.mp4"

    print(f"[youtube-video] título: {title}")
    print(f"[youtube-video] áudio:   {audio}")
    print(f"[youtube-video] thumb:   {thumb}")
    print(f"[youtube-video] intro:   {'SIM' if INTRO.exists() else 'não (pulando)'}")
    print(f"[youtube-video] outro:   {'SIM' if OUTRO.exists() else 'não (pulando)'}")

    tmp = Path(tempfile.mkdtemp(prefix="vld_yt_"))
    episode_seg = tmp / "episodio.mp4"
    build_episode_segment(audio, thumb, episode_seg)

    segments = []
    if INTRO.exists():
        segments.append(str(INTRO))
    segments.append(str(episode_seg))
    if OUTRO.exists():
        segments.append(str(OUTRO))

    if len(segments) > 1:
        concat_segments(segments, Path(out))
    else:
        import shutil
        shutil.copy2(episode_seg, out)

    # limpeza
    for f in tmp.iterdir():
        try:
            f.unlink()
        except Exception:
            pass
    tmp.rmdir()

    size_mb = os.path.getsize(out) / 1e6
    print(f"[youtube-video] OK → {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
