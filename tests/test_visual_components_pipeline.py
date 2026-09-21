#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes para os novos componentes visuais procedurais (Timeline, DataChart, Comparison).
Valida extração semântica, geração de payloads e compatibilidade com o mockup browser.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from bm_scene_timeline import (
    _extract_chart_metrics,
    _extract_comparison_sides,
    _extract_timeline_events,
    build_scene_timeline,
    detect_visual_opportunities,
)
from bm_video.state import _build_mockup_update_payload, _normalize_beat_v2


class VisualComponentsPipelineTests(unittest.TestCase):
    def test_extract_timeline_events(self):
        para = "Em março de 2024 o tribunal acolheu o pedido. Em janeiro de 2025 o recurso foi julgado e em maio de 2026 a decisão transitou em julgado."
        data = _extract_timeline_events(para)
        self.assertIn("timeline_title", data)
        self.assertIn("year", data)
        self.assertIn("events", data)
        self.assertGreaterEqual(len(data["events"]), 2)
        # Verifica formato dos nós
        self.assertTrue(any("2024" in ev["date"] or "2025" in ev["date"] or "2026" in ev["date"] for ev in data["events"]))
        self.assertTrue(all("desc" in ev for ev in data["events"]))

    def test_extract_chart_metrics(self):
        para = "A inflação de serviços registrou alta de 8,4% no último trimestre, acumulando despesas de R$ 120 milhões."
        data = _extract_chart_metrics(para)
        self.assertIn("metric_label", data)
        self.assertEqual(data["metric_value"], "8,4")
        self.assertEqual(data["metric_suffix"], "%")
        self.assertEqual(data["trend"], "up")
        self.assertIn("+8,4%", data["delta_text"])
        self.assertIn("sub_items", data)
        self.assertGreaterEqual(len(data["sub_items"]), 2)

    def test_extract_chart_metrics_dolar_down(self):
        para = "Houve uma queda de 3,5% na cotação do dólar comercial após anúncio de corte de gastos."
        data = _extract_chart_metrics(para)
        self.assertEqual(data["metric_value"], "3,5")
        self.assertEqual(data["trend"], "down")
        self.assertIn("-3,5%", data["delta_text"])

    def test_extract_comparison_sides(self):
        para = "O candidato prometeu congelar tributos, mas após a posse aprovou aumento de 15% nas alíquotas municipais."
        data = _extract_comparison_sides(para)
        self.assertIn("comparison_title", data)
        self.assertIn("side_a", data)
        self.assertIn("side_b", data)
        self.assertIn("header", data["side_a"])
        self.assertIn("details", data["side_a"])
        self.assertIn("header", data["side_b"])
        self.assertIn("details", data["side_b"])

    def test_detect_visual_opportunities_timeline(self):
        para = "Em março de 2024 a assembleia iniciou o debate. Em outubro de 2025 o projeto foi aprovado com alterações substanciais."
        opp = detect_visual_opportunities(para, url="https://g1.globo.com", veiculo="G1")
        # Deve ter detectado timeline entre as oportunidades
        detected_comps = [o["recommended_component"] for o in opp.get("detected_opportunities", [])]
        self.assertIn("timeline", detected_comps)

    def test_detect_visual_opportunities_chart(self):
        para = "A receita tributária total atingiu R$ 45 bilhões, com crescimento de 12,3% no orçamento estadual."
        opp = detect_visual_opportunities(para, url="https://folha.uol.com.br", veiculo="Folha")
        detected_comps = [o["recommended_component"] for o in opp.get("detected_opportunities", [])]
        self.assertIn("chart", detected_comps)

    def test_timeline_beat_payload_generation(self):
        episode = {
            "titulo": "Episódio com Dados e Cronologia",
            "abertura": [{"speaker": "Peter", "texto": "Contexto geral de abertura da edição de notícias."}],
            "desenvolvimento": [
                {
                    "speaker": "Peter",
                    "texto": "Em janeiro de 2024 os autos foram abertos. Em julho de 2025 a liminar foi concedida e em maio de 2026 saiu a sentença final.",
                    "fonte_url": "https://g1.globo.com/politica",
                }
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Fechamento rápido e direto ao ponto com análise."}],
        }
        scenes = [{"veiculo": "G1", "url": "https://g1.globo.com/politica", "shot": "shot-00.png"}]
        beats = build_scene_timeline(episode, total_duration_s=40.0, scenes=scenes, return_v2=True)

        # Encontra o beat do bloco com timeline
        timeline_beats = [b for b in beats if b.visual_component == "timeline"]
        self.assertTrue(len(timeline_beats) >= 1, "Deve identificar e promover o componente timeline")
        tb = timeline_beats[0]
        self.assertTrue(len(tb.visual_payload.get("events", [])) >= 2)

        # Testa o payload repassado para o mockup
        norm = _normalize_beat_v2(tb)
        payload = _build_mockup_update_payload(norm)
        self.assertEqual(payload["kind"], "timeline")
        self.assertEqual(payload["visual_component"], "timeline")
        self.assertIn("events", payload)
        self.assertIn("timeline_title", payload)


if __name__ == "__main__":
    unittest.main()
