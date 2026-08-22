from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_capture import should_block_resource  # noqa: E402


def test_blocks_folha_paywall_script():
    assert should_block_resource("https://paywall.folha.uol.com.br/wall.js")
    assert should_block_resource("https://cdn.tinypass.com/api/tinypass.min.js")


def test_allows_article_assets():
    assert not should_block_resource(
        "https://www1.folha.uol.com.br/colunas/monicabergamo/2026/08/lula.shtml"
    )
    assert not should_block_resource("https://www.cnnbrasil.com.br/politica/foo/")
    assert not should_block_resource("https://f.i.uol.com.br/fotografia/foto.jpg")
