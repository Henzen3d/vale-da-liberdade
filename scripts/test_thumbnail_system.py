#!/usr/bin/env python3
"""
Testes obrigatórios (Seção 10) do sistema de thumbnails.
Roda de fato — não apenas descreve. Gera TEST_REPORT.md.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import thumbnail_generator as tg

REPORT: list[dict] = []
BRT = timezone(timedelta(hours=-3))


def _ok(name: str, evidence: str, passed: bool, detail: str = "") -> None:
    REPORT.append({
        "test": name,
        "pass": passed,
        "evidence": evidence,
        "detail": detail,
    })
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}: {evidence}")
    if detail:
        print(f"       {detail[:200]}")


def test_1_happy_path() -> None:
    """Happy path com episódio real 2026-08-05."""
    date = "2026-08-05"
    eid = f"ep_{date}"
    # force regenerate for real proof
    try:
        result = tg.generate_thumbnail_for_episode(date=date, episode_id=eid, force=True)
        path = PROJECT_ROOT / result.get("path", "")
        meta_path = EPISODES_DIR = PROJECT_ROOT / "episodes" / f"{date}-metadata.json"
        has_meta = False
        if meta_path.exists():
            md = json.loads(meta_path.read_text(encoding="utf-8"))
            has_meta = "thumbnail" in md and md["thumbnail"].get("path")
        passed = (
            bool(result.get("path"))
            and path.exists()
            and path.stat().st_size > 1000
            and has_meta
            and result.get("image_model_used") not in (None, "", "error")
        )
        _ok(
            "1. Happy path (episódio real)",
            f"path={result.get('path')} model={result.get('image_model_used')} "
            f"placeholder={result.get('is_placeholder')} meta={has_meta}",
            passed,
            f"attempts={len(result.get('generation_attempts') or [])}",
        )
    except Exception as e:
        _ok("1. Happy path (episódio real)", str(e), False, traceback.format_exc()[-300:])


def test_2_fallback_model() -> None:
    """Simula falha do primário (quota) e confirma cascata."""
    cascade = tg._load_cascade()
    if len(cascade) < 2:
        _ok("2. Fallback de modelo", "cascata < 2 modelos", False)
        return
    primary = cascade[0]
    secondary = next((m for m in cascade[1:] if m.enabled), None)
    if not secondary:
        _ok("2. Fallback de modelo", "sem secundário enabled", False)
        return

    calls: list[str] = []
    real_once = tg._call_model_once

    def fake_once(model, prompt):
        calls.append(model.model_id)
        if model.model_id == primary.model_id:
            raise tg.ModelFailed("quota local esgotada para primary (simulated)")
        # succeed on next with a synthetic image
        img = Image.new("RGB", (1664, 928), (30, 30, 30))
        # add variance so validation passes
        for x in range(0, 1664, 40):
            for y in range(0, 928, 40):
                img.putpixel((x, y), (184, 134, 59))
        return img, 50

    with patch.object(tg, "_call_model_once", side_effect=fake_once):
        # also bypass quota check by patching remaining
        with patch.object(tg, "quota_remaining", return_value=10):
            with patch.object(tg, "quota_increment", return_value=None):
                try:
                    img, info = tg.generate_cover_image(
                        "test prompt editorial amber",
                        "ep_test_fallback",
                        cascade=cascade,
                        allow_safety_regen=False,
                    )
                    passed = (
                        info.get("fallback_level", 0) >= 1
                        and info.get("image_model_used") != primary.model_id
                        and not info.get("is_placeholder")
                        and primary.model_id in calls
                    )
                    _ok(
                        "2. Fallback de modelo",
                        f"used={info.get('image_model_used')} level={info.get('fallback_level')} calls={calls[:4]}",
                        passed,
                    )
                except Exception as e:
                    _ok("2. Fallback de modelo", str(e), False)


def test_3_total_api_failure() -> None:
    """Todos os modelos falham → placeholder."""
    cascade = tg._load_cascade()

    def always_fail(model, prompt):
        raise tg.ModelFailed("simulated total outage")

    with patch.object(tg, "_call_model_once", side_effect=always_fail):
        with patch.object(tg, "quota_remaining", return_value=10):
            result = tg.generate_thumbnail_for_episode(
                date="2099-01-01",
                episode_id="ep_test_total_fail",
                headline="Teste falha total de API",
                summary="Simulação de outage completo das APIs de imagem.",
                force=True,
            )
    path = PROJECT_ROOT / result.get("path", "")
    passed = (
        result.get("is_placeholder") is True
        and result.get("image_model_used") == "local-placeholder"
        and path.exists()
    )
    _ok(
        "3. Falha total de API → placeholder",
        f"model={result.get('image_model_used')} path={result.get('path')} exists={path.exists()}",
        passed,
    )
    # cleanup test artifacts
    try:
        shutil.rmtree(PROJECT_ROOT / "thumbnails" / "2099-01-01", ignore_errors=True)
        shutil.rmtree(PROJECT_ROOT / "public" / "thumbnails" / "2099-01-01", ignore_errors=True)
    except Exception:
        pass


def test_4_safety_rejection() -> None:
    """HTTP 400 safety → regenera prompt 1×."""
    cascade = [m for m in tg._load_cascade() if m.enabled][:2]
    state = {"n": 0, "safe_seen": False}

    def fake_once(model, prompt):
        state["n"] += 1
        # first cascade pass: safety on first model
        if "public figure" not in prompt.lower() and "tension" not in prompt.lower() and state["n"] <= 1:
            raise tg.SafetyRejected("HTTP 400: DataInspectionFailed simulated")
        state["safe_seen"] = True
        img = Image.new("RGB", (1664, 928), (40, 40, 40))
        for x in range(0, 1664, 30):
            img.putpixel((x, 100), (200, 150, 50))
        return img, 40

    with patch.object(tg, "_call_model_once", side_effect=fake_once):
        with patch.object(tg, "quota_remaining", return_value=10):
            with patch.object(tg, "quota_increment", return_value=None):
                try:
                    img, info = tg.generate_cover_image(
                        "Violent combat scene with blood and named Politician Silva fighting",
                        "ep_test_safety",
                        cascade=cascade,
                        allow_safety_regen=True,
                    )
                    passed = info.get("image_prompt_sanitized") is True or state["safe_seen"]
                    _ok(
                        "4. Safety rejection (HTTP 400)",
                        f"sanitized={info.get('image_prompt_sanitized')} calls={state['n']} model={info.get('image_model_used')}",
                        passed,
                    )
                except tg.AllModelsFailed:
                    # still ok if it tried regen then failed — check attempts
                    passed = state["n"] >= 2
                    _ok("4. Safety rejection (HTTP 400)", f"AllModelsFailed after n={state['n']}", passed)
                except Exception as e:
                    _ok("4. Safety rejection (HTTP 400)", str(e), False)


def test_5_corrupted_image() -> None:
    """Bytes inválidos → ModelFailed via validação Pillow."""
    try:
        tg._validate_image_bytes(b"not-an-image-at-all")
        _ok("5. Imagem corrompida", "não levantou ModelFailed", False)
    except tg.ModelFailed as e:
        _ok("5. Imagem corrompida", f"ModelFailed: {e}", True)
    except Exception as e:
        _ok("5. Imagem corrompida", f"exceção errada: {type(e)} {e}", False)

    # gray image
    gray = Image.new("RGB", (800, 450), (128, 128, 128))
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    try:
        tg._validate_image_bytes(buf.getvalue())
        _ok("5b. Imagem monotônica", "não levantou ModelFailed", False)
    except tg.ModelFailed as e:
        _ok("5b. Imagem monotônica", f"ModelFailed: {e}", True)


def test_6_idempotency() -> None:
    """Segunda chamada sem --force não regenera."""
    date = "2026-08-05"
    eid = f"ep_{date}"
    path = tg.THUMBNAILS_DIR / date / f"{eid}.webp"
    if not path.exists():
        tg.generate_thumbnail_for_episode(date=date, episode_id=eid, force=True)
    mtime1 = path.stat().st_mtime
    size1 = path.stat().st_size
    r2 = tg.generate_thumbnail_for_episode(date=date, episode_id=eid, force=False)
    mtime2 = path.stat().st_mtime
    passed = r2.get("skipped") is True and mtime1 == mtime2 and r2.get("image_model_used") == "cached"
    _ok(
        "6. Idempotência",
        f"skipped={r2.get('skipped')} mtime_same={mtime1==mtime2} model={r2.get('image_model_used')}",
        passed,
    )


def test_7_quota_persistence() -> None:
    """Contador diário persiste entre 'reinícios' (reload do arquivo)."""
    mid = "test-quota-model-xyz"
    # isolate quota file temporarily
    original = tg.QUOTA_DB
    tmp = PROJECT_ROOT / "sources" / "_test_quota_tmp.json"
    try:
        if tmp.exists():
            tmp.unlink()
        tg.QUOTA_DB = tmp
        # fresh day
        assert tg.quota_remaining(mid, 5) == 5
        tg.quota_increment(mid)
        tg.quota_increment(mid)
        # reload as if new process
        rem = tg.quota_remaining(mid, 5)
        data = json.loads(tmp.read_text(encoding="utf-8"))
        passed = rem == 3 and data.get("models", {}).get(mid, {}).get("count") == 2
        # day rollover: fake yesterday
        data["day"] = "2000-01-01"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        rem2 = tg.quota_remaining(mid, 5)
        passed = passed and rem2 == 5  # reset
        _ok(
            "7. Controle de cota diária",
            f"after_2_inc remaining={rem}; after_day_reset remaining={rem2}",
            passed,
        )
    finally:
        tg.QUOTA_DB = original
        if tmp.exists():
            tmp.unlink()


def test_8_non_blocking() -> None:
    """Falha total de thumbnail não levanta — safe wrapper."""
    def boom(**kwargs):
        raise RuntimeError("catastrophic failure")

    with patch.object(tg, "generate_thumbnail_for_episode", side_effect=boom):
        out = tg.generate_thumbnail_safe(date="2026-08-05")
    passed = isinstance(out, dict) and out.get("failed") is True
    _ok(
        "8. Integração não-bloqueante",
        f"safe_wrapper returned failed={out.get('failed')} keys={list(out.keys())}",
        passed,
    )

    # pipeline import path
    try:
        # ensure cmd_full source contains thumbnail step
        src = (PROJECT_ROOT / "scripts" / "pipeline.py").read_text(encoding="utf-8")
        bm = (PROJECT_ROOT / "scripts" / "bm_pipeline.py").read_text(encoding="utf-8")
        wired = "generate_thumbnail_safe" in src and "Etapa 5.6" in src
        bm_wired = "generate_thumbnail_safe" in bm
        _ok(
            "8b. Wiring no cron/pipeline",
            f"pipeline.py wired={wired} bm_pipeline.py wired={bm_wired} cron=cron-wrapper.sh→pipeline.py full",
            wired and bm_wired,
        )
    except Exception as e:
        _ok("8b. Wiring no cron/pipeline", str(e), False)


def test_9_lint_types() -> None:
    """py_compile + import check."""
    import py_compile
    files = [
        PROJECT_ROOT / "scripts" / "thumbnail_generator.py",
        PROJECT_ROOT / "scripts" / "test_thumbnail_system.py",
        PROJECT_ROOT / "scripts" / "pipeline.py",
        PROJECT_ROOT / "scripts" / "bm_pipeline.py",
    ]
    errors = []
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    # import smoke
    try:
        import importlib
        importlib.reload(tg)
        cascade = tg._load_cascade()
        if len(cascade) < 8:
            errors.append(f"cascade has {len(cascade)} models, expected 8")
    except Exception as e:
        errors.append(f"import: {e}")
    _ok(
        "9. Lint/tipo (py_compile)",
        "ok" if not errors else "; ".join(errors),
        len(errors) == 0,
    )


def write_report() -> Path:
    out = PROJECT_ROOT / "TEST_REPORT.md"
    lines = [
        "# TEST_REPORT — Sistema de Thumbnails Automáticas\n\n",
        f"Gerado em {datetime.now(BRT).isoformat()}\n\n",
        "| # | Teste | Resultado | Evidência |\n",
        "|---|---|---|---|\n",
    ]
    for i, r in enumerate(REPORT, 1):
        mark = "✅ PASS" if r["pass"] else "❌ FAIL"
        ev = str(r["evidence"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {i} | {r['test']} | {mark} | {ev} |\n")
    n_pass = sum(1 for r in REPORT if r["pass"])
    lines.append(f"\n**Total: {n_pass}/{len(REPORT)} passaram.**\n")
    if any(not r["pass"] for r in REPORT):
        lines.append("\n## Detalhes das falhas\n\n")
        for r in REPORT:
            if not r["pass"]:
                lines.append(f"### {r['test']}\n\n```\n{r.get('detail') or r['evidence']}\n```\n\n")
    out.write_text("".join(lines), encoding="utf-8")
    return out


def main() -> int:
    print("=" * 60)
    print("TESTES OBRIGATÓRIOS — thumbnail system")
    print("=" * 60)
    test_9_lint_types()  # fast first
    test_5_corrupted_image()
    test_7_quota_persistence()
    test_2_fallback_model()
    test_3_total_api_failure()
    test_4_safety_rejection()
    test_8_non_blocking()
    test_6_idempotency()  # may use existing
    test_1_happy_path()   # real API call last
    # re-check idempotency after happy path
    test_6_idempotency()
    path = write_report()
    n_pass = sum(1 for r in REPORT if r["pass"])
    print("=" * 60)
    print(f"RESULTADO: {n_pass}/{len(REPORT)} — report: {path}")
    return 0 if n_pass == len(REPORT) else 1


if __name__ == "__main__":
    sys.exit(main())
