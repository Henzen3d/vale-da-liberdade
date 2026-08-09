#!/usr/bin/env python3
"""Limpa WAVs intermediários de TTS já convertidos em MP3.

Mantém:
  - MP3 finais (audio/*.mp3, public/audio/*.mp3, output/brasil_e_mundo/audio/*.mp3)
  - referências de voz (voices/**)
  - WAVs de teste/kokoro se --keep-tests

Uso:
  python3 scripts/cleanup_audio_intermediates.py           # dry-run
  python3 scripts/cleanup_audio_intermediates.py --apply   # apaga de verdade
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = [
    ROOT / "audio",
    ROOT / "output" / "brasil_e_mundo" / "audio",
]

# Nunca tocar
PROTECT_GLOBS = [
    "voices/**",
    "moss-tts-nano/**",
    "kokoro_work/**",
]


def is_protected(p: Path) -> bool:
    try:
        rel = p.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    s = str(rel).replace("\\", "/")
    if s.startswith("voices/") or s.startswith("moss-tts-nano/") or s.startswith("kokoro_work/"):
        return True
    return False


def corresponding_mp3(wav: Path) -> list[Path]:
    """Candidatos a MP3 final para um WAV intermediário."""
    name = wav.name
    parent = wav.parent
    cands: list[Path] = []
    if name.endswith("-completo.wav"):
        stem = name[: -len("-completo.wav")]
        cands += [
            parent / f"{stem}.mp3",
            parent / f"{stem}-vale-da-liberdade.mp3",
            ROOT / "public" / "audio" / f"{stem}.mp3",
            ROOT / "public" / "audio" / f"{stem}-vale-da-liberdade.mp3",
            ROOT / "audio" / f"{stem}.mp3",
            ROOT / "audio" / f"{stem}-vale-da-liberdade.mp3",
        ]
    elif name.endswith(".wav"):
        stem = name[:-4]
        cands += [
            parent / f"{stem}.mp3",
            ROOT / "public" / "audio" / f"{stem}.mp3",
        ]
    return cands


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Apaga de verdade (default: dry-run)")
    ap.add_argument("--min-mp3-bytes", type=int, default=100_000, help="MP3 mínimo para considerar OK")
    args = ap.parse_args()

    to_delete: list[tuple[Path, int, str]] = []
    skipped: list[tuple[Path, str]] = []

    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for wav in sorted(d.rglob("*.wav")):
            if is_protected(wav):
                skipped.append((wav, "protegido"))
                continue
            mp3s = [p for p in corresponding_mp3(wav) if p.exists() and p.stat().st_size >= args.min_mp3_bytes]
            if not mp3s:
                skipped.append((wav, "sem MP3 final correspondente"))
                continue
            to_delete.append((wav, wav.stat().st_size, str(mp3s[0].name)))

    total = sum(sz for _, sz, _ in to_delete)
    print(f"{'APLICANDO' if args.apply else 'DRY-RUN'}: {len(to_delete)} WAV(s) · {total/1e6:.1f} MB")
    for wav, sz, mp3 in to_delete:
        action = "DEL" if args.apply else "would-del"
        print(f"  {action} {wav.relative_to(ROOT)} ({sz/1e6:.1f} MB)  [mp3={mp3}]")
        if args.apply:
            try:
                wav.unlink()
            except OSError as e:
                print(f"    ⚠️  falha: {e}")

    if skipped:
        print(f"\nMantidos/pulados: {len(skipped)}")
        for wav, reason in skipped[:15]:
            try:
                rel = wav.relative_to(ROOT)
            except ValueError:
                rel = wav
            print(f"  keep {rel} ({reason})")
        if len(skipped) > 15:
            print(f"  … +{len(skipped)-15} mais")

    if not args.apply and to_delete:
        print("\nPara aplicar: python3 scripts/cleanup_audio_intermediates.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
