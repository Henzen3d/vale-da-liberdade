#!/usr/bin/env python3
"""Teto CHUNK_TARGET_WORDS também no modo halves (BM)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import generate_gemini_tts_multi as tts


class SoloVsDailyInstructionTests(unittest.TestCase):
    """BM Peter solo não pode herdar Director's Notes do diário (Peter+Ricardo)."""

    def test_system_instruction_solo_peter_has_no_ricardo(self) -> None:
        text = tts.build_system_instruction(["Peter"])
        self.assertNotIn("Ricardo", text)
        self.assertNotIn("Kore", text)
        self.assertIn("Charon", text)
        self.assertIn("solo", text.lower())

    def test_system_instruction_duo_keeps_ricardo(self) -> None:
        text = tts.build_system_instruction(["Peter", "Ricardo"])
        self.assertIn("Ricardo", text)
        self.assertIn("Kore", text)
        self.assertIn("Peter", text)

    def test_ffmpeg_chain_accepts_tempo(self) -> None:
        import inspect

        src = inspect.getsource(tts.run_ffmpeg_chain_2pass)
        self.assertIn("atempo", src)
        self.assertIn("tempo", src)

    def test_bm_atempo_is_115(self) -> None:
        self.assertAlmostEqual(tts.BM_TTS_ATEMPO, 1.15)

    def test_prefer_edge_cli_flag_exists(self) -> None:
        import inspect

        src = inspect.getsource(tts.main)
        self.assertIn("--prefer-edge", src)
        self.assertIn("prefer_edge", src)

    def test_halves_prefer_edge_tries_edge_before_gemini(self) -> None:
        import inspect

        src = inspect.getsource(tts.generate_halves_pcm)
        self.assertIn("prefer_edge", src)
        edge_pos = src.find("_edge_tts_generate_audio")
        gemini_pos = src.find("generate_single_speaker_pcm")
        self.assertGreater(edge_pos, 0)
        self.assertGreater(gemini_pos, 0)
        # Com prefer_edge, o ramo Edge aparece ANTES do Gemini no corpo.
        prefer_block = src[src.find("if prefer_edge") :]
        self.assertLess(
            prefer_block.find("_edge_tts_generate_audio"),
            prefer_block.find("generate_single_speaker_pcm"),
        )

    def test_bm_peter_eq_has_warmth_and_presence(self) -> None:
        import inspect

        src = inspect.getsource(tts.run_ffmpeg_chain_2pass)
        self.assertIn("lowshelf", src)
        self.assertIn("equalizer=f=3500", src)
        self.assertIn("highpass=f=80", src)
        self.assertIn("acompressor", src)

    def test_bm_pipeline_step_audio_prefers_edge(self) -> None:
        import inspect
        import bm_pipeline as bm

        src = inspect.getsource(bm.step_audio)
        self.assertIn("--prefer-edge", src)
        self.assertIn("--single-speaker", src)
        self.assertLess(src.find("--prefer-edge"), src.find("gemini-3.1-flash-tts-preview"))


class ChunkCapTests(unittest.TestCase):
    def test_halves_of_938_words_exceed_cap(self) -> None:
        """NJbcFf4f8cs: 938 palavras → 444+494. Ambos passam de 300."""
        words = ["palavra."] * 938
        text = " ".join(words)
        halves = tts.split_text_halves(text)
        self.assertEqual(len(halves), 2)
        self.assertTrue(any(len(h.split()) > tts.CHUNK_TARGET_WORDS for h in halves))

    def test_capped_chunks_never_exceed_300(self) -> None:
        words = ["palavra."] * 938
        text = " ".join(words)
        chunks = tts.split_text_capped(text)
        self.assertGreaterEqual(len(chunks), 4)
        for ch in chunks:
            self.assertLessEqual(len(ch.split()), tts.CHUNK_TARGET_WORDS)

    def test_generate_halves_pcm_uses_word_cap(self) -> None:
        import inspect

        src = inspect.getsource(tts.generate_halves_pcm)
        self.assertIn("split_text_capped", src)
        self.assertNotIn("halves = split_text_halves(joined)", src)


if __name__ == "__main__":
    unittest.main()
