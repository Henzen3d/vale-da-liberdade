#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

# PATH mínimo do cron + bins do usuário (yt-dlp via pipx) + venv Hermes
export PATH="/home/osmar/.local/bin:/home/osmar/.hermes/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin${PATH:+:$PATH}"

# Load environment variables for the project
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

LOG_FILE="$LOG_DIR/daily-$(date +%F).log"
EXEC_DATE="${1:-$(date +%F)}"

{
  echo "=== Daily build started: $(date '+%a %d %b %Y %H:%M:%S %Z') ==="
  /home/osmar/.hermes/hermes-agent/venv/bin/python3 "$PROJECT_DIR/scripts/pipeline.py" full --date "$EXEC_DATE"
  echo "=== Daily build finished: $(date '+%a %d %b %Y %H:%M:%S %Z') ==="
} > "$LOG_FILE" 2>&1

echo "EXIT:$?"
