#!/usr/bin/env python3
"""Testes unitários do compositor mockup BM (sem rede, sem Playwright)."""
from __future__ import annotations

import unittest

from bm_mockup_video import (
    build_metadata,
    episode_summary,
    find_episode_thumbnail,
    host_kind,
    is_blocked_source_url,
    one_line_subhead,
    pick_wallpaper,
    source_scenes,
    ticker_headlines,
)
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
            "abertura": [
                {"speaker": "Peter", "texto": "O Estado chinês condenou o dono da Evergrande. A narrativa oficial é fraude."}
            ],
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
        self.assertIn("news.mob.tec.br", desc)
        self.assertIn("narrativa oficial é fraude", desc)
        self.assertIn("economia", tags)


class HostPrepareTests(unittest.TestCase):
    def test_host_kind(self):
        self.assertEqual(host_kind("https://www.instagram.com/lito/"), "instagram")
        self.assertEqual(host_kind("https://www.bbc.com/portuguese/articles/cwy"), "bbc")
        self.assertEqual(host_kind("https://www.bbc.co.uk/news"), "bbc")
        self.assertEqual(host_kind("https://g1.globo.com/politica/noticia/x.ghtml"), "g1")
        self.assertEqual(host_kind("https://www.cnnbrasil.com.br/x"), "generic")


class WallpaperThumbTests(unittest.TestCase):
    def test_pick_wallpaper_is_deterministic(self):
        a = pick_wallpaper("4B3BAjbSseU")
        b = pick_wallpaper("4B3BAjbSseU")
        c = pick_wallpaper("90v4O6Lx4hg")
        if a is None:
            self.skipTest("pasta wallpaper vazia neste checkout")
        self.assertEqual(a, b)
        self.assertNotEqual(a.suffix.lower(), ".gif")
        if c is not None:
            # ids diferentes quase sempre caem em arquivos diferentes
            self.assertTrue(a.exists())

    def test_summary_uses_abertura(self):
        ep = {"abertura": [{"texto": "Primeira frase. Segunda frase longa sobre o caso."}]}
        s = episode_summary(ep, limit=80)
        self.assertTrue(s.startswith("Primeira frase."))
        self.assertNotIn("youtube", s.lower())

    def test_find_thumbnail_for_known_episode(self):
        p = find_episode_thumbnail("4B3BAjbSseU", "2026-08-22")
        if p is None:
            self.skipTest("thumbnail do episódio não está neste checkout")
        self.assertTrue(p.name.startswith("bm_4B3BAjbSseU"))


class LowerThirdCopyTests(unittest.TestCase):
    def test_subhead_is_not_the_source_name(self):
        ep = {
            "titulo": "CHINA Culpa DONO da EVERGRANDE",
            "fonte_veiculo": "CNN Brasil",
            "abertura": [
                {"texto": "O Estado chinês jogou o dono da Evergrande na prisão perpétua. A narrativa oficial é fraude."}
            ],
        }
        sub = one_line_subhead(ep)
        self.assertNotIn("CNN", sub)
        self.assertNotIn("cnnbrasil", sub.lower())
        self.assertTrue(len(sub) <= 88)
        self.assertTrue(len(sub) > 10)

    def test_ticker_starts_with_current_title(self):
        ep = {"titulo": "Episódio atual de teste do ticker"}
        items = ticker_headlines(ep, video_id="zzzz-not-real")
        self.assertTrue(items)
        self.assertIn("EPISÓDIO ATUAL", items[0])
        self.assertLessEqual(len(items), 7)


class XVideoFitTests(unittest.TestCase):
    def test_mockup_contains_portrait_video(self):
        html = (
            Path(__file__).resolve().parent.parent
            / "references/youtube/mockup-browser/mockup-brower.html"
        ).read_text(encoding="utf-8")
        self.assertIn(".portal-page-shot.is-portrait", html)
        self.assertRegex(
            html,
            r"\.portal-page-shot\.is-portrait\s*\{[^}]*object-fit:\s*contain",
        )
        self.assertIn("pageVideo.videoHeight > pageVideo.videoWidth", html)
        self.assertIn("is-portrait", html)
        self.assertIn("classList.toggle", html)


if __name__ == "__main__":
    unittest.main()
