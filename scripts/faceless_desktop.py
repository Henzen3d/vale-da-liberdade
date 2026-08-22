#!/usr/bin/env python3
"""Papel de parede + janela de browser em volta da captura já feita."""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
CHROME_HTML = ROOT / "references" / "faceless" / "browser-chrome" / "index.html"
W, H, FPS = 1920, 1080, 30
# janela um pouco menor que a tela — laterais mostram o wallpaper
WIN_W, WIN_H = 1560, 920
WIN_X = (W - WIN_W) // 2
WIN_Y = 56
TITLE_H = 44
PANE_W, PANE_H = WIN_W, WIN_H - TITLE_H
PANE_X, PANE_Y = WIN_X, WIN_Y + TITLE_H


def window_box() -> dict[str, int]:
    return {
        "win_w": WIN_W, "win_h": WIN_H, "win_x": WIN_X, "win_y": WIN_Y,
        "title_h": TITLE_H,
        "pane_w": PANE_W, "pane_h": PANE_H, "pane_x": PANE_X, "pane_y": PANE_Y,
    }


def wallpaper_colors(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    h = hashlib.sha1(seed.encode("utf-8")).digest()
    a = (18 + h[0] % 30, 20 + h[1] % 28, 28 + h[2] % 36)
    b = (40 + h[3] % 50, 28 + h[4] % 36, 22 + h[5] % 40)
    return a, b


def write_wallpaper(dest: Path, seed: str) -> Path:
    from PIL import Image, ImageDraw

    dest.parent.mkdir(parents=True, exist_ok=True)
    c0, c1 = wallpaper_colors(seed)
    im = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(im)
    for y in range(H):
        t = y / max(H - 1, 1)
        rgb = tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=rgb)
    im.save(dest, "PNG")
    return dest


def chrome_url(page_url: str) -> str:
    if not CHROME_HTML.exists():
        raise FileNotFoundError(CHROME_HTML)
    host = urlparse(page_url).hostname or page_url
    shown = page_url if len(page_url) < 90 else host + "/…"
    q = f"url={quote(shown)}&x={WIN_X}&y={WIN_Y}&w={WIN_W}&h={WIN_H}"
    return CHROME_HTML.resolve().as_uri() + "?" + q


def render_chrome_png(dest: Path, page_url: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(chrome_url(page_url), wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(200)
        page.screenshot(path=str(dest), omit_background=True)
        browser.close()
    return dest


def desktop_filter() -> str:
    """[0]=site  [1]=wallpaper  [2]=chrome PNG (alpha)."""
    return (
        f"[1:v]scale={W}:{H},format=yuv420p[wall];"
        f"[0:v]scale={PANE_W}:{PANE_H}:force_original_aspect_ratio=increase,"
        f"crop={PANE_W}:{PANE_H},format=yuv420p[site];"
        f"[wall][site]overlay={PANE_X}:{PANE_Y}[desk];"
        f"[2:v]format=rgba[ch];"
        f"[desk][ch]overlay=0:0,format=yuv420p"
    )
