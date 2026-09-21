#!/usr/bin/env python3
"""Testes unitários da timeline de cenas BM (sem rede)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

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
        """Citação textual a post no X em matéria jornalística escolhe 'quote', NÃO x-post."""
        text = "Em postagem no X, o ministro afirmou: 'A regulação digital é indispensável para a soberania do país'."
        opp = detect_visual_opportunities(text, url="https://g1.globo.com/noticia", veiculo="G1")
        self.assertEqual(opp["chosen_component"], "quote")
        quote_cands = [c for c in opp["detected_opportunities"] if c["recommended_component"] == "quote"]
        self.assertTrue(len(quote_cands) > 0)
        self.assertEqual(quote_cands[0]["recommended_variant"], "card_gold")
        self.assertIn("A regulação digital", quote_cands[0]["extracted_data"].get("quote_text", ""))
        self.assertIn("via X", quote_cands[0]["extracted_data"].get("source_name", ""))

        # URL nativa do X recomenda o componente x-post
        opp_native = detect_visual_opportunities(
            "Veja a postagem sobre o tema.",
            url="https://x.com/ministro/status/123",
            veiculo="X",
        )
        self.assertEqual(opp_native["chosen_component"], "x-post")

    def test_x_post_in_timeline_generation(self):
        """Cena nativa com x_post estruturado gera beat de x-post; citação em portal gera quote."""
        # 1. Citação de texto mencionando X em portal tradicional gera quote (Modo 2), não x-post
        episode_portal = {
            "titulo": "Repercussão nas Redes",
            "abertura": [{"speaker": "Peter", "texto": "Veja a manifestação oficial."}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "O presidente declarou no X: 'Não aceitaremos interferências externas'."}
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Até a próxima análise."}],
        }
        scenes_portal = [{"veiculo": "G1", "url": "https://g1.globo.com/post", "shot": "g1.png"}]
        beats_portal = build_scene_timeline(episode_portal, total_duration_s=60.0, scenes=scenes_portal)
        quote_beats = [b for b in beats_portal if b.visual_component == "quote"]
        self.assertTrue(len(quote_beats) > 0, "Citação no roteiro deve gerar quote, não x-post falso")
        self.assertFalse(any(b.visual_component == "x-post" for b in beats_portal))

        # 2. Cena X com payload real NÃO vira x-post se a fala não cita aquele post.
        # O teste antigo exigia o contrário e validava o bug do EXP-0001.
        scenes_x = [{
            "veiculo": "Post no X",
            "url": "https://x.com/pres/status/1",
            "shot": None,
            "kind": "x-post",
            "x_post": {"author_name": "Presidente", "handle": "@pres", "text": "Texto oficial verificado."},
        }]
        beats_x = build_scene_timeline(episode_portal, total_duration_s=60.0, scenes=scenes_x)
        self.assertFalse(
            any(b.visual_component == "x-post" for b in beats_x),
            "Cena X sem fonte_url da fala não pode virar x-post",
        )

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
        """Foto editorial só entra com arquivo real explícito; thumbnail de capa do vídeo NUNCA é usada."""
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
        beats = build_scene_timeline(episode, total_duration_s=300.0, scenes=scenes)
        # Não deve inserir person-photo sem foto real explícita no episódio
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

    def test_semantic_person_photo_resolution_trump(self):
        """Ao citar Donald Trump no roteiro, o timeline injeta automaticamente o beat de person-photo com sua foto e nome."""
        episode = {
            "titulo": "Tarifas Globais e Geopolítica",
            "abertura": [{"speaker": "Peter", "texto": "Abertura com o cenário internacional de comércio exterior. " * 15}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "O presidente Donald Trump anunciou ontem que vai impor tarifas pesadas sobre produtos importados. " * 5},
                {"speaker": "Peter", "texto": "Essa medida protecionista atinge em cheio as cadeias produtivas de vários países emergentes. " * 5},
                {"speaker": "Peter", "texto": "O mercado reagiu com cautela e apreensão diante do novo cenário fiscal globalizado. " * 5},
                {"speaker": "Peter", "texto": "Especialistas apontam que a inflação pode ser pressionada nos próximos trimestres de 2026. " * 5},
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Fechamento provocador e sintético sobre livre mercado. " * 10}],
        }
        scenes = [
            {"veiculo": "Bloomberg", "url": "https://bloomberg.com/news/1", "shot": "src-00.png"},
            {"veiculo": "WSJ", "url": "https://wsj.com/articles/2", "shot": "src-01.png"},
            {"veiculo": "Reuters", "url": "https://reuters.com/business/3", "shot": "src-02.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=180.0, scenes=scenes)
        person_beats = [b for b in beats if b.visual_component == "person-photo" or b.kind == "person-photo"]
        self.assertTrue(len(person_beats) >= 1, "Deveria ter resolvido e inserido o beat de person-photo para Trump")
        payload = person_beats[0].visual_payload or {}
        self.assertEqual(payload.get("name"), "Donald Trump")
        self.assertEqual(payload.get("tag"), "PERSONAGEM EM FOCO")
        self.assertIn("donald-trump", payload.get("photo_src", ""))
        self.assertTrue(Path(payload["photo_src"]).is_file())


    def test_provenance_explicit_inherited_none(self):
        """Verifica que a proveniência distingue explicit, inherited e none (sem inventar fontes no fechamento)."""
        episode = {
            "titulo": "Teste de Proveniência Editorial",
            "abertura": [
                {"speaker": "Peter", "texto": "Abertura com declaração ancorada na matéria principal. " * 5, "fonte_url": "https://portal1.com/artigo1"}
            ],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Comentário analítico que dá sequência à matéria 1 sem URL própria. " * 10},
                {"speaker": "Peter", "texto": "Nova pauta com dados fiscais novos e link próprio. " * 10, "fonte_url": "https://portal2.com/artigo2"},
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": "Conclusão e opinião final do apresentador, sem fonte associada. " * 8}
            ],
        }
        scenes = [
            {"veiculo": "Portal 1", "url": "https://portal1.com/artigo1", "shot": "src-00.png"},
            {"veiculo": "Portal 2", "url": "https://portal2.com/artigo2", "shot": "src-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=60.0, scenes=scenes)
        self.assertTrue(len(beats) >= 3)

        # Beat inicial com URL explícita
        beat_0 = beats[0]
        self.assertEqual(beat_0.provenance_type, "explicit")
        self.assertEqual(beat_0.fonte_url_fala, "https://portal1.com/artigo1")
        self.assertIn(0, beat_0.fala_indices)
        self.assertIn("Abertura com declaração", beat_0.texto_origem)

        # Beat do fechamento (último beat de conteúdo falado)
        last_beat = beats[-1]
        self.assertEqual(last_beat.provenance_type, "none")
        self.assertIsNone(last_beat.fonte_url_fala)
        self.assertIn(3, last_beat.fala_indices)
        self.assertIn("Conclusão e opinião final", last_beat.texto_origem)

    def test_provenance_in_v2_and_mockup_payload(self):
        """Verifica propagação da proveniência para SceneBeatV2 e payload de window.VDL_MOCKUP.update."""
        from bm_video.state import _build_mockup_update_payload, _normalize_beat_v2

        episode = {
            "titulo": "Teste Proveniência Mockup Payload",
            "abertura": [
                {"speaker": "Peter", "texto": "Texto de abertura com URL de fonte. " * 5, "fonte_url": "https://portal1.com/artigo1"}
            ],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Texto de desenvolvimento herdando a fonte. " * 10}
            ],
            "fechamento": [
                {"speaker": "Peter", "texto": "Texto de fechamento livre de fonte. " * 5}
            ],
        }
        scenes = [
            {"veiculo": "Portal 1", "url": "https://portal1.com/artigo1", "shot": "src-00.png"},
        ]
        beats_v2 = build_scene_timeline(episode, total_duration_s=30.0, scenes=scenes, return_v2=True)
        self.assertTrue(len(beats_v2) >= 2)
        b0 = beats_v2[0]
        self.assertEqual(b0.provenance_type, "explicit")
        self.assertEqual(b0.fonte_url_fala, "https://portal1.com/artigo1")

        norm = _normalize_beat_v2(b0)
        self.assertIn("fala_indices", norm)
        self.assertEqual(norm["provenance_type"], "explicit")

        payload = _build_mockup_update_payload(norm)
        self.assertIn("provenance", payload)
        self.assertEqual(payload["provenance"]["provenance_type"], "explicit")
        self.assertEqual(payload["provenance"]["fonte_url_fala"], "https://portal1.com/artigo1")
        self.assertIn(0, payload["provenance"]["fala_indices"])
        self.assertTrue(len(payload["provenance"]["texto_origem"]) > 0)

    def test_provenance_broll_and_transition(self):
        """Verifica proveniência procedural para b-roll e transições broadcast."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as fh:
            json.dump([{"file": "broll1.mp4", "dur_s": 1.2}], fh)
            broll_p = Path(fh.name)
        self.addCleanup(broll_p.unlink, missing_ok=True)

        episode = {
            "titulo": "Procedural Beats",
            "abertura": [{"speaker": "Peter", "texto": " ".join(["palavra"] * 30), "fonte_url": "https://p1.com"}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 80), "fonte_url": "https://p1.com"},
                {"speaker": "Peter", "texto": " ".join(["palavra"] * 80), "fonte_url": "https://p2.com"},
            ],
            "fechamento": [{"speaker": "Peter", "texto": " ".join(["palavra"] * 30), "fonte_url": "https://p2.com"}],
        }
        scenes = [
            {"veiculo": "P1", "url": "https://p1.com", "shot": "p1.png"},
            {"veiculo": "P2", "url": "https://p2.com", "shot": "p2.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=150.0, scenes=scenes, broll_index_path=broll_p)
        broll_beats = [b for b in beats if b.provenance_type == "broll"]
        if broll_beats:
            self.assertEqual(broll_beats[0].fala_indices, [])
            self.assertIsNone(broll_beats[0].fonte_url_fala)
            self.assertEqual(broll_beats[0].texto_origem, "")

        trans_beats = [b for b in beats if b.provenance_type == "transition"]
        if trans_beats:
            self.assertEqual(trans_beats[0].fala_indices, [])
            self.assertIsNone(trans_beats[0].fonte_url_fala)
            self.assertEqual(trans_beats[0].texto_origem, "")

    def test_pacing_anti_monotony_sub_beats_and_variants(self):
        """Valida que nenhum beat de source excede o teto (10s) e que variantes de câmera não se repetem consecutivamente."""
        episode = {
            "titulo": "Episódio Longo Teste Pacing",
            "abertura": [{"speaker": "Peter", "texto": "Abertura rápida de contexto internacional. " * 8}],
            "desenvolvimento": [
                {"speaker": "Peter", "texto": "Comentário analítico longo e detalhado com muitas palavras por segundo. " * 15, "fonte_url": "https://portal1.com/artigo1"},
                {"speaker": "Peter", "texto": "Continuação da mesma matéria com desdobramentos adicionais dos fatos. " * 15, "fonte_url": "https://portal1.com/artigo1"},
            ],
            "fechamento": [{"speaker": "Peter", "texto": "Fechamento sintético provocador. " * 8}],
        }
        scenes = [
            {"veiculo": "Portal 1", "url": "https://portal1.com/artigo1", "shot": "shot-00.png"},
            {"veiculo": "Portal 2", "url": "https://portal2.com/artigo2", "shot": "shot-01.png"},
        ]
        beats = build_scene_timeline(episode, total_duration_s=120.0, scenes=scenes)

        # 1. Teto máximo estrito (Fase 4.3): nenhum beat de source pode exceder 10.0s + tolerância de 0.5s
        for idx, b in enumerate(beats):
            dur = b.t1 - b.t0
            if b.visual_component == "source":
                self.assertLessEqual(dur, 10.5, f"Beat[{idx}] dur={dur:.2f}s excedeu teto de 10s")

        # 2. Alternância de variantes visuais de câmera: consecutivas não repetem
        for idx in range(len(beats) - 1):
            b_curr = beats[idx]
            b_next = beats[idx + 1]
            if (
                b_curr.visual_component == "source"
                and b_next.visual_component == "source"
                and b_curr.url == b_next.url
                and b_curr.visual_variant
                and b_next.visual_variant
            ):
                self.assertNotEqual(
                    b_curr.visual_variant,
                    b_next.visual_variant,
                    f"Beats consecutivos [{idx}] e [{idx+1}] repetiram a mesma variante: {b_curr.visual_variant}",
                )


class Exp0001ProvenanceTests(unittest.TestCase):
    """EXP-0001: a fala escolhe a evidência. Cena vizinha não entra por disponibilidade."""

    def _article(self):
        return {"veiculo": "Metrópoles", "url": "https://www.metropoles.com/materia", "shot": "metro.png"}

    def _x(self, status="2102008469217808460"):
        return {
            "veiculo": "X",
            "url": f"https://x.com/andreshalders/status/{status}",
            "kind": "x-post",
            "shot": None,
            "x_post": {
                "author_name": "André Shalders",
                "handle": "@andreshalders",
                "text": "Texto real do post, não a narração.",
                "likes": "12",
            },
        }

    def test_caso_a_fala_sem_fonte_nao_vira_x_post(self):
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Caso A",
            "abertura": [{"speaker": "Peter", "texto": "Abertura sem fonte marcada no roteiro."}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Desenvolvimento continua sem URL de matéria."}],
            "fechamento": [{"speaker": "Peter", "texto": "Fecho."}],
        }
        beats = build_scene_timeline(episode, 60.0, [self._article(), self._x()])
        self.assertFalse(any(b.visual_component == "x-post" or b.kind == "x-post" for b in beats))
        shown = [b for b in beats if b.visual_component not in ("transition", "broll")]
        self.assertTrue(shown)
        self.assertTrue(all(b.url == "https://www.metropoles.com/materia" for b in shown))

    def test_caso_b_fala_com_post_real_gera_um_x_post(self):
        from bm_scene_timeline import build_scene_timeline
        post_url = "https://x.com/andreshalders/status/2102008469217808460"
        episode = {
            "titulo": "Caso B",
            "abertura": [{"speaker": "Peter", "texto": "Abertura na matéria.", "fonte_url": "https://www.metropoles.com/materia"}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "A narração não pode virar o corpo do card.", "fonte_url": post_url}],
            "fechamento": [{"speaker": "Peter", "texto": "Fecho."}],
        }
        beats = build_scene_timeline(episode, 60.0, [self._article(), self._x()])
        x_beats = [b for b in beats if b.visual_component == "x-post"]
        self.assertEqual(len(x_beats), 1)
        self.assertEqual(x_beats[0].x_post["text"], "Texto real do post, não a narração.")
        self.assertNotIn("narração não pode", x_beats[0].x_post["text"])
        self.assertEqual(x_beats[0].visual_variant, "x_card")

    def test_caso_c_abertura_longa_mesma_url(self):
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Caso C",
            "abertura": [{"speaker": "Peter", "texto": "Texto longo de abertura com mais de cinquenta palavras para ocupar os primeiros trinta segundos de vídeo de forma densa e contínua sem interrupções artificiais."}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Corpo longo. " * 50}],
            "fechamento": [{"speaker": "Peter", "texto": "Fim."}],
        }
        beats = build_scene_timeline(episode, 240.0, [
            self._article(),
            {"veiculo": "Poder360", "url": "https://www.poder360.com.br/outra", "shot": "p360.png"},
        ])
        first = [b for b in beats if b.t0 < 15.0 and b.visual_component not in ("transition", "broll")]
        self.assertGreaterEqual(len(first), 2)
        self.assertEqual({b.url for b in first}, {"https://www.metropoles.com/materia"})
        self.assertTrue(any(b.visual_variant in ("portal_hero", "portal_zoom", "portal_highlight") for b in first))

    def test_caso_d_artigo_sem_shot_nao_promove_x(self):
        from bm_scene_timeline import build_scene_timeline
        from bm_video.cli import select_usable_scenes
        article = {"veiculo": "ICL", "url": "https://iclnoticias.com.br/aviao", "shot": None}
        episode = {
            "titulo": "Caso D",
            "abertura": [{"speaker": "Peter", "texto": "Fala sobre o avião, sem citar post."}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Continua o mesmo fato."}],
            "fechamento": [{"speaker": "Peter", "texto": "Fecho."}],
        }
        usable = select_usable_scenes([article, self._x()], episode, shot_dir=None, rescue=lambda url, dest: False)
        self.assertIn(article, usable)
        beats = build_scene_timeline(episode, 60.0, usable)
        self.assertFalse(any(b.visual_component == "x-post" for b in beats))
        shown = [b for b in beats if b.visual_component not in ("transition", "broll")]
        self.assertTrue(all(b.url == "https://iclnoticias.com.br/aviao" for b in shown))
        self.assertTrue(all(b.url for b in beats))

    def test_caso_e_fonte_explicita_vence_primaria_e_x(self):
        from bm_scene_timeline import build_scene_timeline
        episode = {
            "titulo": "Caso E",
            "abertura": [{"speaker": "Peter", "texto": "Esta fala cita a matéria B.", "fonte_url": "https://www.poder360.com.br/artigo-b"}],
            "desenvolvimento": [{"speaker": "Peter", "texto": "Ainda a matéria B.", "fonte_url": "https://www.poder360.com.br/artigo-b"}],
            "fechamento": [{"speaker": "Peter", "texto": "Fecho."}],
        }
        scenes = [
            self._article(),
            {"veiculo": "Poder360", "url": "https://www.poder360.com.br/artigo-b", "shot": "b.png"},
            self._x(),
        ]
        beats = build_scene_timeline(episode, 60.0, scenes)
        spoken = [b for b in beats if b.fonte_url_fala == "https://www.poder360.com.br/artigo-b"]
        self.assertTrue(spoken)
        self.assertTrue(all(b.url == "https://www.poder360.com.br/artigo-b" for b in spoken))
        self.assertFalse(any(b.visual_component == "x-post" for b in beats))


if __name__ == "__main__":
    unittest.main()



