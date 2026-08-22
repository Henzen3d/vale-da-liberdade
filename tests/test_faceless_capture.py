from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_capture import plan_scroll, should_block_resource  # noqa: E402


def test_blocks_folha_paywall_script():
    assert should_block_resource("https://paywall.folha.uol.com.br/wall.js")
    assert should_block_resource("https://cdn.tinypass.com/api/tinypass.min.js")


def test_allows_article_assets():
    assert not should_block_resource(
        "https://www1.folha.uol.com.br/colunas/monicabergamo/2026/08/lula.shtml"
    )
    assert not should_block_resource("https://www.cnnbrasil.com.br/politica/foo/")
    assert not should_block_resource("https://f.i.uol.com.br/fotografia/foto.jpg")


def test_scroll_holds_top_and_stops_before_footer():
    hold, max_y = plan_scroll(total_s=10.0, article_bottom=2200, footer_top=4000, viewport_h=1080, title_y=400)
    assert hold >= 6.0
    assert max_y <= 400 + 1080 * 0.42 + 1
    hold2, max_y2 = plan_scroll(total_s=8.0, article_bottom=900, footer_top=800, viewport_h=1080, title_y=200)
    assert max_y2 == 0.0
    assert hold2 >= 2.5
