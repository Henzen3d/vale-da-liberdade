"""FASE 4 — Sincronia fina por word-timestamps (Whisper)

O build_scene_timeline estima t0/t1 dos beats pela proporção de palavras do
roteiro (~95% de precisão). Esta fase opcional transcreve o áudio final já
renderizado (Gemini/Edge TTS) com faster-whisper e recalcula os limites dos
beats a partir dos timestamps reais das palavras.

É pós-processamento: não mexe no provedor de TTS ativo, não regenera áudio.
Roda só quando o episódio já tem áudio final + timeline.

Fluxo:
    beats = build_scene_timeline(...)
    fixed = align_beats_to_audio(beats, audio_mp3, roteiro_bloco_textos)

Saída: mesma lista de SceneBeat com t0/t1 ajustados, + campo `aligned_by`
("proporcao" | "whisper") para diagnóstico.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")

# tolerância: se a duração whisper divergir mais que isto da duração do áudio,
# os word-timestamps não são confiáveis (corte, idioma errado) — mantém o original.
MAX_DRIFT_RATIO = 0.15


def transcribe_words(audio_path: Path) -> list[dict[str, Any]]:
    """Transcreve com word_timestamps=True. Retorna [{word, start, end}]."""
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        language="pt",
        vad_filter=True,
        beam_size=1,
        word_timestamps=True,
    )
    words: list[dict[str, Any]] = []
    for seg in segments:
        for w in seg.words or []:
            txt = (w.word or "").strip()
            if not txt:
                continue
            words.append({"word": txt, "start": float(w.start), "end": float(w.end)})
    return words


def _norm_token(w: str) -> str:
    return _WORD_RE.findall((w or "").lower())[-1] if _WORD_RE.findall((w or "").lower()) else ""


def align_beats_to_audio(
    beats: list[Any],
    audio_path: Path,
    block_texts: list[str],
    *,
    cache_dir: Path | None = None,
) -> list[Any]:
    """Recalcula t0/t1 dos beats com word-timestamps reais do áudio final.

    block_texts[i] é o texto (falado) correspondente ao beats[i], na mesma ordem.
    Faz casamento por palavra-guia: encontra no transcript a primeira ocorrência
    da palavra de abertura de cada bloco após o final do bloco anterior.
    """
    if not beats or not audio_path or not Path(audio_path).exists():
        return beats

    # Cache de transcript por hash do áudio (evita re-transcrever no re-render)
    words: list[dict[str, Any]] | None = None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            import hashlib

            h = hashlib.md5(Path(audio_path).read_bytes()).hexdigest()
            cache_file = cache_dir / f"whisper-words-{h}.json"
            if cache_file.exists():
                words = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — cache é best-effort
            words = None

    if words is None:
        try:
            words = transcribe_words(Path(audio_path))
        except Exception as exc:  # noqa: BLE001 — whisper indisponível/falhou
            print(f"  ⚠️ Fase 4: Whisper falhou ({exc}) — mantendo timing por proporção")
            return beats

    if cache_dir and words:
        try:
            import hashlib

            h = hashlib.md5(Path(audio_path).read_bytes()).hexdigest()
            (cache_dir / f"whisper-words-{h}.json").write_text(
                json.dumps(words, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    audio_dur = words[-1]["end"] if words else 0.0
    est_dur = beats[-1].t1 if beats else 0.0
    if not audio_dur or abs(audio_dur - est_dur) / max(audio_dur, 1.0) > MAX_DRIFT_RATIO:
        print(
            f"  ⚠️ Fase 4: duração whisper={audio_dur:.1f}s vs timeline={est_dur:.1f}s "
            f"— divergência > {MAX_DRIFT_RATIO:.0%}, mantendo proporção"
        )
        return beats

    # Índice de busca no transcript: ponteiro global que só avança
    search_from = 0
    out = []
    for i, beat in enumerate(beats):
        if i >= len(block_texts):
            out.append(beat)
            continue
        text = block_texts[i] or ""
        tokens = [_norm_token(t) for t in _WORD_RE.findall(text)]
        # palavra-guia: primeiro token significativo (>= 3 chars) do bloco
        guide = next((t for t in tokens if len(t) >= 3), "")

        new_t0 = None
        if guide:
            for j in range(search_from, len(words)):
                if _norm_token(words[j]["word"]) == guide:
                    new_t0 = words[j]["start"]
                    search_from = j + 1
                    break
        if new_t0 is None:
            out.append(beat)  # não casou — preserva timing original
            continue
        # t1 do beat = t0 do próximo bloco casado, ou final do áudio no último
        out.append(replace(beat, t0=round(new_t0, 2), aligned_by="whisper"))

    # segunda passada: t1 de cada beat = t0 do próximo (ou duração do áudio),
    # e beats não-alinhados são interpolados entre os vizinhos alinhados para
    # garantir monotonicidade estrita (um beat antigo nunca pode recuar).
    for i in range(len(out)):
        nxt = out[i + 1].t0 if i + 1 < len(out) else audio_dur
        if out[i].t0 < nxt:
            out[i] = replace(out[i], t1=round(nxt, 2))

    # interpola beats não-alinhados entre os alinhados mais próximos
    aligned_idx = [i for i, b in enumerate(out) if getattr(b, "aligned_by", "") == "whisper"]
    if aligned_idx and len(out) > 1:
        for i, b in enumerate(out):
            if getattr(b, "aligned_by", "") == "whisper":
                continue
            prev_i = max([j for j in aligned_idx if j < i], default=None)
            next_i = min([j for j in aligned_idx if j > i], default=None)
            if prev_i is None and next_i is not None:
                # antes do primeiro alinhado: distribui proporcionalmente
                span = out[next_i].t0 / (next_i + 1)
                new_t0 = round(span * (i + 1), 2)
            elif next_i is None and prev_i is not None:
                # depois do último alinhado: distribui o tempo restante
                remaining = audio_dur - out[prev_i].t0
                span = remaining / (len(out) - prev_i)
                new_t0 = round(out[prev_i].t0 + span * (i - prev_i), 2)
            elif prev_i is not None and next_i is not None:
                lo, hi = out[prev_i].t0, out[next_i].t0
                frac = (i - prev_i) / (next_i - prev_i)
                new_t0 = round(lo + (hi - lo) * frac, 2)
            else:
                continue
            nxt = out[i + 1].t0 if i + 1 < len(out) else audio_dur
            out[i] = replace(out[i], t0=new_t0, t1=round(max(nxt, new_t0), 2))

    aligned = sum(1 for b in out if getattr(b, "aligned_by", "") == "whisper")
    print(f"  🎯 Fase 4: {aligned}/{len(out)} beats alinhados por word-timestamps")
    return out
