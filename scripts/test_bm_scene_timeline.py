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
    TARGET_MIN_BEATS_5MIN,
    SceneBeat,
    build_scene_timeline,
    count_words,
    detect_visual_opportunities,
    youtube_id_from_episode,
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




    # ---------- FASE 0.2 + FASE 2: herança de fonte e cascata de matching ----------

    def test_heranca_fonte_propaga_para_blocos_sem_fonte(self):
        """Bloco sem fonte herda a última fonte conhecida (exceto fechamento)."""
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Teste Heranca",
            "abertura": [{"speaker": "Peter", "texto": "Contexto inicial.", "fonte_url": "https://a.com/x"}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Argumento um detalhado o suficiente.", "fonte_url": "https://a.com/x"},
                {"speaker": "Peter", "texto": "Continua o mesmo argumento sem fonte marcada."},
                {"speaker": "Peter", "texto": "Mais desenvolvimento do mesmo tema sem fonte."},
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Síntese final."}],
        }
        scenes = [{"veiculo": "A", "url": "https://a.com/x", "shot": "sa.png"}]
        beats = build_scene_timeline(episode, total_duration_s=120.0, scenes=scenes)
        # Desenvolvimento (blocos 1-3) casou com a cena A; fechamento não herda
        urls = [b.url for b in beats if b.kind != "broll"]
        self.assertTrue(all(u == "https://a.com/x" for u in urls),
                        f"blocos deviam herdar a fonte A: {urls}")

    def test_heranca_nao_aplica_se_nao_ha_fonte_previa(self):
        """Episódio sem nenhuma marcação não inventa fonte (round-robin)."""
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Sem Fonte",
            "abertura": [{"speaker": "Peter", "texto": "Contexto."}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Argumento sem fonte alguma aqui."}],
            "fechamento": [{"speaker": "Peter", "texto": "Fim."}],
        }
        scenes = [{"veiculo": "F1", "url": "https://f1.com", "shot": "s1.png"},
                  {"veiculo": "F2", "url": "https://f2.com", "shot": "s2.png"}]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        self.assertTrue(all(b.url in {"https://f1.com", "https://f2.com", ""} for b in beats))

    def test_match_por_dominio_cobre_normalizacao_de_url(self):
        """URL do bloco com www/path diferente casa a cena pelo domínio."""
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Dominio",
            "abertura": [{"speaker": "Peter", "texto": "Contexto.", "fonte_url": "https://www.cnn.com/2026/09/noticia"}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Desenvolvimento.", "fonte_url": "https://www.cnn.com/2026/09/noticia"}],
            "fechamento": [{"speaker": "Peter", "texto": "Fim."}],
        }
        # cena cadastrada com outro path do mesmo host
        scenes = [{"veiculo": "CNN", "url": "https://cnn.com/artigo-diferente", "shot": "c.png"}]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        fontes = [b.url for b in beats if b.kind != "broll"]
        self.assertTrue(all(u == "https://cnn.com/artigo-diferente" for u in fontes),
                        f"match por domínio devia casar CNN: {fontes}")

    def test_host_of_normaliza_www(self):
        from bm_scene_timeline import _host_of
        self.assertEqual(_host_of("https://www.cnn.com/a"), "cnn.com")
        self.assertEqual(_host_of("https://cnn.com/a"), "cnn.com")
        self.assertEqual(_host_of("https://WWW.Example.com"), "example.com")
        self.assertEqual(_host_of(""), "")
        self.assertEqual(_host_of("nao-e-url"), "")

    def test_cascata_preferencia_exato_sobre_dominio(self):
        """Match exato vence o de domínio quando ambos existem."""
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Preferencia",
            "abertura": [{"speaker": "Peter", "texto": "Ctx.", "fonte_url": "https://cnn.com/exata"}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Dev.", "fonte_url": "https://cnn.com/exata"}],
            "fechamento": [{"speaker": "Peter", "texto": "Fim."}],
        }
        scenes = [
            {"veiculo": "CNN exata", "url": "https://cnn.com/exata", "shot": "exata.png"},
            {"veiculo": "CNN outra", "url": "https://cnn.com/outra", "shot": "outra.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        fontes = [b.url for b in beats if b.kind != "broll"]
        self.assertTrue(all(u == "https://cnn.com/exata" for u in fontes),
                        f"match exato devia vencer: {fontes}")


    # ---------- FASE 3: abertura ampla / corpo sincronizado ----------
    def test_fase3_abertura_marcada(self):
        """Vídeos longos marcam abertura_fim > 0 nos beats iniciais (rotação
        livre); vídeos curtos não marcam (abertura_fim = 0)."""
        episode = {
            "titulo": "Abertura",
            "abertura": [{"speaker": "Peter", "texto": "Boa noite, hoje temos três grandes histórias." * 6}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Desenvolvimento " * 12, "fonte_url": "https://cnn.com/a"}],
            "fechamento": [{"speaker": "Peter", "texto": "Encerramos por aqui." * 4}],
        }
        scenes = [{"veiculo": "CNN", "url": "https://cnn.com/a", "shot": "a.png"},
                  {"veiculo": "Reuters", "url": "https://reuters.com/b", "shot": "b.png"}]
        beats = build_scene_timeline(episode, 300.0, scenes)
        self.assertTrue(any(b.abertura_fim > 0 for b in beats))
        # abertura limitada aos ~15s do gancho visual
        self.assertLessEqual(max(b.abertura_fim for b in beats), 15.0 + 0.01)

    def test_fase3_curto_sem_abertura(self):
        episode = {"titulo": "Curto",
                   "abertura": [{"speaker": "Peter", "texto": "Oi."}],
                   "desenvolvimento": [{"speaker": "Peter", "texto": "Dev."}],
                   "fechamento": [{"speaker": "Peter", "texto": "Fim."}]}
        scenes = [{"veiculo": "CNN", "url": "https://cnn.com/a", "shot": "a.png"}]
        beats = build_scene_timeline(episode, 60.0, scenes)
        self.assertEqual(max((b.abertura_fim for b in beats), default=0.0), 0.0)

    # ---------- FASE 4: word-timestamps (sem whisper, protege o guarda) ----------
    def test_fase4_audio_inexistente_mantem_beats(self):
        """Sem áudio, align_beats_to_audio devolve a lista intacta."""
        import sys as _sys
        _sys.path.insert(0, "scripts")
        from bm_whisper_align import align_beats_to_audio
        from bm_scene_timeline import SceneBeat
        beats = [SceneBeat(t0=0.0, t1=10.0, url="https://cnn.com/a", veiculo="CNN", kind="source")]
        out = align_beats_to_audio(beats, "/tmp/inexistente.mp3", ["texto qualquer"])
        self.assertEqual(out, beats)

    # ---------- FRENTE 2 VISUAL: Pacing, Multi-Shot & X-Card ----------
    def test_5min_episode_generates_at_least_18_beats(self):
        """Em vídeos de 5 min (300s), garante densidade dinâmica de pelo menos 18 beats."""
        episode = {
            "titulo": "Escândalo no Congresso",
            "abertura": [{"speaker": "Peter", "texto": "Abertura com gancho inicial relevante. " * 15}],
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
        ]
        beats = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        self.assertGreaterEqual(len(beats), TARGET_MIN_BEATS_5MIN,
                                f"Deveria ter pelo menos {TARGET_MIN_BEATS_5MIN} beats, teve {len(beats)}")
        self.assertEqual(beats[0].t0, 0.0)
        self.assertEqual(beats[-1].t1, 300.0)

    def test_sub_beats_cycle_visual_variants(self):
        """Sub-beats gerados de cenas longas devem ciclar variantes ópticas (hero, zoom, scroll, highlight)."""
        episode = {
            "titulo": "Matéria Longa em Bloco Único",
            "abertura": [{"speaker": "Peter", "texto": "Início da cobertura de hoje."}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Análise detalhada e contínua do tema principal com dezenas de palavras para estender a duração da fala. " * 30}
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Fim da cobertura."}],
        }
        scenes = [
            {"veiculo": "Gazeta", "url": "https://gazeta.com/noticia", "shot": "gazeta.png"},
            {"veiculo": "Poder360", "url": "https://poder360.com.br/noticia", "shot": "poder.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=120.0, scenes=scenes)
        # Deve ter gerado variantes visuais como portal_zoom ou portal_scroll
        variants = [b.visual_variant for b in beats if b.visual_component == "source"]
        self.assertTrue(any(v in ("portal_zoom", "portal_scroll", "portal_highlight") for v in variants),
                        f"Deveria conter variantes dinâmicas de câmera: {variants}")

    def test_x_post_opportunity_detection(self):
        """Detecta citação a post no X e recomenda componente x-post com variante x_card."""
        text = "Em postagem no X, o ministro afirmou: 'A regulação digital é indispensável para a soberania do país'."
        opp = detect_visual_opportunities(text, url="https://g1.globo.com/noticia", veiculo="G1")
        self.assertEqual(opp["chosen_component"], "x-post")
        x_cands = [c for c in opp["detected_opportunities"] if c["recommended_component"] == "x-post"]
        self.assertTrue(len(x_cands) > 0)
        self.assertEqual(x_cands[0]["recommended_variant"], "x_card")
        self.assertIn("A regulação digital", x_cands[0]["extracted_data"].get("text", ""))

    def test_x_post_in_timeline_generation(self):
        """Texto citando @handle ou post no X gera beat nativo de x-post com payload estruturado."""
        episode = {
            "titulo": "Repercussão nas Redes",
            "abertura": [{"speaker": "Peter", "texto": "Veja a manifestação oficial."}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "O presidente publicou no X que não aceitará interferências externas na política tarifária."}
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Até a próxima análise."}],
        }
        scenes = [{"veiculo": "G1", "url": "https://g1.globo.com/post", "shot": "g1.png"}]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        x_beats = [b for b in beats if b.visual_component == "x-post" or b.kind == "x-post"]
        self.assertTrue(len(x_beats) > 0, "Deveria ter gerado beat de x-post")
        self.assertEqual(x_beats[0].visual_variant, "x_card")
        self.assertEqual(x_beats[0].semantic_role, "repercussao_social")
        self.assertIsNotNone(x_beats[0].x_post)

    def test_timeline_propagates_shot_long_and_highlight_box(self):
        """shot_long e highlight_box são propagados do input scenes para os beats."""
        episode = {
            "titulo": "Sincronia de Matéria com Scroll Longo",
            "abertura": [{"speaker": "Peter", "texto": "Abertura rápida com o fato principal da matéria."}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Aqui temos aprofundamento analítico que requer visualização do corpo do texto no portal."}
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Conclusão e encerramento da edição."}],
        }
        hl = {"found": True, "x": 60, "y": 320, "w": 1050, "h": 70}
        scenes = [{
            "veiculo": "Folha",
            "url": "https://www1.folha.uol.com.br/noticia",
            "shot": "src-00.png",
            "shot_long": "src-00-long.png",
            "highlight_box": hl,
        }]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        source_beats = [b for b in beats if b.visual_component == "source"]
        self.assertTrue(len(source_beats) > 0)
        for sb in source_beats:
            self.assertEqual(sb.shot_long, "src-00-long.png")
            self.assertEqual(sb.highlight_box, hl)

    def test_timeline_inserts_transitions_on_scene_change(self):
        """Transições broadcast (wipe_gold, etc.) são inseridas em mudanças de cena após o gancho."""
        episode = {
            "titulo": "Transição de Pauta",
            "abertura": [
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 25), "fonte_url": "https://portal1.com"}
            ],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 60), "fonte_url": "https://portal1.com"},
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 60), "fonte_url": "https://portal2.com"},
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 20), "fonte_url": "https://portal2.com"}
            ],
        }
        scenes = [
            {"veiculo": "Portal 1", "url": "https://portal1.com", "shot": "src-00.png"},
            {"veiculo": "Portal 2", "url": "https://portal2.com", "shot": "src-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=120.0, scenes=scenes)
        trans_beats = [b for b in beats if b.visual_component == "transition" or b.kind == "transition"]
        self.assertTrue(len(trans_beats) >= 1, "Deveria ter inserido pelo menos 1 transição broadcast")
        self.assertIn(trans_beats[0].visual_variant, {"wipe_gold", "dissolve_brand", "flash_cut"})

    def test_person_photo_skips_missing_and_placeholder(self):
        """Foto editorial só entra com arquivo real; placeholder não é pedido."""
        from unittest.mock import patch

        episode = {
            "id": "especial-mGwvmcIrkFM",
            "titulo": "Sem foto real",
            "abertura": [{"speaker": "Peter", "texto": "Abertura com gancho inicial relevante. " * 15}],
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
        ]
        seen = {}

        def fake_resolve(video_id, allow_placeholder=False):
            seen["allow_placeholder"] = allow_placeholder
            raise FileNotFoundError("placeholder recusado")

        with patch("episode_image_manifest.resolve_editorial_image", side_effect=fake_resolve):
            beats = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        self.assertEqual(seen.get("allow_placeholder"), False)
        self.assertFalse(any(b.visual_component == "person-photo" or b.kind == "person-photo" for b in beats))

        episode["editorial_image"] = "/tmp/nao-existe-editorial-vale.jpg"
        beats_missing = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        self.assertFalse(
            any(b.visual_component == "person-photo" or b.kind == "person-photo" for b in beats_missing)
        )

    def test_person_photo_keeps_local_source_path(self):
        """Beat person-photo aponta para arquivo existente via photo_src, não /thumbnails/ solto."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(b"\xff\xd8\xff\xd9")
            src = Path(fh.name)
        self.addCleanup(src.unlink, missing_ok=True)
        episode = {
            "titulo": "Com foto editorial",
            "editorial_image": str(src),
            "abertura": [{"speaker": "Peter", "texto": "Abertura com gancho inicial relevante. " * 15}],
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
        ]
        beats = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        photos = [b for b in beats if b.visual_component == "person-photo" or b.kind == "person-photo"]
        self.assertTrue(len(photos) >= 1, "Deveria inserir person-photo quando o arquivo existe")
        payload = photos[0].visual_payload or {}
        self.assertEqual(payload.get("photo_src"), str(src.resolve()))
        self.assertTrue(str(payload.get("photo") or "").startswith("/shots/"))
        self.assertNotIn("/thumbnails/", str(payload.get("photo") or ""))

    def test_youtube_id_from_episode_sources(self):
        """ID vem de video_id, especial-*, ou URL YouTube — não de slug de portal."""
        self.assertEqual(
            youtube_id_from_episode({"fonte_url": "https://www.youtube.com/watch?v=mGwvmcIrkFM"}),
            "mGwvmcIrkFM",
        )
        self.assertEqual(
            youtube_id_from_episode({"id": "especial-mGwvmcIrkFM"}),
            "mGwvmcIrkFM",
        )
        self.assertEqual(
            youtube_id_from_episode({"fonte_url": "https://youtu.be/mGwvmcIrkFM"}),
            "mGwvmcIrkFM",
        )
        self.assertEqual(
            youtube_id_from_episode({
                "fonte_url": "https://www1.folha.uol.com.br/poder/2026/09/abcdefghijk",
            }),
            "",
        )


if __name__ == "__main__":
    unittest.main()

