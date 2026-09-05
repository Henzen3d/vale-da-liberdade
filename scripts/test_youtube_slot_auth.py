#!/usr/bin/env python3
"""Failover de slot YouTube quando o refresh token morre (invalid_grant)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from youtube_quota import SlotAuthDead, is_invalid_grant
import youtube_uploader as yu


class InvalidGrantFailoverTests(unittest.TestCase):
    def test_detects_invalid_grant(self) -> None:
        self.assertTrue(is_invalid_grant(RuntimeError("invalid_grant: Token has been expired or revoked.")))
        self.assertFalse(is_invalid_grant(RuntimeError("quotaExceeded")))

    def test_run_with_slots_skips_dead_auth(self) -> None:
        s1 = {"name": "slot1", "token": "token.json"}
        s2 = {"name": "slot2", "token": "token.slot2.json"}
        calls: list[str] = []

        def fn():
            slot = yu._ACTIVE_SLOT
            calls.append(slot["name"])
            if slot["name"] == "slot1":
                raise SlotAuthDead("slot1: token expirado/revogado")
            return 42

        with patch.object(yu.yq, "pick_slots", return_value=[s1, s2]), \
             patch.object(yu.yq, "token_path", return_value=Path("/tmp")), \
             patch.object(yu.yq, "used", return_value=0):
            out = yu.run_with_slots("upload", fn)
        self.assertEqual(out, 42)
        self.assertEqual(calls, ["slot1", "slot2"])


if __name__ == "__main__":
    unittest.main()
