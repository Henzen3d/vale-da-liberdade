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
#
# Hermes mata no_agent em 3600s e conta como falha (3 seguidas = alerta).
# TTS (~30–40 min) + mockup (~25–40 min) no mesmo tick passam disso.
# Orçamento: áudio primeiro; mockup só se sobrar >= MOCKUP_MIN segundos.
# ==============================================================================

set -u

WORK_DIR="/home/osmar/web-jornal-vale-da-liberdade"
HERMES_PY="/home/osmar/.hermes/hermes-agent/venv/bin/python3"
PROJECT_PY="$WORK_DIR/.venv/bin/python3"
LOG_DIR="$WORK_DIR/logs"

# 3300s = 55 min. Folga de 5 min antes do kill 3600s do Hermes.
BUDGET_S=3300
MOCKUP_MIN_S=900

cd "$WORK_DIR"
mkdir -p "$LOG_DIR"

START_S=$(date +%s)
remain() {
  echo $(( BUDGET_S - ($(date +%s) - START_S) ))
}

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
QUEUE_RC=0
LEFT=$(remain)
if [[ "$LEFT" -lt 60 ]]; then
  echo "WARN: sem tempo para process-queue (restam ${LEFT}s) — próximo tick" >&2
else
  set +e
  timeout --kill-after=30s "${LEFT}s" "$HERMES_PY" scripts/bm_pipeline.py process-queue --max 1
  QUEUE_RC=$?
  set -e
  if [[ "$QUEUE_RC" -eq 124 ]]; then
    echo "WARN: process-queue parado no orçamento Hermes — próximo tick retoma" >&2
    QUEUE_RC=0
  fi
fi

# ------------------------------------------------------------------------------
# ETAPA 3: Renderização de Vídeo Mockup & Upload YouTube (Ambiente Projeto)
# ------------------------------------------------------------------------------
LEFT=$(remain)
if [[ ! -x "$PROJECT_PY" ]]; then
  echo "WARN: venv do projeto sem python ($PROJECT_PY nao encontrado) — pulando video mockup" >&2
elif [[ "$LEFT" -lt "$MOCKUP_MIN_S" ]]; then
  echo "WARN: pulando mockup nesta rodada (restam ${LEFT}s < ${MOCKUP_MIN_S}s) — próximo tick" >&2
else
  set +e
  timeout --kill-after=30s "${LEFT}s" \
    "$PROJECT_PY" scripts/bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2
  VIDEO_RC=$?
  set -e
  if [[ "$VIDEO_RC" -eq 124 ]]; then
    echo "WARN: bm_mockup_video parado no orçamento Hermes (fila audio rc=$QUEUE_RC)" >&2
  elif [[ "$VIDEO_RC" -ne 0 ]]; then
    echo "WARN: bm_mockup_video exit $VIDEO_RC (fila audio rc=$QUEUE_RC)" >&2
  fi
fi

exit "$QUEUE_RC"
