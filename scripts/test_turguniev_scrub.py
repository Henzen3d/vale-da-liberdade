#!/usr/bin/env python3
"""Turguniev nunca entra em roteiro nem em TTS — vira Albuquerque."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from tts_preprocessor import preprocess_for_tts, scrub_turguniev, scrub_turguniev_tree


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
