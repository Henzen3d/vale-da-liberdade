import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from studio_humanizer import StudioHumanizer


def _create_sine_wav(path: Path, freq: float = 440.0, duration_s: float = 2.0, sr: int = 44100) -> Path:
    """Cria um arquivo WAV com onda senoidal para teste."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    StudioHumanizer.write_wav(path, sig, rate=sr)
    return path


def test_config_loading_and_env_override(monkeypatch):
    """Testa se a configuração carrega e se as variáveis de ambiente sobrescrevem."""
    monkeypatch.setenv("STUDIO_HUMANIZER_ENABLED", "false")
    monkeypatch.setenv("STUDIO_HUMANIZER_PROFILE", "residencial")

    h = StudioHumanizer()
    assert h.enabled is False
    assert h.profile == "residencial"


def test_wav_io_mono_resample(tmp_path):
    """Testa leitura, conversão para float32 e escrita."""
    test_wav = tmp_path / "test.wav"
    _create_sine_wav(test_wav, freq=440.0, duration_s=1.0, sr=44100)

    sr, data = StudioHumanizer.read_wav(test_wav, target_sr=44100)
    assert sr == 44100
    assert len(data) == 44100
    assert np.max(np.abs(data)) > 0.1

    out_wav = tmp_path / "out.wav"
    StudioHumanizer.write_wav(out_wav, data, rate=44100)
    assert out_wav.exists()
    assert out_wav.stat().st_size > 1000


def test_filters_stability():
    """Testa filtros Butterworth passa-alta e passa-baixa."""
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # Sinal com componente de 50 Hz (grave) e 10 kHz (agudo)
    signal = (0.5 * np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 10000 * t)).astype(np.float32)

    filtered = StudioHumanizer.apply_filters(signal, sr, hpf_hz=100, lpf_hz=6000)
    assert len(filtered) == len(signal)
    assert not np.isnan(filtered).any()
    # A energia total deve diminuir após cortar 50Hz e 10kHz
    assert np.var(filtered) < np.var(signal)


def test_failsafe_on_missing_ambience(tmp_path):
    """Testa se o humanizer faz bypass seguro e limpo quando a pasta de ambiência está vazia."""
    voice_wav = tmp_path / "voice.wav"
    _create_sine_wav(voice_wav, freq=220.0, duration_s=3.0, sr=44100)

    # Humanizer apontando para diretório vazio
    h = StudioHumanizer(project_root=tmp_path)
    result = h.humanize(voice_wav)

    assert result == voice_wav
    assert result.exists()


def test_voice_warmth_peaking_eq():
    """Testa se o peaking EQ e voice warmth aplicam ganho/corte estáveis."""
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig_220 = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    sig_6000 = (0.5 * np.sin(2 * np.pi * 6000.0 * t)).astype(np.float32)

    # Boost de +3dB em 220Hz deve aumentar a energia do tom 220Hz
    boosted = StudioHumanizer.apply_peaking_eq(sig_220, sr, freq_hz=220.0, gain_db=3.0, q=1.2)
    assert np.var(boosted) > np.var(sig_220)

    # Corte de -3dB em 6000Hz deve diminuir a energia do tom 6000Hz
    cut = StudioHumanizer.apply_peaking_eq(sig_6000, sr, freq_hz=6000.0, gain_db=-3.0, q=1.5)
    assert np.var(cut) < np.var(sig_6000)

    # Testar apply_voice_warmth
    h = StudioHumanizer()
    composite = sig_220 + sig_6000
    warmed = h.apply_voice_warmth(composite, sr)
    assert len(warmed) == len(composite)
    assert not np.isnan(warmed).any()


def test_full_pipeline_with_mock_ambience(tmp_path):
    """Testa fluxo completo: prepare -> humanize com biblioteca sintética (room, outdoor, foley, IR)."""
    raw_dir = tmp_path / "audio" / "ambience" / "raw"
    prep_dir = tmp_path / "audio" / "ambience" / "prepared"

    # Criar room tone cru
    rt_dir = raw_dir / "room-tones"
    rt_dir.mkdir(parents=True, exist_ok=True)
    _create_sine_wav(rt_dir / "estudio_01.wav", freq=60.0, duration_s=5.0)

    # Criar outdoor cru
    out_dir = raw_dir / "outdoor"
    out_dir.mkdir(parents=True, exist_ok=True)
    _create_sine_wav(out_dir / "transito_01.wav", freq=120.0, duration_s=5.0)

    # Criar foley cru (speech e pause)
    fol_dir = raw_dir / "foley"
    fol_dir.mkdir(parents=True, exist_ok=True)
    _create_sine_wav(fol_dir / "mouse_click_01.wav", freq=2000.0, duration_s=0.2)
    _create_sine_wav(fol_dir / "gole_agua_01.wav", freq=800.0, duration_s=0.5)

    # Criar IR cru
    ir_dir = raw_dir / "impulse-responses"
    ir_dir.mkdir(parents=True, exist_ok=True)
    _create_sine_wav(ir_dir / "small_studio_01.wav", freq=1000.0, duration_s=0.3)

    h = StudioHumanizer(project_root=tmp_path)
    h.raw_dir = raw_dir
    h.prepared_dir = prep_dir

    manifest = h.prepare()
    assert len(manifest["room_tones"]) == 1
    assert len(manifest["outdoor"]) == 1
    assert len(manifest["foley"]) == 2
    assert len(manifest["impulse_responses"]) == 1

    # Criar arquivo de voz de 10 segundos
    voice_wav = tmp_path / "speech.wav"
    _create_sine_wav(voice_wav, freq=300.0, duration_s=10.0)

    out_wav = tmp_path / "speech_humanized.wav"
    res = h.humanize(voice_wav, out_wav)

    assert res.exists()
    assert res.stat().st_size > 1000

    # Ler e checar que o áudio resultante é válido e não clipou
    sr, mixed = StudioHumanizer.read_wav(res)
    assert sr == 44100
    assert len(mixed) == 44100 * 10
    assert np.max(np.abs(mixed)) <= 1.0


def test_foley_ducking_and_breathing(tmp_path):
    """Testa se o agendamento de foley produz envelope de ducking e injeta respiração."""
    raw_dir = tmp_path / "audio" / "ambience" / "raw"
    prep_dir = tmp_path / "audio" / "ambience" / "prepared"
    fol_dir = raw_dir / "foley"
    fol_dir.mkdir(parents=True, exist_ok=True)

    _create_sine_wav(fol_dir / "mouse_click_01.wav", freq=2000.0, duration_s=0.1)
    _create_sine_wav(fol_dir / "respiracao_sutil_01.wav", freq=400.0, duration_s=0.4)

    h = StudioHumanizer(project_root=tmp_path)
    h.raw_dir = raw_dir
    h.prepared_dir = prep_dir
    h.prepare()

    sr = 44100
    target_samples = sr * 10
    # Envelope com pausa nos primeiros 2s, depois fala por 5s, depois pausa
    envelope = np.full(int(target_samples / (sr * 0.15)), -60.0, dtype=np.float32)
    # Bloco de fala do segundo 2 ao 8
    start_block = int(2.0 / 0.15)
    end_block = int(8.0 / 0.15)
    envelope[start_block:end_block] = -15.0

    foley, ducking = h._schedule_foley(target_samples, -20.0, envelope)
    assert len(foley) == target_samples
    assert len(ducking) == target_samples
    # Ducking deve ter valores <= 1.0
    assert np.min(ducking) <= 1.0
    assert np.max(ducking) <= 1.0
    assert not np.isnan(foley).any()
    assert not np.isnan(ducking).any()
