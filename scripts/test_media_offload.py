#!/usr/bin/env python3
"""Testes do offload SSD → HD extra (sem tocar /mnt/hd_extra)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import media_offload as mo


class OffloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.archive = self.root / "hd" / "vale-media"
        self.archive.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def test_copy_verified_and_symlink(self) -> None:
        src = self.root / "clip.mp4"
        src.write_bytes(b"x" * 4096)
        dest = self.archive / "videos" / "clip.mp4"
        status = mo.offload_host_file(src, dest)
        self.assertEqual(status, "ok")
        self.assertTrue(dest.is_file())
        self.assertTrue(src.is_symlink())
        self.assertEqual(src.resolve(), dest.resolve())
        self.assertEqual(dest.stat().st_size, 4096)
        self.assertEqual(mo.offload_host_file(src, dest), "already")

    def test_copy_fail_keeps_original(self) -> None:
        src = self.root / "a.mp3"
        src.write_bytes(b"abc")
        dest = self.archive / "audio" / "a.mp3"

        def boom(*_a, **_k):
            raise OSError("disk full")

        with patch.object(mo.shutil, "copy2", side_effect=boom):
            status = mo.offload_host_file(src, dest)
        self.assertEqual(status, "copy-fail")
        self.assertTrue(src.is_file())
        self.assertFalse(src.is_symlink())

    def test_catalog_uses_r2_from_sidecar(self) -> None:
        epi = self.root / "episodes"
        epi.mkdir()
        (epi / "2026-09-01-r2.json").write_text(
            json.dumps({
                "date": "2026-09-01",
                "r2_uploaded": True,
                "catalog_url": "https://audio.mob.tec.br/audio/2026-09-01.mp3",
            }),
            encoding="utf-8",
        )
        with patch.object(mo, "PROJECT_ROOT", self.root):
            self.assertTrue(mo.catalog_uses_r2("2026-09-01"))
            self.assertFalse(mo.catalog_uses_r2("missing"))

    def test_after_r2_keeps_public_when_catalog_local(self) -> None:
        audio = self.root / "audio"
        public = self.root / "public" / "audio"
        audio.mkdir()
        public.mkdir(parents=True)
        (audio / "2026-01-01.mp3").write_bytes(b"m" * 8000)
        (public / "2026-01-01.mp3").write_bytes(b"m" * 8000)
        epi = self.root / "episodes"
        epi.mkdir()
        (epi / "2026-01-01-r2.json").write_text(
            json.dumps({
                "date": "2026-01-01",
                "r2_uploaded": True,
                "catalog_url": "./audio/2026-01-01.mp3",
            }),
            encoding="utf-8",
        )
        with patch.object(mo, "PROJECT_ROOT", self.root):
            r = mo.after_r2("2026-01-01", root=self.archive)
        self.assertTrue((audio / "2026-01-01.mp3").is_symlink())
        self.assertTrue((public / "2026-01-01.mp3").is_file())
        self.assertFalse((public / "2026-01-01.mp3").is_symlink())
        self.assertTrue(any("local-catalog" in s for s in r["skip"]))

    def test_after_r2_removes_public_when_on_r2(self) -> None:
        audio = self.root / "audio"
        public = self.root / "public" / "audio"
        audio.mkdir()
        public.mkdir(parents=True)
        (audio / "especial-abc.mp3").write_bytes(b"z" * 5000)
        (public / "especial-abc.mp3").write_bytes(b"z" * 5000)
        epi = self.root / "episodes"
        epi.mkdir()
        (epi / "especial-abc-r2.json").write_text(
            json.dumps({
                "date": "especial-abc",
                "r2_uploaded": True,
                "catalog_url": "https://audio.mob.tec.br/audio/especial-abc.mp3",
            }),
            encoding="utf-8",
        )
        with patch.object(mo, "PROJECT_ROOT", self.root):
            r = mo.after_r2("especial-abc", root=self.archive)
        self.assertTrue((audio / "especial-abc.mp3").is_symlink())
        self.assertFalse((public / "especial-abc.mp3").exists())
        self.assertTrue((self.archive / "audio" / "especial-abc.mp3").is_file())
        self.assertTrue(r["ok"])

    def test_after_youtube_moves_mp4_and_mockup_dir(self) -> None:
        videos = self.root / "output" / "videos"
        work = self.root / "output" / "brasil_e_mundo" / "mockup_video" / "AbC123xyz"
        videos.mkdir(parents=True)
        work.mkdir(parents=True)
        mp4 = videos / "especial-AbC123xyz-mockup.mp4"
        mp4.write_bytes(b"v" * 12000)
        (work / "scenes.json").write_text("{}", encoding="utf-8")
        with patch.object(mo, "PROJECT_ROOT", self.root):
            r = mo.after_youtube("AbC123xyz", root=self.archive)
        self.assertTrue(mp4.is_symlink())
        self.assertTrue((self.archive / "videos" / mp4.name).is_file())
        self.assertFalse(work.exists())
        self.assertTrue((self.archive / "mockup" / "AbC123xyz" / "scenes.json").is_file())
        self.assertTrue(r["ok"])

    def test_archive_ready_false_when_parent_missing(self) -> None:
        missing = Path("/no/such/vale-hd-parent-xyz/vale-media")
        self.assertFalse(mo.archive_ready(missing))


if __name__ == "__main__":
    unittest.main()
