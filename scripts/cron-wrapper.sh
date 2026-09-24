#!/bin/bash
set -uo pipefail

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
EXTRA_ARGS=()
if [ "$#" -gt 0 ]; then
  shift
  EXTRA_ARGS=("$@")
fi

# Opção B: Por padrão no cron diário automático, tolera episódios com menos de 1500 palavras
# para garantir que o podcast sempre saia pontualmente às 06:00 (a menos que DISABLE_ALLOW_SHORT=1).
if [ "${DISABLE_ALLOW_SHORT:-0}" != "1" ]; then
  if [[ ! " ${EXTRA_ARGS[*]:-} " =~ " --allow-short-audio " ]]; then
    EXTRA_ARGS+=("--allow-short-audio")
  fi
fi

# Hermes no_agent default = 3600s. Este wrapper precisa sempre fechar o log
# mesmo se pipeline.py sair ≠ 0. O teto do job está em cron.script_timeout_seconds.
PIPELINE_RC=0
{
  echo "=== Daily build started: $(date '+%a %d %b %Y %H:%M:%S %Z') ==="
  /home/osmar/.hermes/hermes-agent/venv/bin/python3 "$PROJECT_DIR/scripts/pipeline.py" full --date "$EXEC_DATE" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
  PIPELINE_RC=$?
  echo "=== Daily build finished: $(date '+%a %d %b %Y %H:%M:%S %Z') rc=$PIPELINE_RC ==="
} > "$LOG_FILE" 2>&1

echo "EXIT:$PIPELINE_RC"
exit "$PIPELINE_RC"
