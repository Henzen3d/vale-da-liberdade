#!/bin/bash
# ==============================================================================
# BM HOURLY PIPELINE RUNNER (Brasil e Mundo)
# ==============================================================================
# SEPARAÇÃO DE AMBIENTES VIRTUAIS (CANÔNICO - NÃO ALTERAR SEM TESTE):
# 1) HERMES_PY  (/home/osmar/.hermes/hermes-agent/venv/bin/python3)
#    -> bm_monitor.py + bm_pipeline.py (feed RSS, LLM, TTS, áudio)
# 2) PROJECT_PY (/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3)
#    -> bm_mockup_video.py (Playwright, renderizador de vídeo, upload YT)
# Não unificar os venvs. Pacote novo vai no interpretador do braço que o usa.
# Falha do vídeo NÃO derruba o process-queue (áudio continua saindo).
# ==============================================================================

set -u

WORK_DIR="/home/osmar/web-jornal-vale-da-liberdade"
HERMES_PY="/home/osmar/.hermes/hermes-agent/venv/bin/python3"
PROJECT_PY="$WORK_DIR/.venv/bin/python3"
LOG_DIR="$WORK_DIR/logs"

cd "$WORK_DIR"
mkdir -p "$LOG_DIR"

# ------------------------------------------------------------------------------
# ETAPA 1: Monitor RSS ANCAPSU -> Fila de episódios (Ambiente Hermes)
# ------------------------------------------------------------------------------
set +e
"$HERMES_PY" scripts/bm_monitor.py >> "$LOG_DIR/bm-monitor.log" 2>&1
MONITOR_RC=$?
set -e
if [[ "$MONITOR_RC" -ne 0 ]]; then
  echo "WARN: bm_monitor exit $MONITOR_RC" >&2
fi

# ------------------------------------------------------------------------------
# ETAPA 2: Processamento da Fila (Áudio / Metadados / Site) (Ambiente Hermes)
# ------------------------------------------------------------------------------
set +e
"$HERMES_PY" scripts/bm_pipeline.py process-queue
QUEUE_RC=$?
set -e

# ------------------------------------------------------------------------------
# ETAPA 3: Renderização de Vídeo Mockup & Upload YouTube (Ambiente Projeto/Playwright)
# ------------------------------------------------------------------------------
if [[ -x "$PROJECT_PY" ]]; then
  set +e
  "$PROJECT_PY" scripts/bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2
  VIDEO_RC=$?
  set -e
  if [[ "$VIDEO_RC" -ne 0 ]]; then
    echo "WARN: bm_mockup_video exit $VIDEO_RC (fila audio rc=$QUEUE_RC)" >&2
  fi
else
  echo "WARN: venv do projeto sem python ($PROJECT_PY nao encontrado) — pulando video mockup" >&2
fi

exit "$QUEUE_RC"
