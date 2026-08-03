#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/osmar/web-jornal-vale-da-liberdade"
AUDIO="$ROOT/audio"
PY="$ROOT/scripts/tts_fallback_chunk.py"
mkdir -p "$AUDIO"

python3 - <<'PY' > /tmp/tts-chunks.txt
from pathlib import Path
from hermes_tools import text_to_speech
import sys
text = Path('/home/osmar/web-jornal-vale-da-liberdade/episodes/2026-07-21-tts.txt').read_text(encoding='utf-8')
lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('[') and not line.strip().startswith('#')]
out = []
for idx, line in enumerate(lines, start=1):
    speaker = 'peter' if line.lower().startswith('peter:') else 'ricardo'
    transcript = line.split(':', 1)[1].strip() if ':' in line else line
    if not transcript:
        continue
    result = text_to_speech(transcript)
    print(f'{idx}\t{speaker}\t{result["file_path"]}\t{len(transcript)}')
PY

tail -n +1 /tmp/tts-chunks.txt || true
