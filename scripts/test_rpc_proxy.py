#!/usr/bin/env python3
"""Prove-it: RPCs via o site (8090 / news.mob.tec.br) não podem devolver 405.

O frontend usa SUPABASE_URL = origem do site. Sem proxy nginx → Kong,
POST /rest/v1/rpc/* cai no try_files e o nginx responde 405.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = os.environ.get("SITE_RPC_BASE", "http://127.0.0.1:8090").rstrip("/")
KONG = os.environ.get("KONG_RPC_BASE", "http://127.0.0.1:8080").rstrip("/")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def rpc_post(base: str, fn: str, payload: dict, key: str) -> tuple[int, object]:
    req = urllib.request.Request(
        f"{base}/rest/v1/rpc/{fn}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body) if body else None
            except json.JSONDecodeError:
                return resp.status, body[:240]
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body[:240]
        return err.code, parsed


def main() -> int:
    env = load_env()
    key = env.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not key:
        print("FAIL: SUPABASE_ANON_KEY ausente")
        return 2

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}: {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    # 1) Site must accept POST (this is the 405 bug)
    code, body = rpc_post(SITE, "fn_get_view_count", {"p_episode_id": "2026-08-06"}, key)
    check(
        "site POST fn_get_view_count != 405",
        code != 405,
        f"status={code} body={body!r}"[:200],
    )
    check(
        "site POST fn_get_view_count == 200",
        code == 200 and isinstance(body, dict) and "view_count" in body,
        f"status={code} body={body!r}"[:200],
    )

    for fn, payload in (
        ("fn_get_monetization_config", {}),
        ("fn_get_active_ad", {"p_format": "audio"}),
        ("get_episode_sponsors", {"p_episode_dates": ["2026-08-06"]}),
    ):
        code, body = rpc_post(SITE, fn, payload, key)
        check(f"site POST {fn} == 200", code == 200, f"status={code} body={body!r}"[:180])

    # 2) Bulk RPC
    code, body = rpc_post(
        SITE,
        "fn_get_view_counts_bulk",
        {"p_episode_ids": ["2026-08-06", "__bulk_missing_id__"]},
        key,
    )
    check(
        "site POST fn_get_view_counts_bulk == 200",
        code == 200 and isinstance(body, dict),
        f"status={code} body={body!r}"[:200],
    )
    if isinstance(body, dict):
        check(
            "bulk includes requested ids as keys",
            "2026-08-06" in body and "__bulk_missing_id__" in body,
            f"keys={list(body)[:8]}",
        )
        check(
            "missing id returns 0 (not omitted)",
            body.get("__bulk_missing_id__") == 0,
            f"value={body.get('__bulk_missing_id__')!r}",
        )

    # 3) Kong still works (control)
    code, body = rpc_post(KONG, "fn_get_view_count", {"p_episode_id": "2026-08-06"}, key)
    check("kong POST fn_get_view_count == 200", code == 200, f"status={code}")

    print()
    if failures:
        print(f"{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("OK: RPCs via site sem 405")
    return 0


if __name__ == "__main__":
    sys.exit(main())
