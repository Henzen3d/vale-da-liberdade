#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import tts_fallback_edge as edge


class ParseTtsLinesTests(unittest.TestCase):
    def test_speakers_and_pauses(self):
        text = (
            "Peter: Bom dia, Blumenau, começamos o jornal agora.\n"
            "Ricardo: [PAUSA] E o recado é direto ao ponto da cidade.\n"
            "# comentario\n"
            "linha curta\n"
            "Peter: Terceiro bloco com conteúdo suficiente para passar.\n"
        )
        chunks = edge.parse_tts_lines(text)
        self.assertEqual(chunks[0][0], "peter")
        self.assertEqual(chunks[1][0], "ricardo")
        self.assertNotIn("[PAUSA]", chunks[1][1])
        self.assertEqual(len(chunks), 3)

    def test_voices_distinct(self):
        self.assertEqual(edge.EDGE_VOICES["peter"], "pt-BR-AntonioNeural")
        self.assertEqual(edge.EDGE_VOICES["ricardo"], "pt-BR-FranciscaNeural")
        self.assertNotEqual(edge.EDGE_VOICES["peter"], edge.EDGE_VOICES["ricardo"])

    def test_concurrency_capped(self):
        self.assertLessEqual(edge.EDGE_CONCURRENCY, 3)


if __name__ == "__main__":
    unittest.main()
