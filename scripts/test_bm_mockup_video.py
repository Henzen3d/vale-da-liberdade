#!/usr/bin/env python3
"""Testes unitários do compositor mockup BM (sem rede, sem Playwright)."""
from __future__ import annotations

import unittest

from bm_mockup_video import build_metadata, host_kind, is_blocked_source_url, source_scenes
from pathlib import Path


class SourceFilterTests(unittest.TestCase):
    def test_blocks_youtube_and_self_pages(self):
        self.assertTrue(is_blocked_source_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_blocked_source_url("https://youtu.be/abc"))
        self.assertTrue(is_blocked_source_url("https://news.mob.tec.br/ep/especial-x.html"))
        self.assertFalse(is_blocked_source_url("https://www.cnnbrasil.com.br/economia/evergrande/"))

    def test_source_scenes_skips_self_and_youtube(self):
        ep = {
            "fonte_referencias": [
                {"veiculo": "ANCAPSU", "url": "https://www.youtube.com/watch?v=4B3BAjbSseU"},
                {"veiculo": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/economia/evergrande/?utm_source=x"},
                {"veiculo": "Vale", "url": "https://news.mob.tec.br/ep/especial-x.html", "self": True},
                {"veiculo": "BBC", "url": "https://www.bbc.com/portuguese/articles/cwy"},
            ]
        }
        scenes = source_scenes(ep)
        urls = [s["url"] for s in scenes]
        self.assertEqual(len(scenes), 2)
        self.assertTrue(urls[0].startswith("https://www.cnnbrasil.com.br"))
        self.assertNotIn("utm_source", urls[0])
        self.assertEqual(urls[1], "https://www.bbc.com/portuguese/articles/cwy")


class MetadataTests(unittest.TestCase):
    def test_metadata_never_cites_youtube(self):
        ep = {
            "titulo": "China culpa dono da Evergrande",
            "fonte_veiculo": "CNN Brasil",
            "tags": ["economia"],
            "fonte_referencias": [
                {"veiculo": "ANCAPSU", "url": "https://www.youtube.com/watch?v=4B3BAjbSseU"},
                {"veiculo": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/economia/evergrande/"},
            ],
        }
        audio = Path("/tmp/4B3BAjbSseU_2026-08-22.mp3")
        title, desc, tags = build_metadata("4B3BAjbSseU", ep, audio)
        self.assertIn("Evergrande", title)
        self.assertNotIn("youtube.com", desc.lower())
        self.assertNotIn("ancapsu", desc.lower())
        self.assertIn("cnnbrasil.com.br", desc)
        self.assertIn("economia", tags)


class HostPrepareTests(unittest.TestCase):
    def test_host_kind(self):
        self.assertEqual(host_kind("https://www.instagram.com/lito/"), "instagram")
        self.assertEqual(host_kind("https://www.bbc.com/portuguese/articles/cwy"), "bbc")
        self.assertEqual(host_kind("https://www.bbc.co.uk/news"), "bbc")
        self.assertEqual(host_kind("https://g1.globo.com/politica/noticia/x.ghtml"), "g1")
        self.assertEqual(host_kind("https://www.cnnbrasil.com.br/x"), "generic")


if __name__ == "__main__":
    unittest.main()
