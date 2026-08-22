from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faceless_desktop import desktop_filter, wallpaper_colors, window_box  # noqa: E402


def test_window_leaves_side_margins():
    b = window_box()
    assert b["win_x"] >= 160
    assert b["win_x"] + b["win_w"] <= 1920 - 160
    assert b["pane_y"] == b["win_y"] + b["title_h"]
    assert b["pane_w"] == b["win_w"]


def test_wallpaper_colors_change_with_seed():
    assert wallpaper_colors("folha.uol.com.br") != wallpaper_colors("cnnbrasil.com.br")


def test_desktop_filter_has_three_inputs():
    f = desktop_filter()
    assert "[0:v]" in f and "[1:v]" in f and "[2:v]" in f
    assert "overlay=" in f
