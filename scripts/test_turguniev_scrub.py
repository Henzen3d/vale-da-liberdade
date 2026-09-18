#!/usr/bin/env python3
"""Turguniev nunca entra em roteiro nem em TTS — vira Albuquerque."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from tts_preprocessor import (
    preprocess_for_tts,
    scrub_ancapsu_channel,
    scrub_ancapsu_tree,
    scrub_turguniev,
    scrub_turguniev_tree,
)


class ScrubAncapsuChannelTests(unittest.TestCase):
    def test_self_intro_rewritten(self):
        self.assertEqual(
            scrub_ancapsu_channel("aqui é Peter Turguniev do Ancapsu"),
            "aqui é Peter Albuquerque do Vale da Liberdade",
        )
        self.assertEqual(
            scrub_ancapsu_channel("aqui é o Peter Turguniev do canal Ancapsu"),
            "aqui é o Peter Albuquerque do Vale da Liberdade",
        )

    def test_albuquerque_intro_rewritten(self):
        self.assertEqual(
            scrub_ancapsu_channel("aqui é Peter Albuquerque do Ancapsu"),
            "aqui é Peter Albuquerque do Vale da Liberdade",
        )

    def test_bare_mention_replaced(self):
        out = scrub_ancapsu_channel("no canal Ancapsu temos muito mais")
        self.assertNotIn("ancap", out.lower())
        self.assertIn("Vale da Liberdade", out)

    def test_url_and_handle_replaced(self):
        out = scrub_ancapsu_channel("se inscreva no youtube.com/@ancap_su")
        self.assertNotIn("ancap", out.lower())

    def test_no_false_positive(self):
        intact = "Peter Albuquerque do Vale da Liberdade comenta o STF"
        self.assertEqual(scrub_ancapsu_channel(intact), intact)

    def test_tree_json(self):
        data = {
            "titulo": "Turguniev no STF",
            "subtitulo": "Ancapsu reage",
            "abertura": [
                {"speaker": "Peter", "texto": "aqui é Peter Turguniev do Ancapsu hoje"}
            ],
        }
        out = scrub_ancapsu_tree(scrub_turguniev_tree(data))
        self.assertEqual(out["titulo"], "Albuquerque no STF")
        self.assertNotIn("ancap", str(out).lower())
        self.assertEqual(
            out["abertura"][0]["texto"],
            "aqui é Peter Albuquerque do Vale da Liberdade hoje",
        )

    def test_tts_pipeline_never_keeps_the_channel(self):
        md = "Peter: aqui é Peter Turguniev do Ancapsu, falando do STF."
        tts = preprocess_for_tts(md)
        self.assertNotIn("ancap", tts.lower())
        self.assertNotIn("turgun", tts.lower())
        self.assertIn("Vale da Liberdade", tts)


class ScrubTurgunievTests(unittest.TestCase):
    def test_plain_and_cased(self):
        self.assertEqual(scrub_turguniev("falou o turguniev ontem"), "falou o Albuquerque ontem")
        self.assertEqual(scrub_turguniev("Turguniev disse"), "Albuquerque disse")
        self.assertEqual(scrub_turguniev("TURGUNIEV"), "Albuquerque")

    def test_peter_prefix(self):
        self.assertEqual(scrub_turguniev("Peter Turguniev comentou"), "Peter Albuquerque comentou")
        self.assertEqual(scrub_turguniev("piter turguniev"), "Peter Albuquerque")

    def test_tree_json(self):
        data = {
            "titulo": "Turguniev no STF",
            "abertura": [{"speaker": "Peter", "texto": "Peter Turguniev abre o caso."}],
        }
        out = scrub_turguniev_tree(data)
        self.assertEqual(out["titulo"], "Albuquerque no STF")
        self.assertEqual(out["abertura"][0]["texto"], "Peter Albuquerque abre o caso.")
        blob = str(out).lower()
        self.assertNotIn("turgun", blob)

    def test_tts_pipeline_never_keeps_the_word(self):
        md = "Peter: O Turguniev comentou a decisão do STF."
        tts = preprocess_for_tts(md)
        self.assertNotIn("turguniev", tts.lower())
        self.assertIn("Albuquerque", tts)


if __name__ == "__main__":
    unittest.main()
