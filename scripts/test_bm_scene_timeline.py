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

    def test_5min_episode_generates_at_least_10_beats(self):
        # Simula episódio real de 5 minutos (~830 palavras, 300 segundos)
        episode = {
            "titulo": "Escândalo no Planalto",
            "abertura": [{"speaker": "Peter", "texto": "Abertura com contexto inicial relevante. " * 15}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": f"Parágrafo {i} com detalhes do caso factual para preencher o tempo. " * 10}
                for i in range(1, 8)
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Fechamento provocador e sintético. " * 10}],
        }
        scenes = [
            {"veiculo": "VEJA", "url": "https://veja.abril.com.br/1", "shot": "src-00.png"},
            {"veiculo": "Folha", "url": "https://folha.uol.com.br/2", "shot": "src-01.png"},
            {"veiculo": "G1", "url": "https://g1.globo.com/3", "shot": "src-02.png"},
            {"veiculo": "Metrópoles", "url": "https://metropoles.com/4", "shot": "src-03.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        self.assertGreaterEqual(len(beats), 10, f"Deveria ter pelo menos 10 beats em 5 minutos, teve {len(beats)}")
        self.assertEqual(beats[0].t0, 0.0)
        self.assertEqual(beats[-1].t1, 300.0)

    def test_opening_15s_hook_cuts(self):
        episode = {
            "titulo": "Pauta de Abertura Impactante",
            "abertura": [{"speaker": "Peter", "texto": "Texto longo de abertura com mais de cinquenta palavras para ocupar os primeiros trinta segundos de vídeo de forma densa e contínua sem interrupções artificiais."}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Corpo longo. " * 50}],
            "fechamento": [{"speaker": "Peter", "texto": "Fim."}],
        }
        scenes = [
            {"veiculo": "Fonte 1", "url": "https://1.com", "shot": "s1.png"},
            {"veiculo": "Fonte 2", "url": "https://2.com", "shot": "s2.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=240.0, scenes=scenes)
        # Nos primeiros 15s deve haver mais de 1 corte para prender a atenção do público
        first_15s_beats = [b for b in beats if b.t0 < 15.0]
        self.assertGreaterEqual(len(first_15s_beats), 2, "Deveria ter pelo menos 2 cortes nos primeiros 15s")


if __name__ == "__main__":
    unittest.main()
