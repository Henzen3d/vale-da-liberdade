#!/usr/bin/env python3
"""QA visual pré/pós-render do pipeline BM (Evolução Visual — Etapa 9).

Protocolo: youtube/Evolucao-Visual/05_VISUAL_QA_E_METRICAS.md
Contrato:  youtube/Evolucao-Visual/02_SCHEMAS_E_CONTRATOS.md

Pré-render (<1s): schema SceneBeatV2, timings 8–22s, assets, higiene de payload.
Pós-render (~3s): 4–6 frames FFmpeg + luminância/contraste (Pillow).
Sem re-render pesado. Fallback gracioso: componente inválido → source.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIN_BEAT_S = 8.0
MAX_BEAT_S = 22.0
MIN_ASSET_BYTES = 8 * 1024
MIN_QUOTE_CHARS = 20
LUMINANCE_STDDEV_MIN = 12.0
LOWER_THIRD_Y0 = 940
LOWER_THIRD_Y1 = 1040
FRAME_PCTS = (0.10, 0.30, 0.50, 0.75, 0.90)
AUDIO_TOLERANCE_S = 2.5
TIMING_EPS = 0.05

VISUAL_COMPONENTS = {
    "source", "x-post", "quote", "document", "timeline",
    "chart", "comparison", "broll",
}
SPECIAL_COMPONENTS = {"quote", "document", "timeline", "chart", "comparison", "x-post"}

AVATAR_LOOP = (
    ROOT / "references" / "youtube" / "Apresentadores"
    / "Peter Albuquerque" / "Peter-Loop-Picsart-BackgroundRemover.mp4"
)


def _as_dict_beat(beat: Any) -> dict[str, Any]:
    if beat is None:
        return {}
    if isinstance(beat, dict):
        return dict(beat)
    if hasattr(beat, "to_dict"):
        return dict(beat.to_dict())
    out: dict[str, Any] = {}
    for k in (
        "t0", "t1", "semantic_role", "visual_component", "visual_variant",
        "visual_payload", "url", "veiculo", "shot", "video", "broll_file", "kind",
    ):
        if hasattr(beat, k):
            out[k] = getattr(beat, k)
    return out


def _normalize_plan(scene_plan: Any) -> dict[str, Any]:
    if scene_plan is None:
        return {"video_id": "", "total_duration_s": 0.0, "beats": []}
    if isinstance(scene_plan, dict):
        plan = dict(scene_plan)
        beats = plan.get("beats") or []
        plan["beats"] = [_as_dict_beat(b) for b in beats]
        return plan
    if isinstance(scene_plan, (list, tuple)):
        return {
            "video_id": "",
            "total_duration_s": 0.0,
            "beats": [_as_dict_beat(b) for b in scene_plan],
        }
    raise TypeError(f"scene_plan inválido: {type(scene_plan)!r}")


def _resolve_asset(path_like: Any, base_dirs: list[Path]) -> Path | None:
    if not path_like:
        return None
    p = Path(str(path_like))
    if p.is_file():
        return p
    name = p.name
    for base in base_dirs:
        cand = base / name
        if cand.is_file():
            return cand
        cand2 = base / str(path_like)
        if cand2.is_file():
            return cand2
    return None


def _image_ok(path: Path) -> tuple[bool, str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"stat falhou: {exc}"
    if size < MIN_ASSET_BYTES:
        return False, f"tamanho {size}B < {MIN_ASSET_BYTES}B"
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.verify()
        except Exception as exc:  # noqa: BLE001
            return False, f"imagem corrompida: {exc}"
    return True, "ok"


def _payload_issues(component: str, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    payload = payload or {}
    if component == "quote":
        text = str(payload.get("quote_text") or "").strip()
        if len(text) < MIN_QUOTE_CHARS:
            issues.append(f"quote_text curto ({len(text)}<{MIN_QUOTE_CHARS})")
    elif component == "chart":
        val = payload.get("metric_value")
        try:
            num = float(val)
            if math.isnan(num) or math.isinf(num):
                issues.append("metric_value NaN/Inf")
        except (TypeError, ValueError):
            issues.append("metric_value inválido")
    elif component == "document":
        if not str(payload.get("doc_title") or "").strip():
            issues.append("doc_title vazio")
        if not str(payload.get("highlight_text") or "").strip():
            issues.append("highlight_text vazio")
    elif component == "timeline":
        events = payload.get("events")
        if not isinstance(events, list) or len(events) < 2:
            issues.append("timeline precisa de >=2 events")
    elif component == "comparison":
        for side in ("side_a", "side_b"):
            if not isinstance(payload.get(side), dict):
                issues.append(f"{side} ausente")
    return issues


def validate_pre_render(
    scene_plan: Any,
    *,
    audio_duration_s: float | None = None,
    work_dir: Path | None = None,
    avatar_loop: Path | None = None,
    demote_invalid: bool = True,
) -> dict[str, Any]:
    """Valida SceneBeatV2 antes do Playwright. Alvo: <1s.

    Retorna dict com ok, warnings, demotions, beats (possivelmente rebaixados).
    Não aborta o vídeo por falha de componente especial — rebaixa para source.
    """
    t0 = time.perf_counter()
    plan = _normalize_plan(scene_plan)
    beats = [dict(b) for b in (plan.get("beats") or [])]
    warnings: list[str] = []
    demotions: list[dict[str, Any]] = []
    blocking: list[str] = []

    total = float(plan.get("total_duration_s") or audio_duration_s or 0.0)
    if audio_duration_s is not None and audio_duration_s > 0:
        total = float(audio_duration_s)

    base_dirs: list[Path] = []
    if work_dir:
        base_dirs.extend([work_dir, work_dir / "shots", work_dir / "rec"])
    base_dirs.append(ROOT / "references" / "youtube" / "broll")

    avatar = avatar_loop or AVATAR_LOOP
    if not avatar.is_file():
        warnings.append(f"avatar Peter ausente: {avatar}")

    if not beats:
        blocking.append("scene_plan sem beats")
    else:
        prev_t1: float | None = None
        sum_dur = 0.0
        for i, beat in enumerate(beats):
            try:
                bt0 = float(beat.get("t0", 0.0) or 0.0)
                bt1 = float(beat.get("t1", 0.0) or 0.0)
            except (TypeError, ValueError):
                blocking.append(f"beat[{i}] t0/t1 inválidos")
                continue
            dur = bt1 - bt0
            sum_dur += max(0.0, dur)
            if dur + TIMING_EPS < MIN_BEAT_S or dur - TIMING_EPS > MAX_BEAT_S:
                warnings.append(
                    f"beat[{i}] duração {dur:.2f}s fora de {MIN_BEAT_S}-{MAX_BEAT_S}s"
                )
            if prev_t1 is not None:
                if bt0 + TIMING_EPS < prev_t1:
                    blocking.append(f"beat[{i}] overlap com anterior (t0={bt0}, prev_t1={prev_t1})")
                elif bt0 - prev_t1 > 0.5:
                    warnings.append(f"beat[{i}] gap {bt0 - prev_t1:.2f}s após anterior")
            prev_t1 = bt1

            comp = (
                str(beat.get("visual_component") or beat.get("kind") or "source").strip()
                or "source"
            )
            if comp not in VISUAL_COMPONENTS:
                warnings.append(f"beat[{i}] visual_component desconhecido: {comp}")
                comp = "source"
                beat["visual_component"] = "source"
                beat["kind"] = "source"

            payload = dict(beat.get("visual_payload") or {})
            beat["visual_payload"] = payload

            asset_fail = False
            for key in ("shot", "video", "broll_file"):
                raw = beat.get(key)
                if not raw:
                    continue
                resolved = _resolve_asset(raw, base_dirs)
                if resolved is None:
                    # caminho relativo ainda não capturado — só alerta
                    if Path(str(raw)).is_absolute():
                        warnings.append(f"beat[{i}] {key} não encontrado: {raw}")
                        asset_fail = True
                    continue
                ok, reason = _image_ok(resolved) if key == "shot" else (resolved.stat().st_size > 0, "ok")
                if key == "shot" and not ok:
                    warnings.append(f"beat[{i}] shot inválido: {reason}")
                    asset_fail = True
                elif key != "shot" and resolved.stat().st_size < 1024:
                    warnings.append(f"beat[{i}] {key} muito pequeno")
                    asset_fail = True

            if comp == "document":
                doc_img = payload.get("doc_image")
                if doc_img:
                    resolved = _resolve_asset(doc_img, base_dirs)
                    if resolved is not None:
                        ok, reason = _image_ok(resolved)
                        if not ok:
                            warnings.append(f"beat[{i}] doc_image inválido: {reason}")
                            asset_fail = True

            pay_issues = _payload_issues(comp, payload)
            if pay_issues or (asset_fail and comp in SPECIAL_COMPONENTS):
                msg = "; ".join(pay_issues) or "asset inválido"
                if demote_invalid and comp in SPECIAL_COMPONENTS:
                    demotions.append({
                        "index": i,
                        "from": comp,
                        "to": "source",
                        "reason": msg,
                    })
                    beat["visual_component"] = "source"
                    beat["kind"] = "source"
                    beat["visual_variant"] = beat.get("visual_variant") or "portal_clean"
                    warnings.append(f"beat[{i}] demote {comp}→source ({msg})")
                else:
                    warnings.append(f"beat[{i}] payload: {msg}")

        if total > 0 and abs(sum_dur - total) > AUDIO_TOLERANCE_S:
            warnings.append(
                f"soma beats {sum_dur:.1f}s ≠ áudio/total {total:.1f}s (±{AUDIO_TOLERANCE_S}s)"
            )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    ok = not blocking
    result = {
        "ok": ok,
        "elapsed_ms": round(elapsed_ms, 2),
        "video_id": plan.get("video_id") or "",
        "total_duration_s": total,
        "beats": beats,
        "warnings": warnings,
        "demotions": demotions,
        "blocking_errors": blocking,
        "status": "APPROVED" if ok else "ALERT",
    }
    return result


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def _extract_frames(mp4: Path, out_dir: Path, duration_s: float) -> list[Path]:
    frames: list[Path] = []
    dur = duration_s if duration_s > 1 else 10.0
    for pct in FRAME_PCTS:
        ss = max(0.0, min(dur - 0.05, dur * pct))
        dest = out_dir / f"frame_{int(pct * 100):02d}pct.png"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{ss:.3f}", "-i", str(mp4),
            "-vframes", "1", "-q:v", "2", str(dest),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=8)
            if dest.is_file() and dest.stat().st_size > 0:
                frames.append(dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️  frame {pct:.0%} falhou: {exc}")
    return frames


def _luminance_stats(path: Path) -> dict[str, float]:
    from PIL import Image
    import numpy as np

    with Image.open(path) as im:
        gray = im.convert("L")
        arr = np.asarray(gray, dtype=np.float32)
    std = float(arr.std())
    mean = float(arr.mean())
    # lower third band
    h, w = arr.shape
    y0 = min(h - 1, int(LOWER_THIRD_Y0 * h / 1080))
    y1 = min(h, int(LOWER_THIRD_Y1 * h / 1080))
    band = arr[y0:y1, :] if y1 > y0 else arr[-max(1, h // 10):, :]
    band_std = float(band.std()) if band.size else 0.0
    # presenter region: bottom-left ~546x432 at overlay
    x1 = max(1, int(546 * w / 1920))
    y_top = max(0, h - int(432 * h / 1080) - int(38 * h / 1080))
    region = arr[y_top:h, 0:x1]
    presenter_std = float(region.std()) if region.size else 0.0
    presenter_mean = float(region.mean()) if region.size else 0.0
    return {
        "stddev": std,
        "mean": mean,
        "lower_third_stddev": band_std,
        "presenter_stddev": presenter_std,
        "presenter_mean": presenter_mean,
    }


def inspect_post_render(
    mp4_path: str | Path,
    *,
    video_id: str = "",
    report_path: Path | None = None,
    keep_frames: bool = False,
) -> dict[str, Any]:
    """Extrai 4–6 frames e afere luminância/contraste. Alvo: <3s."""
    t0 = time.perf_counter()
    mp4 = Path(mp4_path)
    warnings: list[str] = []
    if not mp4.is_file():
        report = {
            "video_id": video_id,
            "rendered_at": datetime.now().isoformat(timespec="seconds"),
            "status": "ALERT",
            "metrics": {},
            "warnings": [f"mp4 ausente: {mp4}"],
            "elapsed_ms": 0.0,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    duration_s = _ffprobe_duration(mp4)
    tmp = Path(tempfile.mkdtemp(prefix="qa_frames_"))
    try:
        frames = _extract_frames(mp4, tmp, duration_s)
        black = 0
        lt_ok = 0
        presenter_ok = 0
        contrasts: list[float] = []
        frame_details: list[dict[str, Any]] = []
        for fr in frames:
            try:
                st = _luminance_stats(fr)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{fr.name}: análise falhou ({exc})")
                continue
            contrasts.append(st["stddev"])
            if st["stddev"] < LUMINANCE_STDDEV_MIN:
                black += 1
            if st["lower_third_stddev"] >= 8.0:
                lt_ok += 1
            # presenter: não uniforme e não preto puro
            if st["presenter_stddev"] >= 6.0 and st["presenter_mean"] > 8.0:
                presenter_ok += 1
            frame_details.append({"file": fr.name, **{k: round(v, 2) for k, v in st.items()}})

        n = max(1, len(frames))
        lower_third_detected = lt_ok >= max(1, n // 2)
        presenter_detected = presenter_ok >= max(1, n // 2)
        avg_contrast = float(statistics.mean(contrasts)) if contrasts else 0.0

        if black > 0:
            warnings.append(f"black_frames_detected={black}")
        if not lower_third_detected:
            warnings.append("lower_third fraco/ausente na amostra")
        if not presenter_detected:
            warnings.append("presenter fraco/ausente na amostra")

        status = "APPROVED"
        if black > 0 or not frames:
            status = "ALERT"
        elif warnings:
            status = "ALERT"

        report = {
            "video_id": video_id or mp4.stem,
            "rendered_at": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "metrics": {
                "total_duration_s": round(duration_s, 2),
                "frames_analyzed": len(frames),
                "black_frames_detected": black,
                "lower_third_detected": lower_third_detected,
                "presenter_detected": presenter_detected,
                "average_contrast_ratio": round(avg_contrast, 2),
            },
            "frames": frame_details,
            "warnings": warnings,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "mp4": str(mp4),
        }
        if report_path is None:
            report_path = mp4.with_name("qa_report.json")
            # prefer work dir sibling if mp4 is under videos/
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        return report
    finally:
        if not keep_frames:
            shutil.rmtree(tmp, ignore_errors=True)


def run_gate(
    *,
    scene_plan: Any,
    mp4_path: str | Path,
    video_id: str = "",
    audio_duration_s: float | None = None,
    work_dir: Path | None = None,
    block_upload_on_alert: bool = True,
) -> dict[str, Any]:
    """Pré + pós. Retorna gate com allow_upload."""
    pre = validate_pre_render(
        scene_plan,
        audio_duration_s=audio_duration_s,
        work_dir=work_dir,
    )
    report_path = None
    if work_dir:
        report_path = Path(work_dir) / "qa_report.json"
    post = inspect_post_render(mp4_path, video_id=video_id or pre.get("video_id") or "", report_path=report_path)

    severe = (
        post.get("status") == "ALERT"
        and (
            (post.get("metrics") or {}).get("black_frames_detected", 0) > 0
            or (post.get("metrics") or {}).get("frames_analyzed", 0) == 0
        )
    )
    allow = True
    if block_upload_on_alert and severe:
        allow = False
    if not pre.get("ok"):
        # pré bloqueante só por erros estruturais graves; demote não bloqueia
        allow = allow and True

    gate = {
        "pre": pre,
        "post": post,
        "allow_upload": allow,
        "status": post.get("status") if allow else "ALERT",
    }
    return gate


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QA visual BM pré/pós-render")
    sub = p.add_subparsers(dest="cmd", required=True)

    pre = sub.add_parser("pre", help="validate_pre_render")
    pre.add_argument("--scene-plan", required=True, help="JSON scene_plan ou lista de beats")
    pre.add_argument("--audio-duration", type=float, default=None)
    pre.add_argument("--work-dir", default=None)

    post = sub.add_parser("post", help="inspect_post_render")
    post.add_argument("--mp4", required=True)
    post.add_argument("--video-id", default="")
    post.add_argument("--report", default=None)

    args = p.parse_args(argv)
    if args.cmd == "pre":
        plan = json.loads(Path(args.scene_plan).read_text(encoding="utf-8"))
        work = Path(args.work_dir) if args.work_dir else None
        out = validate_pre_render(plan, audio_duration_s=args.audio_duration, work_dir=work)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("ok") else 2
    if args.cmd == "post":
        report = Path(args.report) if args.report else None
        out = inspect_post_render(args.mp4, video_id=args.video_id, report_path=report)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("status") == "APPROVED" else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
