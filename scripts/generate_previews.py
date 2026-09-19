#!/usr/bin/env python3
"""Gera arquivos de prévia comparativa A/B do Studio Humanizer.

Gera 4 arquivos de demonstração:
1. 01-fundo-estudio-isolado.mp3: apenas a ambiência do estúdio (room tone + foleys).
2. 02-voz-original-seca.mp3: 45 segundos da locução original seca (sem ambiência).
3. 03-voz-com-humanizacao-completa.mp3: a mesma locução tratada com o Studio Humanizer.
4. 04-comparativo-ab-alternado.mp3: alternância A/B (15s seco vs 15s humanizado) para teste cego imediato.
"""

from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from studio_humanizer import StudioHumanizer

PREVIEW_DIR = PROJECT_ROOT / "audio" / "previa-humanizer"
SAMPLE_RATE = 44100


def run_ffmpeg(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{r.stderr}")


def create_tone_beep(duration_s: float = 0.2, freq: float = 880.0, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Gera um bipe suave de transição A/B."""
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    env = np.sin(np.pi * (t / duration_s)) ** 2
    beep = 0.3 * np.sin(2 * np.pi * freq * t) * env
    return beep.astype(np.float32)


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    humanizer = StudioHumanizer()

    print("=" * 60)
    print("Gerando arquivos de previa do Studio Humanizer...")
    print("=" * 60)

    # 1. Obter trecho de voz original de ~45s
    # Usar audio/2026-06-14-vale-da-liberdade.mp3 ou 2026-06-12-peter-1.mp3
    src_mp3 = PROJECT_ROOT / "audio" / "2026-06-14-vale-da-liberdade.mp3"
    if not src_mp3.exists():
        src_mp3 = PROJECT_ROOT / "audio" / "2026-06-12-peter-1.mp3"

    print(f"\n[1/4] Extraindo 45 segundos de locucao de: {src_mp3.name}...")
    tmp_voice_wav = PREVIEW_DIR / "temp_voice_45s.wav"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-ss", "00:00:04",
        "-t", "45",
        "-i", str(src_mp3),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(tmp_voice_wav),
    ])

    sr, voice_data = StudioHumanizer.read_wav(tmp_voice_wav, target_sr=SAMPLE_RATE)
    # Normalizar levemente para ter volume confortável
    v_peak = np.max(np.abs(voice_data)) + 1e-9
    voice_data = (voice_data / v_peak) * 0.85
    StudioHumanizer.write_wav(tmp_voice_wav, voice_data, sr)

    # Exportar Prévia 2: Voz Seca Original (MP3)
    out_02 = PREVIEW_DIR / "02-voz-original-seca.mp3"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(tmp_voice_wav),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_02),
    ])
    print(f"  -> {out_02.name} (45s)")

    # 2. Gerar Prévia 3: Voz com Humanização Completa
    print("\n[2/4] Aplicando Studio Humanizer na locucao...")
    tmp_humanized_wav = PREVIEW_DIR / "temp_humanized_45s.wav"
    humanizer.humanize(input_wav=tmp_voice_wav, output_wav=tmp_humanized_wav)

    out_03 = PREVIEW_DIR / "03-voz-com-humanizacao-completa.mp3"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(tmp_humanized_wav),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_03),
    ])
    print(f"  -> {out_03.name} (45s)")

    # 3. Gerar Prévia 1: Apenas o Fundo do Estúdio Isolado (60s)
    print("\n[3/4] Gerando ambiencia isolada do estudio (60s)...")
    # Geramos uma linha de silêncio de 60s simulando fala esparsa para acionar room tone e foleys
    duration_s = 60.0
    n_samples = int(SAMPLE_RATE * duration_s)
    # Simular nível de voz médio de -20 dBFS para calibrar o volume relativo do room tone
    ref_voice_rms_db = -20.0

    # Montar room tone
    room = humanizer._assemble_room_tone(n_samples, ref_voice_rms_db)
    # Gerar envelope simulado com trechos de fala e pausas
    t = np.arange(n_samples) / SAMPLE_RATE
    # Blocos de fala de 4s a cada 6s
    speech_mask = (t % 8.0) < 5.0
    sim_env = np.where(speech_mask, -18.0, -55.0).astype(np.float32)
    # Aumentar ligeiramente a densidade e ganho do foley para a prévia isolada ser bem audível
    humanizer.cfg["foley"]["events_per_minute_min"] = 4
    humanizer.cfg["foley"]["events_per_minute_max"] = 7
    humanizer.cfg["foley"]["volume_db"] = -26.0  # +9dB para demonstração isolada
    foley = humanizer._schedule_foley(n_samples, ref_voice_rms_db, sim_env)

    ambience_only = room + foley
    # Normalizar para não clipar
    a_peak = np.max(np.abs(ambience_only)) + 1e-9
    ambience_only = (ambience_only / a_peak) * 0.7

    tmp_ambience_wav = PREVIEW_DIR / "temp_ambience_60s.wav"
    StudioHumanizer.write_wav(tmp_ambience_wav, ambience_only, SAMPLE_RATE)

    out_01 = PREVIEW_DIR / "01-fundo-estudio-isolado.mp3"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(tmp_ambience_wav),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_01),
    ])
    print(f"  -> {out_01.name} (60s)")

    # 4. Gerar Prévia 4: Comparativo A/B Alternado (15s Seco / Bipe / 15s Humanizado)
    print("\n[4/4] Montando comparativo direto A/B (15s seco vs 15s humanizado)...")
    sr, h_data = StudioHumanizer.read_wav(tmp_humanized_wav, target_sr=SAMPLE_RATE)
    sr, s_data = StudioHumanizer.read_wav(tmp_voice_wav, target_sr=SAMPLE_RATE)

    segment_len = int(15.0 * SAMPLE_RATE)
    beep = create_tone_beep(duration_s=0.25, freq=750.0)
    silence_half = np.zeros(int(SAMPLE_RATE * 0.25), dtype=np.float32)

    # Bloco A (Seco)
    part_a = s_data[:segment_len]
    # Bloco B (Humanizado)
    part_b = h_data[:segment_len]
    # Bloco C (Seco - continuação)
    part_c = s_data[segment_len:segment_len*2]
    # Bloco D (Humanizado - continuação)
    part_d = h_data[segment_len:segment_len*2]

    # Sequência: [Voz Seca 15s] -> Bipe -> [Voz Humanizada 15s] -> Bipe -> [Voz Seca 15s] -> Bipe -> [Voz Humanizada 15s]
    ab_demo = np.concatenate([
        part_a, silence_half, beep, silence_half,
        part_b, silence_half, beep, silence_half,
        part_c, silence_half, beep, silence_half,
        part_d
    ])

    tmp_ab_wav = PREVIEW_DIR / "temp_ab_compare.wav"
    StudioHumanizer.write_wav(tmp_ab_wav, ab_demo, SAMPLE_RATE)

    out_04 = PREVIEW_DIR / "04-comparativo-ab-alternado.mp3"
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(tmp_ab_wav),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(out_04),
    ])
    print(f"  -> {out_04.name} (~60s)")

    # Limpeza dos WAVs temporários
    for tmp in [tmp_voice_wav, tmp_humanized_wav, tmp_ambience_wav, tmp_ab_wav]:
        if tmp.exists():
            tmp.unlink()

    print("\n" + "=" * 60)
    print("Previa concluida com sucesso!")
    print(f"Arquivos prontos em: {PREVIEW_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
