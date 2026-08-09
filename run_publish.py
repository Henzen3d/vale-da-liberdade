#!/usr/bin/env python3
"""Publica o episódio de hoje."""
import sys
import subprocess

result = subprocess.run(
    ['/home/osmar/.hermes/hermes-agent/venv/bin/python3',
     'scripts/publish_site.py'],
    cwd='/home/osmar/web-jornal-vale-da-liberdade'
)
sys.exit(result.returncode)
