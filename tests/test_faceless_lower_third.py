from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_lower_third import clip_payload, overlay_filter, overlay_url  # noqa: E402


def test_clip_payload_bm():
    p = clip_payload(
        {"veiculo": "Folha", "url": "https://www1.folha.uol.com.br/colunas/x.shtml"},
        episode_title="Lula liga para Trump",
        date="2026-08-21",
        kind="bm",
    )
    assert p["preset"] == "vdl-brasil-mundo"
    assert p["title"].startswith("LULA LIGA")
    assert "folha.uol.com.br" in p["subtitle"]
    assert p["date"] == "2026-08-21"


def test_overlay_url_points_at_engine():
    url = overlay_url(
        {
            "preset": "vdl-brasil-mundo",
            "title": "TESTE",
            "subtitle": "Folha",
            "eyebrow": "BRASIL",
            "tag": "BRASIL & MUNDO",
            "live": "ANÁLISE",
            "date": "2026-08-21",
            "showLive": "1",
            "ticker": "A | B",
        }
    )
    assert url.startswith("file://")
    assert "Lower-third-engine/obs-overlay.html?" in url
    assert "preset=vdl-brasil-mundo" in url
    assert "title=TESTE" in url


def test_overlay_filter_uses_chromakey():
    f = overlay_filter()
    assert "colorkey=0x00ff00" in f
    assert "overlay=0:0" in f
