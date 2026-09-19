#!/usr/bin/env python3
"""Studio Humanizer — Humanização Acústica do Estúdio Virtual.

Adiciona camadas orgânicas (Room Tone, Foley contextual e Cola Acústica)
ao pipeline de voz do Vale da Liberdade, mantendo isolamento dinâmico
(sem noise pumping) e alta performance via scipy.signal.oaconvolve.

Uso CLI:
    python scripts/studio_humanizer.py prepare
    python scripts/studio_humanizer.py humanize --input audio.wav --output out.wav
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Humanizer] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("studio_humanizer")

# Tentar importar dependências opcionais/dsp
try:
    import yaml
except ImportError:
    yaml = None  # Fallback manual de configuração se yaml não estiver disponível

try:
    from scipy.signal import butter, oaconvolve, resample_poly, sosfilt
except ImportError:
    butter = None
    oaconvolve = None
    resample_poly = None
    sosfilt = None


def find_project_root() -> Path:
    """Encontra o diretório raiz do projeto."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "config").exists() and (parent / "scripts").exists():
            return parent
    return current.parent


PROJECT_ROOT = find_project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "studio_humanizer.yaml"


class StudioHumanizer:
    """Motor de humanização e pré-processamento de áudio acústico."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        cfg_file = Path(config_path or DEFAULT_CONFIG_PATH)
        self.cfg = self._load_config(cfg_file)

        # Respeitar flags de ambiente para overrides rápidos
        self.enabled = self._get_bool_env(
            "STUDIO_HUMANIZER_ENABLED", self.cfg.get("enabled", True)
        )
        self.profile = os.getenv(
            "STUDIO_HUMANIZER_PROFILE", self.cfg.get("profile", "escritorio")
        )

        prep_cfg = self.cfg.get("prepare", {})
        self.raw_dir = self.project_root / prep_cfg.get("raw_dir", "audio/ambience/raw")
        self.prepared_dir = self.project_root / prep_cfg.get(
            "prepared_dir", "audio/ambience/prepared"
        )
        self.auto_prepare = prep_cfg.get("auto_prepare", True)

        self.sample_rate = int(self.cfg.get("output", {}).get("sample_rate", 44100))

    def _load_config(self, cfg_file: Path) -> dict[str, Any]:
        """Carrega configuração YAML ou defaults estruturados."""
        if cfg_file.exists() and yaml is not None:
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                log.warning(f"Erro ao ler {cfg_file}: {e}. Usando configuração padrão.")

        # Fallback padrão
        return {
            "enabled": True,
            "profile": "escritorio",
            "prepare": {
                "raw_dir": "audio/ambience/raw",
                "prepared_dir": "audio/ambience/prepared",
                "auto_prepare": True,
            },
            "room_tone": {
                "enabled": True,
                "volume_db": -30.0,
                "crossfade_s": 4.0,
                "fade_in_s": 2.0,
                "fade_out_s": 3.0,
                "breathing": {"enabled": True, "amplitude_db": 1.5, "period_s": 25.0},
            },
            "voice_warmth": {
                "enabled": true,
                "hpf_hz": 80.0,
                "warmth_boost_hz": 220.0,
                "warmth_boost_db": 1.5,
                "warmth_q": 1.2,
                "harshness_cut_hz": 6000.0,
                "harshness_cut_db": -1.8,
                "harshness_q": 1.5,
            },
            "outdoor": {
                "enabled": True,
                "volume_db": -42.0,
                "crossfade_s": 5.0,
                "eq": {"highpass_hz": 60.0, "lowpass_hz": 1800.0},
            },
            "foley": {
                "enabled": True,
                "volume_db": -35.0,
                "volume_variation_db": 3.0,
                "events_per_minute_min": 2,
                "events_per_minute_max": 5,
                "min_gap_s": 3.0,
                "speaker_change_exclusion_ms": 500,
                "silence_detection": {"threshold_db": -40.0, "window_ms": 150},
                "ducking": {
                    "enabled": True,
                    "depth_db": -1.2,
                    "attack_ms": 25,
                    "release_ms": 100,
                },
                "pre_speech_breaths": {
                    "enabled": True,
                    "min_pause_s": 0.5,
                    "min_speech_s": 2.5,
                    "lead_time_s": 0.35,
                    "volume_db": -36.0,
                },
            },
            "reverb": {
                "enabled": False,
                "wet_mix": 0.015,
                "pre_delay_ms": 18,
            },
            "output": {"sample_rate": 44100, "bit_depth": 16, "channels": 1},
        }

    @staticmethod
    def _get_bool_env(var_name: str, default: bool) -> bool:
        val = os.getenv(var_name)
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "on"}

    # ── DSP Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def read_wav(path: Path | str, target_sr: int = 44100) -> tuple[int, np.ndarray]:
        """Lê um arquivo WAV mono/estéreo e converte para float32 mono [-1.0, 1.0]."""
        with wave.open(str(path), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            raw_bytes = wf.readframes(frames)

        if width == 2:
            data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        elif width == 1:
            data = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif width == 3:
            # 24-bit PCM
            a24 = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(-1, 3)
            # expand to 32-bit signed
            padded = np.pad(a24, ((0, 0), (1, 0)), "constant", constant_values=0)
            data = (padded.view(np.int32).flatten() >> 8).astype(np.float32) / 8388608.0
        elif width == 4:
            data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Largura de amostra não suportada: {width} bytes")

        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)

        # Resample se necessário
        if rate != target_sr and resample_poly is not None:
            gcd = math.gcd(rate, target_sr)
            up = target_sr // gcd
            down = rate // gcd
            data = resample_poly(data, up, down).astype(np.float32)
            rate = target_sr

        return rate, data

    @staticmethod
    def write_wav(path: Path | str, data: np.ndarray, rate: int = 44100) -> None:
        """Salva array float32 em WAV 16-bit mono com proteção anti-clipping."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        clipped = np.clip(data, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm16.tobytes())

    @staticmethod
    def apply_filters(
        data: np.ndarray,
        sr: int,
        hpf_hz: float | None = None,
        lpf_hz: float | None = None,
    ) -> np.ndarray:
        """Aplica filtros passa-alta e passa-baixa Butterworth estáveis."""
        if butter is None or sosfilt is None or len(data) < 32:
            return data

        out = data.copy()
        nyquist = 0.5 * sr

        if hpf_hz and 0 < hpf_hz < nyquist:
            sos = butter(2, hpf_hz / nyquist, btype="highpass", output="sos")
            out = sosfilt(sos, out)

        if lpf_hz and 0 < lpf_hz < nyquist:
            sos = butter(2, lpf_hz / nyquist, btype="lowpass", output="sos")
            out = sosfilt(sos, out)

        return out.astype(np.float32)

    @staticmethod
    def apply_peaking_eq(
        data: np.ndarray,
        sr: int,
        freq_hz: float,
        gain_db: float,
        q: float = 1.0,
    ) -> np.ndarray:
        """Aplica filtro paramétrico peaking (bell) analógico bi-quad estável (RBJ Cookbook)."""
        if sosfilt is None or len(data) < 32 or abs(gain_db) < 0.05:
            return data

        nyquist = 0.5 * sr
        if not (20.0 < freq_hz < nyquist):
            return data

        w0 = 2.0 * math.pi * (freq_hz / sr)
        alpha = math.sin(w0) / (2.0 * max(0.1, q))
        A = 10.0 ** (gain_db / 40.0)

        b0 = 1.0 + alpha * A
        b1 = -2.0 * math.cos(w0)
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * math.cos(w0)
        a2 = 1.0 - alpha / A

        sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)
        filtered = sosfilt(sos, data.astype(np.float64))
        return filtered.astype(np.float32)

    def apply_voice_warmth(self, voice: np.ndarray, sr: int) -> np.ndarray:
        """Aplica calor broadcast e de-harshing anti-plástico na voz sintetizada."""
        vw_cfg = self.cfg.get("voice_warmth", {})
        if not vw_cfg.get("enabled", True):
            return voice

        out = voice.copy()
        hpf = float(vw_cfg.get("hpf_hz", 80.0))
        if hpf > 20.0:
            out = self.apply_filters(out, sr, hpf_hz=hpf)

        wb_hz = float(vw_cfg.get("warmth_boost_hz", 220.0))
        wb_db = float(vw_cfg.get("warmth_boost_db", 1.5))
        wb_q = float(vw_cfg.get("warmth_q", 1.2))
        if abs(wb_db) > 0.05:
            out = self.apply_peaking_eq(out, sr, wb_hz, wb_db, wb_q)

        hc_hz = float(vw_cfg.get("harshness_cut_hz", 6000.0))
        hc_db = float(vw_cfg.get("harshness_cut_db", -1.8))
        hc_q = float(vw_cfg.get("harshness_q", 1.5))
        if abs(hc_db) > 0.05:
            out = self.apply_peaking_eq(out, sr, hc_hz, hc_db, hc_q)

        return out

    @staticmethod
    def compute_rms_envelope(
        signal: np.ndarray, sr: int, window_ms: int = 150
    ) -> np.ndarray:
        """Calcula curva de RMS em dBFS ao longo do sinal."""
        win_size = max(16, int(sr * (window_ms / 1000.0)))
        pad_size = (win_size - (len(signal) % win_size)) % win_size
        padded = np.pad(signal, (0, pad_size), mode="constant")
        reshaped = padded.reshape(-1, win_size)
        rms = np.sqrt(np.mean(reshaped**2, axis=1) + 1e-12)
        rms_db = 20.0 * np.log10(np.maximum(rms, 1e-6))
        # Expandir para ter resolução por bloco
        return rms_db

    # ── Fase 0: Prepare ──────────────────────────────────────────────────────

    def prepare(self, force: bool = False) -> dict[str, Any]:
        """Processa sons brutos de raw/ e gera prepared/ com manifesto."""
        log.info("Iniciando FASE PREPARE do Studio Humanizer...")
        self.prepared_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "version": "1.0",
            "sample_rate": self.sample_rate,
            "room_tones": [],
            "outdoor": [],
            "foley": [],
            "impulse_responses": [],
        }

        # 1. Room Tones
        raw_rt_dir = self.raw_dir / "room-tones"
        prep_rt_dir = self.prepared_dir / "room-tones"
        prep_rt_dir.mkdir(parents=True, exist_ok=True)

        rt_cfg = self.cfg.get("room_tone", {}).get("eq", {})
        hpf = rt_cfg.get("highpass_hz", 100)
        lpf = rt_cfg.get("lowpass_hz", 3500)

        if raw_rt_dir.exists():
            for f in sorted(raw_rt_dir.glob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                audio = audio - np.mean(audio)
                audio = self.apply_filters(audio, sr, hpf_hz=hpf, lpf_hz=lpf)
                peak = np.max(np.abs(audio)) + 1e-9
                audio = (audio / peak) * 0.5

                dest = prep_rt_dir / f.name
                self.write_wav(dest, audio, sr)
                manifest["room_tones"].append({
                    "name": f.stem,
                    "file": str(dest.relative_to(self.project_root)),
                    "duration_s": round(len(audio) / sr, 2),
                })
                log.info(f"  [Room Tone preparado] {f.name}")

        # 2. Outdoor Muffled (Ambiente externo abafado < 2kHz)
        raw_out_dir = self.raw_dir / "outdoor"
        prep_out_dir = self.prepared_dir / "outdoor"
        prep_out_dir.mkdir(parents=True, exist_ok=True)

        out_eq = self.cfg.get("outdoor", {}).get("eq", {})
        o_hpf = out_eq.get("highpass_hz", 60.0)
        o_lpf = out_eq.get("lowpass_hz", 1800.0)

        if raw_out_dir.exists():
            for f in sorted(raw_out_dir.glob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                audio = audio - np.mean(audio)
                audio = self.apply_filters(audio, sr, hpf_hz=o_hpf, lpf_hz=o_lpf)
                peak = np.max(np.abs(audio)) + 1e-9
                audio = (audio / peak) * 0.5

                dest = prep_out_dir / f.name
                self.write_wav(dest, audio, sr)
                manifest["outdoor"].append({
                    "name": f.stem,
                    "file": str(dest.relative_to(self.project_root)),
                    "duration_s": round(len(audio) / sr, 2),
                })
                log.info(f"  [Outdoor preparado] {f.name}")

        # 3. Foley
        raw_fol_dir = self.raw_dir / "foley"
        prep_fol_dir = self.prepared_dir / "foley"
        prep_fol_dir.mkdir(parents=True, exist_ok=True)

        fol_eq = self.cfg.get("foley", {}).get("eq", {})
        f_hpf = fol_eq.get("highpass_hz", 100)
        f_lpf = fol_eq.get("lowpass_hz", 6500)

        if raw_fol_dir.exists():
            for f in sorted(raw_fol_dir.rglob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                audio = audio - np.mean(audio)
                audio = self.apply_filters(audio, sr, hpf_hz=f_hpf, lpf_hz=f_lpf)
                peak = np.max(np.abs(audio)) + 1e-9
                audio = (audio / peak) * 0.5

                rel_sub = f.relative_to(raw_fol_dir)
                dest = prep_fol_dir / rel_sub
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.write_wav(dest, audio, sr)

                is_pause = any(k in f.stem.lower() for k in ["agua", "garganta", "respiracao"])
                manifest["foley"].append({
                    "name": f.stem,
                    "category": "pause_transition" if is_pause else "speech_concurrent",
                    "file": str(dest.relative_to(self.project_root)),
                    "duration_s": round(len(audio) / sr, 3),
                })
                log.info(f"  [Foley preparado] {f.name} ({'pause' if is_pause else 'speech'})")

        # 4. Impulse Responses
        raw_ir_dir = self.raw_dir / "impulse-responses"
        prep_ir_dir = self.prepared_dir / "ir"
        prep_ir_dir.mkdir(parents=True, exist_ok=True)

        ir_eq = self.cfg.get("reverb", {}).get("ir_eq", {})
        ir_hpf = ir_eq.get("highpass_hz", 350)
        ir_lpf = ir_eq.get("lowpass_hz", 3500)

        if raw_ir_dir.exists():
            for f in sorted(raw_ir_dir.glob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                audio = audio - np.mean(audio)
                audio = self.apply_filters(audio, sr, hpf_hz=ir_hpf, lpf_hz=ir_lpf)
                peak = np.max(np.abs(audio)) + 1e-9
                norm = audio / peak
                thresh = 10 ** (-60.0 / 20.0)
                above = np.where(np.abs(norm) > thresh)[0]
                if len(above) > 0:
                    last_idx = min(len(norm), above[-1] + int(sr * 0.05))
                    norm = norm[:last_idx]

                dest = prep_ir_dir / f.name
                self.write_wav(dest, norm * 0.5, sr)
                manifest["impulse_responses"].append({
                    "name": f.stem,
                    "file": str(dest.relative_to(self.project_root)),
                    "duration_s": round(len(norm) / sr, 3),
                })
                log.info(f"  [IR preparado] {f.name}")

        manifest_path = self.prepared_dir / "_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        total_files = (
            len(manifest["room_tones"])
            + len(manifest["outdoor"])
            + len(manifest["foley"])
            + len(manifest["impulse_responses"])
        )
        log.info(f"✅ Prepare concluído! {total_files} arquivos processados em {self.prepared_dir}")
        return manifest

    # ── Montagem e Humanização por Episódio ───────────────────────────────────

    def _assemble_room_tone(
        self, target_samples: int, voice_rms_db: float
    ) -> np.ndarray:
        """Carrega e monta o Room Tone em loop com crossfade e breathing."""
        rt_cfg = self.cfg.get("room_tone", {})
        if not rt_cfg.get("enabled", True):
            return np.zeros(target_samples, dtype=np.float32)

        prep_rt_dir = self.prepared_dir / "room-tones"
        rt_files = list(prep_rt_dir.glob("*.wav")) if prep_rt_dir.exists() else []

        if not rt_files:
            return np.zeros(target_samples, dtype=np.float32)

        rt_file = random.choice(rt_files)
        sr, rt_data = self.read_wav(rt_file, self.sample_rate)

        cf_s = float(rt_cfg.get("crossfade_s", 4.0))
        cf_samples = int(sr * cf_s)

        assembled: list[np.ndarray] = []
        cur_samples = 0

        while cur_samples < target_samples:
            if not assembled:
                assembled.append(rt_data)
                cur_samples += len(rt_data)
            else:
                if len(rt_data) > cf_samples:
                    fade_out = np.linspace(1.0, 0.0, cf_samples, dtype=np.float32)
                    fade_in = np.linspace(0.0, 1.0, cf_samples, dtype=np.float32)

                    tail = assembled[-1][-cf_samples:] * fade_out
                    head = rt_data[:cf_samples] * fade_in
                    assembled[-1] = assembled[-1][:-cf_samples]
                    assembled.append(tail + head)
                    assembled.append(rt_data[cf_samples:])
                    cur_samples = sum(len(x) for x in assembled)
                else:
                    assembled.append(rt_data)
                    cur_samples += len(rt_data)

        full_rt = np.concatenate(assembled)[:target_samples]

        # Breathing sinusoidal (±1.2 dB)
        b_cfg = rt_cfg.get("breathing", {})
        if b_cfg.get("enabled", True):
            amp_db = float(b_cfg.get("amplitude_db", 1.2))
            period_s = float(b_cfg.get("period_s", 25.0))
            t = np.arange(target_samples) / sr
            mod_db = amp_db * np.sin(2 * np.pi * t / period_s)
            gain_mod = 10 ** (mod_db / 20.0)
            full_rt = full_rt * gain_mod.astype(np.float32)

        # Fade in e Fade out
        fade_in_s = float(rt_cfg.get("fade_in_s", 2.0))
        fade_out_s = float(rt_cfg.get("fade_out_s", 3.0))
        in_samps = min(target_samples, int(sr * fade_in_s))
        out_samps = min(target_samples, int(sr * fade_out_s))

        if in_samps > 0:
            full_rt[:in_samps] *= np.linspace(0.0, 1.0, in_samps, dtype=np.float32)
        if out_samps > 0:
            full_rt[-out_samps:] *= np.linspace(1.0, 0.0, out_samps, dtype=np.float32)

        target_db = float(rt_cfg.get("volume_db", -38.0))
        rt_rms = np.sqrt(np.mean(full_rt**2) + 1e-12)
        rt_rms_db = 20.0 * np.log10(rt_rms)
        desired_rms_db = voice_rms_db + target_db
        gain = 10 ** ((desired_rms_db - rt_rms_db) / 20.0)

        return full_rt * gain

    def _assemble_outdoor(
        self, target_samples: int, voice_rms_db: float
    ) -> np.ndarray:
        """Carrega e monta o ambiente externo abafado em loop suave (profundidade 3D)."""
        o_cfg = self.cfg.get("outdoor", {})
        if not o_cfg.get("enabled", True):
            return np.zeros(target_samples, dtype=np.float32)

        prep_out_dir = self.prepared_dir / "outdoor"
        out_files = list(prep_out_dir.glob("*.wav")) if prep_out_dir.exists() else []
        if not out_files:
            return np.zeros(target_samples, dtype=np.float32)

        out_file = random.choice(out_files)
        sr, out_data = self.read_wav(out_file, self.sample_rate)

        cf_s = float(o_cfg.get("crossfade_s", 5.0))
        cf_samples = int(sr * cf_s)

        assembled: list[np.ndarray] = []
        cur_samples = 0

        while cur_samples < target_samples:
            if not assembled:
                assembled.append(out_data)
                cur_samples += len(out_data)
            else:
                if len(out_data) > cf_samples:
                    fade_out = np.linspace(1.0, 0.0, cf_samples, dtype=np.float32)
                    fade_in = np.linspace(0.0, 1.0, cf_samples, dtype=np.float32)
                    tail = assembled[-1][-cf_samples:] * fade_out
                    head = out_data[:cf_samples] * fade_in
                    assembled[-1] = assembled[-1][:-cf_samples]
                    assembled.append(tail + head)
                    assembled.append(out_data[cf_samples:])
                    cur_samples = sum(len(x) for x in assembled)
                else:
                    assembled.append(out_data)
                    cur_samples += len(out_data)

        full_out = np.concatenate(assembled)[:target_samples]

        fade_s = 3.0
        fade_samples = min(target_samples // 4, int(sr * fade_s))
        if fade_samples > 0:
            full_out[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            full_out[-fade_samples:] *= np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)

        target_db = float(o_cfg.get("volume_db", -42.0))
        o_rms = np.sqrt(np.mean(full_out**2) + 1e-12)
        o_rms_db = 20.0 * np.log10(o_rms)
        desired_rms_db = voice_rms_db + target_db
        gain = 10 ** ((desired_rms_db - o_rms_db) / 20.0)

        return full_out * gain

    def _apply_reverb(self, voice: np.ndarray) -> np.ndarray:
        """Aplica convolução com IR via Overlap-Add de baixo uso de memória."""
        r_cfg = self.cfg.get("reverb", {})
        if not r_cfg.get("enabled", False) or oaconvolve is None:
            return voice

        prep_ir_dir = self.prepared_dir / "ir"
        ir_files = list(prep_ir_dir.glob("*.wav")) if prep_ir_dir.exists() else []
        if not ir_files:
            return voice

        preferred = r_cfg.get("preferred_ir")
        ir_file = None
        if preferred:
            for f in ir_files:
                if f.name == preferred:
                    ir_file = f
                    break
        if not ir_file:
            ir_file = random.choice(ir_files)

        sr, ir_data = self.read_wav(ir_file, self.sample_rate)

        pre_delay_ms = float(r_cfg.get("pre_delay_ms", 18.0))
        pre_delay_samples = int(sr * (pre_delay_ms / 1000.0))
        if pre_delay_samples > 0:
            ir_data = np.pad(ir_data, (pre_delay_samples, 0), mode="constant")

        wet_signal = oaconvolve(voice, ir_data, mode="full")[: len(voice)].astype(
            np.float32
        )
        wet_signal = self.apply_filters(wet_signal, sr, hpf_hz=350.0, lpf_hz=3500.0)

        wet_mix = float(r_cfg.get("wet_mix", 0.015))
        return (voice + (wet_mix * wet_signal)).astype(np.float32)

    def _schedule_foley(
        self,
        target_samples: int,
        voice_rms_db: float,
        envelope: np.ndarray,
        turn_boundaries: list[float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Distribui eventos incidentais de Foley, respirações e envelope de ducking."""
        f_cfg = self.cfg.get("foley", {})
        if not f_cfg.get("enabled", True):
            return np.zeros(target_samples, dtype=np.float32), np.ones(target_samples, dtype=np.float32)

        prep_fol_dir = self.prepared_dir / "foley"
        if not prep_fol_dir.exists():
            return np.zeros(target_samples, dtype=np.float32), np.ones(target_samples, dtype=np.float32)

        sr = self.sample_rate
        total_minutes = target_samples / (sr * 60.0)
        events_min = int(f_cfg.get("events_per_minute_min", 2))
        events_max = int(f_cfg.get("events_per_minute_max", 4))
        num_events = int(round(random.uniform(events_min, events_max) * total_minutes))

        manifest_path = self.prepared_dir / "_manifest.json"
        categories: dict[str, list[Path]] = {
            "speech_concurrent": [],
            "pause_transition": [],
        }

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    data = json.load(mf)
                for item in data.get("foley", []):
                    cat = item.get("category", "speech_concurrent")
                    p = self.project_root / item["file"]
                    if p.exists():
                        categories[cat].append(p)
            except Exception:
                pass

        if not categories["speech_concurrent"] and not categories["pause_transition"]:
            for f in prep_fol_dir.rglob("*.wav"):
                is_pause = any(k in f.stem.lower() for k in ["agua", "garganta", "respiracao"])
                if is_pause:
                    categories["pause_transition"].append(f)
                else:
                    categories["speech_concurrent"].append(f)

        if not categories["speech_concurrent"] and not categories["pause_transition"]:
            return np.zeros(target_samples, dtype=np.float32), np.ones(target_samples, dtype=np.float32)

        out_foley = np.zeros(target_samples, dtype=np.float32)
        min_gap_s = float(f_cfg.get("min_gap_s", 3.0))
        silence_thresh = float(
            f_cfg.get("silence_detection", {}).get("threshold_db", -40.0)
        )
        base_vol_db = float(f_cfg.get("volume_db", -38.0))
        var_vol_db = float(f_cfg.get("volume_variation_db", 3.0))
        win_ms = float(f_cfg.get("silence_detection", {}).get("window_ms", 150))
        win_samples = max(16, int(sr * (win_ms / 1000.0)))

        placed_times: list[float] = []

        # ── 1. Injeção de Respirações Pré-Fala Contextuais ──────────────────
        breath_cfg = f_cfg.get("pre_speech_breaths", {})
        if breath_cfg.get("enabled", True) and categories["pause_transition"]:
            breath_files = [f for f in categories["pause_transition"] if "respiracao" in f.stem.lower()]
            if not breath_files:
                breath_files = categories["pause_transition"]

            min_pause_s = float(breath_cfg.get("min_pause_s", 0.5))
            min_speech_s = float(breath_cfg.get("min_speech_s", 2.5))
            lead_time_s = float(breath_cfg.get("lead_time_s", 0.35))
            b_vol_db = float(breath_cfg.get("volume_db", -36.0))

            min_pause_blocks = max(1, int(min_pause_s / (win_ms / 1000.0)))
            min_speech_blocks = max(2, int(min_speech_s / (win_ms / 1000.0)))

            is_speaking = envelope >= silence_thresh
            pause_count = 0

            for b_idx in range(len(is_speaking)):
                if not is_speaking[b_idx]:
                    pause_count += 1
                else:
                    if pause_count >= min_pause_blocks:
                        speech_len = 0
                        for k in range(b_idx, min(len(is_speaking), b_idx + min_speech_blocks + 1)):
                            if is_speaking[k]:
                                speech_len += 1
                            else:
                                break
                        if speech_len >= min_speech_blocks:
                            speech_start_t = (b_idx * win_samples) / sr
                            breath_t = speech_start_t - lead_time_s
                            if breath_t > 0.8 and not any(abs(breath_t - p) < min_gap_s for p in placed_times):
                                b_file = random.choice(breath_files)
                                _, b_data = self.read_wav(b_file, sr)
                                b_sample_idx = int(breath_t * sr)
                                b_rms = np.sqrt(np.mean(b_data**2) + 1e-12)
                                b_gain = 10 ** ((voice_rms_db + b_vol_db - (20.0 * np.log10(b_rms))) / 20.0)
                                end_b = min(target_samples, b_sample_idx + len(b_data))
                                out_foley[b_sample_idx:end_b] += b_data[:end_b - b_sample_idx] * b_gain
                                placed_times.append(breath_t)
                    pause_count = 0

        # ── 2. Eventos Aleatórios de Foley (teclado, mouse, papel, etc.) ────
        attempts = 0
        max_attempts = max(20, num_events * 6)

        while len(placed_times) < num_events and attempts < max_attempts:
            attempts += 1
            t_sec = random.uniform(2.0, max(2.0, (target_samples / sr) - 4.0))

            if any(abs(t_sec - p) < min_gap_s for p in placed_times):
                continue

            if turn_boundaries:
                excl_s = float(f_cfg.get("speaker_change_exclusion_ms", 500)) / 1000.0
                if any(abs(t_sec - tb) < excl_s for tb in turn_boundaries):
                    continue

            sample_idx = int(t_sec * sr)
            block_idx = min(len(envelope) - 1, sample_idx // win_samples)
            current_rms_db = envelope[block_idx]

            is_pause = current_rms_db < silence_thresh
            pool = categories["pause_transition"] if is_pause else categories["speech_concurrent"]
            if not pool:
                pool = categories["speech_concurrent"] or categories["pause_transition"]
            if not pool:
                continue

            chosen_file = random.choice(pool)
            _, f_data = self.read_wav(chosen_file, sr)

            vol_offset = random.uniform(-var_vol_db, var_vol_db)
            event_db = voice_rms_db + base_vol_db + vol_offset
            f_rms = np.sqrt(np.mean(f_data**2) + 1e-12)
            f_rms_db = 20.0 * np.log10(f_rms)
            gain = 10 ** ((event_db - f_rms_db) / 20.0)

            end_idx = min(target_samples, sample_idx + len(f_data))
            fit_len = end_idx - sample_idx
            out_foley[sample_idx:end_idx] += f_data[:fit_len] * gain

            placed_times.append(t_sec)

        # ── 3. Envelope de Micro-Sidechain Ducking ─────────────────────────
        duck_cfg = f_cfg.get("ducking", {})
        duck_enabled = bool(duck_cfg.get("enabled", True))
        duck_depth_db = float(duck_cfg.get("depth_db", -1.2))
        duck_attack_s = float(duck_cfg.get("attack_ms", 25)) / 1000.0
        duck_release_s = float(duck_cfg.get("release_ms", 100)) / 1000.0
        duck_ratio = float(10.0 ** (duck_depth_db / 20.0))

        ducking_gain = np.ones(target_samples, dtype=np.float32)

        if duck_enabled and placed_times:
            att_samps = max(1, int(sr * duck_attack_s))
            rel_samps = max(1, int(sr * duck_release_s))

            for t_ev in placed_times:
                s_idx = int(t_ev * sr)
                if s_idx < 0 or s_idx >= target_samples:
                    continue
                att_start = max(0, s_idx - att_samps)
                if att_start < s_idx:
                    seg_len = s_idx - att_start
                    ramp_down = np.linspace(1.0, duck_ratio, seg_len, dtype=np.float32)
                    ducking_gain[att_start:s_idx] = np.minimum(ducking_gain[att_start:s_idx], ramp_down)
                rel_end = min(target_samples, s_idx + rel_samps)
                if s_idx < rel_end:
                    seg_len = rel_end - s_idx
                    ramp_up = np.linspace(duck_ratio, 1.0, seg_len, dtype=np.float32)
                    ducking_gain[s_idx:rel_end] = np.minimum(ducking_gain[s_idx:rel_end], ramp_up)

        return out_foley, ducking_gain

    def humanize(
        self,
        input_wav: Path | str,
        output_wav: Path | str | None = None,
        turn_boundaries: list[float] | None = None,
    ) -> Path:
        """Aplica camadas completas de humanização acústica sobre um arquivo WAV."""
        in_path = Path(input_wav).resolve()
        out_path = Path(output_wav or in_path).resolve()

        if not self.enabled:
            log.info("Studio Humanizer desabilitado via configuração.")
            return in_path

        prep_rt = self.prepared_dir / "room-tones"
        if not prep_rt.exists() or not list(prep_rt.glob("*.wav")):
            if self.auto_prepare and self.raw_dir.exists():
                log.info("Pasta prepared/ vazia. Rodando prepare() automático...")
                try:
                    self.prepare()
                except Exception as prep_exc:
                    log.warning(f"Auto-prepare falhou: {prep_exc}. Prosseguindo sem humanização.")
                    return in_path
            else:
                log.warning("Nenhum som preparado encontrado em audio/ambience/prepared/. Bypassando.")
                return in_path

        log.info(f"Humanizando áudio com cadeia broadcast: {in_path.name}...")
        try:
            sr, voice = self.read_wav(in_path, self.sample_rate)
            if len(voice) < sr:
                log.warning("Áudio muito curto para humanização. Bypassando.")
                return in_path

            # RMS médio da voz
            v_rms = np.sqrt(np.mean(voice**2) + 1e-12)
            voice_rms_db = 20.0 * np.log10(v_rms)

            # 1. Warmth analógico e de-harshing anti-plástico na voz
            voice_shaped = self.apply_voice_warmth(voice, sr)

            # 2. Cola acústica (reverb na voz, se configurado)
            voice_glued = self._apply_reverb(voice_shaped)

            # 3. Room Tone contínuo de estúdio
            room = self._assemble_room_tone(len(voice), voice_rms_db)

            # 4. Ambiente externo abafado (profundidade 3D: trânsito/pássaros < 2kHz)
            outdoor = self._assemble_outdoor(len(voice), voice_rms_db)

            # 5. Foley inteligente com respirações contextuais e micro-ducking
            envelope = self.compute_rms_envelope(voice, sr)
            foley, ducking_gain = self._schedule_foley(len(voice), voice_rms_db, envelope, turn_boundaries)

            # Aplicar micro-ducking na voz durante foleys
            voice_glued = voice_glued * ducking_gain

            # 6. Soma de todas as camadas acústicas
            mixed = voice_glued + room + outdoor + foley

            peak = np.max(np.abs(mixed))
            if peak > 0.98:
                mixed = (mixed / peak) * 0.98

            self.write_wav(out_path, mixed, sr)
            log.info(f"✅ Áudio humanizado com sucesso → {out_path.name}")
            return out_path

        except Exception as e:
            log.error(f"Falha na humanização do áudio: {e}. Retornando original.")
            return in_path


# ── CLI Interface ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Studio Humanizer CLI")
    subparsers = parser.add_subparsers(dest="command")

    # prepare
    subparsers.add_parser("prepare", help="Pré-processa arquivos de raw/ para prepared/")

    # humanize
    h_parser = subparsers.add_parser("humanize", help="Humaniza um arquivo WAV")
    h_parser.add_argument("--input", "-i", required=True, help="Arquivo WAV de entrada")
    h_parser.add_argument("--output", "-o", help="Arquivo WAV de saída (default: in-place)")
    h_parser.add_argument("--profile", help="Perfil acústico ('escritorio' ou 'residencial')")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    humanizer = StudioHumanizer()

    if getattr(args, "profile", None):
        humanizer.profile = args.profile

    if args.command == "prepare":
        manifest = humanizer.prepare()
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    if args.command == "humanize":
        out = humanizer.humanize(args.input, args.output)
        print(f"Humanizado: {out}")
        return 0

    print("Comando não especificado. Use --help para opções.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
