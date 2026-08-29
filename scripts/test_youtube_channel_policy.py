#!/usr/bin/env python3
"""Testes da política de metadados YouTube do canal (sem API)."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from youtube_channel_policy import (  # noqa: E402
    CATEGORY_EDUCATION,
    CATEGORY_NEWS_POLITICS,
    CATEGORY_PEOPLE_BLOGS,
    PL_BRASILIA,
    PL_ECONOMIA,
    PL_JUIZES,
    PL_MUNDO,
    PL_SOCIALISMO,
    choose_category,
    choose_playlists,
    recording_date_iso,
    video_resource_body,
)


class PlaylistChoiceTests(unittest.TestCase):
    def test_juizes_stf_multa(self):
        d = choose_playlists("STF multa jornal e abre inquérito contra o site")
        self.assertEqual(d.names, (PL_JUIZES,))

    def test_economia_recuperacao(self):
        d = choose_playlists("Empresa pede recuperação judicial e o caixa some")
        self.assertEqual(d.names[0], PL_ECONOMIA)

    def test_brasilia_palanque(self):
        d = choose_playlists("Lula no palanque e pesquisa eleitoral no JN")
        self.assertEqual(d.names, (PL_BRASILIA,))

    def test_mundo_china_tarifa(self):
        d = choose_playlists("China sobe tarifa e o preço chega no Brasil")
        self.assertEqual(d.names, (PL_MUNDO,))

    def test_socialismo_marx(self):
        d = choose_playlists("Marx, o plano quinquenal e o Estado engenheiro")
        self.assertEqual(d.names, (PL_SOCIALISMO,))

    def test_lobista_lula_jn_fotos(self):
        d = choose_playlists("Lobista com Lula no JN e as fotos do encontro")
        self.assertEqual(d.names, (PL_BRASILIA,))

    def test_lula_preco_tse_duas(self):
        d = choose_playlists("TSE proíbe comparar preço e Lula entra na briga")
        self.assertEqual(set(d.names), {PL_ECONOMIA, PL_JUIZES})
        self.assertEqual(len(d.names), 2)

    def test_nunca_tres(self):
        d = choose_playlists(
            "STF multa, Lula no palanque, China tarifa e Marx no plano quinquenal com preço no Brasil"
        )
        self.assertLessEqual(len(d.names), 2)

    def test_sem_encaixe(self):
        d = choose_playlists("Receita de bolo de milho da vovó")
        self.assertEqual(d.names, ())
        self.assertIn("fora das cinco", d.reason)

    def test_ingles_sem_data(self):
        d = choose_playlists("The State and the Market in this essay for you and the reader")
        self.assertEqual(d.names, ())
        self.assertIn("inglês", d.reason)

    def test_imigracao_sc_custo(self):
        d = choose_playlists("Imigração em SC aperta o preço da moradia")
        self.assertEqual(d.names, (PL_ECONOMIA,))

    def test_imigracao_sc_fluxo(self):
        d = choose_playlists("Fluxo de imigração em SC e a fronteira")
        self.assertEqual(d.names, (PL_MUNDO,))


class CategoryAndBodyTests(unittest.TestCase):
    def test_news_default(self):
        self.assertEqual(choose_category("STF decide multa"), CATEGORY_NEWS_POLITICS)

    def test_ensaio_educacao(self):
        self.assertEqual(choose_category("Ensaio sobre o Estado"), CATEGORY_EDUCATION)

    def test_bastidor(self):
        self.assertEqual(
            choose_category("Bastidor do canal: como gravamos"),
            CATEGORY_PEOPLE_BLOGS,
        )

    def test_body_ai_lang_category(self):
        body = video_resource_body(
            "STF abre inquérito",
            "Análise do Vale.",
            ["vale"],
            "public",
            recording_date="2026-08-29T00:00:00-03:00",
        )
        self.assertTrue(body["status"]["containsSyntheticMedia"])
        self.assertEqual(body["snippet"]["defaultLanguage"], "pt")
        self.assertEqual(body["snippet"]["defaultAudioLanguage"], "pt-BR")
        self.assertEqual(body["snippet"]["categoryId"], "25")
        self.assertEqual(body["recordingDetails"]["recordingDate"], "2026-08-29T00:00:00-03:00")
        self.assertNotIn("location", body["recordingDetails"])

    def test_recording_date_sao_paulo(self):
        now = datetime(2026, 8, 29, 23, 10, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertTrue(recording_date_iso(now).startswith("2026-08-29"))
        utc = datetime(2026, 8, 30, 2, 10, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(recording_date_iso(utc).startswith("2026-08-29"))


if __name__ == "__main__":
    unittest.main()
