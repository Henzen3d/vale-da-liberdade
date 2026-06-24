#!/usr/bin/env python3
"""
Green-build (regressão) do Web Jornal Vale da Liberdade.

Valida que o template de roteiro结构ural (`episodes/roteiro-template.json`)
passa pelo pipeline `process` + `validate` sem erros críticos.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EPISODES_DIR = PROJECT_ROOT / "episodes"
TEMPLATE = EPISODES_DIR / "roteiro-template.json"
TEST_DATE = "2026-06-20"
PYTHON = sys.executable
PIPELINE = PROJECT_ROOT / "scripts" / "pipeline.py"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> int:
    if not TEMPLATE.exists():
        print(f"❌ Template não encontrado: {TEMPLATE}")
        return 1

    json_path = EPISODES_DIR / f"roteiro-{TEST_DATE}.json"
    shutil.copy(TEMPLATE, json_path)

    env = {"PYTHONPATH": str(PROJECT_ROOT / "scripts")}

    proc = _run([PYTHON, str(PIPELINE), "process", "--date", TEST_DATE])
    print(proc.stdout)
    if proc.returncode != 0:
        print("❌ process falhou")
        return proc.returncode

    proc = _run([PYTHON, str(PIPELINE), "validate", "--date", TEST_DATE])
    print(proc.stdout)
    if proc.returncode != 0:
        return proc.returncode

    if "❌" in proc.stdout:
        print("❌ Green build quebrado: erros críticos encontrados")
        return 1

    print("✅ Green build passou")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
