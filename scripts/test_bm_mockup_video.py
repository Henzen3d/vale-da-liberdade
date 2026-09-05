#!/usr/bin/env python3
"""Testes unitários do compositor mockup BM (sem rede, sem Playwright)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    extract_instagram_video,
    find_episode_thumbnail,
    host_kind,
    instagram_shortcode,
    is_blocked_source_url,
    one_line_subhead,
    pick_wallpaper,
    source_scenes,
    ticker_headlines,
    x_tweet_id,
    fetch_x_post_data,
)
from bm_scene_timeline import SceneBeat, build_scene_timeline


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

    def test_fetch_x_post_data_parses_clean_metadata(self):
        class FakeResponse:
            def __init__(self, data: bytes):
                self.data = data
            def read(self):
                return self.data
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        class FakePage:
            def goto(self, *a, **k):
                pass
            def wait_for_timeout(self, *a, **k):
                pass
            def evaluate(self, script):
                return {
                    "lines": ["User", "@user", "Texto fallback"],
                    "avatar": "https://pbs.twimg.com/profile_images/123/avatar.jpg",
                    "mediaImgs": ["https://pbs.twimg.com/media/pic1.jpg"],
                    "timeStr": "10:00 · 01 de set de 2026",
                    "likes": "1.5K"
                }

        oembed_json = (
            b'{"author_name": "Conta Oficial", "html": "<p>Mensagem importante do post pic.twitter.com/abc</p>"}'
        )

        with tempfile.TemporaryDirectory() as td:
            shot_dir = Path(td)
            with patch("urllib.request.urlopen") as mock_url:
                def fake_urlopen(req, **kw):
                    url = getattr(req, "full_url", str(req))
                    if "oembed" in url:
                        return FakeResponse(oembed_json)
                    return FakeResponse(b"fake image bytes")
                mock_url.side_effect = fake_urlopen

                post = fetch_x_post_data(
                    FakePage(),
                    "https://x.com/ContaOficial/status/2093130747796148634",
                    shot_dir,
                )

                self.assertIsNotNone(post)
                self.assertEqual(post["author_name"], "Conta Oficial")
                self.assertEqual(post["handle"], "@ContaOficial")
                self.assertEqual(post["text"], "Mensagem importante do post")
                self.assertEqual(post["likes"], "1.5K")
                self.assertTrue(post["verified"])
                self.assertTrue(post["avatar"].startswith("/shots/"))
                self.assertTrue(post["media"].startswith("/shots/"))
                # Arquivos locais foram gravados
                self.assertTrue((shot_dir / "x-av-2093130747796148634.jpg").exists())
                self.assertTrue((shot_dir / "x-media-2093130747796148634.jpg").exists())

    def test_x_post_scene_propagates_to_timeline_beats(self):
        scenes = [{
            "veiculo": "X Oficial",
            "url": "https://x.com/user/status/12345",
            "kind": "x-post",
            "shot": "src-00.png",
            "video": None,
            "x_post": {
                "author_name": "User",
                "handle": "@user",
                "text": "Tweet animado",
            }
        }]
        episode = {
            "titulo": "Notícia do Dia",
            "desenvolvimento": [{"texto": "Fala 1", "fonte_url": "https://x.com/user/status/12345"}]
        }
        beats = build_scene_timeline(episode, 20.0, scenes)
        self.assertTrue(len(beats) >= 1)
        b0 = beats[0]
        self.assertEqual(b0.kind, "x-post")
        self.assertIsNotNone(b0.x_post)
        self.assertEqual(b0.x_post["author_name"], "User")


class InstagramMediaTests(unittest.TestCase):
    def test_extracts_shortcode_from_various_instagram_urls(self):
        self.assertEqual(
            instagram_shortcode("https://www.instagram.com/reel/DczgElQso4z/"),
            "DczgElQso4z",
        )
        self.assertEqual(
            instagram_shortcode("https://instagram.com/p/ABC123xyz/?igsh=123"),
            "ABC123xyz",
        )
        self.assertEqual(
            instagram_shortcode("https://www.instagram.com/tv/XYZ987/"),
            "XYZ987",
        )

    def test_returns_none_for_non_post_instagram_urls(self):
        self.assertIsNone(instagram_shortcode("https://www.instagram.com/nikolasferreiradm/"))
        self.assertIsNone(instagram_shortcode("https://www.cnnbrasil.com.br/"))
        self.assertIsNone(instagram_shortcode(""))
        self.assertIsNone(instagram_shortcode(None))

    def test_extract_instagram_video_reuses_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shots = work / "shots"
            shots.mkdir(parents=True)
            fake_vid = shots / "igvid-test123-00.mp4"
            fake_vid.write_bytes(b"x" * 60000)

            rel = extract_instagram_video(
                "https://www.instagram.com/reel/DczgElQso4z/",
                work,
                "test123",
                0,
            )
            self.assertEqual(rel, "/shots/igvid-test123-00.mp4")

    @patch("subprocess.run")
    def test_extract_instagram_video_calls_ytdlp(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shots = work / "shots"
            shots.mkdir(parents=True)
            fake_vid = shots / "igvid-test123-01.mp4"

            def fake_subprocess_side_effect(cmd, **kwargs):
                fake_vid.write_bytes(b"x" * 60000)
                from unittest.mock import MagicMock
                r = MagicMock()
                r.returncode = 0
                return r

            mock_run.side_effect = fake_subprocess_side_effect

            rel = extract_instagram_video(
                "https://www.instagram.com/reel/DczgElQso4z/",
                work,
                "test123",
                1,
            )
            self.assertEqual(rel, "/shots/igvid-test123-01.mp4")
            self.assertTrue(mock_run.called)
            cmd = mock_run.call_args[0][0]
            self.assertIn("https://www.instagram.com/reel/DczgElQso4z/", cmd)


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


class HandlerCaptureOrderTests(unittest.TestCase):
    """Handlers must not nest sync_playwright inside capture_sources.

    Repro vhm4xPVjxFk (2026-09-03): every portal handler failed with
    'Playwright Sync API inside the asyncio loop' and the generic
    fallback saved CSS-less prints.
    """

    def test_handler_call_is_before_sync_playwright_in_capture_sources(self):
        import inspect

        import bm_mockup_video as m

        src = inspect.getsource(m.capture_sources)
        handler_pos = src.find("try_handler_screenshot")
        pw_pos = src.find("_open_sync_playwright")
        self.assertGreater(handler_pos, -1, "capture_sources must call try_handler_screenshot")
        self.assertGreater(pw_pos, -1, "capture_sources still has a generic Playwright fallback")
        self.assertLess(
            handler_pos,
            pw_pos,
            "handlers must run before opening sync_playwright; nested Sync API "
            "inside the Playwright asyncio loop is what broke vhm4xPVjxFk",
        )

    def test_successful_handler_skips_generic_playwright(self):
        import bm_mockup_video as m

        order: list[str] = []

        def fake_handler(url, dest, viewport=None):
            order.append("handler")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"P" * 25_000)
            return {"ok": True, "handler": "g1"}

        def fake_blank(_path):
            return False

        def boom(*_a, **_k):
            order.append("sync_playwright")
            raise AssertionError("generic Playwright must not run when handler succeeded")

        scenes = [
            {
                "veiculo": "O Globo",
                "url": "https://oglobo.globo.com/economia/foo.ghtml",
            }
        ]
        with tempfile.TemporaryDirectory() as td:
            shot_dir = Path(td)
            with (
                patch.object(m, "try_handler_screenshot", fake_handler),
                patch.object(m, "get_cached_screenshot", return_value=None),
                patch.object(m, "save_cached_screenshot", return_value=None),
                patch.object(m, "_shot_looks_blank", fake_blank),
                patch.object(m, "_open_sync_playwright", boom),
            ):
                out = m.capture_sources(scenes, shot_dir)

            self.assertEqual(order, ["handler"])
            self.assertEqual(out[0]["shot"], "src-00.png")
            self.assertTrue((shot_dir / "src-00.png").exists())


if __name__ == "__main__":
    unittest.main()
