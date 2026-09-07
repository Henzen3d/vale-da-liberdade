#!/usr/bin/env python3
"""
scripts/build_outro.py — Compositor de Vídeos de Encerramento (Outro) para o YouTube.

Transforma gravações em tela cheia do apresentador (1280x720 ou 1920x1080)
em vídeos de encerramento com o layout de 1/4 de tela (854x480), espaços livres
para os cards do YouTube End Screen, e trilha de fundo com auto-ducking suave.

Uso:
  # Processar todos os takes da pasta gravacoes:
  python scripts/build_outro.py --all

  # Processar um take específico:
  python scripts/build_outro.py -i branding/encerramento/gravacoes/final01.mp4 -o branding/encerramento/prontos/outro_01.mp4

  # Definir um template customizado:
  python scripts/build_outro.py --all --template branding/encerramento/templates/fundo.png
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BRANDING_DIR = ROOT / "branding"
GRAVACOES_DIR = BRANDING_DIR / "encerramento" / "gravacoes"
TEMPLATES_DIR = BRANDING_DIR / "encerramento" / "templates"
PRONTOS_DIR = BRANDING_DIR / "encerramento" / "prontos"
OUTRO_CANONICO = BRANDING_DIR / "outro.mp4"
AUDIO_OUTRO_DIR = BRANDING_DIR / "audio" / "outro"
DEFAULT_WALLPAPER = ROOT / "references" / "youtube" / "mockup-browser" / "wallpaper" / "Aesthetic Desktop Background 4k Wallpaper.jpg"


def probe_duration(file_path: Path) -> float:
    """Obtém duração precisa em segundos via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(r.stdout.strip() or 0.0)
    except Exception:
        return 0.0


def find_music() -> Path | None:
    """Localiza a trilha musical de encerramento em branding/audio/outro/."""
    candidates = [
        AUDIO_OUTRO_DIR / "final-mix-25s.wav",
        AUDIO_OUTRO_DIR / "outro_tema.wav",
        AUDIO_OUTRO_DIR / "outro_tema.mp3",
        AUDIO_OUTRO_DIR / "final.mp3",
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 1000:
            return c
    if AUDIO_OUTRO_DIR.is_dir():
        for p in sorted(AUDIO_OUTRO_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac"}:
                return p
    return None


def find_template(custom: Path | None = None) -> Path:
    """Localiza o template ou wallpaper de fundo."""
    if custom and custom.is_file():
        return custom

    if TEMPLATES_DIR.is_dir():
        for p in sorted(TEMPLATES_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and "readme" not in p.name.lower():
                return p

    if DEFAULT_WALLPAPER.is_file():
        return DEFAULT_WALLPAPER

    # Fallback: wallpaper da pasta mockup-browser
    wp_dir = ROOT / "references" / "youtube" / "mockup-browser" / "wallpaper"
    if wp_dir.is_dir():
        for p in sorted(wp_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                return p

    raise FileNotFoundError("Nenhum template ou wallpaper encontrado para o encerramento.")


def compose_outro(
    video_input: Path,
    output_path: Path,
    music_path: Path | None = None,
    template_path: Path | None = None,
) -> bool:
    """Renderiza um vídeo de encerramento completo no formato 1920x1080 30fps."""
    if not video_input.is_file():
        print(f"❌ Vídeo não encontrado: {video_input}")
        return False

    dur = probe_duration(video_input)
    if dur <= 0.0:
        print(f"❌ Duração inválida para {video_input}")
        return False

    template = find_template(template_path)
    music = music_path or find_music()

    t1 = max(0.0, dur - 3.5)
    t2 = max(t1 + 0.2, dur - 1.2)
    ramp_dur = t2 - t1
    fade_dur = max(0.2, dur - t2)

    print(f"🎬 Renderizando encerramento: {video_input.name} ({dur:.1f}s)")
    print(f"   Template: {template.name}")
    print(f"   Trilha:   {music.name if music else 'sem trilha'}")
    print(f"   Saída:    {output_path}")

    # Filtro de vídeo:
    # 1. Apresentador redimensionado para 854x480 com borda branca elegante de 3px
    # 2. Fundo 1920x1080 com os backdrops dos cards do YouTube:
    #    - Card 1: 1200x100 (608x342)
    #    - Card 2: 1200x520 (608x342)
    #    - Inscrever-se: 420x640 (180x180)
    vf_pres = (
        "[1:v]scale=854:480:force_original_aspect_ratio=decrease,"
        "pad=854:480:(ow-iw)/2:(oh-ih)/2:color=black,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=3[pres]"
    )
    vf_bg = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        "drawbox=x=1200:y=100:w=608:h=342:color=black@0.4:t=fill,"
        "drawbox=x=1200:y=100:w=608:h=342:color=white@0.2:t=2,"
        "drawbox=x=1200:y=520:w=608:h=342:color=black@0.4:t=fill,"
        "drawbox=x=1200:y=520:w=608:h=342:color=white@0.2:t=2,"
        "drawbox=x=420:y=640:w=180:h=180:color=black@0.4:t=fill,"
        "drawbox=x=420:y=640:w=180:h=180:color=white@0.2:t=2[bg]"
    )
    vf_overlay = "[bg][pres]overlay=80:100:shortest=1[v]"

    inputs = [
        "-loop", "1", "-i", str(template),
        "-i", str(video_input),
    ]

    if music and music.is_file():
        inputs += ["-i", str(music)]
        af_bgm = (
            f"[2:a]volume='if(lt(t,{t1:.2f}),0.12,if(lt(t,{t2:.2f}),0.12+0.63*(t-{t1:.2f})/{ramp_dur:.2f},0.75))':eval=frame,"
            f"afade=t=out:st={t2:.2f}:d={fade_dur:.2f},"
            f"atrim=0:{dur:.2f}[bgm]"
        )
        af_voz = "[1:a]volume=1.0[voz]"
        af_mix = "[voz][bgm]amix=inputs=2:duration=first:normalize=0[a]"
        filter_complex = f"{vf_pres};{vf_bg};{vf_overlay};{af_bgm};{af_voz};{af_mix}"
        map_args = ["-map", "[v]", "-map", "[a]"]

    else:
        filter_complex = f"{vf_pres};{vf_bg};{vf_overlay}"
        map_args = ["-map", "[v]", "-map", "1:a"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *map_args,
        "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not output_path.exists():
        print(f"❌ Falha no ffmpeg: {(r.stderr or '')[-500:]}")
        return False

    print(f"✅ Encerramento concluído: {output_path.name} ({output_path.stat().st_size // 1024} KB)")
    return True


def build_all(custom_template: Path | None = None) -> list[Path]:
    """Compila todas as gravações brutas em vídeos prontos."""
    PRONTOS_DIR.mkdir(parents=True, exist_ok=True)
    gravacoes = sorted(
        p for p in GRAVACOES_DIR.glob("*.mp4")
        if p.is_file() and not p.name.startswith(".")
    )
    if not gravacoes:
        print(f"⚠️  Nenhuma gravação encontrada em {GRAVACOES_DIR}")
        return []

    built: list[Path] = []
    for g in gravacoes:
        out_name = f"outro_{g.stem}.mp4"
        out_path = PRONTOS_DIR / out_name
        ok = compose_outro(g, out_path, template_path=custom_template)
        if ok:
            built.append(out_path)

    # Atualiza o branding/outro.mp4 com o primeiro da lista
    if built:
        shutil.copy2(built[0], OUTRO_CANONICO)
        print(f"📌 Atualizado canônico default: {OUTRO_CANONICO.name} <- {built[0].name}")

    return built


def main() -> None:
    parser = argparse.ArgumentParser(description="Compositor de Vídeos de Encerramento (Outro)")
    parser.add_argument("-i", "--input", help="Arquivo de gravação específico")
    parser.add_argument("-o", "--output", help="Arquivo de saída específico")
    parser.add_argument("--all", action="store_true", help="Processa todas as gravações em branding/encerramento/gravacoes/")
    parser.add_argument("--template", help="Imagem de template/wallpaper customizada")
    parser.add_argument("--music", help="Trilha musical customizada")

    args = parser.parse_args()

    tmpl = Path(args.template) if args.template else None
    mus = Path(args.music) if args.music else None

    if args.all or (not args.input and not args.output):
        built = build_all(custom_template=tmpl)
        print(f"\n🎉 Total de {len(built)} encerramentos gerados com sucesso!")
        sys.exit(0 if built else 1)

    if args.input:
        in_path = Path(args.input)
        out_path = Path(args.output) if args.output else PRONTOS_DIR / f"outro_{in_path.stem}.mp4"
        ok = compose_outro(in_path, out_path, music_path=mus, template_path=tmpl)
        if ok and not OUTRO_CANONICO.exists():
            shutil.copy2(out_path, OUTRO_CANONICO)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
