#!/usr/bin/env python3
"""
Fallback TTS #3 — MOSS-TTS-Nano com duas vozes (Peter / Ricardo) via voice clone.

Cadeia do pipeline (cmd_audio):
  1) Gemini multi-TTS
  2) MOSS-TTS-Nano (este script)
  3) Edge TTS + FX Ricardo

Uso (venv moss-nano-env):
  /home/osmar/moss-nano-env/bin/python scripts/tts_fallback_moss.py --date 2026-07-22
  /home/osmar/moss-nano-env/bin/python scripts/tts_fallback_moss.py --date 2026-07-22 --limit 4
  /home/osmar/moss-nano-env/bin/python scripts/tts_fallback_moss.py \\
      --text "Olá Ricardo" --speaker Ricardo --out /tmp/r.wav

Config: config/moss_tts.yaml
Vozes: voices/moss/peter_ref.wav · voices/moss/ricardo_ref.wav
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CFG = ROOT / "config" / "moss_tts.yaml"
NANO_REPO = Path(os.environ.get("MOSS_NANO_REPO", "/home/osmar/MOSS-TTS-Nano"))

# Prefer project scripts for optional Ricardo FX
sys.path.insert(0, str(ROOT / "scripts"))
# MOSS-TTS-Nano package (editable install) + local modules
if NANO_REPO.exists():
    sys.path.insert(0, str(NANO_REPO))


def load_cfg(path: Path) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "python": "/home/osmar/moss-nano-env/bin/python",
        "model_path": "OpenMOSS-Team/MOSS-TTS-Nano",
        "audio_tokenizer_path": "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano",
        "device": "cpu",
        "dtype": "float32",
        "voices": {
            "Peter": "voices/moss/peter_ref.wav",
            "Ricardo": "voices/moss/ricardo_ref.wav",
        },
        "max_chars_per_chunk": 180,
        "min_words": 3,
        "min_chunk_bytes": 6000,
        "min_final_bytes": 1_000_000,
        "max_new_frames": 280,
        "voice_clone_max_text_tokens": 60,
        "apply_ricardo_fx": False,
        "disable_wetext": True,
    }
    if not path.exists():
        return defaults
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    cfg = defaults.copy()
    for k, v in data.items():
        if k == "voices" and isinstance(v, dict):
            cfg["voices"] = {**defaults["voices"], **v}
        else:
            cfg[k] = v
    return cfg


def resolve_voice(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"Referência de voz ausente: {p}")
    return p


class MossNanoBackend:
    """Carrega MOSS-TTS-Nano uma vez e clona voz por referência WAV."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.model = None
        self.device = None
        self.dtype = None

    def load(self) -> None:
        if self.model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM

        # import helpers from local nano repo if present
        sys.path.insert(0, str(NANO_REPO))
        from moss_tts_nano.defaults import (  # type: ignore
            DEFAULT_AUDIO_TOKENIZER_PATH,
            DEFAULT_CHECKPOINT_PATH,
        )

        # patch infer helpers by copying minimal resolve from infer.py
        device_s = str(self.cfg.get("device") or "cpu")
        if device_s == "auto":
            device_s = "cuda" if torch.cuda.is_available() else "cpu"
        if device_s.startswith("cuda") and not torch.cuda.is_available():
            device_s = "cpu"
        self.device = torch.device(device_s)

        dtype_s = str(self.cfg.get("dtype") or "float32")
        if dtype_s == "auto":
            self.dtype = torch.float32 if self.device.type == "cpu" else torch.bfloat16
        else:
            self.dtype = {
                "float32": torch.float32,
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
            }.get(dtype_s, torch.float32)

        ckpt = self.cfg.get("model_path") or DEFAULT_CHECKPOINT_PATH
        print(f"[moss] Loading {ckpt} on {self.device} ({self.dtype})...")
        t0 = time.time()
        # Same load path as MOSS-TTS-Nano/infer.py::load_model
        self.model = AutoModelForCausalLM.from_pretrained(
            ckpt,
            trust_remote_code=True,
        )
        self.model.to(device=self.device, dtype=self.dtype)
        if hasattr(self.model, "_set_attention_implementation"):
            self.model._set_attention_implementation("sdpa")
        self.model.eval()
        if not self.cfg.get("audio_tokenizer_path"):
            self.cfg["audio_tokenizer_path"] = DEFAULT_AUDIO_TOKENIZER_PATH
        print(f"[moss] Ready in {time.time() - t0:.1f}s")

    def synthesize(self, text: str, reference_wav: Path, out_wav: Path) -> Path:
        self.load()
        assert self.model is not None
        text = text.strip()
        if not text:
            raise ValueError("texto vazio")
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        tok = self.cfg.get("audio_tokenizer_path") or "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano"
        result = self.model.inference(
            text=text,
            output_audio_path=str(out_wav),
            mode="voice_clone",
            prompt_text=None,
            prompt_audio_path=str(reference_wav),
            reference_audio_path=None,
            text_tokenizer_path=None,
            audio_tokenizer_type="moss-audio-tokenizer-nano",
            audio_tokenizer_pretrained_name_or_path=tok,
            device=self.device,
            nq=None,
            max_new_frames=int(self.cfg.get("max_new_frames", 280)),
            voice_clone_max_text_tokens=int(self.cfg.get("voice_clone_max_text_tokens", 60)),
            voice_clone_max_memory_per_sample_gb=1.0,
            do_sample=True,
            use_kv_cache=True,
        )
        path = Path(result.get("audio_path") or out_wav)
        if not path.exists():
            raise RuntimeError("MOSS não gravou áudio")
        if path.resolve() != out_wav.resolve():
            # copy/move to requested path
            out_wav.write_bytes(path.read_bytes())
        return out_wav


def parse_tts_lines(path: Path, min_words: int = 3) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        speaker = "Ricardo"
        text = line
        m = re.match(r"^(Peter|Ricardo)\s*:\s*(.*)$", line, re.I)
        if m:
            speaker = "Peter" if m.group(1).lower() == "peter" else "Ricardo"
            text = m.group(2).strip()
        text = re.sub(r"\[PAUSA(?:_CURTA)?\]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text.split()) < min_words:
            continue
        turns.append((speaker, text))
    return turns


def split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    buf = ""
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if not s:
            continue
        if len(buf) + len(s) + 1 <= max_chars:
            buf = f"{buf} {s}".strip()
        else:
            if buf:
                parts.append(buf)
            if len(s) <= max_chars:
                buf = s
            else:
                for i in range(0, len(s), max_chars):
                    chunk = s[i : i + max_chars].strip()
                    if chunk:
                        parts.append(chunk)
                buf = ""
    if buf:
        parts.append(buf)
    return parts or [text[:max_chars]]


def wav_to_mp3(wav: Path, mp3: Path) -> None:
    # MOSS nano often outputs 48k stereo — downmix mono 44.1k
    cmd = [
        "ffmpeg", "-y", "-i", str(wav),
        "-ar", "44100", "-ac", "1",
        "-codec:a", "libmp3lame", "-b:a", "192k",
        str(mp3),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0 or not mp3.exists():
        raise RuntimeError(f"ffmpeg wav→mp3: {proc.stderr.decode()[:250]}")


def concat_mp3s(paths: list[Path], out_mp3: Path) -> None:
    lst = out_mp3.with_suffix(".filelist.txt")
    lst.write_text("\n".join(f"file '{p.resolve()}'" for p in paths) + "\n", encoding="utf-8")
    tmp = out_mp3.with_suffix(".concat.mp3")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(tmp)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat: {proc.stderr.decode()[:250]}")
    proc2 = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(tmp),
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "192k", str(out_mp3),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    tmp.unlink(missing_ok=True)
    if proc2.returncode != 0 or not out_mp3.exists():
        raise RuntimeError(f"ffmpeg loudnorm: {proc2.stderr.decode()[:250]}")


def run_episode(date: str, cfg: dict, limit: int | None = None) -> Path:
    if not cfg.get("enabled", True):
        raise RuntimeError("MOSS fallback desabilitado em config/moss_tts.yaml")

    episodes = ROOT / "episodes"
    audio_dir = ROOT / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts_txt = episodes / f"{date}-tts.txt"
    md = episodes / f"{date}.md"
    if not tts_txt.exists() and md.exists():
        hermes = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
        if hermes.exists():
            subprocess.run(
                [str(hermes), str(ROOT / "scripts/tts_preprocessor.py"),
                 "--input", str(md), "--output", str(tts_txt)],
                check=False,
            )
    if not tts_txt.exists():
        raise FileNotFoundError(f"Sem {tts_txt}")

    voices = {
        "Peter": resolve_voice(cfg["voices"]["Peter"]),
        "Ricardo": resolve_voice(cfg["voices"]["Ricardo"]),
    }
    print(f"[moss] Peter ref:   {voices['Peter']}")
    print(f"[moss] Ricardo ref: {voices['Ricardo']}")

    turns = parse_tts_lines(tts_txt, min_words=int(cfg.get("min_words", 3)))
    if limit:
        turns = turns[:limit]
    if not turns:
        raise RuntimeError("Nenhuma fala útil no TTS")

    backend = MossNanoBackend(cfg)
    backend.load()

    kept: list[Path] = []
    idx = 0
    max_chars = int(cfg.get("max_chars_per_chunk", 180))
    min_bytes = int(cfg.get("min_chunk_bytes", 6000))
    total_parts = sum(len(split_long_text(t, max_chars)) for _, t in turns)

    for speaker, text in turns:
        for part in split_long_text(text, max_chars):
            idx += 1
            tag = speaker.lower()
            wav = audio_dir / f"{date}-moss-{tag}-{idx:03d}.wav"
            mp3 = audio_dir / f"{date}-moss-{tag}-{idx:03d}.mp3"
            print(f"[moss] {idx}/{total_parts} {speaker}: {part[:70]}...")
            t0 = time.time()
            try:
                backend.synthesize(part, voices[speaker], wav)
                wav_to_mp3(wav, mp3)
                if speaker == "Ricardo" and cfg.get("apply_ricardo_fx"):
                    try:
                        from ricardo_voice_fx import process_file
                        fx = mp3.with_name(mp3.stem + "-fx.mp3")
                        process_file(mp3, fx)
                        if fx.exists() and fx.stat().st_size >= min_bytes:
                            mp3 = fx
                    except Exception as exc:
                        print(f"  ⚠ FX skip: {exc}")
                size = mp3.stat().st_size if mp3.exists() else 0
                if size < min_bytes:
                    print(f"  ⚠ pequeno ({size}B) skip")
                    continue
                kept.append(mp3)
                print(f"  ✓ {size}B · {time.time()-t0:.1f}s → {mp3.name}")
            except Exception as exc:
                print(f"  ✗ {exc}")

    if not kept:
        raise RuntimeError("Nenhum chunk MOSS gerado")
    if len(kept) < 3 and not limit:
        raise RuntimeError(f"Poucos chunks MOSS ({len(kept)})")

    final = audio_dir / f"{date}.mp3"
    named = audio_dir / f"{date}-vale-da-liberdade.mp3"
    print(f"[moss] Concat {len(kept)} chunks → {named}")
    concat_mp3s(kept, named)
    nbytes = named.stat().st_size
    if nbytes < int(cfg.get("min_final_bytes", 1_000_000)) and not limit:
        raise RuntimeError(f"MP3 final pequeno: {nbytes}B")
    final.write_bytes(named.read_bytes())
    print(f"✅ MOSS fallback OK: {final} ({nbytes} bytes, {len(kept)} chunks)")
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description="Fallback MOSS-TTS-Nano duas vozes")
    ap.add_argument("--date")
    ap.add_argument("--config", default=str(DEFAULT_CFG))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--text")
    ap.add_argument("--speaker", default="Peter", choices=["Peter", "Ricardo"])
    ap.add_argument("--out", default="/tmp/moss_smoke.wav")
    args = ap.parse_args()
    cfg = load_cfg(Path(args.config))

    if args.text:
        backend = MossNanoBackend(cfg)
        ref = resolve_voice(cfg["voices"][args.speaker])
        out = Path(args.out)
        wav = out if out.suffix.lower() == ".wav" else out.with_suffix(".wav")
        backend.synthesize(args.text, ref, wav)
        if out.suffix.lower() == ".mp3":
            wav_to_mp3(wav, out)
        print(f"✅ {out if out.exists() else wav}")
        return 0

    if not args.date:
        ap.error("--date ou --text obrigatório")
    try:
        run_episode(args.date, cfg, limit=args.limit or None)
        return 0
    except Exception as exc:
        print(f"❌ MOSS fallback falhou: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
