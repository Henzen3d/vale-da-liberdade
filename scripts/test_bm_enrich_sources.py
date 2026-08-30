#!/usr/bin/env python3
"""Testes unitários do enriquecedor de fontes BM (sem rede)."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bm_enrich_sources import (
    clean_url,
    domain_of,
    enrich_episode_sources,
    extract_keywords_from_title,
    is_blocked_source,
    site_referencias,
    veiculo_from_url,
)


class SourceEnricherTests(unittest.TestCase):
    def test_domain_of(self):
        self.assertEqual(domain_of("https://www.cnnbrasil.com.br/politica"), "cnnbrasil.com.br")
        self.assertEqual(domain_of("https://g1.globo.com/sc"), "g1.globo.com")
        self.assertEqual(domain_of(""), "")

    def test_clean_url(self):
        dirty = "https://www.folha.uol.com.br/poder/noticia.shtml?utm_source=twitter&utm_medium=social&id=123"
        cleaned = clean_url(dirty)
        self.assertNotIn("utm_source", cleaned)
        self.assertNotIn("utm_medium", cleaned)
        self.assertIn("id=123", cleaned)

    def test_is_blocked_source(self):
        self.assertTrue(is_blocked_source("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_blocked_source("https://youtu.be/abc"))
        self.assertTrue(is_blocked_source("https://ancapsu.com/artigo"))
        self.assertTrue(is_blocked_source("https://news.mob.tec.br/ep/123.html"))
        self.assertTrue(is_blocked_source("ftp://invalido.com"))
        self.assertFalse(is_blocked_source("https://g1.globo.com/politica"))
        self.assertFalse(is_blocked_source("https://www.bbc.com/portuguese"))

    def test_veiculo_from_url(self):
        self.assertEqual(veiculo_from_url("https://g1.globo.com/sp/noticia"), "G1")
        self.assertEqual(veiculo_from_url("https://www1.folha.uol.com.br/poder"), "Folha de S.Paulo")
        self.assertEqual(veiculo_from_url("https://www.cnnbrasil.com.br/nacional"), "CNN Brasil")
        self.assertEqual(veiculo_from_url("https://feeds.bbci.co.uk/portuguese/rss.xml"), "BBC News")

    def test_extract_keywords_from_title(self):
        title = "LULA e LUCHSINGER: A Polêmica das FOTOS Negadas no Palácio"
        keywords = extract_keywords_from_title(title)
        self.assertIn("lula", keywords)
        self.assertIn("luchsinger", keywords)
        self.assertIn("polêmica", keywords)
        self.assertIn("fotos", keywords)
        self.assertNotIn("das", keywords)

    def test_enrich_episode_sources_from_raw_paired(self):
        raw = {
            "title": "Escândalo em Brasília",
            "sources": [
                {"veiculo": "CNN Brasil", "url": "https://www.cnnbrasil.com.br/politica/fato"},
                {"veiculo": "Folha", "url": "https://www1.folha.uol.com.br/poder/fato"},
                {"veiculo": "YouTube", "url": "https://www.youtube.com/watch?v=123"},
            ]
        }
        refs, briefing = enrich_episode_sources(raw, "teste123", max_external=8)
        # Deve filtrar YouTube e incluir self ao final
        urls = [r["url"] for r in refs]
        self.assertTrue(any("cnnbrasil" in u for u in urls))
        self.assertTrue(any("folha" in u for u in urls))
        self.assertFalse(any("youtube.com" in u for u in urls))
        self.assertTrue(any(r.get("self") for r in refs))
        self.assertIn("CNN Brasil", briefing)
        self.assertIn("Folha", briefing)

    def test_site_referencias(self):
        refs = site_referencias("videoXYZ")
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(r.get("self") for r in refs))
        self.assertTrue(all(r.get("role") == "visual" for r in refs))


if __name__ == "__main__":
    unittest.main()
