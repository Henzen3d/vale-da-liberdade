"""Gera os arquivos de áudio de efeito sonoro (SFX) whoosh para transições do webjornal."""
from __future__ import annotations

import math
import struct
import wave
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def generate_whoosh_wav(dest_wav: Path) -> Path:
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    sr = 48000
    duration = 0.55
    num_samples = int(sr * duration)
    peak_t = 0.24

    import random
    b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
    frames = bytearray()
    phase_sub = 0.0

    for i in range(num_samples):
        t = i / sr

        # Envelope suave
        if t < peak_t:
            env = math.sin((math.pi / 2.0) * (t / peak_t)) ** 2
        else:
            env = math.cos((math.pi / 2.0) * ((t - peak_t) / (duration - peak_t))) ** 2

        # Ruído Rosa
        white = random.uniform(-1.0, 1.0)
        b0 = 0.99886 * b0 + white * 0.0555179
        b1 = 0.99332 * b1 + white * 0.0750759
        b2 = 0.96900 * b2 + white * 0.1538520
        b3 = 0.86650 * b3 + white * 0.3104856
        b4 = 0.55000 * b4 + white * 0.5329522
        b5 = -0.7616 * b5 - white * 0.0168980
        pink = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11
        b6 = white * 0.115926

        f_noise = pink * env * 0.22

        # Sub-bass body sweep (90Hz -> 240Hz -> 50Hz)
        f_sub = 90.0 + 150.0 * math.exp(-((t - peak_t) / 0.14) ** 2)
        phase_sub += 2.0 * math.pi * f_sub / sr
        sub_body = math.sin(phase_sub) * env * 0.10

        # Stereo pan sweep suave
        pan = -0.3 + 0.6 * (t / duration)
        gain_l = math.cos((pan + 1.0) * math.pi / 4.0)
        gain_r = math.sin((pan + 1.0) * math.pi / 4.0)

        sample_l = (f_noise + sub_body) * gain_l
        sample_r = (f_noise + sub_body) * gain_r

        val_l = int(max(-32767, min(32767, sample_l * 32767.0)))
        val_r = int(max(-32767, min(32767, sample_r * 32767.0)))
        frames.extend(struct.pack("<hh", val_l, val_r))

    with wave.open(str(dest_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(frames)

    return dest_wav


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> Path:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3_path)],
        check=True,
        capture_output=True,
    )
    return mp3_path


def main():
    targets = [
        ROOT / "references" / "youtube" / "mockup-browser" / "assets" / "sfx",
        ROOT / "branding" / "audio" / "sfx",
    ]
    for t in targets:
        wav = t / "whoosh.wav"
        mp3 = t / "whoosh.mp3"
        generate_whoosh_wav(wav)
        convert_wav_to_mp3(wav, mp3)
        print(f"Generated: {wav} ({wav.stat().st_size}B) and {mp3} ({mp3.stat().st_size}B)")


if __name__ == "__main__":
    main()
