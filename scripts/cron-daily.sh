#!/bin/bash
# ============================================================================
# ⚠️  OBSOLETO — este script NÃO é mais usado.
# ============================================================================
#
# HISTÓRICO: chamava scripts/daily-pipeline.sh, que NÃO existe mais, e por isso
# quebrava (arquivo ausente). Verificado em 2026-08-03: NÃO está no crontab.
#
# O agendamento REAL da regeneração diária do site é:
#
#   crontab (UTC):   0 6 * * *   →  scripts/cron-wrapper.sh
#                     (06:00 UTC; executa scripts/pipeline.py full --date <hoje>,
#                      que ao final chama scripts/publish_site.py)
#
# Execuções manuais recomendadas:
#   - Publicar (catálogo + feeds + shell):  python3 scripts/publish_site.py
#   - Sync rápido do frontend (dev):        scripts/dev-sync.sh
#   - Sync completo do frontend:            scripts/dev-sync.sh --full
#
# Para reativar no futuro, substitua o corpo por:
#   "$(dirname "$0")/cron-wrapper.sh"
# ============================================================================
set -euo pipefail

echo "[cron-daily.sh] OBSOLETO — removido do agendamento. O job diário real é scripts/cron-wrapper.sh (06:00 UTC)." >&2
exit 0
