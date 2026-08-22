#!/usr/bin/env python3
"""Renderiza o motor CSS de lower-third (branding/lower-third/index.html) p/ overlay."""
from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
_BRANDING = ROOT / "branding" / "lower-third" / "index.html"
_REF = ROOT / "references" / "faceless" / "lower-third" / "index.html"
TEMPLATE = _BRANDING if _BRANDING.exists() else _REF
W, H = 1920, 1080
GREEN = "00ff00"


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.").removeprefix("www1.")


def clip_copy(clip: dict, episode_title: str = "") -> tuple[str, str, str]:
    kicker = (clip.get("veiculo") or host_of(clip.get("url") or "") or "FONTE").strip()
    line = (clip.get("line") or episode_title or clip.get("quadro") or "").strip()
    if len(line) > 88:
        line = line[:85].rstrip() + "…"
    src = host_of(clip.get("url") or "")
    return kicker.upper(), line, src


def template_url(kicker: str, line: str, src: str) -> str:
    if not TEMPLATE.exists():
        raise FileNotFoundError(TEMPLATE)
    q = f"kicker={quote(kicker)}&line={quote(line)}&src={quote(src)}"
    return TEMPLATE.resolve().as_uri() + "?" + q


def render_lower_third(dest: Path, kicker: str, line: str, src: str, seconds: float = 2.4) -> Path:
    """Grava o HTML animado em fundo verde (chromakey no compose)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    url = template_url(kicker, line, src)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(dest.parent),
            record_video_size={"width": W, "height": H},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(int(max(seconds, 1.6) * 1000))
        page.close()
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    if not video or not Path(video).exists():
        raise RuntimeError("lower-third: vídeo não gerado")
    Path(video).replace(dest)
    return dest


def overlay_filter() -> str:
    # tpad clona o último frame da animação pelo resto do clipe
    return (
        f"[1:v]colorkey=0x{GREEN}:0.18:0.04,format=rgba,"
        f"tpad=stop_mode=clone:stop_duration=600[l3];"
        f"[0:v][l3]overlay=0:0:shortest=1,format=yuv420p"
    )


# html.escape kept imported so callers can sanitize if they inject into HTML later
_ = html
