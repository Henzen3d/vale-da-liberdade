#!/usr/bin/env python3
"""Regressão: a imagem editorial do episódio X tem de ser a entrada do mockup X.

Prove-it / TDD — estes testes devem FALHAR no código antigo (heurística,
placeholder silencioso, fallback para ep_*.jpg / bm_* sem mockup) e PASSAR
depois do manifesto explícito + fail-hard.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import episode_image_manifest as eim  # noqa: E402
import youtube_thumbnail as yt  # noqa: E402
import bm_mockup_video as bmv  # noqa: E402


def _png(path: Path, color: tuple[int, int, int], size=(64, 36)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def _jpg(path: Path, color: tuple[int, int, int], size=(1280, 720)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG", quality=90)
    return path


class ManifestIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.eps = self.root / "output" / "brasil_e_mundo" / "episodes"
        self.thumbs = self.root / "thumbnails"
        self.eps.mkdir(parents=True)
        self.thumbs.mkdir(parents=True)
        self.patches = [
            patch.object(eim, "PROJECT_ROOT", self.root),
            patch.object(eim, "EPS_DIR", self.eps),
            patch.object(eim, "THUMBS_DIR", self.thumbs),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_missing_editorial_raises(self) -> None:
        with self.assertRaises(eim.EditorialImageError) as ctx:
            eim.resolve_editorial_image("vidMISSING")
        self.assertIn("manifest", str(ctx.exception).lower())

    def test_placeholder_is_refused(self) -> None:
        img = _jpg(self.thumbs / "2026-08-24" / "bm_vidPH.jpg", (10, 10, 10))
        eim.record_editorial(
            video_id="vidPH",
            date="2026-08-24",
            editorial_image_path=img,
            model="local-placeholder",
            is_placeholder=True,
        )
        with self.assertRaises(eim.EditorialImageError) as ctx:
            eim.resolve_editorial_image("vidPH")
        self.assertIn("placeholder", str(ctx.exception).lower())

    def test_other_episode_file_is_refused(self) -> None:
        other = _jpg(self.thumbs / "2026-08-24" / "bm_OTHER.jpg", (200, 0, 0))
        eim.record_editorial(
            video_id="vidX",
            date="2026-08-24",
            editorial_image_path=other,
            model="@cf/black-forest-labs/flux-1-schnell",
            is_placeholder=False,
        )
        with self.assertRaises(eim.EditorialImageError):
            eim.resolve_editorial_image("vidX")

    def test_stale_hash_is_refused(self) -> None:
        img = _jpg(self.thumbs / "2026-08-24" / "bm_vidH.jpg", (0, 200, 0))
        eim.record_editorial(
            video_id="vidH",
            date="2026-08-24",
            editorial_image_path=img,
            model="@cf/black-forest-labs/flux-1-schnell",
            is_placeholder=False,
        )
        # corrompe o arquivo depois do manifesto
        _jpg(img, (1, 2, 3))
        with self.assertRaises(eim.EditorialImageError) as ctx:
            eim.resolve_editorial_image("vidH")
        self.assertIn("hash", str(ctx.exception).lower())

    def test_empty_file_is_refused(self) -> None:
        img = self.thumbs / "2026-08-24" / "bm_vidE.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"")
        man = eim.manifest_path("vidE")
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps({
            "episode_id": "especial-vidE",
            "editorial_image_path": str(img),
            "editorial_image_hash": "00",
            "editorial_image_generated_at": "now",
            "editorial_is_placeholder": False,
        }))
        with self.assertRaises(eim.EditorialImageError):
            eim.resolve_editorial_image("vidE")

    def test_happy_path_returns_same_hash(self) -> None:
        img = _jpg(self.thumbs / "2026-08-24" / "bm_vidOK.jpg", (30, 80, 180))
        rec = eim.record_editorial(
            video_id="vidOK",
            date="2026-08-24",
            editorial_image_path=img,
            model="@cf/black-forest-labs/flux-1-schnell",
            is_placeholder=False,
        )
        resolved = eim.resolve_editorial_image("vidOK")
        self.assertEqual(resolved.resolve(), img.resolve())
        self.assertEqual(eim.sha256_file(resolved), rec["editorial_image_hash"])

    def test_two_episodes_do_not_contaminate(self) -> None:
        a = _jpg(self.thumbs / "2026-08-24" / "bm_AAA.jpg", (255, 0, 0))
        b = _jpg(self.thumbs / "2026-08-24" / "bm_BBB.jpg", (0, 0, 255))
        eim.record_editorial("AAA", "2026-08-24", a, "@cf/black-forest-labs/flux-1-schnell", False)
        eim.record_editorial("BBB", "2026-08-24", b, "@cf/black-forest-labs/flux-1-schnell", False)
        self.assertEqual(eim.resolve_editorial_image("AAA").name, "bm_AAA.jpg")
        self.assertEqual(eim.resolve_editorial_image("BBB").name, "bm_BBB.jpg")
        self.assertNotEqual(eim.sha256_file(a), eim.sha256_file(b))

    def test_concurrent_writes_keep_identity(self) -> None:
        errors: list[str] = []

        def worker(vid: str, color: tuple[int, int, int]) -> None:
            try:
                img = _jpg(self.thumbs / "2026-08-24" / f"bm_{vid}.jpg", color)
                eim.record_editorial(vid, "2026-08-24", img, "@cf/black-forest-labs/flux-1-schnell", False)
                got = eim.resolve_editorial_image(vid)
                if got.name != f"bm_{vid}.jpg":
                    errors.append(f"{vid} resolved {got.name}")
                if eim.sha256_file(got) != eim.sha256_file(img):
                    errors.append(f"{vid} hash mismatch")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{vid}: {exc}")

        threads = [
            threading.Thread(target=worker, args=("CON1", (11, 22, 33))),
            threading.Thread(target=worker, args=("CON2", (44, 55, 66))),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_youtube_record_stores_input_hash(self) -> None:
        img = _jpg(self.thumbs / "2026-08-24" / "bm_vidYT.jpg", (9, 9, 9))
        eim.record_editorial("vidYT", "2026-08-24", img, "@cf/black-forest-labs/flux-1-schnell", False)
        out = _jpg(self.thumbs / "2026-08-24" / "yt_bm_vidYT.jpg", (1, 1, 1))
        rec = eim.record_youtube_thumbnail("vidYT", out, editorial_used=img)
        self.assertEqual(rec["youtube_thumbnail_input_hash"], eim.sha256_file(img))
        self.assertEqual(eim.resolve_youtube_thumbnail("vidYT").resolve(), out.resolve())

    def test_upload_resolver_refuses_editorial_fallback(self) -> None:
        img = _jpg(self.thumbs / "2026-08-24" / "bm_vidFB.jpg", (8, 8, 8))
        eim.record_editorial("vidFB", "2026-08-24", img, "@cf/black-forest-labs/flux-1-schnell", False)
        with self.assertRaises(eim.YoutubeThumbnailError):
            eim.resolve_youtube_thumbnail("vidFB")


class LegacyHeuristicBanTests(unittest.TestCase):
    """O código de produção não pode mais escolher ep_*.jpg nem 'latest'."""

    def test_episode_topic_image_does_not_offer_daily_ep(self) -> None:
        src = (SCRIPT_DIR / "youtube_thumbnail.py").read_text(encoding="utf-8")
        self.assertNotIn('ep_{date}.jpg', src)
        self.assertNotIn('ep_{date}', src)
        self.assertIn("resolve_editorial_image", src)

    def test_youtube_thumbnail_does_not_glob_latest(self) -> None:
        src = (SCRIPT_DIR / "youtube_thumbnail.py").read_text(encoding="utf-8")
        self.assertNotIn("THUMBS_DIR.glob", src)
        self.assertNotIn("sorted(THUMBS_DIR", src)

    def test_find_episode_thumbnail_does_not_fall_back_to_bm(self) -> None:
        src = (SCRIPT_DIR / "bm_mockup_video.py").read_text(encoding="utf-8")
        self.assertIn("resolve_youtube_thumbnail", src)
        # a lista antiga entregava bm_ como se fosse thumbnail do YouTube
        self.assertNotIn('f"bm_{video_id}.jpg"', src)

    def test_bm_pipeline_has_step_4_6(self) -> None:
        src = (SCRIPT_DIR / "bm_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("Etapa 4.6", src)
        self.assertIn("generate_youtube_thumbnail", src)

    def test_hourly_still_goes_through_pipeline(self) -> None:
        src = (PROJECT_ROOT / "scripts" / "bm-hourly-pipeline.sh").read_text(encoding="utf-8")
        self.assertIn("bm_pipeline.py process-queue", src)
        self.assertIn("bm_mockup_video.py", src)


class YoutubeGenerateIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.eps = self.root / "output" / "brasil_e_mundo" / "episodes"
        self.thumbs = self.root / "thumbnails" / "2026-08-24"
        self.eps.mkdir(parents=True)
        self.thumbs.mkdir(parents=True)
        self.img = _jpg(self.thumbs / "bm_IDEM.jpg", (120, 40, 200))
        self.patches = [
            patch.object(eim, "PROJECT_ROOT", self.root),
            patch.object(eim, "EPS_DIR", self.eps),
            patch.object(eim, "THUMBS_DIR", self.root / "thumbnails"),
            patch.object(yt, "PROJECT_ROOT", self.root),
            patch.object(yt, "THUMBS_DIR", self.root / "thumbnails"),
            patch.object(yt, "EPS_DIR", self.eps),
        ]
        for p in self.patches:
            p.start()
        eim.record_editorial(
            "IDEM", "2026-08-24", self.img,
            "@cf/black-forest-labs/flux-1-schnell", False,
        )

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_generate_twice_same_hash(self) -> None:
        fake_out = self.thumbs / "yt_bm_IDEM.png"

        def fake_render(cfg, out_png: Path) -> None:
            # o mockup tem de incorporar o hash da editorial usada
            payload = eim.sha256_file(Path(cfg["topicImage"])).encode() + b"|mockup"
            out_png.parent.mkdir(parents=True, exist_ok=True)
            out_png.write_bytes(payload)
            Image.new("RGB", (100, 56), (1, 2, 3)).save(out_png.with_suffix(".jpg"), "JPEG")

        with patch.object(yt, "_render_to", side_effect=lambda cfg, out: fake_render(cfg, out)), \
             patch.object(yt, "next_presenter", return_value=self.img), \
             patch.object(yt, "generate_headline", return_value=("TITULO FIXO", "FIXO")), \
             patch.object(yt, "load_episode", return_value={"titulo": "TITULO FIXO"}):
            r1 = yt.generate_youtube_thumbnail("IDEM", date="2026-08-24")
            r2 = yt.generate_youtube_thumbnail("IDEM", date="2026-08-24")
        self.assertTrue(r1["ok"])
        self.assertTrue(r2["ok"])
        h1 = eim.sha256_file(Path(r1["youtube_thumbnail_path"]))
        h2 = eim.sha256_file(Path(r2["youtube_thumbnail_path"]))
        self.assertEqual(h1, h2)
        man = eim.load_manifest("IDEM")
        self.assertEqual(man["youtube_thumbnail_input_hash"], eim.sha256_file(self.img))
        self.assertEqual(man["editorial_image_hash"], man["youtube_thumbnail_input_hash"])


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    unittest.main(verbosity=2)
