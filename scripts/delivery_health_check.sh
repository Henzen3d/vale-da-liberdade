#!/usr/bin/env bash
# Health-check de entrega do Web Jornal / Hermes gateway.
#
# Comportamento (watchdog no_agent):
#   - stdout vazio + exit 0  → silêncio (entrega OK o suficiente)
#   - stdout com alerta + exit 0 → avisa o usuário
#   - exit 2 → problemas críticos (Telegram offline também)
#
# Uso:
#   bash scripts/delivery_health_check.sh
#   bash scripts/delivery_health_check.sh --strict-whatsapp   # alerta se WA down
#   bash scripts/delivery_health_check.sh --json
set -euo pipefail

STRICT_WA=0
JSON=0
for arg in "$@"; do
  case "$arg" in
    --strict-whatsapp) STRICT_WA=1 ;;
    --json) JSON=1 ;;
  esac
done

GATEWAY_STATE="${HERMES_GATEWAY_STATE:-$HOME/.hermes/gateway_state.json}"
CHANNEL_DIR="${HERMES_CHANNEL_DIR:-$HOME/.hermes/channel_directory.json}"
WA_PORT="${WHATSAPP_BRIDGE_PORT:-3000}"

python3 - "$GATEWAY_STATE" "$CHANNEL_DIR" "$WA_PORT" "$STRICT_WA" "$JSON" <<'PY'
import json, os, socket, sys
from pathlib import Path
from datetime import datetime, timezone

gw_path, ch_path, wa_port, strict_wa, as_json = sys.argv[1:6]
strict_wa = strict_wa == "1"
as_json = as_json == "1"
wa_port = int(wa_port)

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
wa = (platforms.get("whatsapp") or {})
tg_state = (tg.get("state") or "unknown").lower()
wa_state = (wa.get("state") or "unknown").lower()
gw_state = (gw.get("gateway_state") or "unknown").lower()

# TCP probe bridge WhatsApp (localhost:3000)
bridge_up = False
try:
    with socket.create_connection(("127.0.0.1", wa_port), timeout=1.5):
        bridge_up = True
except OSError:
    bridge_up = False

ch = load_json(ch_path) or {}
tg_chats = (ch.get("platforms") or {}).get("telegram") or []
tg_home = tg_chats[0]["id"] if tg_chats else None

report = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "gateway_state": gw_state,
    "telegram": {"state": tg_state, "home_chat_id": tg_home},
    "whatsapp": {"state": wa_state, "bridge_port": wa_port, "bridge_up": bridge_up},
    "ok_for_media_delivery": tg_state == "connected",
    "ok_for_whatsapp_text": wa_state == "connected" and bridge_up,
}

issues = []
if gw_state not in ("running", "unknown"):
    # unknown allowed if file missing partially
    if gw_state != "running":
        issues.append(f"gateway_state={gw_state}")
if tg_state != "connected":
    issues.append(f"Telegram offline (state={tg_state})")
if wa_state != "connected":
    issues.append(f"WhatsApp offline (state={wa_state})")
if not bridge_up:
    issues.append(f"Bridge WhatsApp porta {wa_port} fechada (localhost)")

report["issues"] = issues

critical = tg_state != "connected"
warn_wa = (wa_state != "connected") or (not bridge_up)

if as_json:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if critical:
        sys.exit(2)
    sys.exit(0)

# Delivery policy for Web Jornal audio:
# - Media prefers Telegram (reliable MEDIA path)
# - WhatsApp is nice-to-have for text/status
if critical:
    print("⚠ Entrega Web Jornal — Telegram OFFLINE")
    print("")
    print(f"Gateway: {gw_state}")
    print(f"Telegram: {tg_state}")
    print(f"WhatsApp: {wa_state} | bridge :{wa_port}={'UP' if bridge_up else 'DOWN'}")
    print("")
    print("Ação: reconecte o gateway/Telegram antes das 06:00 UTC.")
    print("  hermes gateway status")
    print("  hermes gateway restart   # se necessário")
    sys.exit(2)

if warn_wa:
    # Soft alert (stdout non-empty → cron no_agent delivers; exit 0)
    print("⚠ WhatsApp desconectado — áudio do Web Jornal vai pelo Telegram")
    print("")
    print(f"WhatsApp state: {wa_state}")
    print(f"Bridge localhost:{wa_port}: {'UP' if bridge_up else 'DOWN'}")
    print(f"Telegram: {tg_state} (ok para mídia)")
    if tg_home:
        print(f"Destino mídia sugerido: telegram:{tg_home}")
    print("")
    print("Para religar o WhatsApp no Hermes:")
    print("  hermes gateway status")
    print("  # reconecte a sessão WhatsApp do gateway se pedir QR/pair")
    print("")
    print("O cron diário deve entregar o MP3 no Telegram enquanto o WA estiver fora.")
    sys.exit(0)

# All good → silence
sys.exit(0)
PY
