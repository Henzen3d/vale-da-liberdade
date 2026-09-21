#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Juiz Visual Pós-Render de Vídeo Broadcast (Fase 5).

Audita o arquivo MP4 final após a composição do apresentador e encerramento.
Extrai frames estratégicos com FFmpeg, verifica integridade técnica (resolução 1080p,
presença de áudio e vídeo, ausência de frames pretos/congelados) e emite video.qa.json.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("video_judge")

MIN_VIDEO_BYTES = 500_000  # 500 KB mínimo para um MP4 válido
MIN_FRAME_LUMINANCE_STDDEV = 6.0
MIN_FRAME_MEAN_BRIGHTNESS = 5.0
MAX_FRAME_MEAN_BRIGHTNESS = 250.0


def _probe_video_info(mp4_path: Path) -> dict[str, Any]:
    """Extrai informações de streams e duração do MP4 via ffprobe."""
    info: dict[str, Any] = {
        "width": 0,
        "height": 0,
        "duration": 0.0,
        "video_codec": None,
        "audio_codec": None,
        "has_video": False,
        "has_audio": False,
    }
    if not mp4_path.is_file():
        return info

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # Fallback básico caso ffprobe não esteja no path
        return info

    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "stream=width,height,codec_name,codec_type:format=duration",
        "-of", "json",
        str(mp4_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            fmt = data.get("format") or {}
            if "duration" in fmt:
                try:
                    info["duration"] = round(float(fmt["duration"]), 2)
                except ValueError:
                    pass

            for s in data.get("streams") or []:
                ctype = s.get("codec_type")
                if ctype == "video" and not info["has_video"]:
                    info["has_video"] = True
                    info["video_codec"] = s.get("codec_name")
                    info["width"] = int(s.get("width") or 0)
                    info["height"] = int(s.get("height") or 0)
                elif ctype == "audio" and not info["has_audio"]:
                    info["has_audio"] = True
                    info["audio_codec"] = s.get("codec_name")
    except Exception as exc:
        log.warning("ffprobe falhou ao inspecionar %s: %exc", mp4_path, exc)

    return info


def _extract_sample_frames(
    mp4_path: Path,
    timestamps: list[float],
    out_dir: Path,
) -> list[tuple[float, Path]]:
    """Extrai frames PNG do MP4 nos instantes especificados."""
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[tuple[float, Path]] = []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not mp4_path.is_file():
        return extracted

    for ts in timestamps:
        ts_clean = max(0.1, round(ts, 2))
        out_file = out_dir / f"frame_{int(ts_clean * 1000):06d}.png"
        cmd = [
            ffmpeg,
            "-y",
            "-ss", f"{ts_clean:.2f}",
            "-i", str(mp4_path),
            "-vframes", "1",
            "-q:v", "2",
            str(out_file),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, check=False, timeout=8)
            if res.returncode == 0 and out_file.is_file() and out_file.stat().st_size > 5000:
                extracted.append((ts_clean, out_file))
        except Exception:
            pass

    return extracted


def _audit_frame_pixels(frame_path: Path) -> dict[str, Any]:
    """Audita a variância e luminância de um frame para detectar telas pretas ou corrompidas."""
    res = {
        "valid_image": False,
        "stddev": 0.0,
        "mean": 0.0,
        "is_black": False,
        "is_blank": False,
    }
    if not frame_path.is_file():
        return res

    try:
        from PIL import Image, ImageStat

        with Image.open(frame_path) as im:
            im.verify()
        with Image.open(frame_path) as im:
            gray = im.convert("L")
            stat = ImageStat.Stat(gray)
            mean_val = float(stat.mean[0]) if stat.mean else 0.0
            std_val = float(stat.stddev[0]) if stat.stddev else 0.0
            res["valid_image"] = True
            res["mean"] = round(mean_val, 2)
            res["stddev"] = round(std_val, 2)
            res["is_black"] = mean_val < MIN_FRAME_MEAN_BRIGHTNESS or std_val < MIN_FRAME_LUMINANCE_STDDEV
            res["is_blank"] = mean_val > MAX_FRAME_MEAN_BRIGHTNESS and std_val < MIN_FRAME_LUMINANCE_STDDEV
    except Exception:
        pass

    return res


def _compare_frames_for_freeze(frame1: Path, frame2: Path) -> bool:
    """Retorna True se dois frames forem pixel a pixel quase idênticos (indicando freeze)."""
    try:
        from PIL import Image, ImageChops, ImageStat

        with Image.open(frame1) as im1, Image.open(frame2) as im2:
            if im1.size != im2.size:
                return False
            diff = ImageChops.difference(im1.convert("RGB"), im2.convert("RGB"))
            stat = ImageStat.Stat(diff)
            avg_diff = sum(stat.mean) / len(stat.mean)
            return avg_diff < 0.8
    except Exception:
        return False


def audit_rendered_video(
    mp4_path: Path,
    work_dir: Path,
    timeline_beats: list[Any] | None = None,
    expected_duration_s: float | None = None,
) -> dict[str, Any]:
    """Auditoria completa pós-render do MP4 final, gerando video.qa.json."""
    mp4_path = Path(mp4_path)
    work_dir = Path(work_dir)
    file_exists = mp4_path.is_file()
    size_bytes = mp4_path.stat().st_size if file_exists else 0
    size_valid = size_bytes >= MIN_VIDEO_BYTES

    probe = _probe_video_info(mp4_path)
    dur = probe.get("duration") or 0.0
    width = probe.get("width") or 0
    height = probe.get("height") or 0
    has_video = probe.get("has_video", False)
    has_audio = probe.get("has_audio", False)
    dimensions_1080p = (width == 1920 and height == 1080)

    # Determina instantes para amostragem
    sample_times: list[float] = []
    if dur > 5.0:
        sample_times.append(2.0)
        sample_times.append(round(dur * 0.5, 2))
        sample_times.append(round(max(2.0, dur - 4.0), 2))

    # Inclui pontos de transição da timeline se fornecidos
    if timeline_beats:
        for b in timeline_beats:
            t0 = getattr(b, "t0", None) if not isinstance(b, dict) else b.get("t0")
            if t0 is not None and 3.0 < float(t0) < (dur - 5.0):
                sample_times.append(round(float(t0) + 0.3, 2))

    # Limita e ordena os pontos de amostragem
    sample_times = sorted(list(set(sample_times)))[:8]

    frames_dir = work_dir / "qa_frames"
    extracted_frames = _extract_sample_frames(mp4_path, sample_times, frames_dir)

    audited_frames: list[dict[str, Any]] = []
    has_black_frame = False
    has_corrupt_frame = False

    for ts, fpath in extracted_frames:
        f_audit = _audit_frame_pixels(fpath)
        if not f_audit["valid_image"]:
            has_corrupt_frame = True
        if f_audit["is_black"]:
            has_black_frame = True

        audited_frames.append({
            "timestamp_s": ts,
            "frame_file": str(fpath.name),
            "mean_brightness": f_audit["mean"],
            "luminance_stddev": f_audit["stddev"],
            "status": "REJECTED" if f_audit["is_black"] else ("APPROVED" if f_audit["valid_image"] else "WARNING"),
        })

    # Detecção de congelamento entre o primeiro e último frame amostrado no corpo do vídeo
    has_freeze = False
    if len(extracted_frames) >= 2:
        f_first = extracted_frames[0][1]
        f_mid = extracted_frames[len(extracted_frames) // 2][1]
        if _compare_frames_for_freeze(f_first, f_mid):
            has_freeze = True

    # Checagem de duração
    dur_valid = True
    if expected_duration_s and expected_duration_s > 0:
        # Vídeo final com encerramento pode ter alguns segundos a mais
        diff = dur - expected_duration_s
        dur_valid = (-2.0 <= diff <= 35.0)

    checks = {
        "file_exists": file_exists,
        "min_size": size_valid,
        "has_video": has_video,
        "has_audio": has_audio,
        "dimensions_1080p": dimensions_1080p,
        "no_black_frames": not has_black_frame,
        "no_corrupt_frames": not has_corrupt_frame,
        "no_excessive_freeze": not has_freeze,
        "duration_valid": dur_valid,
    }

    # Status geral
    if not file_exists or not size_valid or not has_video or not has_audio or has_black_frame:
        overall_status = "REJECTED"
    elif not dimensions_1080p or not dur_valid or has_freeze:
        overall_status = "WARNING"
    else:
        overall_status = "APPROVED"

    report = {
        "video_path": str(mp4_path),
        "file_size_bytes": size_bytes,
        "duration_s": dur,
        "width": width,
        "height": height,
        "video_codec": probe.get("video_codec"),
        "audio_codec": probe.get("audio_codec"),
        "sampled_frames_count": len(audited_frames),
        "sampled_frames": audited_frames,
        "checks": checks,
        "overall_status": overall_status,
        "audit_timestamp": datetime.now().isoformat(),
    }

    # Grava video.qa.json
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        qa_out = work_dir / "video.qa.json"
        qa_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("Falha ao gravar video.qa.json: %s", exc)

    return report
