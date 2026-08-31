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


def clip_payload(
    clip: dict,
    episode_title: str = "",
    date: str = "",
    kind: str = "bm",
    subtitle: str | None = None,
    ticker: list[str] | str | None = None,
) -> dict:
    veiculo = (clip.get("veiculo") or host_of(clip.get("url") or "") or "FONTE").strip()
    host = host_of(clip.get("url") or "")
    title = (clip.get("line") or clip.get("titulo") or episode_title or clip.get("quadro") or "").strip()
    if len(title) > 115:
        title = title[:112].rstrip() + "…"
    bm = kind != "daily"
    sub = (subtitle or clip.get("subhead") or clip.get("subtitulo") or clip.get("submanchete") or clip.get("linha_fina") or clip.get("resumo") or "").strip()
    if len(sub) > 98:
        sub = sub[:95].rstrip() + "…"
    if isinstance(ticker, list):
        ticker_s = " | ".join(t.strip() for t in ticker if t and str(t).strip())
    elif ticker:
        ticker_s = str(ticker)
    else:
        ticker_s = title
    return {
        "preset": "vdl-brasil-mundo" if bm else "vdl-diario",
        "eyebrow": "VALE DA LIBERDADE • BRASIL & MUNDO" if bm else "VALE DA LIBERDADE • DIÁRIO REGIONAL",
        "title": title.upper() if title else veiculo.upper(),
        "subtitle": sub,
        "tag": "BRASIL & MUNDO" if bm else "VALE DA LIBERDADE",
        "live": "ANÁLISE" if bm else "DIÁRIO",
        "date": date or "",
        "showLive": "1",
        "ticker": ticker_s,
        "tickerSpeed": "55",
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
        "tickerSpeed": str(payload.get("tickerSpeed") or "55"),
    }
    return ENGINE.resolve().as_uri() + "?" + urlencode(q, quote_via=quote)


def date_from_audio(audio: str) -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", audio or "")
    return m.group(1) if m else ""


TICKER_PX_S = 55
WIPE_S = 1.7


def render_lower_third(dest: Path, payload: dict, seconds: float = 14.0) -> Path:
    """Grava o overlay OBS em fundo verde. Corta a entrada e deixa o ticker andando."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    from playwright.sync_api import sync_playwright

    url = overlay_url(payload)
    raw = dest.with_name(dest.stem + "_raw.webm")
    speed = int(payload.get("tickerSpeed") or TICKER_PX_S)
    cycle_s = 28.0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(dest.parent),
            record_video_size={"width": W, "height": H},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        # Não zerar --lt-layer-gap (o motor usa 7px). Pinta o vão pra o key não furar.
        page.add_style_tag(
            content=(
                "html,body,.obs-stage{background:#00ff00 !important;}"
                ".lt-bottom-layer{"
                "box-shadow:0 calc(-1 * var(--lt-layer-gap,7px)) 0 0 #0b0c0e,"
                "0 4px 12px rgba(0,0,0,.4) !important;}"
                ".lt-ticker-scroll{backface-visibility:hidden;"
                "transform:translate3d(0,0,0);}"
            )
        )
        page.wait_for_timeout(400)
        try:
            cycle_s = float(
                page.evaluate(
                    """async (speed) => {
                      if (!window.engine) return 28;
                      const items = window.engine.currentData.ticker;
                      if (Array.isArray(items) && items.length) window.engine.setTicker(items, speed);
                      window.engine.animateIn();
                      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                      const el = document.querySelector('#ltTickerScroll');
                      if (!el) return 28;
                      const n = parseFloat(getComputedStyle(el).animationDuration);
                      return Number.isFinite(n) && n > 6 ? n : 28;
                    }""",
                    speed,
                )
            )
        except Exception:
            pass
        # 1 ciclo completo depois do wipe — o ffmpeg loopa sem salto no ticker
        hold = WIPE_S + 0.35 + max(cycle_s, 8.0)
        hold = max(hold, float(seconds))
        page.wait_for_timeout(int(hold * 1000))
        page.close()
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    if not video or not Path(video).exists():
        raise RuntimeError("lower-third: vídeo não gerado")
    loop_t = max(8.0, min(float(cycle_s), 90.0))
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(WIPE_S), "-i", str(video),
            "-t", f"{loop_t:.3f}", "-an", "-c:v", "libvpx", "-crf", "18", "-b:v", "0",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    Path(video).unlink(missing_ok=True)
    raw.unlink(missing_ok=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"lower-third trim falhou: {(r.stderr or '')[-400:]}")
    return dest


def overlay_filter() -> str:
    # 444 + blend alto: cantos arredondados viram alpha, não dente de serra.
    # Sem tpad/clone — o compose faz -stream_loop no L3 pra o ticker continuar.
    return (
        f"[1:v]format=yuva444p,colorkey=0x{GREEN}:0.10:0.22,"
        f"despill=type=green:mix=0.45:expand=0,format=rgba[l3];"
        f"[0:v][l3]overlay=0:0:shortest=1,format=yuv420p"
    )
