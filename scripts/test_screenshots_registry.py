#!/usr/bin/env python3
"""Registry dos handlers de screenshot — sem rede, sem Playwright."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.screenshots.sites import get_scraper, list_registered  # noqa: E402


# Domínios que o pipeline BM precisa despachar (get_scraper → try_handler_screenshot).
REQUIRED_DOMAINS = (
    "abril.com.br",
    "ainvestigacao.com",
    "ainvestigacao.com.br",
    "aosfatos.org",
    "bbc.co.uk",
    "bbc.com",
    "blogdobg.com.br",
    "brasil247.com",
    "brasildefato.com.br",
    "cartacapital.com.br",
    "claudiodantas.com.br",
    "cnnbrasil.com.br",
    "congressoemfoco.com.br",
    "congressoemfoco.uol.com.br",
    "correiobraziliense.com.br",
    "datafolha.folha.uol.com.br",
    "diariodocentrodomundo.com.br",
    "diariodopoder.com.br",
    "economia.uol.com.br",
    "educacao.uol.com.br",
    "estadao.com.br",
    "folha.com.br",
    "folha.uol.com.br",
    "g1.globo.com",
    "gazetadopovo.com.br",
    "ge.globo.com",
    "globo.com",
    "iclnoticias.com.br",
    "infobae.com",
    "infomoney.com.br",
    "intercept.com.br",
    "jota.info",
    "metropoles.com",
    "noticias.uol.com.br",
    "nytimes.com",
    "oglobo.globo.com",
    "piaui.uol.com.br",
    "poder360.com.br",
    "quaest.com.br",
    "r7.com",
    "noticias.r7.com",
    "record.r7.com",
    "revistaforum.com.br",
    "revistaoeste.com",
    "sbtnews.com.br",
    "sbtnews.sbt.com.br",
    "splash.uol.com.br",
    "theguardian.com",
    "theintercept.com",
    "uol.com.br",
    "valor.globo.com",
    "veja.abril.com.br",
    "vejasp.abril.com.br",
    "www1.folha.uol.com.br",
)


class RegistryTests(unittest.TestCase):
    def test_required_domains_registered(self):
        sites = set(list_registered())
        missing = [d for d in REQUIRED_DOMAINS if d not in sites]
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

    def test_datafolha_folha_handler(self):
        scraper = get_scraper("datafolha.folha.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "folha")

    def test_abril_parent_covers_subdomains(self):
        scraper = get_scraper("vejasp.abril.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "veja")

    def test_piaui_wins_over_uol_parent(self):
        scraper = get_scraper("piaui.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "piaui")

    def test_congressoemfoco_uol_not_uol_handler(self):
        scraper = get_scraper("congressoemfoco.uol.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "congressoemfoco")

    def test_sbtnews_sbt_subdomain(self):
        scraper = get_scraper("sbtnews.sbt.com.br")
        self.assertIsNotNone(scraper)
        assert scraper is not None
        self.assertEqual(scraper.name, "sbtnews")

    def test_unknown_domain_has_no_handler(self):
        self.assertIsNone(get_scraper("example.com"))


if __name__ == "__main__":
    unittest.main()
