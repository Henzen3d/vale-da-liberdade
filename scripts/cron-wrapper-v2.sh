#!/bin/bash
# Wrapper para o pipeline diário - versão corrigida
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

LOG_FILE="$LOG_DIR/daily-$(date +%F).log"
EXEC_DATE="${1:-$(date +%F)}"

python3 "$PROJECT_DIR/scripts/pipeline.py" full --date "$EXEC_DATE" 2>&1 | tee "$LOG_FILE"
