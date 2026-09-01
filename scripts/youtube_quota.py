#!/usr/bin/env python3
"""Contabilidade de quota + rotação de projetos (slots) da YouTube Data API v3.

A quota da API v3 é por PROJETO do Google Cloud (10.000 unidades/dia, reset à
meia-noite do Pacífico). Duas contas/projetos autorizando o MESMO canal dobram
a quota. Este módulo:

  * lê os slots de credentials/youtube_slots.json (ordem = prioridade);
  * mantém um ledger diário em credentials/youtube_quota.json;
  * embrulha o serviço googleapiclient para cobrar cada request automaticamente
    (custo derivado de recurso + método HTTP);
  * marca o slot como esgotado quando o Google devolve quotaExceeded e levanta
    QuotaExhausted para o chamador tentar o slot seguinte.

Só passa para o slot seguinte quando o atual não tem folga para a operação —
isto é, usa um até quase o limite antes de trocar.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CRED_DIR = ROOT / "credentials"
SLOTS_FILE = CRED_DIR / "youtube_slots.json"
LEDGER_FILE = CRED_DIR / "youtube_quota.json"
try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:
    from datetime import timezone, timedelta
    PACIFIC = timezone(timedelta(hours=-7))
DAILY_LIMIT = int(os.environ.get("YT_QUOTA_LIMIT", "10000"))
# Folga para requests baratos de verificação (whoami, list) no fim do dia.
SAFETY_MARGIN = int(os.environ.get("YT_QUOTA_MARGIN", "300"))

DEFAULT_SLOTS: list[dict] = [
    {
        "name": "slot1",
        "client_secret": "client_secret.json",
        "token": "token.json",
        "project": "hermes-youtube-uploader-506310",
        "account": "osmargfmi@gmail.com",
    },
]

# Custos oficiais por (recurso, método HTTP). Fonte: developers.google.com/
# youtube/v3/determine_quota_cost
COST: dict[str, dict[str, int]] = {
    "videos": {"GET": 1, "POST": 1600, "PUT": 50, "DELETE": 50},
    "thumbnails": {"POST": 50},
    "captions": {"GET": 50, "POST": 400, "PUT": 450, "DELETE": 50},
    "playlistItems": {"GET": 1, "POST": 50, "PUT": 50, "DELETE": 50},
    "playlists": {"GET": 1, "POST": 50, "PUT": 50, "DELETE": 50},
    "channels": {"GET": 1, "PUT": 50},
    "channelSections": {"GET": 1, "POST": 50, "PUT": 50, "DELETE": 50},
    "commentThreads": {"GET": 1, "POST": 50, "PUT": 50},
    "comments": {"GET": 1, "POST": 50, "PUT": 50, "DELETE": 50},
    "search": {"GET": 100},
    "subscriptions": {"GET": 1, "POST": 50, "DELETE": 50},
    "videoCategories": {"GET": 1},
    "i18nLanguages": {"GET": 1},
}
FALLBACK_COST = 50

# Custo estimado das operações do pipeline — usado para escolher o slot ANTES
# de gastar. upload = insert(1600) + playlists(~150) + margem.
OP_COST = {
    "upload": 1900,
    "apply-policy": 300,
    "thumbnail": 60,
    "captions": 900,
    "localize-en": 60,
    "comment": 60,
    "dynamic-playlist": 110,
    "whoami": 5,
    "quota": 0,
}


class QuotaExhausted(RuntimeError):
    """O slot não tem quota para a operação (ou o Google recusou por quota)."""


def quota_day(now: datetime | None = None) -> str:
    """Dia da quota no fuso do Pacífico (onde o Google faz o reset)."""
    return (now or datetime.now(PACIFIC)).astimezone(PACIFIC).date().isoformat()


def load_slots() -> list[dict]:
    if SLOTS_FILE.exists():
        data = json.loads(SLOTS_FILE.read_text(encoding="utf-8"))
        slots = data.get("slots") if isinstance(data, dict) else data
        if slots:
            return [s for s in slots if not s.get("disabled")]
    return list(DEFAULT_SLOTS)


def slot_by_name(name: str) -> dict:
    for s in load_slots():
        if s["name"] == name:
            return s
    raise SystemExit(f"❌ slot desconhecido: {name} (veja {SLOTS_FILE})")


def client_secret_path(slot: dict) -> Path:
    return CRED_DIR / slot["client_secret"]


def token_path(slot: dict) -> Path:
    return CRED_DIR / slot["token"]


def _load_ledger() -> dict:
    today = quota_day()
    if LEDGER_FILE.exists():
        try:
            data = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if data.get("date") == today:
            data.setdefault("slots", {})
            return data
        # Novo dia: guarda o histórico do dia anterior e zera.
        history = data.get("history") or []
        if data.get("date"):
            history.append({"date": data["date"], "slots": data.get("slots", {})})
            history = history[-30:]
        return {"date": today, "slots": {}, "history": history}
    return {"date": today, "slots": {}, "history": []}


def _save_ledger(data: dict) -> None:
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LEDGER_FILE)
    LEDGER_FILE.chmod(0o600)


def used(slot_name: str) -> int:
    entry = _load_ledger()["slots"].get(slot_name) or {}
    return int(entry.get("used", 0))


def charge(slot_name: str, units: int, *, label: str = "") -> int:
    data = _load_ledger()
    entry = data["slots"].setdefault(slot_name, {"used": 0, "calls": 0})
    entry["used"] = int(entry.get("used", 0)) + int(units)
    entry["calls"] = int(entry.get("calls", 0)) + 1
    entry["last"] = datetime.now(PACIFIC).isoformat(timespec="seconds")
    if label:
        entry["last_op"] = label
    _save_ledger(data)
    return entry["used"]


def mark_exhausted(slot_name: str, reason: str = "quotaExceeded") -> None:
    data = _load_ledger()
    entry = data["slots"].setdefault(slot_name, {"used": 0, "calls": 0})
    entry["used"] = max(int(entry.get("used", 0)), DAILY_LIMIT)
    entry["exhausted"] = reason
    entry["exhausted_at"] = datetime.now(PACIFIC).isoformat(timespec="seconds")
    _save_ledger(data)


def headroom(slot_name: str) -> int:
    return max(0, DAILY_LIMIT - SAFETY_MARGIN - used(slot_name))


def pick_slots(need: int) -> list[dict]:
    """Slots com folga para `need`, em ordem de prioridade.

    Sem candidato com folga, devolve todos os slots não esgotados pelo Google —
    melhor tentar e receber 403 do que travar por estimativa conservadora.
    """
    slots = load_slots()
    ok = [s for s in slots if headroom(s["name"]) >= need]
    if ok:
        return ok
    ledger = _load_ledger()["slots"]
    return [s for s in slots if not (ledger.get(s["name"], {}).get("exhausted"))]


def status_lines() -> list[str]:
    data = _load_ledger()
    lines = [f"quota day (PT): {data['date']}   limite/slot: {DAILY_LIMIT}  margem: {SAFETY_MARGIN}"]
    for s in load_slots():
        name = s["name"]
        entry = data["slots"].get(name) or {}
        u = int(entry.get("used", 0))
        flag = "  ESGOTADO" if entry.get("exhausted") else ""
        lines.append(
            f"  {name:6s} {u:>6d}/{DAILY_LIMIT}  folga={headroom(name):>5d}  "
            f"calls={entry.get('calls', 0)}  proj={s.get('project', '?')}{flag}"
        )
    return lines


# --------------------------------------------------------------------------- #
# Cobrança automática por request
# --------------------------------------------------------------------------- #

def request_cost(uri: str, method: str) -> int:
    path = uri.split("?", 1)[0]
    parts = [p for p in path.split("/") if p]
    resource = ""
    if "v3" in parts:
        idx = parts.index("v3")
        if idx + 1 < len(parts):
            resource = parts[idx + 1]
    if resource == "videos" and "rating" in parts:
        return 50
    table = COST.get(resource)
    if not table:
        return FALLBACK_COST
    return table.get(method.upper(), FALLBACK_COST)


def _is_quota_error(exc: Exception) -> bool:
    from googleapiclient.errors import HttpError

    if not isinstance(exc, HttpError):
        return False
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status not in (403, 429):
        return False
    text = str(exc).lower()
    return any(k in text for k in ("quotaexceeded", "dailylimitexceeded", "ratelimitexceeded", "quota"))


class _ChargedRequest:
    def __init__(self, inner, slot_name: str):
        self._inner = inner
        self._slot = slot_name

    def __getattr__(self, name) -> Any:
        return getattr(self._inner, name)

    def execute(self, *args, **kwargs) -> Any:
        cost = request_cost(getattr(self._inner, "uri", ""), getattr(self._inner, "method", "GET"))
        label = f"{getattr(self._inner, 'method', '')} {getattr(self._inner, 'uri', '')[:80]}"
        try:
            result = self._inner.execute(*args, **kwargs)
        except Exception as exc:
            # O Google debita a quota mesmo em erro; contabiliza igual.
            charge(self._slot, cost, label=label)
            if _is_quota_error(exc):
                mark_exhausted(self._slot)
                raise QuotaExhausted(f"{self._slot}: quota estourada ({exc})") from exc
            raise
        charge(self._slot, cost, label=label)
        return result


class ChargedResource:
    """Proxy do Resource do googleapiclient que cobra cada .execute()."""

    def __init__(self, inner, slot_name: str):
        self._inner = inner
        self._slot = slot_name

    @property
    def slot_name(self) -> str:
        return self._slot

    def __getattr__(self, name) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs) -> Any:
            return _wrap(attr(*args, **kwargs), self._slot)

        return wrapper


def _wrap(obj, slot_name: str) -> Any:
    from googleapiclient.discovery import Resource
    from googleapiclient.http import HttpRequest

    if isinstance(obj, HttpRequest):
        return _ChargedRequest(obj, slot_name)
    if isinstance(obj, Resource):
        return ChargedResource(obj, slot_name)
    return obj


def main() -> int:
    for line in status_lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
