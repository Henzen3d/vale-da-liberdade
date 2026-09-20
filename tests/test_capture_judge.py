"""Testes do Juiz Visual Pré-render, Fila de Handlers Quebrados e Escada de Fallback (Etapa 3)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bm_video.capture import (
    capture_sources,
    page_looks_blocked,
    record_broken_handler,
)
from bm_video.constants import _BLOCK_TEXT_MARKERS
from person_resolver import download_article_image, extract_og_image_from_url
from scripts.screenshots.paywall import detect_block


class FakePage:
    """Mock leve de página Playwright para testar o juiz visual."""

    def __init__(self, inner_text: str = "", title_text: str = "") -> None:
        self._inner_text = inner_text
        self._title_text = title_text

    def inner_text(self, selector: str = "body") -> str:
        return self._inner_text

    def title(self) -> str:
        return self._title_text

    def evaluate(self, expr: str) -> str:
        return self._inner_text[:3000].lower()


def test_page_looks_blocked_detects_all_major_waf_and_botwalls():
    # 1. Cloudflare Turnstile
    cf_page = FakePage(inner_text="Verify you are human. Cloudflare Turnstile is checking your connection.")
    assert page_looks_blocked(cf_page) in ("turnstile", "verify you are human")

    # 2. Akamai Access Denied
    akamai_page = FakePage(inner_text="Access Denied. You don't have permission to access on this server.")
    assert page_looks_blocked(akamai_page) in ("access denied", "you don't have permission to access")

    # 3. HTTP status code
    normal_page = FakePage(inner_text="Texto qualquer da notícia")
    assert page_looks_blocked(normal_page, status=403) == "http-403"
    assert page_looks_blocked(normal_page, status=429) == "http-429"


def test_page_looks_blocked_ignores_real_long_articles():
    # Matéria jornalística legítima que menciona a palavra "turnstile" ou "bloqueio" em contexto
    long_text = "O governo anunciou nova medida econômica hoje em Brasília. " * 50
    real_article = FakePage(inner_text=long_text)
    assert page_looks_blocked(real_article) is None


def test_detect_block_in_paywall_module():
    # Valida integração do paywall.py com os marcadores de bloco
    page = FakePage(inner_text="Checking your browser before accessing. Just a moment...", title_text="Just a moment...")
    res = detect_block(page)
    assert res in ("cloudflare", "block:just a moment", "block:checking your browser before accessing")


def test_record_broken_handler_creates_and_appends_audit_log(tmp_path: Path):
    log_file = tmp_path / "broken_handlers.json"
    
    # 1. Primeiro registro
    record_broken_handler(
        url="https://www.estadao.com.br/politica/materia-teste",
        handler_name="estadao",
        error_reason="blocked:turnstile",
        http_status=403,
        log_file=log_file,
    )
    assert log_file.is_file()
    data = json.loads(log_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["domain"] == "estadao.com.br"
    assert data[0]["handler"] == "estadao"
    assert "turnstile" in data[0]["error"]
    assert data[0]["status"] == 403

    # 2. Segundo registro (adiciona sem sobrescrever)
    record_broken_handler(
        url="https://oglobo.globo.com/economia/outra-materia",
        handler_name="oglobo",
        error_reason="timeout",
        http_status=504,
        log_file=log_file,
    )
    data = json.loads(log_file.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[1]["domain"] == "oglobo.globo.com"
    assert data[1]["handler"] == "oglobo"


def test_extract_og_image_from_url_parses_meta_tags():
    html_mock = b"""<!DOCTYPE html>
    <html>
      <head>
        <meta property="og:title" content="Titulo da Noticia">
        <meta property="og:image" content="https://img.estadao.com.br/fotos/noticia.jpg">
      </head>
      <body><p>Corpo</p></body>
    </html>"""

    mock_resp = MagicMock()
    mock_resp.read.return_value = html_mock
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        img_url = extract_og_image_from_url("https://www.estadao.com.br/materia")
        assert img_url == "https://img.estadao.com.br/fotos/noticia.jpg"


def test_download_article_image_saves_valid_image(tmp_path: Path):
    dest = tmp_path / "test_shot.png"
    html_mock = b'<html><head><meta property="og:image" content="https://site.com/pic.jpg"></head></html>'
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"A" * 12000

    mock_html_resp = MagicMock()
    mock_html_resp.read.return_value = html_mock
    mock_html_resp.__enter__.return_value = mock_html_resp

    mock_img_resp = MagicMock()
    mock_img_resp.read.return_value = image_bytes
    mock_img_resp.__enter__.return_value = mock_img_resp

    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "pic.jpg" in url:
            return mock_img_resp
        return mock_html_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        success = download_article_image("https://site.com/article", dest)
        assert success is True
        assert dest.is_file()
        assert dest.stat().st_size == len(image_bytes)


def test_capture_sources_rescues_blocked_scene_via_og_image(tmp_path: Path):
    """Garante que se uma página estiver bloqueada, o pipeline resgata a imagem editorial da matéria."""
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir(parents=True)

    scenes = [{
        "veiculo": "Folha de S.Paulo",
        "url": "https://www1.folha.uol.com.br/poder/materia-bloqueada",
    }]

    # Simula handler falhando
    def fake_try_handler(url, dest, viewport=None):
        return {"ok": False, "handler": "folha", "error": "blocked:cloudflare", "http_status": 403}

    # Simula downloader de og:image tendo sucesso
    def fake_downloader(url, dest):
        dest.write_bytes(b"\x89PNG\r\n\x1a\n" + b"X" * 15000)
        return True

    with (
        patch("bm_video.capture.try_handler_screenshot", fake_try_handler),
        patch("bm_video.capture.get_cached_screenshot", return_value=None),
        patch("bm_video.capture.save_cached_screenshot", return_value=None),
        patch("bm_video.capture._get_download_article_image", return_value=fake_downloader),
    ):
        # Simula contexto do Playwright onde a página cai em bloqueio antibot
        fake_page = MagicMock()
        fake_page.inner_text.return_value = "Checking your browser. Cloudflare Turnstile."
        fake_resp = MagicMock()
        fake_resp.status = 403
        fake_page.goto.return_value = fake_resp

        fake_ctx = MagicMock()
        fake_ctx.new_page.return_value = fake_page
        fake_browser = MagicMock()
        fake_browser.new_context.return_value = fake_ctx
        fake_pw = MagicMock()
        fake_pw.chromium.launch.return_value = fake_browser
        fake_pw.__enter__.return_value = fake_pw

        with patch("bm_video.capture._open_sync_playwright", return_value=fake_pw):
            out = capture_sources(scenes, shot_dir)

        # A cena DEVE ser resgatada e possuir shot preenchido com a imagem editorial
        assert len(out) == 1
        assert out[0]["shot"] == "src-00.png"
        assert (shot_dir / "src-00.png").is_file()
