#!/bin/bash
# Hourly Brasil e Mundo pipeline runner
# 0) monitor RSS ANCAPSU → fila (sem isso episódios novos nunca entram)
# 1) processa a fila (áudio / site)
# 2) gera vídeo mockup-browser do episódio novo e sobe público no YouTube
# Falha do vídeo NÃO derruba o process-queue (áudio continua saindo).

set -u

WORK_DIR="/home/osmar/web-jornal-vale-da-liberdade"
HERMES_PY="/home/osmar/.hermes/hermes-agent/venv/bin/python3"
PROJECT_PY="$WORK_DIR/.venv/bin/python3"
LOG_DIR="$WORK_DIR/logs"

cd "$WORK_DIR"
mkdir -p "$LOG_DIR"

set +e
"$HERMES_PY" scripts/bm_monitor.py >> "$LOG_DIR/bm-monitor.log" 2>&1
MONITOR_RC=$?
set -e
if [[ "$MONITOR_RC" -ne 0 ]]; then
  echo "WARN: bm_monitor exit $MONITOR_RC" >&2
fi

set +e
"$HERMES_PY" scripts/bm_pipeline.py process-queue
QUEUE_RC=$?
set -e

if [[ -x "$PROJECT_PY" ]]; then
  set +e
  "$PROJECT_PY" scripts/bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2
  VIDEO_RC=$?
  set -e
  if [[ "$VIDEO_RC" -ne 0 ]]; then
    echo "WARN: bm_mockup_video exit $VIDEO_RC (fila áudio rc=$QUEUE_RC)" >&2
  fi
else
  echo "WARN: venv do projeto sem python — pulando vídeo mockup" >&2
fi

exit "$QUEUE_RC"
