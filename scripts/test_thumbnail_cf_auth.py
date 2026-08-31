#!/usr/bin/env python3
"""RED/GREEN: Cloudflare OAuth 1h + placeholder cache bloqueavam a thumbnail YouTube."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import thumbnail_generator as tg  # noqa: E402


def _fake_img(color=(40, 40, 40)) -> Image.Image:
    img = Image.new("RGB", (1280, 720), color)
    for x in range(0, 1280, 40):
        img.putpixel((x, 100), (184, 134, 59))
    return img


class WranglerOauthTests(unittest.TestCase):
    def test_expired_oauth_is_detected(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        self.assertTrue(tg._wrangler_oauth_expired(past))
        self.assertFalse(tg._wrangler_oauth_expired(future))
        self.assertTrue(tg._wrangler_oauth_expired(""))

    def test_refresh_writes_new_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "default.toml"
            cfg.write_text(
                'oauth_token = "cfoat_OLD"\n'
                'expiration_time = "2020-01-01T00:00:00.000Z"\n'
                'refresh_token = "cfort_OLD"\n',
                encoding="utf-8",
            )
            payload = {
                "access_token": "cfoat_NEW",
                "refresh_token": "cfort_NEW",
                "expires_in": 3600,
                "token_type": "bearer",
            }
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = payload
            with patch.object(tg, "_WRANGLER_CONFIGS", (cfg,)):
                with patch.object(tg.requests, "post", return_value=mock_resp) as post:
                    account, token = tg._refresh_wrangler_oauth()
            self.assertEqual(token, "cfoat_NEW")
            text = cfg.read_text(encoding="utf-8")
            self.assertIn("cfoat_NEW", text)
            self.assertIn("cfort_NEW", text)
            self.assertNotIn("cfoat_OLD", text)
            self.assertTrue(post.called)
            args, kwargs = post.call_args
            self.assertIn("oauth2/token", args[0])
            self.assertEqual(kwargs["data"]["grant_type"], "refresh_token")
            self.assertEqual(kwargs["data"]["refresh_token"], "cfort_OLD")


class CascadeFallbackTests(unittest.TestCase):
    def test_pollinations_is_enabled_after_cloudflare(self) -> None:
        enabled = [m for m in tg._load_cascade() if m.enabled]
        names = [m.name for m in enabled]
        self.assertGreaterEqual(len(enabled), 2, names)
        self.assertEqual(enabled[0].api_style, "cloudflare")
        self.assertIn("pollinations-flux", names)
        self.assertEqual(
            next(m.api_style for m in enabled if m.name == "pollinations-flux"),
            "pollinations",
        )

    def test_cloudflare_fail_uses_pollinations(self) -> None:
        cascade = [m for m in tg._load_cascade() if m.enabled]

        def fake_once(model, prompt):
            if model.api_style == "cloudflare":
                raise tg.ModelFailed("auth HTTP 401: Authentication error")
            if model.api_style == "pollinations":
                return _fake_img((20, 20, 20)), 40
            raise tg.ModelFailed(f"unexpected {model.api_style}")

        with patch.object(tg, "_call_model_once", side_effect=fake_once):
            with patch.object(tg, "quota_remaining", return_value=10):
                img, info = tg.generate_cover_image(
                    "editorial amber",
                    "bm_test401",
                    cascade=cascade,
                    allow_safety_regen=False,
                )
        self.assertFalse(info.get("is_placeholder"))
        self.assertEqual(info.get("image_model_used"), "pollinations-flux")
        self.assertGreaterEqual(info.get("fallback_level", -1), 1)
        self.assertEqual(img.size, (1280, 720))

    def test_placeholder_cache_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            date = "2099-02-02"
            eid = "bm_regenPH"
            thumb_dir = root / "thumbnails" / date
            thumb_dir.mkdir(parents=True)
            webp = thumb_dir / f"{eid}.webp"
            jpg = thumb_dir / f"{eid}.jpg"
            _fake_img((5, 5, 5)).save(webp, "WEBP")
            _fake_img((5, 5, 5)).save(jpg, "JPEG")
            eps = root / "output" / "brasil_e_mundo" / "episodes"
            eps.mkdir(parents=True)
            man = {
                "episode_id": f"especial-{eid[3:]}",
                "video_id": eid[3:],
                "date": date,
                "editorial_image_path": str(jpg),
                "editorial_is_placeholder": True,
                "editorial_image_model": "local-placeholder",
            }
            (eps / f"especial-{eid[3:]}.image-manifest.json").write_text(
                json.dumps(man), encoding="utf-8"
            )

            fresh = _fake_img((90, 40, 10))

            def fake_cover(prompt, episode_id, **kwargs):
                return fresh, {
                    "image_model_used": "pollinations-flux",
                    "fallback_level": 1,
                    "is_placeholder": False,
                    "estimated_cost_usd": 0.0,
                    "generation_attempts": [],
                }

            with patch.object(tg, "PROJECT_ROOT", root), patch.object(
                tg, "THUMBNAILS_DIR", root / "thumbnails"
            ), patch.object(tg, "generate_cover_image", side_effect=fake_cover), patch.object(
                tg, "generate_image_prompt", return_value=("p", "test")
            ), patch(
                "episode_image_manifest.PROJECT_ROOT", root
            ), patch(
                "episode_image_manifest.EPS_DIR", eps
            ), patch(
                "episode_image_manifest.THUMBS_DIR", root / "thumbnails"
            ):
                result = tg.generate_thumbnail_for_episode(
                    date=date,
                    episode_id=eid,
                    headline="Manchete teste",
                    summary="Resumo teste",
                    force=False,
                )
            self.assertFalse(result.get("skipped"))
            self.assertFalse(result.get("is_placeholder"))
            self.assertEqual(result.get("image_model_used"), "pollinations-flux")


if __name__ == "__main__":
    unittest.main()
