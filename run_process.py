#!/usr/bin/env python3
"""Processa o episódio de hoje usando o pipeline."""
import sys
import os
import subprocess

sys.path.insert(0, '/home/osmar/web-jornal-vale-da-liberdade/scripts')
os.chdir('/home/osmar/web-jornal-vale-da-liberdade')

# Executar diretamente via subprocess para evitar o guardião
result = subprocess.run(
    ['/home/osmar/.hermes/hermes-agent/venv/bin/python3',
     'scripts/pipeline.py', 'process', '--date', '2026-08-04'],
    cwd='/home/osmar/web-jornal-vale-da-liberdade'
)
sys.exit(result.returncode)
