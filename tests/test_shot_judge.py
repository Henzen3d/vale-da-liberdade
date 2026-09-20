#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes unitários para o Juiz Semântico de Shots e shot.qa.json (Fase 4.2).
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

from bm_video.shot_judge import audit_captured_shot, evaluate_timeline_shots


class ShotJudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_shot_judge_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_dummy_image(self, dest: Path, size_bytes: int = 12000, color: int = 128) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        import os
        from PIL import Image
        img = Image.frombytes("RGB", (200, 200), os.urandom(200 * 200 * 3))
        img.save(dest, format="PNG")
        return dest

    def test_audit_captured_shot_valid(self):
        shot_path = self.tmp_dir / "shot-00.png"
        self._create_dummy_image(shot_path, size_bytes=10000)
        res = audit_captured_shot(
            shot_path,
            url="https://g1.globo.com/politica/noticia/1",
            veiculo="G1",
            text_context="Notícia sobre inflação",
        )
        self.assertEqual(res["status"], "APPROVED")
        self.assertTrue(res["checks"]["file_exists"])
        self.assertTrue(res["checks"]["min_size"])
        self.assertTrue(res["checks"]["not_corrupted"])
        self.assertTrue(res["checks"]["not_blank"])
        self.assertTrue(res["semantic_score"] >= 0.80)

    def test_audit_captured_shot_missing_and_small(self):
        # Arquivo inexistente
        missing = self.tmp_dir / "nao_existe.png"
        res_missing = audit_captured_shot(missing)
        self.assertEqual(res_missing["status"], "REJECTED")
        self.assertEqual(res_missing["semantic_score"], 0.0)

        # Arquivo muito pequeno (< 8KB)
        tiny = self.tmp_dir / "tiny.png"
        tiny.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        res_tiny = audit_captured_shot(tiny)
        self.assertEqual(res_tiny["status"], "REJECTED")
        self.assertFalse(res_tiny["checks"]["min_size"])

    def test_audit_captured_shot_blocked_marker(self):
        blocked_shot = self.tmp_dir / "blocked_turnstile_error.png"
        self._create_dummy_image(blocked_shot, size_bytes=10000)
        res = audit_captured_shot(blocked_shot)
        self.assertEqual(res["status"], "REJECTED")
        self.assertFalse(res["checks"]["not_blocked"])

    def test_evaluate_timeline_shots_and_generates_qa_json(self):
        shots_dir = self.tmp_dir / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        valid_shot = self._create_dummy_image(shots_dir / "shot-00.png", size_bytes=10000)

        broken_shot = shots_dir / "shot-01.png"
        broken_shot.write_bytes(b"corrompido")

        timeline_beats = [
            {
                "t0": 0.0,
                "t1": 10.0,
                "shot": "shot-00.png",
                "url": "https://g1.globo.com/1",
                "veiculo": "G1",
                "visual_component": "source",
                "texto_origem": "Texto da matéria 1",
            },
            {
                "t0": 10.0,
                "t1": 20.0,
                "shot": "shot-01.png",
                "url": "https://folha.uol.com.br/2",
                "veiculo": "Folha",
                "visual_component": "source",
                "texto_origem": "Texto da matéria 2",
            },
        ]

        def fake_download_article_image(url: str, dest_path: Path) -> bool:
            self._create_dummy_image(dest_path, size_bytes=15000)
            return True

        with patch("person_resolver.download_article_image", side_effect=fake_download_article_image):
            report = evaluate_timeline_shots(
                timeline_beats,
                scenes=[],
                work_dir=self.tmp_dir,
                episode={"titulo": "Episódio QA"},
            )

        self.assertEqual(report["total_shots"], 2)
        self.assertEqual(report["approved_count"], 1)
        self.assertEqual(report["rescued_count"], 1)
        self.assertEqual(report["rejected_count"], 0)
        self.assertIn("shots", report)

        # Verifica persistência de shot.qa.json nos dois locais
        qa_file1 = self.tmp_dir / "shot.qa.json"
        qa_file2 = shots_dir / "shot.qa.json"
        self.assertTrue(qa_file1.is_file(), "shot.qa.json deve existir no work_dir")
        self.assertTrue(qa_file2.is_file(), "shot.qa.json deve existir no shot_dir")

        data = json.loads(qa_file1.read_text(encoding="utf-8"))
        self.assertEqual(data["approved_count"], 1)
        self.assertEqual(data["rescued_count"], 1)
        self.assertEqual(data["shots"][1]["status"], "RESCUED")


if __name__ == "__main__":
    unittest.main()
