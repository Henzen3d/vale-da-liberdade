#!/usr/bin/env python3
"""Testes unitários do Otimizador A/B de Títulos (sem rede/API real)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from youtube_ab_optimizer import (
    apply_new_title,
    audit_underperformers,
    load_ab_history,
    record_optimization,
    suggest_alternative_titles,
    was_already_optimized,
)


class AbOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.mock_yt = MagicMock()

    def test_history_recording_and_idempotency(self):
        fake_hist = {"history": {}}
        with patch("youtube_ab_optimizer.load_ab_history", return_value=fake_hist), \
             patch("youtube_ab_optimizer.save_ab_history") as mock_save:
            record_optimization(
                yt_id="test_vid_123",
                old_title="Título Antigo",
                new_title="Título Novo",
                views_before=50,
                median_views=200,
                reason="test",
            )
            mock_save.assert_called_once()
            self.assertIn("test_vid_123", fake_hist["history"])
            self.assertEqual(fake_hist["history"]["test_vid_123"]["new_title"], "Título Novo")

    def test_audit_underperformers_detection(self):
        mock_candidates = [
            {"video_id": "v1", "yt_id": "yt1", "title": "Vídeo 1", "published_at": "2026-08-25T10:00:00-03:00"},
            {"video_id": "v2", "yt_id": "yt2", "title": "Vídeo 2", "published_at": "2026-08-26T10:00:00-03:00"},
            {"video_id": "v3", "yt_id": "yt3", "title": "Vídeo 3", "published_at": "2026-08-27T10:00:00-03:00"},
            {"video_id": "v4", "yt_id": "yt4", "title": "Vídeo 4", "published_at": "2026-08-28T10:00:00-03:00"},
            {"video_id": "v5", "yt_id": "yt5", "title": "Vídeo 5", "published_at": "2026-08-29T10:00:00-03:00"},
        ]

        # Views: 100, 100, 100, 100, 20 -> Mediana = 100.
        # yt5 tem 20 views (< 60% de 100 = 60). Deve ser identificado como underperformer.
        mock_items = [
            {"id": "yt1", "snippet": {"title": "Vídeo 1", "publishedAt": "2026-08-25T10:00:00Z"}, "statistics": {"viewCount": "100"}},
            {"id": "yt2", "snippet": {"title": "Vídeo 2", "publishedAt": "2026-08-26T10:00:00Z"}, "statistics": {"viewCount": "100"}},
            {"id": "yt3", "snippet": {"title": "Vídeo 3", "publishedAt": "2026-08-27T10:00:00Z"}, "statistics": {"viewCount": "100"}},
            {"id": "yt4", "snippet": {"title": "Vídeo 4", "publishedAt": "2026-08-28T10:00:00Z"}, "statistics": {"viewCount": "100"}},
            {"id": "yt5", "snippet": {"title": "Vídeo 5", "publishedAt": "2026-08-29T10:00:00Z"}, "statistics": {"viewCount": "20"}},
        ]

        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": mock_items}
        self.mock_yt.videos().list.return_value = mock_list

        with patch("youtube_ab_optimizer.load_recent_published_candidates", return_value=mock_candidates), \
             patch("youtube_ab_optimizer.was_already_optimized", return_value=False):
            under, median_views = audit_underperformers(self.mock_yt, days=7, threshold_pct=0.60)

        self.assertEqual(median_views, 100)
        self.assertEqual(len(under), 1)
        self.assertEqual(under[0]["yt_id"], "yt5")
        self.assertEqual(under[0]["views"], 20)
        self.assertAlmostEqual(under[0]["ratio"], 0.20, places=2)

    def test_suggest_alternative_titles_llm(self):
        fake_llm_res = {
            "recomendado": "STF Muda Regras e Afeta Pequenas Empresas no Brasil",
            "opcoes": [
                "Empresas em Alerta: STF Publica Nova Decisão",
                "O que Muda para os Negócios Após Julgamento do STF",
            ],
            "porque": "Foco na dor direta do empreendedor.",
        }

        with patch("youtube_ab_optimizer.generate_title_via_llm", return_value=fake_llm_res):
            suggestions = suggest_alternative_titles("Título Original Longo de Notícia")

        self.assertGreaterEqual(len(suggestions), 2)
        self.assertIn("STF Muda Regras e Afeta Pequenas Empresas no Brasil", suggestions)
        for s in suggestions:
            self.assertLessEqual(len(s), 70)

    def test_apply_new_title(self):
        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "items": [
                {
                    "id": "yt_target",
                    "snippet": {"title": "Título Antigo", "description": "Desc"},
                    "status": {"privacyStatus": "public"},
                }
            ]
        }
        mock_update = MagicMock()
        mock_update.execute.return_value = {}

        self.mock_yt.videos().list.return_value = mock_get
        self.mock_yt.videos().update.return_value = mock_update

        with patch("youtube_ab_optimizer.record_optimization") as mock_record:
            res = apply_new_title(self.mock_yt, "yt_target", "Título Novo e Atraente")

        self.assertTrue(res["applied"])
        self.assertEqual(res["old_title"], "Título Antigo")
        self.assertEqual(res["new_title"], "Título Novo e Atraente")
        self.mock_yt.videos().update.assert_called_once()
        mock_record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
