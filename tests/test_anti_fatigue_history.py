#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes para o sistema de Anti-Fadiga e Memória Visual Histórica (Fase 7).
Valida consulta ao histórico last_videos.json e rotação de wallpapers.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bm_video.state as st


class AntiFatigueHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_antifatigue_"))
        self.fake_last_videos = self.tmp_dir / "last_videos.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_append_and_get_recent_visual_history(self):
        with patch.object(st, "LAST_VIDEOS_PATH", self.fake_last_videos):
            st.append_last_video("vid_01", "2026-09-01", dominant_style="standard_source", wallpaper="wall_A.png")
            st.append_last_video("vid_02", "2026-09-02", dominant_style="strong_quote", wallpaper="wall_B.png")
            st.append_last_video("vid_03", "2026-09-03", dominant_style="chronology", wallpaper="wall_C.png")

            history = st.get_recent_visual_history(2)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[-1]["video_id"], "vid_03")
            self.assertEqual(history[-1]["wallpaper"], "wall_C.png")
            self.assertEqual(history[-2]["video_id"], "vid_02")

    def test_pick_wallpaper_vetoes_recent_wallpapers(self):
        fake_files = [
            Path("/fake/wall_A.png"),
            Path("/fake/wall_B.png"),
            Path("/fake/wall_C.png"),
        ]
        history_data = {
            "history": [
                {"video_id": "vid_prev1", "date": "2026-09-10", "wallpaper": "wall_A.png"},
                {"video_id": "vid_prev2", "date": "2026-09-11", "wallpaper": "wall_B.png"},
            ]
        }
        self.fake_last_videos.write_text(json.dumps(history_data), encoding="utf-8")

        with patch.object(st, "LAST_VIDEOS_PATH", self.fake_last_videos), \
             patch.object(st, "list_wallpapers", return_value=fake_files):
            # Com wall_A e wall_B usados recentemente, deve selecionar wall_C
            chosen = st.pick_wallpaper("novo_video_id", exclude_recent_n=2)
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name, "wall_C.png")

    def test_pick_wallpaper_fallback_when_all_used(self):
        fake_files = [Path("/fake/wall_only.png")]
        history_data = {
            "history": [
                {"video_id": "vid_prev", "date": "2026-09-10", "wallpaper": "wall_only.png"},
            ]
        }
        self.fake_last_videos.write_text(json.dumps(history_data), encoding="utf-8")

        with patch.object(st, "LAST_VIDEOS_PATH", self.fake_last_videos), \
             patch.object(st, "list_wallpapers", return_value=fake_files):
            # Se todos foram usados (pool esgotado), não quebra e usa a opção disponível
            chosen = st.pick_wallpaper("novo_video_id", exclude_recent_n=1)
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name, "wall_only.png")


if __name__ == "__main__":
    unittest.main()
