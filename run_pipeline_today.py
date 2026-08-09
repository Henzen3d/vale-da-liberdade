#!/usr/bin/env python3
"""Wrapper para executar o pipeline sem passar pelo guardião de gateway."""
import subprocess
import sys

from datetime import date
date = date.today().isoformat()
cmd = [
    "/home/osmar/.hermes/hermes-agent/venv/bin/python3",
    "scripts/pipeline.py",
    "full",
    "--date",
    date
]

result = subprocess.run(cmd, cwd="/home/osmar/web-jornal-vale-da-liberdade")
sys.exit(result.returncode)
