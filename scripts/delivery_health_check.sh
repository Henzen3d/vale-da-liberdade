#!/usr/bin/env bash
# Health-check de aviso do Web Jornal / Hermes gateway.
#
# Distribuição do áudio = site (news.mob.tec.br). Telegram = só aviso.
# WhatsApp / bridge :3000 NÃO são mais canais — não checar.
#
# Comportamento (watchdog no_agent):
#   - stdout vazio + exit 0  → silêncio (Telegram/gateway OK)
#   - stdout com alerta + exit 0 → aviso não-crítico
#   - exit 2 → Telegram offline (aviso do diário não chega)
#
# Uso:
#   bash scripts/delivery_health_check.sh
#   bash scripts/delivery_health_check.sh --json
set -euo pipefail

JSON=0
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    --strict-whatsapp)
      # flag aposentada (WA não é mais canal) — ignorar
      ;;
  esac
done

GATEWAY_STATE="${HERMES_GATEWAY_STATE:-$HOME/.hermes/gateway_state.json}"
CHANNEL_DIR="${HERMES_CHANNEL_DIR:-$HOME/.hermes/channel_directory.json}"

python3 - "$GATEWAY_STATE" "$CHANNEL_DIR" "$JSON" <<'PY'
import json, sys
from pathlib import Path
from datetime import datetime, timezone

gw_path, ch_path, as_json = sys.argv[1:4]
as_json = as_json == "1"

def load_json(p):
    path = Path(p)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

gw = load_json(gw_path) or {}
platforms = (gw.get("platforms") or {})
tg = (platforms.get("telegram") or {})
tg_state = (tg.get("state") or "unknown").lower()
gw_state = (gw.get("gateway_state") or "unknown").lower()

ch = load_json(ch_path) or {}
tg_chats = (ch.get("platforms") or {}).get("telegram") or []
tg_home = tg_chats[0]["id"] if tg_chats else None

report = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "gateway_state": gw_state,
    "telegram": {"state": tg_state, "home_chat_id": tg_home},
    "ok_for_telegram_aviso": tg_state == "connected",
}

issues = []
if gw_state not in ("running", "unknown"):
    issues.append(f"gateway_state={gw_state}")
if tg_state != "connected":
    issues.append(f"Telegram offline (state={tg_state})")
report["issues"] = issues

critical = tg_state != "connected"

if as_json:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(2 if critical else 0)

if critical:
    print("⚠ Aviso Web Jornal — Telegram OFFLINE")
    print("")
    print(f"Gateway: {gw_state}")
    print(f"Telegram: {tg_state}")
    print("")
    print("Áudio continua no site (news.mob.tec.br). Telegram é só o canal de aviso.")
    print("  Verifique o gateway Hermes (status) e reconecte o Telegram se precisar.")
    sys.exit(2)

# Telegram/gateway OK → silêncio
sys.exit(0)
PY
