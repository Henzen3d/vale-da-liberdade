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

    def test_free_tier_requests_with_short_retry_is_not_daily(self):
        """429 real do Google (TTS/flash): mesma métrica do RPD, mas retry em segundos = RPM."""
        msg = (
            "429 RESOURCE_EXHAUSTED. You exceeded your current quota, please check "
            "your plan and billing details. "
            "* Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 10, model: gemini-2.5-flash-tts\n"
            "Please retry in 33.295323111s."
        )
        self.assertFalse(gc._is_google_daily_quota_error(msg))
        self.assertFalse(gc._is_google_daily_quota_error(msg, model="gemini-3.1-flash-tts-preview"))

    def test_free_tier_limit_matching_rpd_without_short_retry_is_daily(self):
        msg = (
            "You exceeded your current quota. "
            "* Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 10, "
            "model: gemini-3.1-flash-tts-preview"
        )
        self.assertTrue(gc._is_google_daily_quota_error(msg))
        self.assertTrue(
            gc._is_google_daily_quota_error(msg, model="gemini-3.1-flash-tts-preview")
        )

    def test_flash_limit_20_without_retry_is_daily(self):
        msg = (
            "Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash"
        )
        self.assertTrue(gc._is_google_daily_quota_error(msg, model="gemini-3.6-flash"))

    def test_flash_limit_5_is_rpm_not_daily(self):
        msg = (
            "Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 5, model: gemini-3.6-flash"
        )
        self.assertFalse(gc._is_google_daily_quota_error(msg, model="gemini-3.6-flash"))


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

    def test_stale_exhausted_until_does_not_block_when_no_real_requests(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            usage_file = Path(tmp) / "gemini_usage.json"
            client = gc.GeminiClient(api_key="AIzaSyTESTKEY0001", usage_file=str(usage_file))
            client.client = MagicMock()
            key_id = gc._key_id(client.api_key)
            now = datetime(2026, 9, 5, 15, 46, tzinfo=PACIFIC).timestamp()
            until = datetime(2026, 9, 6, 0, 0, tzinfo=PACIFIC).timestamp()
            gc._save_usage(
                usage_file,
                {
                    key_id: {
                        "gemini-3.1-flash-tts-preview": {
                            "requests": [],
                            "tokens": [],
                            "exhausted_until": until,
                        }
                    }
                },
            )
            with patch("gemini_client.time.time", return_value=now):
                reserved = client._enforce_rate_limit("gemini-3.1-flash-tts-preview", 10)
            self.assertGreater(reserved, 0)
            data = gc._load_usage(usage_file)
            slot = data[key_id]["gemini-3.1-flash-tts-preview"]
            self.assertEqual(float(slot.get("exhausted_until") or 0), 0)

    def test_ten_real_requests_still_block_local_rpd(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            usage_file = Path(tmp) / "gemini_usage.json"
            client = gc.GeminiClient(api_key="AIzaSyTESTKEY0001", usage_file=str(usage_file))
            client.client = MagicMock()
            key_id = gc._key_id(client.api_key)
            now = datetime(2026, 9, 5, 15, 46, tzinfo=PACIFIC).timestamp()
            stamps = [now - 3600 + i * 30 for i in range(10)]
            gc._save_usage(
                usage_file,
                {key_id: {"gemini-3.1-flash-tts-preview": {"requests": stamps, "tokens": []}}},
            )
            with patch("gemini_client.time.time", return_value=now):
                with self.assertRaises(RuntimeError) as ctx:
                    client._enforce_rate_limit("gemini-3.1-flash-tts-preview", 10)
            self.assertIn("Limite diário atingido", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
