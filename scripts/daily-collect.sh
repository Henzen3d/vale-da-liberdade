#!/usr/bin/env bash
# Coleta diária — delega ao pipeline real (não escreve mais stubs vazios).
# Mantido por compatibilidade com o cron Hermes que ainda chama este script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TODAY="${1:-$(date +%Y-%m-%d)}"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

PYTHON_BIN="${PYTHON_BIN:-/home/osmar/.hermes/hermes-agent/venv/bin/python3}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "=== daily-collect → pipeline.py init --date $TODAY ==="
exec "$PYTHON_BIN" "$PROJECT_DIR/scripts/pipeline.py" init --date "$TODAY"
