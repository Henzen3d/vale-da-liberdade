#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes para o Juiz Visual Pós-Render de Vídeo (Fase 5).
Valida inspeção de streams, integridade de frames, detecção de telas pretas e geração de video.qa.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from bm_video.video_judge import (
    _audit_frame_pixels,
    _compare_frames_for_freeze,
    _probe_video_info,
    audit_rendered_video,
)


class VideoJudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_video_judge_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_dummy_image(self, dest: Path, color: tuple[int, int, int] = (128, 128, 128), noise: bool = True) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        if noise:
            img = Image.frombytes("RGB", (100, 100), os.urandom(100 * 100 * 3))
        else:
            img = Image.new("RGB", (100, 100), color)
        img.save(dest, format="PNG")
        return dest

    def test_audit_frame_pixels_valid_and_black(self):
        valid_p = self._create_dummy_image(self.tmp_dir / "valid.png", noise=True)
        res_valid = _audit_frame_pixels(valid_p)
        self.assertTrue(res_valid["valid_image"])
        self.assertFalse(res_valid["is_black"])
        self.assertGreater(res_valid["stddev"], 6.0)

        # Imagem preta sólida
        black_p = self._create_dummy_image(self.tmp_dir / "black.png", color=(0, 0, 0), noise=False)
        res_black = _audit_frame_pixels(black_p)
        self.assertTrue(res_black["valid_image"])
        self.assertTrue(res_black["is_black"])

    def test_compare_frames_for_freeze(self):
        f1 = self._create_dummy_image(self.tmp_dir / "f1.png", color=(80, 80, 80), noise=False)
        f2 = self._create_dummy_image(self.tmp_dir / "f2.png", color=(80, 80, 80), noise=False)
        f3 = self._create_dummy_image(self.tmp_dir / "f3.png", noise=True)

        self.assertTrue(_compare_frames_for_freeze(f1, f2), "Frames idênticos devem indicar freeze")
        self.assertFalse(_compare_frames_for_freeze(f1, f3), "Frames distintos não devem indicar freeze")

    def test_probe_video_info_missing_file(self):
        info = _probe_video_info(self.tmp_dir / "nao_existe.mp4")
        self.assertFalse(info["has_video"])
        self.assertEqual(info["duration"], 0.0)

    def test_audit_rendered_video_end_to_end_mocked(self):
        dummy_mp4 = self.tmp_dir / "video_final.mp4"
        # Cria arquivo com tamanho suficiente
        dummy_mp4.write_bytes(b"0" * 600_000)

        f_sample1 = self._create_dummy_image(self.tmp_dir / "qa_frames" / "frame_002000.png", noise=True)
        f_sample2 = self._create_dummy_image(self.tmp_dir / "qa_frames" / "frame_010000.png", noise=True)

        mock_probe = {
            "width": 1920,
            "height": 1080,
            "duration": 25.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "has_video": True,
            "has_audio": True,
        }

        with patch("bm_video.video_judge._probe_video_info", return_value=mock_probe), \
             patch("bm_video.video_judge._extract_sample_frames", return_value=[(2.0, f_sample1), (10.0, f_sample2)]):
            report = audit_rendered_video(
                dummy_mp4,
                self.tmp_dir,
                timeline_beats=[{"t0": 5.0}],
                expected_duration_s=25.0,
            )

        self.assertEqual(report["overall_status"], "APPROVED")
        self.assertTrue(report["checks"]["dimensions_1080p"])
        self.assertTrue(report["checks"]["no_black_frames"])
        self.assertTrue(report["checks"]["has_audio"])
        self.assertTrue(report["checks"]["has_video"])

        # Verifica se gravou video.qa.json no work_dir
        qa_file = self.tmp_dir / "video.qa.json"
        self.assertTrue(qa_file.is_file())
        data = json.loads(qa_file.read_text(encoding="utf-8"))
        self.assertEqual(data["overall_status"], "APPROVED")
        self.assertEqual(data["sampled_frames_count"], 2)


if __name__ == "__main__":
    unittest.main()
