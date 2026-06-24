set -euo pipefail
PROJECT="/home/osmar/web-jornal-vale-da-liberdade"
"$PROJECT/scripts/daily-pipeline.sh" > /tmp/daily-pipeline.log 2>&1
cp /tmp/daily-pipeline.log "$PROJECT/logs/daily-$(date +%F).log"
