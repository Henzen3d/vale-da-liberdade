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
            "foley": {
                "enabled": True,
                "volume_db": -35.0,
                "volume_variation_db": 3.0,
                "events_per_minute_min": 2,
                "events_per_minute_max": 5,
                "min_gap_s": 3.0,
                "speaker_change_exclusion_ms": 500,
                "silence_detection": {"threshold_db": -40.0, "window_ms": 150},
            },
            "reverb": {
                "enabled": True,
                "wet_mix": 0.04,
                "pre_delay_ms": 10,
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
            "foley": [],
            "impulse_responses": [],
        }

        # 1. Room Tones
        raw_rt_dir = self.raw_dir / "room-tones"
        prep_rt_dir = self.prepared_dir / "room-tones"
        prep_rt_dir.mkdir(parents=True, exist_ok=True)

        rt_cfg = self.cfg.get("room_tone", {}).get("eq", {})
        hpf = rt_cfg.get("highpass_hz", 100)
        lpf = rt_cfg.get("lowpass_hz", 6000)

        if raw_rt_dir.exists():
            for f in sorted(raw_rt_dir.glob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                # Remover DC offset
                audio = audio - np.mean(audio)
                # Filtros
                audio = self.apply_filters(audio, sr, hpf_hz=hpf, lpf_hz=lpf)
                # Normalização peak a -6 dBFS (0.5 linear)
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

        # 2. Foley
        raw_fol_dir = self.raw_dir / "foley"
        prep_fol_dir = self.prepared_dir / "foley"
        prep_fol_dir.mkdir(parents=True, exist_ok=True)

        fol_eq = self.cfg.get("foley", {}).get("eq", {})
        f_hpf = fol_eq.get("highpass_hz", 100)
        f_lpf = fol_eq.get("lowpass_hz", 8000)

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

                # Classificar como speech_concurrent ou pause_transition
                is_pause = any(k in f.stem.lower() for k in ["agua", "garganta", "respiracao"])
                manifest["foley"].append({
                    "name": f.stem,
                    "category": "pause_transition" if is_pause else "speech_concurrent",
                    "file": str(dest.relative_to(self.project_root)),
                    "duration_s": round(len(audio) / sr, 3),
                })
                log.info(f"  [Foley preparado] {f.name} ({'pause' if is_pause else 'speech'})")

        # 3. Impulse Responses
        raw_ir_dir = self.raw_dir / "impulse-responses"
        prep_ir_dir = self.prepared_dir / "ir"
        prep_ir_dir.mkdir(parents=True, exist_ok=True)

        ir_eq = self.cfg.get("reverb", {}).get("ir_eq", {})
        ir_hpf = ir_eq.get("highpass_hz", 200)
        ir_lpf = ir_eq.get("lowpass_hz", 8000)

        if raw_ir_dir.exists():
            for f in sorted(raw_ir_dir.glob("*.wav")):
                sr, audio = self.read_wav(f, self.sample_rate)
                audio = audio - np.mean(audio)
                audio = self.apply_filters(audio, sr, hpf_hz=ir_hpf, lpf_hz=ir_lpf)
                # Truncar cauda a -60 dBFS
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
        prep_rt_dir = self.prepared_dir / "room-tones"
        rt_files = list(prep_rt_dir.glob("*.wav")) if prep_rt_dir.exists() else []

        if not rt_files:
            return np.zeros(target_samples, dtype=np.float32)

        # Selecionar arquivo
        rt_file = random.choice(rt_files)
        sr, rt_data = self.read_wav(rt_file, self.sample_rate)

        # Loop com crossfade
        cf_s = float(self.cfg.get("room_tone", {}).get("crossfade_s", 4.0))
        cf_samples = int(sr * cf_s)

        assembled: list[np.ndarray] = []
        cur_samples = 0

        while cur_samples < target_samples:
            if not assembled:
                assembled.append(rt_data)
                cur_samples += len(rt_data)
            else:
                # Crossfade
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

        # Breathing sinusoidal (±1.5 dB)
        b_cfg = self.cfg.get("room_tone", {}).get("breathing", {})
        if b_cfg.get("enabled", True):
            amp_db = float(b_cfg.get("amplitude_db", 1.5))
            period_s = float(b_cfg.get("period_s", 25.0))
            t = np.arange(target_samples) / sr
            # modulação em ganho linear
            mod_db = amp_db * np.sin(2 * np.pi * t / period_s)
            gain_mod = 10 ** (mod_db / 20.0)
            full_rt = full_rt * gain_mod.astype(np.float32)

        # Fade in e Fade out
        fade_in_s = float(self.cfg.get("room_tone", {}).get("fade_in_s", 2.0))
        fade_out_s = float(self.cfg.get("room_tone", {}).get("fade_out_s", 3.0))
        in_samps = min(target_samples, int(sr * fade_in_s))
        out_samps = min(target_samples, int(sr * fade_out_s))

        if in_samps > 0:
            full_rt[:in_samps] *= np.linspace(0.0, 1.0, in_samps, dtype=np.float32)
        if out_samps > 0:
            full_rt[-out_samps:] *= np.linspace(1.0, 0.0, out_samps, dtype=np.float32)

        # Ajuste de volume relativo à voz
        target_db = float(self.cfg.get("room_tone", {}).get("volume_db", -30.0))
        rt_rms = np.sqrt(np.mean(full_rt**2) + 1e-12)
        rt_rms_db = 20.0 * np.log10(rt_rms)
        desired_rms_db = voice_rms_db + target_db
        gain = 10 ** ((desired_rms_db - rt_rms_db) / 20.0)

        return full_rt * gain

    def _apply_reverb(self, voice: np.ndarray) -> np.ndarray:
        """Aplica convolução com IR via Overlap-Add de baixo uso de memória."""
        r_cfg = self.cfg.get("reverb", {})
        if not r_cfg.get("enabled", True) or oaconvolve is None:
            return voice

        prep_ir_dir = self.prepared_dir / "ir"
        ir_files = list(prep_ir_dir.glob("*.wav")) if prep_ir_dir.exists() else []
        if not ir_files:
            return voice

        ir_file = ir_files[0]
        sr, ir_data = self.read_wav(ir_file, self.sample_rate)

        # Pre-delay (15-20ms afasta o reverb para eliminar comb filtering / som de lata)
        pre_delay_ms = float(r_cfg.get("pre_delay_ms", 18.0))
        pre_delay_samples = int(sr * (pre_delay_ms / 1000.0))
        if pre_delay_samples > 0:
            ir_data = np.pad(ir_data, (pre_delay_samples, 0), mode="constant")

        # Overlap-add convolução ultrarrápida
        wet_signal = oaconvolve(voice, ir_data, mode="full")[: len(voice)].astype(
            np.float32
        )

        # High-pass a 350Hz no sinal de reverb: impede cancelamento de fase nos graves da voz
        wet_signal = self.apply_filters(wet_signal, sr, hpf_hz=350.0, lpf_hz=3500.0)

        wet_mix = float(r_cfg.get("wet_mix", 0.015))
        # Preserva 100% da voz original (peso, corpo e graves intactos) + toque sutil de cola
        return (voice + (wet_mix * wet_signal)).astype(np.float32)

    def _schedule_foley(
        self,
        target_samples: int,
        voice_rms_db: float,
        envelope: np.ndarray,
        turn_boundaries: list[float] | None = None,
    ) -> np.ndarray:
        """Distribui eventos incidentais de Foley conforme contexto de fala vs pausa."""
        f_cfg = self.cfg.get("foley", {})
        if not f_cfg.get("enabled", True):
            return np.zeros(target_samples, dtype=np.float32)

        prep_fol_dir = self.prepared_dir / "foley"
        if not prep_fol_dir.exists():
            return np.zeros(target_samples, dtype=np.float32)

        sr = self.sample_rate
        total_minutes = target_samples / (sr * 60.0)
        events_min = int(f_cfg.get("events_per_minute_min", 2))
        events_max = int(f_cfg.get("events_per_minute_max", 5))
        num_events = int(round(random.uniform(events_min, events_max) * total_minutes))

        if num_events == 0:
            return np.zeros(target_samples, dtype=np.float32)

        # Carregar pool de arquivos por categoria
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

        # Fallback de busca se manifesto estiver vazio
        if not categories["speech_concurrent"] and not categories["pause_transition"]:
            for f in prep_fol_dir.rglob("*.wav"):
                is_pause = any(k in f.stem.lower() for k in ["agua", "garganta", "respiracao"])
                if is_pause:
                    categories["pause_transition"].append(f)
                else:
                    categories["speech_concurrent"].append(f)

        if not categories["speech_concurrent"] and not categories["pause_transition"]:
            return np.zeros(target_samples, dtype=np.float32)

        out_foley = np.zeros(target_samples, dtype=np.float32)
        min_gap_s = float(f_cfg.get("min_gap_s", 3.0))
        silence_thresh = float(
            f_cfg.get("silence_detection", {}).get("threshold_db", -40.0)
        )
        base_vol_db = float(f_cfg.get("volume_db", -35.0))
        var_vol_db = float(f_cfg.get("volume_variation_db", 3.0))
        win_ms = float(f_cfg.get("silence_detection", {}).get("window_ms", 150))
        win_samples = max(16, int(sr * (win_ms / 1000.0)))

        # Sorteio de tempos potenciais
        placed_times: list[float] = []
        attempts = 0
        max_attempts = num_events * 5

        while len(placed_times) < num_events and attempts < max_attempts:
            attempts += 1
            t_sec = random.uniform(2.0, max(2.0, (target_samples / sr) - 4.0))

            # Respeitar min_gap
            if any(abs(t_sec - p) < min_gap_s for p in placed_times):
                continue

            # Respeitar turn_boundaries (troca de locutor Peter/Ricardo)
            if turn_boundaries:
                excl_s = float(f_cfg.get("speaker_change_exclusion_ms", 500)) / 1000.0
                if any(abs(t_sec - tb) < excl_s for tb in turn_boundaries):
                    continue

            # Verificar se t_sec cai em fala ou silêncio
            sample_idx = int(t_sec * sr)
            block_idx = min(len(envelope) - 1, sample_idx // win_samples)
            current_rms_db = envelope[block_idx]

            is_pause = current_rms_db < silence_thresh

            # Escolher arquivo apropriado para o contexto
            pool = categories["pause_transition"] if is_pause else categories["speech_concurrent"]
            if not pool:
                pool = categories["speech_concurrent"] or categories["pause_transition"]
            if not pool:
                continue

            chosen_file = random.choice(pool)
            _, f_data = self.read_wav(chosen_file, sr)

            # Ajuste de ganho para o evento
            vol_offset = random.uniform(-var_vol_db, var_vol_db)
            event_db = voice_rms_db + base_vol_db + vol_offset
            f_rms = np.sqrt(np.mean(f_data**2) + 1e-12)
            f_rms_db = 20.0 * np.log10(f_rms)
            gain = 10 ** ((event_db - f_rms_db) / 20.0)

            end_idx = min(target_samples, sample_idx + len(f_data))
            fit_len = end_idx - sample_idx
            out_foley[sample_idx:end_idx] += f_data[:fit_len] * gain

            placed_times.append(t_sec)

        return out_foley

    def humanize(
        self,
        input_wav: Path | str,
        output_wav: Path | str | None = None,
        turn_boundaries: list[float] | None = None,
    ) -> Path:
        """Aplica camadas de humanização sobre um arquivo de voz WAV."""
        in_path = Path(input_wav).resolve()
        out_path = Path(output_wav or in_path).resolve()

        if not self.enabled:
            log.info("Studio Humanizer desabilitado via configuração.")
            return in_path

        # Se prepared/ não existe ou vazio, tentar auto_prepare
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

        log.info(f"Humanizando áudio: {in_path.name}...")
        try:
            sr, voice = self.read_wav(in_path, self.sample_rate)
            if len(voice) < sr:
                log.warning("Áudio muito curto para humanização. Bypassando.")
                return in_path

            # RMS médio da voz
            v_rms = np.sqrt(np.mean(voice**2) + 1e-12)
            voice_rms_db = 20.0 * np.log10(v_rms)

            # 1. Cola acústica (reverb na voz)
            voice_glued = self._apply_reverb(voice)

            # 2. Room Tone contínuo
            room = self._assemble_room_tone(len(voice), voice_rms_db)

            # 3. Foley inteligente
            envelope = self.compute_rms_envelope(voice, sr)
            foley = self._schedule_foley(len(voice), voice_rms_db, envelope, turn_boundaries)

            # 4. Soma das camadas com checagem anti-clipping
            mixed = voice_glued + room + foley

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
