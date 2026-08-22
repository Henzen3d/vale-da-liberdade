#!/usr/bin/env python3
"""Renderiza o Lower Third Engine (youtube/Lower-third-engine) p/ overlay."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "youtube" / "Lower-third-engine" / "obs-overlay.html"
W, H = 1920, 1080
GREEN = "00ff00"


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.").removeprefix("www1.")


def clip_payload(clip: dict, episode_title: str = "", date: str = "", kind: str = "bm") -> dict:
    veiculo = (clip.get("veiculo") or host_of(clip.get("url") or "") or "FONTE").strip()
    host = host_of(clip.get("url") or "")
    title = (clip.get("line") or episode_title or clip.get("quadro") or "").strip()
    if len(title) > 88:
        title = title[:85].rstrip() + "…"
    bm = kind != "daily"
    return {
        "preset": "vdl-brasil-mundo" if bm else "vdl-diario",
        "eyebrow": "VALE DA LIBERDADE • BRASIL & MUNDO" if bm else "VALE DA LIBERDADE • DIÁRIO REGIONAL",
        "title": title.upper() if title else veiculo.upper(),
        "subtitle": " · ".join(p for p in (veiculo, host) if p),
        "tag": "BRASIL & MUNDO" if bm else "VALE DA LIBERDADE",
        "live": "ANÁLISE" if bm else "DIÁRIO",
        "date": date or "",
        "showLive": "1",
        "ticker": " | ".join(
            t for t in (title, f"FONTE: {veiculo}", host, "VALE DA LIBERDADE") if t
        ),
    }


def overlay_url(payload: dict) -> str:
    if not ENGINE.exists():
        raise FileNotFoundError(ENGINE)
    q = {
        "preset": payload.get("preset") or "vdl-brasil-mundo",
        "eyebrow": payload.get("eyebrow") or "",
        "title": payload.get("title") or "",
        "subtitle": payload.get("subtitle") or "",
        "tag": payload.get("tag") or "",
        "live": payload.get("live") or "",
        "date": payload.get("date") or "",
        "showLive": payload.get("showLive") or "1",
        "ticker": payload.get("ticker") or "",
    }
    return ENGINE.resolve().as_uri() + "?" + urlencode(q, quote_via=quote)


def date_from_audio(audio: str) -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", audio or "")
    return m.group(1) if m else ""


def render_lower_third(dest: Path, payload: dict, seconds: float = 3.2) -> Path:
    """Grava o overlay OBS em fundo verde (chromakey no compose)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    url = overlay_url(payload)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(dest.parent),
            record_video_size={"width": W, "height": H},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.add_style_tag(
            content=(
                "html,body,.obs-stage{background:#00ff00 !important;}"
                ".lt-root{--lt-layer-gap:0px !important;}"
            )
        )
        page.wait_for_timeout(700)
        try:
            page.evaluate("() => { if (window.engine) window.engine.animateIn(); }")
        except Exception:
            pass
        page.wait_for_timeout(int(max(seconds, 2.2) * 1000))
        page.close()
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    if not video or not Path(video).exists():
        raise RuntimeError("lower-third: vídeo não gerado")
    Path(video).replace(dest)
    return dest


def overlay_filter() -> str:
    return (
        f"[1:v]colorkey=0x{GREEN}:0.18:0.04,format=rgba,"
        f"tpad=stop_mode=clone:stop_duration=600[l3];"
        f"[0:v][l3]overlay=0:0:shortest=1,format=yuv420p"
    )
