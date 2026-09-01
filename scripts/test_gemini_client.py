#!/usr/bin/env python3
"""Testes do tracker RPD/RPM do GeminiClient (sem rede)."""
from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gemini_client as gc

PACIFIC = ZoneInfo("America/Los_Angeles")


class DailyQuotaDetectionTests(unittest.TestCase):
    def test_google_per_day_is_daily(self):
        self.assertTrue(gc._is_daily_quota_error("Quota exceeded for metric: GenerateRequestsPerDay"))
        self.assertTrue(gc._is_daily_quota_error("You exceeded your current quota per day"))

    def test_local_rpd_message_rotates_but_is_not_google_confirm(self):
        msg = (
            "Limite diário atingido (RPD de 10) para o modelo "
            "gemini-3.1-flash-tts-preview. Aguarde o reset da janela."
        )
        self.assertTrue(gc._is_local_rpd_block(msg))
        self.assertFalse(gc._is_google_daily_quota_error(msg))

    def test_rpm_429_is_not_daily(self):
        self.assertFalse(
            gc._is_google_daily_quota_error(
                "429 RESOURCE_EXHAUSTED. Resource has been exhausted (e.g. check quota)."
            )
        )


class PacificRpdWindowTests(unittest.TestCase):
    def test_requests_before_pacific_midnight_are_dropped(self):
        now = datetime(2026, 9, 2, 0, 5, tzinfo=PACIFIC)
        yesterday = datetime(2026, 9, 1, 12, 0, tzinfo=PACIFIC).timestamp()
        today = datetime(2026, 9, 2, 0, 1, tzinfo=PACIFIC).timestamp()
        kept = gc._requests_in_rpd_window([yesterday, today], now.timestamp())
        self.assertEqual(kept, [today])

    def test_identical_exhausted_pad_is_not_real_usage(self):
        now = 1_788_216_047.6210706
        padded = [now] * 10
        cleaned = gc._collapse_fake_rpd_pad(padded)
        self.assertEqual(cleaned, [])


class EnforceRateLimitTests(unittest.TestCase):
    def test_pacific_reset_allows_new_day_after_false_pad(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            usage_file = Path(tmp) / "gemini_usage.json"
            client = gc.GeminiClient(api_key="AIzaSyTESTKEY0001", usage_file=str(usage_file))
            client.client = MagicMock()
            key_id = gc._key_id(client.api_key)
            yesterday_noon = datetime(2026, 9, 1, 12, 0, tzinfo=PACIFIC).timestamp()
            gc._save_usage(
                usage_file,
                {key_id: {"gemini-3.1-flash-tts-preview": {"requests": [yesterday_noon] * 10, "tokens": []}}},
            )
            now = datetime(2026, 9, 2, 0, 10, tzinfo=PACIFIC).timestamp()
            with patch("gemini_client.time.time", return_value=now):
                reserved = client._enforce_rate_limit("gemini-3.1-flash-tts-preview", 10)
            self.assertGreater(reserved, 0)
            data = gc._load_usage(usage_file)
            reqs = data[key_id]["gemini-3.1-flash-tts-preview"]["requests"]
            self.assertEqual(len(reqs), 1)


if __name__ == "__main__":
    unittest.main()
