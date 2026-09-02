#!/usr/bin/env python3
"""Registry dos handlers de screenshot — sem rede, sem Playwright."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.screenshots.sites import get_scraper, list_registered  # noqa: E402


NEW_DOMAINS = (
    "veja.abril.com.br",
    "uol.com.br",
    "noticias.uol.com.br",
    "economia.uol.com.br",
    "metropoles.com",
    "cnnbrasil.com.br",
    "poder360.com.br",
    "claudiodantas.com.br",
    "revistaoeste.com",
    "diariodopoder.com.br",
    "bbc.com",
    "bbc.co.uk",
)

OLD_DOMAINS = (
    "g1.globo.com",
    "oglobo.globo.com",
    "valor.globo.com",
    "estadao.com.br",
    "folha.uol.com.br",
    "www1.folha.uol.com.br",
    "gazetadopovo.com.br",
    "revistaforum.com.br",
    "brasil247.com",
    "piaui.uol.com.br",
)


class RegistryTests(unittest.TestCase):
    def test_new_and_old_domains_registered(self):
        sites = set(list_registered())
        missing = [d for d in (*NEW_DOMAINS, *OLD_DOMAINS) if d not in sites]
        self.assertEqual(missing, [], f"domínios sem handler: {missing}")

    def test_uol_parent_covers_unknown_subdomain(self):
        scraper = get_scraper("noticiasdatv.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "uol")

    def test_folha_wins_over_uol_parent(self):
        scraper = get_scraper("www1.folha.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "folha")

    def test_piaui_wins_over_uol_parent(self):
        scraper = get_scraper("piaui.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "piaui")

    def test_unknown_domain_has_no_handler(self):
        self.assertIsNone(get_scraper("example.com"))


if __name__ == "__main__":
    unittest.main()
