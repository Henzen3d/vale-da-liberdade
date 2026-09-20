"""Testes de validação da animação suave de zoom out/in ao mudar de portal no browser mockup e SFX de transição (whoosh)."""
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
    assert "_playTransitionSfx" in content, "Deve conter método para disparar som de transição"
    assert "_synthWhoosh" in content, "Deve conter sintetizador Web Audio API de whoosh para fallback"
    assert "whoosh.mp3" in content, "Deve referenciar assets/sfx/whoosh.mp3"


def test_transition_sfx_assets_exist():
    """Garante que os arquivos de SFX whoosh existem tanto no mockup quanto em branding."""
    mockup_sfx_dir = MOCKUP_DIR / "assets" / "sfx"
    branding_sfx_dir = ROOT / "branding" / "audio" / "sfx"

    for d in (mockup_sfx_dir, branding_sfx_dir):
        wav = d / "whoosh.wav"
        mp3 = d / "whoosh.mp3"
        assert wav.is_file(), f"{wav} deve existir"
        assert mp3.is_file(), f"{mp3} deve existir"
        assert wav.stat().st_size > 1000, f"{wav} não deve ser vazio"
        assert mp3.stat().st_size > 1000, f"{mp3} não deve ser vazio"


def test_find_whoosh_sfx_helper():
    """Valida a resolução do SFX whoosh no módulo de render."""
    from scripts.bm_video.render import find_whoosh_sfx
    sfx = find_whoosh_sfx()
    assert sfx is not None, "find_whoosh_sfx deve localizar o arquivo de áudio"
    assert sfx.is_file()


def test_find_portal_transition_times():
    """Valida identificação de momentos de troca de portal a partir de timeline_beats."""
    from scripts.bm_video.render import find_portal_transition_times

    beats = [
        {"kind": "source", "t0": 0.0, "t1": 10.0, "shot": "shot_01.png", "url": "https://g1.com", "titulo": "A"},
        {"kind": "source", "t0": 10.0, "t1": 15.0, "shot": "shot_01.png", "url": "https://g1.com", "titulo": "A", "visual_variant": "portal_zoom"},
        {"kind": "source", "t0": 15.0, "t1": 25.0, "shot": "shot_02.png", "url": "https://folha.com", "titulo": "B"},
        {"kind": "quote", "t0": 25.0, "t1": 30.0, "visual_payload": {"quote": "X"}},
        {"kind": "source", "t0": 30.0, "t1": 40.0, "shot": "shot_03.png", "url": "https://poder360.com", "titulo": "C"},
    ]
    times = find_portal_transition_times(beats)
    # Deve detectar t0=15.0 (mudança de shot_01 para shot_02) e t0=30.0 (mudança para shot_03)
    assert 15.0 in times
    assert 30.0 in times
    assert 0.0 not in times  # Frame zero ignorado


def test_mix_portal_transition_sfx(tmp_path):
    """Valida a mixagem do SFX whoosh em um áudio existente via ffmpeg."""
    import subprocess
    from scripts.bm_video.render import mix_portal_transition_sfx

    dummy_audio = tmp_path / "voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=4", "-c:a", "pcm_s16le", str(dummy_audio)],
        check=True, capture_output=True,
    )
    mixed = mix_portal_transition_sfx(dummy_audio, [1.5], tmp_path, vol=0.18)
    assert mixed.is_file(), "Arquivo mixado com SFX deve ser gerado"
    assert mixed.stat().st_size > 10000


def test_portal_transition_playwright_runtime():
    """Testa no runtime do Playwright se a transição ocorre na mudança de portal e preserva sub-beats."""
    from playwright.sync_api import sync_playwright
    import http.server
    import socketserver
    import threading

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
                
                page.goto(f"http://127.0.0.1:{port}/references/youtube/mockup-browser/mockup-browser.html", wait_until="domcontentloaded")
                page.wait_for_function("() => !!window.VDL_MOCKUP")

                # 1. Frame zero: carga estática
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
                assert res_init["hasRendered"] is True
                assert res_init["hasZoomTween"] is False

                # 2. Mudança de portal: dispara animação de zoom e SFX
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
                assert res_change["hasZoomTween"] is True

                page.wait_for_timeout(800)

                # 3. Sub-beat na mesma matéria: sem reanimar a janela
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
                assert res_subbeat["hasZoomTween"] is False

                browser.close()
        finally:
            httpd.shutdown()
