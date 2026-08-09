#!/usr/bin/env python3
"""Gera o áudio do episódio de hoje."""
import sys
import subprocess

result = subprocess.run(
    ['/home/osmar/.hermes/hermes-agent/venv/bin/python3',
     'scripts/pipeline.py', 'audio', '--date', '2026-08-04'],
    cwd='/home/osmar/web-jornal-vale-da-liberdade'
)
sys.exit(result.returncode)
