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


def test_full_pipeline_with_mock_ambience(tmp_path):
    """Testa fluxo completo: prepare -> humanize com biblioteca sintética."""
    raw_dir = tmp_path / "audio" / "ambience" / "raw"
    prep_dir = tmp_path / "audio" / "ambience" / "prepared"

    # Criar room tone cru
    rt_dir = raw_dir / "room-tones"
    rt_dir.mkdir(parents=True, exist_ok=True)
    _create_sine_wav(rt_dir / "estudio_01.wav", freq=60.0, duration_s=5.0)

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
