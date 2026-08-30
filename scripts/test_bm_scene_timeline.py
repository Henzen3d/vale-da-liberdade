#!/usr/bin/env python3
"""Testes unitários da timeline de cenas BM (sem rede)."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bm_scene_timeline import (
    MIN_SCENE_DURATION_S,
    SceneBeat,
    build_scene_timeline,
    count_words,
)


class SceneTimelineTests(unittest.TestCase):
    def test_count_words(self):
        self.assertEqual(count_words("Uma duas três quatro"), 4)
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words(None), 0)

    def test_timeline_distribution_and_monotonicity(self):
        episode = {
            "titulo": "Episódio de Teste",
            "abertura": [
                {"speaker": "Peter", "texto": "Fala 1 com dez palavras para iniciar a introdução do assunto."}
            ],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Fala 2 com bastante conteúdo factual para preencher a matéria principal e detalhar todos os acontecimentos relevantes."}
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": "Fechamento curto."}
            ],
        }
        scenes = [
            {"veiculo": "Folha", "url": "https://www1.folha.uol.com.br/fato", "shot": "src-00.png"},
            {"veiculo": "CNN", "url": "https://www.cnnbrasil.com.br/fato", "shot": "src-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=120.0, scenes=scenes)
        self.assertTrue(len(beats) >= 2)
        self.assertEqual(beats[0].t0, 0.0)
        self.assertAlmostEqual(beats[-1].t1, 120.0, places=1)

        # Continuidade temporal
        for i in range(len(beats) - 1):
            self.assertEqual(beats[i].t1, beats[i + 1].t0)
            self.assertGreaterEqual(beats[i + 1].t1, beats[i + 1].t0)

    def test_sync_with_fonte_url(self):
        episode = {
            "titulo": "Teste de Sincronização",
            "abertura": [
                {"speaker": "Peter", "texto": "Abertura geral sem citação direta de fonte."}
            ],
            "desenvolvimento": [
                {
                    "speaker": "Peter",
                    "texto": "Segundo a reportagem da CNN Brasil, o evento teve grande repercussão.",
                    "fonte_url": "https://www.cnnbrasil.com.br/evento",
                },
                {
                    "speaker": "Peter",
                    "texto": "Já o G1 destacou outro ângulo sobre a investigação.",
                    "fonte_url": "https://g1.globo.com/investigacao",
                },
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": "Encerramento do vídeo."}
            ],
        }
        scenes = [
            {"veiculo": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/evento", "shot": "src-00.png"},
            {"veiculo": "G1", "url": "https://g1.globo.com/investigacao", "shot": "src-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        urls_in_beats = [b.url for b in beats]
        self.assertIn("https://www.cnnbrasil.com.br/evento", urls_in_beats)
        self.assertIn("https://g1.globo.com/investigacao", urls_in_beats)

    def test_minimum_scene_duration(self):
        episode = {
            "titulo": "Teste de Piso de Duração",
            "abertura": [{"speaker": "Peter", "texto": "A"}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "B " * 100}],
            "fechamento": [{"speaker": "Peter", "texto": "C"}],
        }
        scenes = [
            {"veiculo": "Fonte A", "url": "https://a.com", "shot": "src-00.png"},
            {"veiculo": "Fonte B", "url": "https://b.com", "shot": "src-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=100.0, scenes=scenes)
        # O primeiro beat deve respeitar o piso mínimo
        self.assertGreaterEqual(beats[0].t1 - beats[0].t0, MIN_SCENE_DURATION_S)


if __name__ == "__main__":
    unittest.main()
