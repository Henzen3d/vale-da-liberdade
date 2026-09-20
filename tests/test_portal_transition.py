"""Testes de validação da animação suave de zoom out/in ao mudar de portal no browser mockup."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"


@pytest.mark.parametrize("filename", ["mockup-browser.html", "mockup-brower.html"])
def test_portal_transition_code_present_in_mockups(filename):
    """Garante que a lógica de animação de zoom out/in ao trocar de portal está em ambos os arquivos HTML."""
    path = MOCKUP_DIR / filename
    assert path.is_file(), f"{filename} deve existir"
    content = path.read_text(encoding="utf-8")

    assert "transform-origin: center center;" in content, "CSS do .browser-wrapper deve ter transform-origin: center center"
    assert "_animatePortalTransition" in content, "VDL_MOCKUP_ENGINE deve conter o método _animatePortalTransition"
    assert "_getPortalKey" in content, "VDL_MOCKUP_ENGINE deve conter o método _getPortalKey"
    assert "_updateArticleText" in content, "VDL_MOCKUP_ENGINE deve conter o método _updateArticleText"
    assert "_portalZoomTween" in content, "VDL_MOCKUP_ENGINE deve rastrear _portalZoomTween"
    assert "_hasRenderedFirstPortal" in content, "VDL_MOCKUP_ENGINE deve rastrear _hasRenderedFirstPortal"
    assert "scale: 0.88" in content, "Deve usar escala reduzida (~0.88) no ponto de contração central"
    assert "power2.inOut" in content, "Deve usar easing suave na redução ao centro"
    assert "power3.out" in content, "Deve usar easing suave na expansão a partir do centro"


def test_portal_transition_playwright_runtime():
    """Testa no runtime do Playwright se a transição ocorre na mudança de portal e preserva sub-beats."""
    from playwright.sync_api import sync_playwright
    import http.server
    import socketserver
    import threading

    # Sobe servidor HTTP temporário apontando para MOCKUP_DIR
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                
                # Carga da página
                page.goto(f"http://127.0.0.1:{port}/references/youtube/mockup-browser/mockup-browser.html", wait_until="domcontentloaded")
                page.wait_for_function("() => !!window.VDL_MOCKUP")

                # 1. Frame zero / carga inicial: não deve disparar animação de contração
                res_init = page.evaluate("""() => {
                    window.VDL_MOCKUP.update({
                        url: "https://g1.globo.com/politica",
                        titulo: "Matéria Inicial",
                        pageImage: "/shots/shot_001.png"
                    });
                    const browserEl = document.getElementById("browserMockup");
                    return {
                        hasRendered: window.VDL_MOCKUP._hasRenderedFirstPortal,
                        hasZoomTween: !!window.VDL_MOCKUP._portalZoomTween,
                        display: browserEl.style.display
                    };
                }""")
                assert res_init["hasRendered"] is True, "Primeira carga deve marcar _hasRenderedFirstPortal como True"
                assert res_init["hasZoomTween"] is False, "Frame zero não deve disparar animação de contração"

                # 2. Mudança de portal: deve disparar _animatePortalTransition
                res_change = page.evaluate("""() => {
                    window.VDL_MOCKUP.update({
                        url: "https://folha.uol.com.br/poder",
                        titulo: "Nova Matéria de Outro Portal",
                        pageImage: "/shots/shot_002.png"
                    });
                    return {
                        hasZoomTween: !!window.VDL_MOCKUP._portalZoomTween
                    };
                }""")
                assert res_change["hasZoomTween"] is True, "Troca de portal deve iniciar _portalZoomTween"

                # Aguarda término da animação
                page.wait_for_timeout(800)

                # 3. Sub-beat na mesma matéria (ex: portal_zoom): NÃO deve reanimar a janela do browser
                res_subbeat = page.evaluate("""() => {
                    window.VDL_MOCKUP.update({
                        url: "https://folha.uol.com.br/poder",
                        titulo: "Nova Matéria de Outro Portal",
                        pageImage: "/shots/shot_002.png",
                        visual_variant: "portal_zoom"
                    });
                    return {
                        hasZoomTween: !!window.VDL_MOCKUP._portalZoomTween
                    };
                }""")
                assert res_subbeat["hasZoomTween"] is False, "Sub-beat da mesma matéria não deve disparar zoom out/in da janela"

                browser.close()
        finally:
            httpd.shutdown()
