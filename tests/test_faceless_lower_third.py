from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_lower_third import clip_copy, overlay_filter, template_url  # noqa: E402


def test_clip_copy_uses_veiculo_and_host():
    k, line, src = clip_copy(
        {"veiculo": "Folha", "url": "https://www1.folha.uol.com.br/colunas/x.shtml", "quadro": "abertura"},
        episode_title="Lula liga para Trump",
    )
    assert k == "FOLHA"
    assert line == "Lula liga para Trump"
    assert src == "folha.uol.com.br"


def test_template_url_points_at_branding_html():
    url = template_url("CNN BRASIL", "Reunião", "cnnbrasil.com.br")
    assert url.startswith("file://")
    assert "lower-third/index.html?" in url
    assert "kicker=CNN%20BRASIL" in url


def test_overlay_filter_uses_chromakey():
    f = overlay_filter()
    assert "colorkey=0x00ff00" in f
    assert "overlay=0:0" in f
