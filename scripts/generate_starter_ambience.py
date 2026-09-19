#!/usr/bin/env python3
"""Gerador do Starter Pack Acústico para o Studio Humanizer.

Gera sons iniciais sintetizados com alta fidelidade para popular
a pasta audio/ambience/raw/ e permitir a inicialização imediata
do estúdio virtual do Vale da Liberdade.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "audio" / "ambience" / "raw"
SAMPLE_RATE = 44100


def save_wav(path: Path, data: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    """Salva array float32 em arquivo WAV 16-bit mono."""
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def generate_pink_noise(num_samples: int) -> np.ndarray:
    """Gera ruído rosa exato (1/f) filtrando ruído branco no domínio da frequência."""
    white = np.random.randn(num_samples).astype(np.float32)
    fft = np.fft.rfft(white)
    frequencies = np.fft.rfftfreq(num_samples)
    frequencies[0] = frequencies[1] if len(frequencies) > 1 else 1.0
    scale = 1.0 / np.sqrt(frequencies)
    scale[0] = 0.0  # remover DC
    fft_pink = fft * scale
    pink = np.fft.irfft(fft_pink, n=num_samples)
    peak = np.max(np.abs(pink)) + 1e-9
    return (pink / peak).astype(np.float32)


def generate_room_tone(duration_s: float, hum_freq: float = 60.0, ac_noise: bool = True) -> np.ndarray:
    """Gera ruído ambiente contínuo de estúdio de gravação."""
    n_samples = int(SAMPLE_RATE * duration_s)
    t = np.arange(n_samples) / SAMPLE_RATE

    # 1. Base térmica (ruído rosa suave)
    noise = generate_pink_noise(n_samples) * 0.35

    # 2. Sopro de ar condicionado suave (filtro passa-faixa simulado)
    if ac_noise:
        # Modulação de ar lento
        air_mod = 0.8 + 0.2 * np.sin(2 * np.pi * 0.08 * t)
        noise = noise * air_mod

    # 3. Zumbido elétrico residual ultra-sutil (60 Hz + harmônicos)
    hum = (
        0.008 * np.sin(2 * np.pi * hum_freq * t)
        + 0.004 * np.sin(2 * np.pi * (hum_freq * 2) * t)
        + 0.002 * np.sin(2 * np.pi * (hum_freq * 3) * t)
    )

    combined = noise + hum
    # Normalizar peak para ~0.4 (headroom)
    peak = np.max(np.abs(combined)) + 1e-9
    return (combined / peak * 0.4).astype(np.float32)


def generate_mouse_click(variation: int = 1) -> np.ndarray:
    """Gera o clique de microswitch de mouse."""
    duration_s = 0.08 + (variation * 0.02)
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # Impacto inicial (spike transitório de alta frequência)
    freq = 3200.0 + (variation * 350.0)
    decay = 180.0 + (variation * 30.0)
    click = np.sin(2 * np.pi * freq * t) * np.exp(-decay * t)

    # Segundo 're-clique' metálico breve (soltura do botão)
    t_release = 0.035
    release_mask = t > t_release
    t_rel = t[release_mask] - t_release
    release_click = np.sin(2 * np.pi * (freq * 1.1) * t_rel) * np.exp(-250.0 * t_rel)
    click[release_mask] += release_click * 0.45

    # Adicionar toque de ruído de atrito plástico
    noise = np.random.randn(n) * np.exp(-120.0 * t) * 0.2
    total = click + noise
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.5).astype(np.float32)


def generate_key_tap(variation: int = 1) -> np.ndarray:
    """Gera o toque seco de tecla mecânica."""
    duration_s = 0.12 + (variation * 0.03)
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # Ressonância oca de plástico e mola
    freq = 1100.0 + (variation * 200.0)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-90.0 * t)
    thump = np.sin(2 * np.pi * 320.0 * t) * np.exp(-140.0 * t) * 0.8
    noise = np.random.randn(n) * np.exp(-110.0 * t) * 0.35

    total = body + thump + noise
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.5).astype(np.float32)


def generate_chair_creak() -> np.ndarray:
    """Gera um ajuste sutil de cadeira de escritório."""
    duration_s = 0.75
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # Frequência modulada em tom grave rangendo
    f0 = 240.0 + 60.0 * np.sin(2 * np.pi * 3.5 * t)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    envelope = np.sin(np.pi * (t / duration_s)) ** 1.8

    tone = np.sin(phase) * envelope * 0.7
    noise = np.random.randn(n) * envelope * 0.25
    total = tone + noise
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.45).astype(np.float32)


def generate_paper_turn() -> np.ndarray:
    """Gera o folhear breve de papel na bancada."""
    duration_s = 0.6
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    envelope = np.sin(np.pi * (t / duration_s)) ** 2
    noise = generate_pink_noise(n) * envelope
    # Modulação de fricção
    friction = 0.7 + 0.3 * np.sin(2 * np.pi * 18.0 * t)
    total = noise * friction
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.45).astype(np.float32)


def generate_pen_tap() -> np.ndarray:
    """Gera a batida leve de caneta plástica na mesa."""
    duration_s = 0.1
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    tap = np.sin(2 * np.pi * 1850.0 * t) * np.exp(-190.0 * t)
    thump = np.sin(2 * np.pi * 420.0 * t) * np.exp(-150.0 * t) * 0.5
    total = tap + thump
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.5).astype(np.float32)


def generate_water_sip() -> np.ndarray:
    """Gera um gole d'água sutil (para pausas/transições)."""
    duration_s = 0.55
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # Tom de garganta abafado com envelope de deglutição
    f0 = 310.0 + 80.0 * np.exp(-15.0 * t)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    env = np.sin(np.pi * (t / duration_s)) ** 2.2
    sip = np.sin(phase) * env
    noise = np.random.randn(n) * env * 0.15
    total = sip + noise
    peak = np.max(np.abs(total)) + 1e-9
    return (total / peak * 0.45).astype(np.float32)


def generate_throat_clear() -> np.ndarray:
    """Gera um pigarro/limpeza de garganta ultra-discreto."""
    duration_s = 0.35
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    env = np.sin(np.pi * (t / duration_s)) ** 2
    f0 = 220.0 + 40.0 * np.sin(2 * np.pi * 12.0 * t)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    sound = np.sin(phase) * env * 0.6 + np.random.randn(n) * env * 0.35
    peak = np.max(np.abs(sound)) + 1e-9
    return (sound / peak * 0.4).astype(np.float32)


def generate_subtle_breath() -> np.ndarray:
    """Gera uma tomada de ar/respiração suave entre blocos."""
    duration_s = 0.5
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # Envelope assimétrico de inspiração (sobe devagar, desce rápido)
    env = (t / duration_s) * (1.0 - (t / duration_s) ** 2)
    env = env / (np.max(env) + 1e-9)
    noise = generate_pink_noise(n) * env
    peak = np.max(np.abs(noise)) + 1e-9
    return (noise / peak * 0.4).astype(np.float32)


def generate_studio_impulse_response(rt60: float = 0.22) -> np.ndarray:
    """Gera Impulse Response sintética de estúdio de podcast tratado."""
    duration_s = rt60 * 1.2
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n) / SAMPLE_RATE

    # 1. Reflexões iniciais discretas (early reflections) de paredes próximas
    early = np.zeros(n, dtype=np.float32)
    delays_ms = [4.2, 7.8, 12.1, 16.5, 21.0, 26.3]
    gains = [0.65, 0.45, 0.32, 0.22, 0.15, 0.10]
    for d_ms, g in zip(delays_ms, gains):
        idx = int(SAMPLE_RATE * (d_ms / 1000.0))
        if idx < n:
            early[idx] = g * (1 if np.random.rand() > 0.5 else -1)

    # 2. Cauda estocástica difusa com decaimento exponencial (-60 dB em RT60)
    decay_rate = 6.91 / rt60
    tail = np.random.randn(n).astype(np.float32) * np.exp(-decay_rate * t)

    # Somar early reflections + cauda difusa
    ir = early + tail * 0.25
    peak = np.max(np.abs(ir)) + 1e-9
    return (ir / peak * 0.5).astype(np.float32)


def main() -> None:
    print("=" * 60)
    print("[Studio Humanizer] Gerando Starter Pack Acustico...")
    print("=" * 60)

    # 1. Room Tones (60s cada para loops confortáveis)
    rt_dir = RAW_DIR / "room-tones"
    print("\n[1/4] Gerando Room Tones (60s)...")
    save_wav(rt_dir / "estudio_podcast_01.wav", generate_room_tone(60.0, hum_freq=60.0))
    print("  - estudio_podcast_01.wav (60s)")
    save_wav(rt_dir / "estudio_podcast_02.wav", generate_room_tone(60.0, hum_freq=120.0))
    print("  - estudio_podcast_02.wav (60s)")
    save_wav(rt_dir / "escritorio_ac_leve.wav", generate_room_tone(60.0, ac_noise=True))
    print("  - escritorio_ac_leve.wav (60s)")

    # 2. Foley Escritório (Speech-Concurrent)
    fol_esc = RAW_DIR / "foley" / "escritorio"
    print("\n[2/4] Gerando Foley de Fala (speech-concurrent)...")
    save_wav(fol_esc / "mouse_click_01.wav", generate_mouse_click(1))
    save_wav(fol_esc / "mouse_click_02.wav", generate_mouse_click(2))
    save_wav(fol_esc / "mouse_click_03.wav", generate_mouse_click(3))
    print("  - 3 cliques de mouse (variacoes 1, 2, 3)")

    save_wav(fol_esc / "teclado_curto_01.wav", generate_key_tap(1))
    save_wav(fol_esc / "teclado_curto_02.wav", generate_key_tap(2))
    save_wav(fol_esc / "teclado_longo_01.wav", np.concatenate([generate_key_tap(1), generate_key_tap(2), generate_key_tap(3)]))
    print("  - 3 toques de teclado (curto 1, curto 2, longo)")

    save_wav(fol_esc / "cadeira_range_01.wav", generate_chair_creak())
    save_wav(fol_esc / "papel_vira_01.wav", generate_paper_turn())
    save_wav(fol_esc / "caneta_mesa_01.wav", generate_pen_tap())
    print("  - cadeira_range_01, papel_vira_01, caneta_mesa_01")

    # 3. Foley Pausa / Transição (Pause-Transition)
    print("\n[3/4] Gerando Foley de Pausa (pause-transition)...")
    save_wav(fol_esc / "gole_agua_01.wav", generate_water_sip())
    save_wav(fol_esc / "limpar_garganta_01.wav", generate_throat_clear())
    save_wav(fol_esc / "respiracao_sutil_01.wav", generate_subtle_breath())
    print("  - gole_agua_01, limpar_garganta_01, respiracao_sutil_01")

    # 4. Impulse Responses (Cola Acústica de Sala Tratada)
    ir_dir = RAW_DIR / "impulse-responses"
    print("\n[4/4] Gerando Impulse Responses (IR)...")
    save_wav(ir_dir / "small_studio_01.wav", generate_studio_impulse_response(0.22))
    save_wav(ir_dir / "small_studio_02.wav", generate_studio_impulse_response(0.28))
    print("  - small_studio_01.wav (RT60 = 0.22s)")
    print("  - small_studio_02.wav (RT60 = 0.28s)")

    print("\n" + "=" * 60)
    print("Starter pack gerado com sucesso em:")
    print(f"   {RAW_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
