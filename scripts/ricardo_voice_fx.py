#!/usr/bin/env python3
"""
Pós-processamento vocal do Ricardo Souto (CPU-only).

Objetivo: diferenciar o timbre do Ricardo do Peter quando ambos usam a
mesma voz Edge TTS (pt-BR-AntonioNeural).

Pipeline de efeitos (ordem):
  1. Formant shift (pyworld) — principal
  2. Pitch shift (librosa) — sutil
  3. Time stretch (librosa) — cadência
  4. EQ + compressão + saturação leve (scipy/numpy)
  5. Normalize peak

Config: config/ricardo_voice_fx.yaml

CLI:
  python3 scripts/ricardo_voice_fx.py --in chunk.mp3 --out chunk_fx.mp3
  python3 scripts/ricardo_voice_fx.py --batch-dir audio/ --glob '*edge-ricardo-*.mp3'
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "ricardo_voice_fx.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_CONFIG
    if not path.exists():
        return _defaults()
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
    except Exception:
        # fallback mínimo se PyYAML ausente: parse key: value raso
        data = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            if line.startswith("-"):
                continue
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if not k or v.startswith("{") or v == "":
                continue
            if v.lower() in ("true", "false"):
                data[k] = v.lower() == "true"
            else:
                try:
                    data[k] = float(v) if "." in v else int(v)
                except ValueError:
                    data[k] = v.strip("'\"")
    cfg = _defaults()
    cfg.update({k: v for k, v in data.items() if not isinstance(v, dict)})
    if isinstance(data.get("eq"), dict):
        cfg["eq"].update(data["eq"])
    if isinstance(data.get("compress"), dict):
        cfg["compress"].update(data["compress"])
    return cfg


def _defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "formant_ratio": 0.88,
        "pitch_semitones": -2.5,
        "time_stretch": 0.94,
        "eq": {
            "highpass_hz": 70.0,
            "lowpass_hz": 12000.0,
            "presence_hz": 2800.0,
            "presence_db": -2.0,
            "body_hz": 180.0,
            "body_db": 1.5,
        },
        "compress": {
            "threshold_db": -22.0,
            "ratio": 2.5,
            "attack_ms": 20.0,
            "release_ms": 120.0,
            "makeup_db": 1.0,
        },
        "saturation": 0.06,
        "target_sr": 44100,
        "normalize_peak_db": -1.5,
        "debug_wav": False,
    }


def load_audio(path: Path, target_sr: int) -> tuple[np.ndarray, int]:
    import librosa
    import soundfile as sf

    try:
        y, sr = sf.read(str(path), always_2d=False)
        if y.ndim > 1:
            y = np.mean(y, axis=1)
        y = y.astype(np.float64)
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
    except Exception:
        y, sr = librosa.load(str(path), sr=target_sr, mono=True)
        y = y.astype(np.float64)
    # avoid pure silence crash
    if y.size < int(0.05 * sr):
        return y, sr
    peak = np.max(np.abs(y)) + 1e-12
    if peak > 1.0:
        y = y / peak
    return y, sr


def save_audio(path: Path, y: np.ndarray, sr: int) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.asarray(y, dtype=np.float64)
    peak = np.max(np.abs(y)) + 1e-12
    if peak > 1.0:
        y = y / peak
    # write wav then optional ffmpeg mp3
    if path.suffix.lower() == ".wav":
        sf.write(str(path), y, sr, subtype="PCM_16")
        return
    tmp = path.with_suffix(".tmp.wav")
    sf.write(str(tmp), y, sr, subtype="PCM_16")
    if path.suffix.lower() == ".mp3":
        import subprocess

        cmd = [
            "ffmpeg", "-y", "-i", str(tmp),
            "-codec:a", "libmp3lame", "-b:a", "192k",
            str(path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tmp.unlink(missing_ok=True)
        if proc.returncode != 0:
            # fallback: keep wav renamed
            wav_fallback = path.with_suffix(".wav")
            sf.write(str(wav_fallback), y, sr, subtype="PCM_16")
            raise RuntimeError(
                f"ffmpeg mp3 falhou; WAV em {wav_fallback}: {proc.stderr.decode()[:200]}"
            )
    else:
        sf.write(str(path), y, sr, subtype="PCM_16")
        tmp.unlink(missing_ok=True)


def formant_shift_pyworld(y: np.ndarray, sr: int, ratio: float) -> np.ndarray:
    """
    Desloca o envelope espectral (formantes) sem alterar F0 na mesma proporção.
    ratio < 1 → formantes mais baixos (timbre mais “cheio/grave”).
    """
    if abs(ratio - 1.0) < 1e-3 or y.size < sr // 10:
        return y

    import pyworld as pw

    x = np.ascontiguousarray(y, dtype=np.float64)
    # WORLD analysis
    f0, t = pw.harvest(x, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)

    # Resample spectral envelope along frequency axis
    n_frames, n_bins = sp.shape
    src_idx = np.arange(n_bins, dtype=np.float64)
    # map destination bin j to source j * ratio (ratio<1 pulls high freqs from higher bins → lower formants)
    # For formant down: stretch envelope so peaks move down
    # sp_new[j] = sp[j / ratio] clamped
    query = np.clip(src_idx / ratio, 0, n_bins - 1)
    i0 = np.floor(query).astype(int)
    i1 = np.minimum(i0 + 1, n_bins - 1)
    frac = query - i0
    sp_new = (1.0 - frac)[None, :] * sp[:, i0] + frac[None, :] * sp[:, i1]
    # keep energy roughly stable
    e_old = np.sum(sp, axis=1, keepdims=True) + 1e-12
    e_new = np.sum(sp_new, axis=1, keepdims=True) + 1e-12
    sp_new *= e_old / e_new

    f0 = np.ascontiguousarray(f0, dtype=np.float64)
    sp_new = np.ascontiguousarray(sp_new, dtype=np.float64)
    ap = np.ascontiguousarray(ap, dtype=np.float64)
    y_out = pw.synthesize(f0, sp_new, ap, sr)
    # match length
    if len(y_out) > len(x):
        y_out = y_out[: len(x)]
    elif len(y_out) < len(x):
        y_out = np.pad(y_out, (0, len(x) - len(y_out)))
    return y_out.astype(np.float64)


def pitch_shift_librosa(y: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    if abs(semitones) < 1e-3:
        return y
    import librosa

    return librosa.effects.pitch_shift(y=y.astype(np.float32), sr=sr, n_steps=semitones).astype(np.float64)


def time_stretch_librosa(y: np.ndarray, rate: float) -> np.ndarray:
    if abs(rate - 1.0) < 1e-3:
        return y
    import librosa

    # rate < 1 slower
    return librosa.effects.time_stretch(y=y.astype(np.float32), rate=rate).astype(np.float64)


def biquad_peaking(y: np.ndarray, sr: int, freq: float, gain_db: float, q: float = 1.0) -> np.ndarray:
    if abs(gain_db) < 1e-3:
        return y
    from scipy.signal import sosfilt, tf2sos
    # RBJ peaking EQ
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * freq / sr
    alpha = np.sin(w0) / (2 * q)
    cosw = np.cos(w0)
    b0 = 1 + alpha * A
    b1 = -2 * cosw
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * cosw
    a2 = 1 - alpha / A
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    sos = tf2sos(b, a)
    return sosfilt(sos, y)


def apply_eq(y: np.ndarray, sr: int, eq: dict) -> np.ndarray:
    from scipy.signal import butter, sosfilt

    hp = float(eq.get("highpass_hz") or 0)
    lp = float(eq.get("lowpass_hz") or 0)
    if hp > 0:
        sos = butter(2, hp, btype="highpass", fs=sr, output="sos")
        y = sosfilt(sos, y)
    if lp > 0 and lp < sr / 2:
        sos = butter(2, lp, btype="lowpass", fs=sr, output="sos")
        y = sosfilt(sos, y)
    y = biquad_peaking(y, sr, float(eq.get("body_hz", 180)), float(eq.get("body_db", 0)), q=0.8)
    y = biquad_peaking(y, sr, float(eq.get("presence_hz", 2800)), float(eq.get("presence_db", 0)), q=1.2)
    return y


def compress_simple(y: np.ndarray, sr: int, cfg: dict) -> np.ndarray:
    thr_db = float(cfg.get("threshold_db", -22))
    ratio = float(cfg.get("ratio", 2.5))
    atk = float(cfg.get("attack_ms", 20)) / 1000.0
    rel = float(cfg.get("release_ms", 120)) / 1000.0
    makeup = float(cfg.get("makeup_db", 0))

    thr = 10 ** (thr_db / 20.0)
    eps = 1e-12
    env = 0.0
    atk_c = np.exp(-1.0 / (atk * sr + eps))
    rel_c = np.exp(-1.0 / (rel * sr + eps))
    out = np.empty_like(y)
    for i, s in enumerate(y):
        a = abs(s)
        if a > env:
            env = atk_c * env + (1 - atk_c) * a
        else:
            env = rel_c * env + (1 - rel_c) * a
        if env > thr:
            # gain reduction
            over = env / thr
            gain = (over ** (1.0 / ratio - 1.0))
        else:
            gain = 1.0
        out[i] = s * gain
    if abs(makeup) > 1e-3:
        out *= 10 ** (makeup / 20.0)
    return out


def soft_saturate(y: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return y
    # amount 0..0.2 typical
    drive = 1.0 + amount * 8.0
    return np.tanh(y * drive) / np.tanh(drive)


def normalize_peak(y: np.ndarray, peak_db: float = -1.5) -> np.ndarray:
    peak = np.max(np.abs(y)) + 1e-12
    target = 10 ** (peak_db / 20.0)
    return y * (target / peak)


def process_array(y: np.ndarray, sr: int, cfg: dict) -> np.ndarray:
    if not cfg.get("enabled", True):
        return y
    if y.size < int(0.08 * sr):
        # too short — skip heavy DSP
        return y

    # 1) formant
    y = formant_shift_pyworld(y, sr, float(cfg.get("formant_ratio", 0.88)))
    # 2) pitch
    y = pitch_shift_librosa(y, sr, float(cfg.get("pitch_semitones", -2.5)))
    # 3) time stretch (cadence)
    y = time_stretch_librosa(y, float(cfg.get("time_stretch", 0.94)))
    # 4) EQ
    y = apply_eq(y, sr, cfg.get("eq") or {})
    # 5) compress + sat
    y = compress_simple(y, sr, cfg.get("compress") or {})
    y = soft_saturate(y, float(cfg.get("saturation", 0.0)))
    # 6) normalize
    y = normalize_peak(y, float(cfg.get("normalize_peak_db", -1.5)))
    return y


def process_file(
    in_path: Path,
    out_path: Path,
    config_path: Path | None = None,
    cfg: dict | None = None,
) -> Path:
    cfg = cfg or load_config(config_path)
    if not cfg.get("enabled", True):
        # copy through
        out_path.write_bytes(in_path.read_bytes())
        return out_path

    sr_t = int(cfg.get("target_sr") or 44100)
    y, sr = load_audio(in_path, sr_t)
    y_out = process_array(y, sr, cfg)
    save_audio(out_path, y_out, sr)
    if cfg.get("debug_wav"):
        save_audio(out_path.with_name(out_path.stem + "_debug.wav"), y_out, sr)
    return out_path


def process_if_ricardo(
    in_path: Path,
    out_path: Path | None = None,
    config_path: Path | None = None,
    force: bool = False,
) -> Path:
    """
    Aplica FX só se o nome do arquivo indicar Ricardo.
    Caso contrário, copia/retorna o original.
    """
    name = in_path.name.lower()
    is_ricardo = "ricardo" in name
    out = out_path or in_path
    if not is_ricardo and not force:
        if out != in_path:
            out.write_bytes(in_path.read_bytes())
        return in_path if out == in_path else out
    return process_file(in_path, out, config_path=config_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="FX vocal Ricardo (formant/pitch/EQ/CPU)")
    ap.add_argument("--in", dest="inp", help="Arquivo de entrada (.mp3/.wav)")
    ap.add_argument("--out", dest="out", help="Arquivo de saída")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="YAML de parâmetros")
    ap.add_argument("--batch-dir", help="Processa vários arquivos no diretório")
    ap.add_argument("--glob", default="*ricardo*.mp3", help="Glob no batch-dir")
    ap.add_argument("--inplace", action="store_true", help="Sobrescreve o arquivo de entrada")
    ap.add_argument("--force", action="store_true", help="Aplica mesmo sem 'ricardo' no nome")
    ap.add_argument("--print-config", action="store_true")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    if args.print_config:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return 0

    if args.batch_dir:
        d = Path(args.batch_dir)
        files = sorted(d.glob(args.glob))
        if not files:
            print(f"Nenhum arquivo em {d}/{args.glob}")
            return 1
        for f in files:
            if "ricardo" not in f.name.lower() and not args.force:
                continue
            out = f if args.inplace else f.with_name(f.stem + "_fx" + f.suffix)
            print(f"→ {f.name} → {out.name}")
            try:
                process_file(f, out, config_path=cfg_path, cfg=cfg)
            except Exception as exc:
                print(f"  FALHA: {exc}", file=sys.stderr)
        return 0

    if not args.inp:
        ap.error("--in ou --batch-dir é obrigatório")
    inp = Path(args.inp)
    if args.inplace:
        out = inp
    else:
        out = Path(args.out) if args.out else inp.with_name(inp.stem + "_fx" + inp.suffix)

    if "ricardo" not in inp.name.lower() and not args.force:
        print("AVISO: arquivo não parece Ricardo; use --force para processar assim mesmo")
        return 2

    process_file(inp, out, config_path=cfg_path, cfg=cfg)
    print(f"✅ {inp} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
