#!/usr/bin/env python3
"""Testes unitários do compositor mockup BM (sem rede, sem Playwright)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bm_mockup_video import (
    MAX_PER_HOST,
    MAX_SCENES,
    build_chapters,
    build_metadata,
    cache_path_for_url,
    domain_of,
    episode_summary,
    find_episode_thumbnail,
    host_kind,
    is_blocked_source_url,
    one_line_subhead,
    pick_wallpaper,
    source_scenes,
    ticker_headlines,
    x_tweet_id,
)
from bm_scene_timeline import SceneBeat


class XEmbedTests(unittest.TestCase):
    def test_extracts_status_id_from_x_and_twitter(self):
        self.assertEqual(
            x_tweet_id("https://x.com/Maxcardoso/status/2094447494700626073"),
            "2094447494700626073",
        )
        self.assertEqual(
            x_tweet_id("https://twitter.com/mendlowicz/status/2094426086977253770"),
            "2094426086977253770",
        )
        self.assertEqual(
            x_tweet_id("https://x.com/user/status/123456789?s=20&t=abc"),
            "123456789",
        )

    def test_returns_none_for_non_status_urls(self):
        self.assertIsNone(x_tweet_id("https://x.com/Maxcardoso"))
        self.assertIsNone(x_tweet_id("https://www.cnnbrasil.com.br/economia/"))
        self.assertIsNone(x_tweet_id(""))
        self.assertIsNone(x_tweet_id(None))


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

    def test_source_scenes_respects_max_per_host_and_max_scenes(self):
        # 12 referências de 4 domínios diferentes
        ep = {
            "abertura": [{"texto": "Fala inicial", "fonte_url": "https://folha.uol.com.br/m3"}],
            "fonte_referencias": [
                {"veiculo": "G1", "url": "https://g1.globo.com/1", "role": "primary"},
                {"veiculo": "G1", "url": "https://g1.globo.com/2", "role": "supporting"},
                {"veiculo": "G1", "url": "https://g1.globo.com/3", "role": "visual"},
                {"veiculo": "G1", "url": "https://g1.globo.com/4", "role": "visual"},
                {"veiculo": "CNN", "url": "https://cnnbrasil.com.br/1", "role": "supporting"},
                {"veiculo": "CNN", "url": "https://cnnbrasil.com.br/2", "role": "supporting"},
                {"veiculo": "CNN", "url": "https://cnnbrasil.com.br/3", "role": "supporting"},
                {"veiculo": "Folha", "url": "https://folha.uol.com.br/m1", "role": "visual"},
                {"veiculo": "Folha", "url": "https://folha.uol.com.br/m2", "role": "visual"},
                {"veiculo": "Folha", "url": "https://folha.uol.com.br/m3", "role": "supporting"},
                {"veiculo": "Metrópoles", "url": "https://metropoles.com/1", "role": "supporting"},
                {"veiculo": "Metrópoles", "url": "https://metropoles.com/2", "role": "supporting"},
                {"veiculo": "Metrópoles", "url": "https://metropoles.com/3", "role": "visual"},
            ]
        }
        scenes = source_scenes(ep, max_sources=8)
        self.assertLessEqual(len(scenes), 8)

        # Nenhum host pode aparecer mais que 2 vezes
        host_counts: dict[str, int] = {}
        for s in scenes:
            h = domain_of(s["url"])
            host_counts[h] = host_counts.get(h, 0) + 1
        for h, count in host_counts.items():
            self.assertLessEqual(count, MAX_PER_HOST)

        # A URL citada no roteiro (folha/m3) deve estar incluída entre as primeiras
        urls = [s["url"] for s in scenes]
        self.assertIn("https://folha.uol.com.br/m3", urls)


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

    def test_chapters_with_timeline_beats(self):
        beats = [
            SceneBeat(t0=0.0, t1=30.0, url="https://g1.globo.com/1", veiculo="G1", kind="source"),
            SceneBeat(t0=30.0, t1=31.0, url="", veiculo="Transição", kind="broll"),
            SceneBeat(t0=31.0, t1=90.0, url="https://folha.uol.com.br/2", veiculo="Folha", kind="source"),
        ]
        chapters = build_chapters([], dur=100.0, timeline_beats=beats)
        labels = [c[1] for c in chapters]
        self.assertIn("Introdução", labels)
        self.assertIn("G1", labels)
        self.assertIn("Folha", labels)
        self.assertNotIn("Transição", labels)
        self.assertIn("Conclusão", labels)


class HostPrepareTests(unittest.TestCase):
    def test_host_kind(self):
        self.assertEqual(host_kind("https://www.instagram.com/lito/"), "instagram")
        self.assertEqual(host_kind("https://www.bbc.com/portuguese/articles/cwy"), "bbc")
        self.assertEqual(host_kind("https://www.bbc.co.uk/news"), "bbc")
        self.assertEqual(host_kind("https://g1.globo.com/politica/noticia/x.ghtml"), "g1")
        self.assertEqual(host_kind("https://www.cnnbrasil.com.br/x"), "generic")


class CacheTests(unittest.TestCase):
    def test_cache_path_for_url(self):
        url = "https://www.cnnbrasil.com.br/politica/artigo"
        p = cache_path_for_url(url)
        self.assertTrue(p.name.endswith(".png"))
        self.assertIn("capture-cache", str(p))

    def test_cache_version_invalidates_unstyled_shots(self):
        from bm_mockup_video import CAPTURE_CACHE_VERSION, wait_for_styled_capture
        self.assertTrue(
            CAPTURE_CACHE_VERSION.startswith("css-")
            or CAPTURE_CACHE_VERSION.startswith("handler-")
        )
        self.assertNotEqual(
            cache_path_for_url("https://www.cnnbrasil.com.br/politica/artigo").name,
            "same-as-old-hash",
        )
        self.assertTrue(callable(wait_for_styled_capture))


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
        # find_episode_thumbnail resolve a capa YouTube do manifesto (yt_bm_*),
        # sem fallback para bm_*; aceita ambos os prefixos por segurança.
        self.assertTrue(p.name.startswith(("yt_bm_4B3BAjbSseU", "bm_4B3BAjbSseU")))


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
        self.assertRegex(
            html,
            r"\.portal-page-shot\.is-portrait\s*\{[^}]*background:\s*#ffffff",
        )
        self.assertNotIn("background: #0b0d12", html)
        self.assertIn("pageVideo.videoHeight > pageVideo.videoWidth", html)
        self.assertIn("is-portrait", html)
        self.assertIn("classList.toggle", html)


if __name__ == "__main__":
    unittest.main()
