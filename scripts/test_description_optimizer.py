#!/usr/bin/env python3
"""
Testes unitários para o módulo description_optimizer.py
Verifica compliance de URLs, formatação de saída, fallbacks determinísticos e regras de canal.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from description_optimizer import (
    ANCAPSU_URL_PATTERNS,
    APP_CANONICAL_URL,
    build_description_prompt,
    clean_youtube_description,
    deterministic_description,
    generate_daily_description,
    strip_forbidden_urls,
)


class TestDescriptionOptimizer(unittest.TestCase):

    def test_strip_forbidden_ancapsu_urls(self):
        sample = (
            "Análise do tema de hoje.\n"
            "Veja também https://www.youtube.com/@ancap_su e https://ancap.su/noticia.\n"
            "Fonte real: https://ndmais.com.br/blumenau/noticia-123\n"
        )
        cleaned = strip_forbidden_urls(sample)
        self.assertNotIn("youtube.com/@ancap_su", cleaned)
        self.assertNotIn("ancap.su", cleaned)
        self.assertIn("https://ndmais.com.br/blumenau/noticia-123", cleaned)

    def test_clean_youtube_description_removes_cliches_and_adds_app_link(self):
        raw = (
            "### DESCRIÇÃO\n\n"
            "Olá pessoal, sejam bem-vindos! Hoje vamos analisar o novo decreto municipal de Blumenau.\n\n"
            "Peter e Ricardo debatem os gastos públicos.\n\n"
            "Você concorda com essa decisão?\n\n"
            "### HASHTAGS\n"
            "#Tag1 #Tag2 #Tag3 #Tag4"
        )
        cleaned = clean_youtube_description(
            raw,
            sources=["https://ndmais.com.br/noticia"],
            hashtags=["#Webjornal", "#ValedaLiberdade", "#Economia", "#Extra"],
            is_bm=False,
        )

        # Sem clichês
        self.assertFalse(cleaned.lower().startswith("olá pessoal"))
        self.assertFalse(cleaned.lower().startswith("sejam bem-vindos"))

        # Link canônico do app presente
        self.assertIn(APP_CANONICAL_URL, cleaned)

        # Máximo de 3 hashtags
        tags = [w for w in cleaned.split() if w.startswith("#")]
        self.assertLessEqual(len(tags), 3)
        self.assertIn("#Webjornal", tags)
        self.assertIn("#ValedaLiberdade", tags)

    def test_deterministic_description_daily(self):
        ctx = {
            "date": "2026-08-10",
            "title": "Câmara de Blumenau e Obras da BR-470",
            "manchetes": [
                "Revisão do IPTU gera polêmica",
                "Obras da rodovia atrasam",
                "Nova regra na saúde pública",
            ],
            "is_bm": False,
        }
        desc = deterministic_description(ctx)
        self.assertIn("Peter Albuquerque", desc)
        self.assertIn("Ricardo Souto", desc)
        self.assertIn("Revisão do IPTU gera polêmica", desc)
        self.assertIn("comentários", desc.lower())

    def test_deterministic_description_bm(self):
        ctx = {
            "video_id": "xyz123",
            "title": "Nova Taxa sobre Importações Aprovada",
            "resumo": "Discussão sobre o aumento de impostos alfandegários.",
            "is_bm": True,
        }
        desc = deterministic_description(ctx)
        self.assertIn("Peter Albuquerque", desc)
        self.assertIn("Nova Taxa sobre Importações Aprovada", desc)
        self.assertIn("comentários", desc.lower())

    def test_build_description_prompt_rules(self):
        ctx = {
            "date": "2026-08-10",
            "title": "Teste do Episódio",
            "manchetes": ["Manchete 1", "Manchete 2"],
            "quadros": [{"quadro": "Segurança", "destaque": "Fatos de segurança"}],
            "is_bm": False,
        }
        prompt = build_description_prompt(ctx)
        self.assertIn("Webjornal Vale da Liberdade", prompt)
        self.assertIn("Peter Albuquerque", prompt)
        self.assertIn("ANCAPSU", prompt)  # regra explícita de proibição
        self.assertIn("Manchete 1", prompt)

    def test_generate_daily_description_dry_run(self):
        desc, path = generate_daily_description("2026-06-15", dry_run=True)
        self.assertTrue(len(desc) > 100)
        self.assertIn(APP_CANONICAL_URL, desc)
        self.assertIn("#Webjornal", desc)


if __name__ == "__main__":
    unittest.main()
