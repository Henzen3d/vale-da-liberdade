#!/usr/bin/env python3
"""Testes do SRT e da localização EN (sem Whisper, sem YouTube)."""
from __future__ import annotations

import unittest

from youtube_captions import (
    Cue,
    cues_to_srt,
    parse_srt,
    srt_timestamp,
    merge_short_cues,
    parse_en_cues_json,
    clamp_title,
)


class SrtFormatTests(unittest.TestCase):
    def test_timestamp(self):
        self.assertEqual(srt_timestamp(0), "00:00:00,000")
        self.assertEqual(srt_timestamp(61.5), "00:01:01,500")
        self.assertEqual(srt_timestamp(3723.04), "01:02:03,040")

    def test_roundtrip(self):
        cues = [
            Cue(0.0, 2.1, "Olá, Brasil."),
            Cue(2.1, 5.0, "O Estado não é seu amigo."),
        ]
        srt = cues_to_srt(cues)
        back = parse_srt(srt)
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0].text, "Olá, Brasil.")
        self.assertAlmostEqual(back[1].start, 2.1, places=2)
        self.assertIn("-->", srt)

    def test_merge_short(self):
        cues = [
            Cue(0.0, 0.8, "Olá"),
            Cue(0.8, 2.5, "Brasil."),
            Cue(4.0, 8.0, "Bloco longo o suficiente."),
        ]
        merged = merge_short_cues(cues)
        self.assertEqual(len(merged), 2)
        self.assertIn("Olá", merged[0].text)
        self.assertIn("Brasil", merged[0].text)

    def test_parse_en_json(self):
        raw = '[{"i":1,"en":"Hello"},{"i":2,"en":"The State is not your friend."}]'
        m = parse_en_cues_json(raw)
        self.assertEqual(m[1], "Hello")
        self.assertEqual(m[2], "The State is not your friend.")

    def test_parse_en_json_fenced(self):
        raw = '```json\n[{"i": 1, "en": "Hi"}]\n```'
        m = parse_en_cues_json(raw)
        self.assertEqual(m[1], "Hi")

    def test_clamp_title(self):
        long = "A" * 140
        t = clamp_title(long)
        self.assertLessEqual(len(t), 100)
        self.assertTrue(t)


if __name__ == "__main__":
    unittest.main()
