"""Testes de regressão: Integração do Card do X e padronização do mockup-browser.html."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"


def test_mockup_browser_files_exist_and_in_sync():
    browser_html = MOCKUP_DIR / "mockup-browser.html"
    brower_html = MOCKUP_DIR / "mockup-brower.html"

    assert browser_html.is_file(), "mockup-browser.html deve existir"
    assert brower_html.is_file(), "mockup-brower.html (compatibilidade) deve existir"

    content_browser = browser_html.read_text(encoding="utf-8")
    content_brower = brower_html.read_text(encoding="utf-8")

    # Verifica elementos essenciais do card do X em ambos
    for content in (content_browser, content_brower):
        assert 'id="xCard"' in content, "Elemento #xCard deve estar presente"
        assert ".bcard-x-post" in content, "Classe CSS .bcard-x-post deve estar presente"
        assert "transitionToX" in content, "Método transitionToX deve estar implementado no VDL_MOCKUP_ENGINE"
        assert '"xCard"' in content, "xCard deve estar registrado em _hideAllCards()"
        assert 'kind === "x-post"' in content, "update() deve rotear kind x-post para transitionToX"
        assert 'id="xMediaBox"' in content, "#xMediaBox deve existir para imagens de tweets"
        assert 'id="xLikeBtn"' in content, "#xLikeBtn deve existir para micro-animação de like"


def test_demo_broadcast_studio_points_to_browser_and_has_x_post():
    studio_html = (MOCKUP_DIR / "demo-broadcast-studio.html").read_text(encoding="utf-8")
    assert 'src="mockup-browser.html"' in studio_html, "iframe do studio deve apontar para mockup-browser.html"
    assert 'data-kind="x-post"' in studio_html, "Botão Modo 8 do switcher deve ter data-kind='x-post'"
    assert '"x-post": {' in studio_html, "Preset do x-post deve estar definido em DEMO_PRESETS"


def test_constants_mockup_html_resolution():
    from scripts.bm_video.constants import MOCKUP_HTML
    assert MOCKUP_HTML == "mockup-browser.html", "Constante oficial MOCKUP_HTML deve priorizar mockup-browser.html"


def test_build_mockup_update_payload_x_post():
    from scripts.bm_video.state import _build_mockup_update_payload

    beat = {
        "visual_component": "x-post",
        "url": "https://x.com/alexandre/status/1830689409823485952",
        "x_post": {
            "author_name": "Alexandre de Moraes",
            "handle": "@alexandre",
            "text": "STF em defesa da Constituição.",
            "media": "/shots/x-media-123.jpg",
        },
    }
    payload = _build_mockup_update_payload(beat)
    assert payload["kind"] == "x-post"
    assert payload["visual_component"] == "x-post"
    assert payload["xPost"]["author_name"] == "Alexandre de Moraes"
    assert payload["xPost"]["media"] == "/shots/x-media-123.jpg"
