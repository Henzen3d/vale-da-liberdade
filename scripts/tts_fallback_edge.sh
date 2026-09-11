#!/usr/bin/env bash
# Wrapper LF → tts_fallback_edge.py (HERMES_PY). CLI estável: [DATE]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_PY="${HERMES_PY:-/home/osmar/.hermes/hermes-agent/venv/bin/python3}"
exec "$HERMES_PY" "$ROOT/scripts/tts_fallback_edge.py" "$@"
