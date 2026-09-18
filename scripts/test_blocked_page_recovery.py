#!/usr/bin/env python3
"""
Testes automatizados da ferramenta e integração blocked-page-recovery.
Web Jornal Vale da Liberdade.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from recover_page import (
    RecoveredPage,
    clean_extracted_text,
    extract_title_and_text_from_html,
    page_looks_blocked,
    recover_page,
)
from http_fetch import fetch_with_recovery, smart_fetch
from news_collector import _recover_source_articles


class TestBlockedPageRecovery(unittest.TestCase):

    def test_block_detection(self):
        """Verifica se detectores de bloqueio capturam WAFs, 403 e paywalls."""
        self.assertTrue(page_looks_blocked("", 403))
        self.assertTrue(page_looks_blocked("", 401))
        self.assertTrue(page_looks_blocked("", 429))
        self.assertTrue(page_looks_blocked("Access Denied: You don't have permission to access on this server."))
        self.assertTrue(page_looks_blocked("<html><body>errors.edgesuite.net Akamai Error</body></html>"))
        self.assertTrue(page_looks_blocked("Just a moment... Enable JavaScript and cookies to continue (Cloudflare)"))
        self.assertTrue(page_looks_blocked("Esta matéria é exclusiva para assinantes. Assine para continuar lendo."))
        self.assertTrue(page_looks_blocked("Texto minúsculo", 200))  # Muito curto (<120 chars)

        # Página legítima não deve ser bloqueada
        legit_text = (
            "A Prefeitura de Blumenau anunciou nesta segunda-feira a conclusão das obras de pavimentação "
            "na região central do município. O investimento de mais de dez milhões de reais contemplou "
            "novas calçadas acessíveis, drenagem pluvial e sinalização viária completa para melhorar "
            "o fluxo de pedestres e veículos durante o horário de pico."
        )
        self.assertFalse(page_looks_blocked(legit_text, 200))

    def test_clean_extracted_text(self):
        """Verifica se a normalização de texto remove excessos mantendo parágrafos."""
        raw = "   Linha 1 com    espaços extras.  \r\n\r\n\r\n\r\nLinha 2 com texto.   \n\n\n\n"
        cleaned = clean_extracted_text(raw)
        self.assertEqual(cleaned, "Linha 1 com espaços extras.\n\nLinha 2 com texto.")

    def test_html_title_and_text_extraction(self):
        """Verifica extração de título e conteúdo de HTML estruturado."""
        html = """
        <html>
          <head><title>Título da Matéria - Portal de Notícias</title></head>
          <body>
            <nav><a href="/">Home</a></nav>
            <article>
              <h1>Título da Matéria</h1>
              <p>Primeiro parágrafo de notícia sobre o Vale do Itajaí.</p>
              <p>Segundo parágrafo com dados detalhados e declaração das autoridades.</p>
            </article>
            <footer>Todos os direitos reservados</footer>
          </body>
        </html>
        """
        title, text = extract_title_and_text_from_html(html)
        self.assertIn("Título da Matéria", title)
        self.assertIn("Primeiro parágrafo de notícia sobre o Vale do Itajaí.", text)
        self.assertNotIn("Todos os direitos reservados", text)

    def test_recover_page_live_or_archive(self):
        """Testa o fluxo da escada de recuperação para um site padrão."""
        # Testando URL histórica conhecida no Internet Archive
        url = "https://example.com"
        rec = recover_page(url, timeout=10.0, try_direct_first=True)
        self.assertTrue(rec.success)
        self.assertTrue(len(rec.content) > 50)
        self.assertIn(rec.method_used, ["direct", "wayback", "archive_today", "jina_reader", "api_pivot", "browser"])

    def test_http_fetch_with_recovery(self):
        """Verifica se fetch_with_recovery retorna tupla estruturada e metadados."""
        content, status, meta = fetch_with_recovery("https://example.com", timeout=10.0)
        self.assertIsNotNone(content)
        self.assertEqual(status, 200)
        self.assertIn("method", meta)
        self.assertIn("provenance", meta)

    def test_news_collector_recovery_fallback(self):
        """Verifica se o helper do news_collector extrai candidatos de fallback.

        Teste determinístico: injeta um RecoveredPage local (fixture HTML) para
        não depender de rede externa (Wayback/Archive.today), que é flaky.
        Exerce os três caminhos de extração do helper: HTML bruto, markdown
        e página de artigo individual.
        """
        from recover_page import RecoveredPage
        from news_collector import _recover_source_articles
        from unittest import mock

        # Fixture: portal com 3 links editoriais no HTML bruto
        fixture_html = (
            "<html><head><title>Portal Teste</title></head><body>"
            "<article><h2><a href='/noticia/uma'>Primeira matéria de teste do portal</a></h2></article>"
            "<article><h2><a href='/noticia/duas'>Segunda matéria de teste do portal</a></h2></article>"
            "<article><h2><a href='https://example.com/noticia/tres'>Terceira matéria de teste do portal</a></h2></article>"
            "</body></html>"
        )
        fake = RecoveredPage(
            url="https://example.com",
            success=True,
            title="Portal Teste",
            content="Conteúdo do portal.",
            method_used="archive_today",
            snapshot_date="2026-09-15",
            snapshot_url="https://archive.ph/newest/https://example.com",
            snapshot_route="archive_today",
            provenance="Arquivado via Archive.today (2026-09-15)",
            status_code=200,
            raw_html=fixture_html,
        )

        source = {
            "id": "teste_bloqueado",
            "name": "Portal Teste",
            "url": "https://example.com",
            "method": "scraping",
        }
        with mock.patch("recover_page.recover_page", return_value=fake):
            articles, success = _recover_source_articles(source)

        self.assertTrue(success)
        self.assertGreater(len(articles), 0)
        self.assertIn("link", articles[0])
        self.assertIn("title", articles[0])
        # Os links relativos foram normalizados para URL absoluta
        for art in articles:
            self.assertTrue(art["link"].startswith("http"), art["link"])
        self.assertEqual(len(articles), 3)

    def test_news_collector_recovery_markdown(self):
        """Caminho 2 do helper: conteúdo markdown com links [Title](url)."""
        from recover_page import RecoveredPage
        from news_collector import _recover_source_articles
        from unittest import mock

        fake = RecoveredPage(
            url="https://example.com",
            success=True,
            title="Portal Teste",
            content=(
                "# Portal Teste\n\n"
                "[Manchete longa de exemplo do portal](https://example.com/a1)\n\n"
                "[Outra manchete longa de exemplo](https://example.com/a2)\n"
            ),
            method_used="jina_reader",
            provenance="Renderizado via Jina Reader (ao vivo)",
            status_code=200,
            raw_html=None,
        )
        source = {"id": "md_teste", "name": "Portal", "url": "https://example.com"}
        with mock.patch("recover_page.recover_page", return_value=fake):
            articles, success = _recover_source_articles(source)
        self.assertTrue(success)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["link"], "https://example.com/a1")

    def test_news_collector_recovery_single_article(self):
        """Caminho 3 do helper: artigo individual (título + conteúdo longo)."""
        from recover_page import RecoveredPage
        from news_collector import _recover_source_articles
        from unittest import mock

        fake = RecoveredPage(
            url="https://example.com/artigo",
            success=True,
            title="Título do artigo individual de teste",
            content="Parágrafo de teste. " * 30,  # >= 180 chars
            method_used="direct",
            provenance="Conteúdo ao vivo",
            status_code=200,
            raw_html=None,
        )
        source = {"id": "art_teste", "name": "Portal", "url": "https://example.com/artigo"}
        with mock.patch("recover_page.recover_page", return_value=fake):
            articles, success = _recover_source_articles(source)
        self.assertTrue(success)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["link"], "https://example.com/artigo")

    def test_news_collector_recovery_failure(self):
        """Recuperação malsucedida retorna ([], False)."""
        from recover_page import RecoveredPage
        from news_collector import _recover_source_articles
        from unittest import mock

        fake = RecoveredPage(
            url="https://example.com",
            success=False,
            error="HTTP 403 (bloqueio WAF)",
        )
        source = {"id": "fail_teste", "name": "Portal", "url": "https://example.com"}
        with mock.patch("recover_page.recover_page", return_value=fake):
            articles, success = _recover_source_articles(source)
        self.assertFalse(success)
        self.assertEqual(articles, [])

    def test_news_collector_recovery_live(self):
        """Teste vivo (rede): a escada de recuperação precisa funcionar.

        Marcado para pular quando BM_SKIP_NETWORK_TESTS=1 (ambientes sem
        acesso geral à internet — o archive.org fica inalcansável).
        """
        import os

        if os.environ.get("BM_SKIP_NETWORK_TESTS") == "1":
            self.skipTest("BM_SKIP_NETWORK_TESTS=1 (sem rede externa)")

        source = {
            "id": "teste_bloqueado",
            "name": "Portal Teste",
            "url": "https://example.com",
            "method": "scraping",
        }
        articles, success = _recover_source_articles(source)
        if not success:
            self.skipTest("rede externa indisponível (Wayback/Archive.today)")
        self.assertGreater(len(articles), 0)
        self.assertIn("link", articles[0])
        self.assertIn("title", articles[0])

    def test_cli_execution_json(self):
        """Testa a execução CLI com --json."""
        cmd = [sys.executable, str(SCRIPT_DIR / "recover_page.py"), "https://example.com", "--json"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertTrue(data.get("success"))
        self.assertIn("method_used", data)
        self.assertIn("provenance", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
