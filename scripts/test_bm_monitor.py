#!/usr/bin/env python3
"""Filtros do monitor ANCAPSU: shorts, lives, entrevistas."""
from __future__ import annotations

import unittest

from bm_monitor import is_interview, is_short_or_live


class InterviewFilterTests(unittest.TestCase):
    def test_peter_entrevista_with_colon(self):
        self.assertTrue(
            is_interview("PETER ENTREVISTA: ALTIVO DUARTE | Deputado Federal por MG")
        )

    def test_peter_entrevista_without_colon(self):
        self.assertTrue(
            is_interview("PETER ENTREVISTA MARINA HELENA - Deputada Federal por SP - 3007")
        )
        self.assertTrue(
            is_interview("PETER ENTREVISTA JESSÉ SANGALLI - Deputado Federal pelo RS - 2230")
        )

    def test_entrevista_com(self):
        self.assertTrue(is_interview("ENTREVISTA COM o deputado X"))

    def test_news_about_someone_elses_interview_is_kept(self):
        self.assertFalse(
            is_interview("FOLHA Entrevista DITADOR CUBANO e Culpa o CAPITALISMO")
        )


class ShortLiveFilterTests(unittest.TestCase):
    def test_shorts_url(self):
        self.assertTrue(is_short_or_live("qualquer", "https://www.youtube.com/shorts/abc"))

    def test_news_title_with_vivo_is_not_live(self):
        self.assertFalse(
            is_short_or_live(
                "PF investiga OPERADOR de DINHEIRO VIVO de LULINHA",
                "https://www.youtube.com/watch?v=tHw7m2hT3JU",
            )
        )


if __name__ == "__main__":
    unittest.main()
