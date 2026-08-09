#!/usr/bin/env python3
"""Emergency: process-only stage of the daily pipeline (no TTS/publish).

Usage:
  python3 scripts/run_process.py
  python3 scripts/run_process.py --date 2026-08-04
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "scripts"
PY = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
if not PY.exists():
    PY = Path(sys.executable)


def _load_env() -> None:
    env_path = PROJECT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()
    _load_env()
    os.environ["PYTHONPATH"] = str(PROJECT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONUNBUFFERED"] = "1"
    cmd = [str(PY), str(SCRIPTS / "pipeline.py"), "process", "--date", args.date]
    print(f"▶ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(PROJECT), env=os.environ.copy())
    print(f"EXIT:{proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
