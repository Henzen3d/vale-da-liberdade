import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from youtube_session_captions import (  # noqa: E402
    AUTH_COOKIE_NAMES,
    cookie_header_from_records,
    extract_yt_json_object,
    netscape_from_records,
    parse_caption_payload,
    parse_cookie_file,
    pick_cookie_file,
    score_cookie_records,
    select_caption_track,
    strip_timedtext_exp,
)


class TestCookieFileParsing(unittest.TestCase):
    def test_parse_netscape_names(self):
        text = (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tabc\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tPREF\tf1=40000000\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(text)
            path = Path(fh.name)
        recs = parse_cookie_file(path)
        names = [r["name"] for r in recs]
        self.assertIn("LOGIN_INFO", names)
        self.assertIn("PREF", names)
        self.assertGreaterEqual(score_cookie_records(recs), 10)

    def test_parse_chrome_json_export(self):
        data = [
            {
                "domain": ".youtube.com",
                "expirationDate": 1999999999,
                "hostOnly": False,
                "httpOnly": True,
                "name": "LOGIN_INFO",
                "path": "/",
                "secure": True,
                "value": "AFmmF2swRQIh",
            },
            {
                "domain": ".youtube.com",
                "expirationDate": 1999999999,
                "hostOnly": False,
                "httpOnly": False,
                "name": "PREF",
                "path": "/",
                "secure": True,
                "value": "f1=40000000",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            json.dump(data, fh)
            path = Path(fh.name)
        recs = parse_cookie_file(path)
        names = {r["name"] for r in recs}
        self.assertEqual(names, {"LOGIN_INFO", "PREF"})
        header = cookie_header_from_records(recs)
        self.assertIn("LOGIN_INFO=AFmmF2swRQIh", header)
        ns = netscape_from_records(recs)
        self.assertIn("LOGIN_INFO", ns)
        self.assertIn("\tAFmmF2swRQIh", ns)

    def test_pick_prefers_login_info_over_visitor_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            visitor = tmp_path / "youtube_cookies.txt"
            visitor.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tVISITOR_INFO1_LIVE\tx\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tPREF\tf1=1\n",
                encoding="utf-8",
            )
            session = tmp_path / "youtube_cookies_bazar.txt"
            session.write_text(
                json.dumps(
                    [
                        {
                            "domain": ".youtube.com",
                            "name": "LOGIN_INFO",
                            "path": "/",
                            "secure": True,
                            "value": "sess",
                            "expirationDate": 1999999999,
                        },
                        {
                            "domain": ".youtube.com",
                            "name": "__Secure-3PSID",
                            "path": "/",
                            "secure": True,
                            "value": "sid",
                            "expirationDate": 1999999999,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            picked = pick_cookie_file([visitor, session])
            self.assertEqual(picked, session)
            recs = parse_cookie_file(picked)
            self.assertTrue(AUTH_COOKIE_NAMES & {r["name"] for r in recs})

    def test_youtube_only_jar_beats_full_browser_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dump = tmp_path / "youtube_cookies.txt"
            dump.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tdump\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-3PSID\tsid\n"
                ".fandom.com\tTRUE\t/\tTRUE\t1999999999\tSID\tother\n",
                encoding="utf-8",
            )
            heron = tmp_path / "youtube_cookies_heron.txt"
            heron.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\theron\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-3PSID\tsid\n",
                encoding="utf-8",
            )
            picked = pick_cookie_file([dump, heron])
            self.assertEqual(picked, heron)

    def test_newer_youtube_jar_wins_score_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old = tmp_path / "youtube_cookies_heron.txt"
            new = tmp_path / "www.youtube.com_cookies.txt"
            body = (
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tx\n"
                ".youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-3PSID\tsid\n"
            )
            old.write_text(body, encoding="utf-8")
            import time
            time.sleep(0.05)
            new.write_text(body, encoding="utf-8")
            picked = pick_cookie_file([old, new])
            self.assertEqual(picked, new)


class TestPlayerAndCaptions(unittest.TestCase):
    def test_extract_player_response_and_pick_pt_asr(self):
        player = {
            "videoDetails": {
                "title": "Vídeo teste",
                "author": "ANCAPSU",
                "lengthSeconds": "10",
                "shortDescription": "Referências:\nhttps://example.com/materia",
            },
            "captions": {
                "playerCaptionsTracklistRenderer": {
                    "captionTracks": [
                        {
                            "languageCode": "en",
                            "kind": "asr",
                            "baseUrl": "https://www.youtube.com/api/timedtext?v=abc&lang=en&kind=asr&exp=xpe",
                            "name": {"simpleText": "English"},
                        },
                        {
                            "languageCode": "pt",
                            "kind": "asr",
                            "baseUrl": "https://www.youtube.com/api/timedtext?v=abc&lang=pt&kind=asr&exp=xpe",
                            "name": {"simpleText": "Português"},
                        },
                    ]
                }
            },
        }
        html = (
            "<html><script>var ytInitialPlayerResponse = "
            + json.dumps(player)
            + ";</script></html>"
        )
        parsed = extract_yt_json_object(html, "ytInitialPlayerResponse")
        self.assertEqual(parsed["videoDetails"]["title"], "Vídeo teste")
        track = select_caption_track(parsed)
        self.assertEqual(track["languageCode"], "pt")
        stripped = strip_timedtext_exp(track["baseUrl"])
        self.assertNotIn("exp=", stripped)
        self.assertIn("lang=pt", stripped)

    def test_parse_json3_and_xml(self):
        json3 = json.dumps(
            {
                "events": [
                    {"segs": [{"utf8": "Olá "}, {"utf8": "mundo"}]},
                    {"segs": [{"utf8": "Olá mundo"}]},
                    {"segs": [{"utf8": "segunda frase"}]},
                ]
            }
        )
        text = parse_caption_payload(json3, "json3")
        self.assertIn("Olá mundo", text)
        self.assertIn("segunda frase", text)
        xml = (
            '<?xml version="1.0"?>'
            "<transcript>"
            '<text start="0">Olá</text>'
            '<text start="1">mundo</text>'
            "</transcript>"
        )
        xml_text = parse_caption_payload(xml, "xml")
        self.assertEqual(xml_text, "Olá mundo")


if __name__ == "__main__":
    unittest.main()
