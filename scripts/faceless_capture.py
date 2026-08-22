#!/usr/bin/env python3
"""Captura um clipe curto de scroll por URL (Playwright). PNG só no fallback."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
COOKIE_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button#onetrust-accept-btn-handler",
    ".banner-lgpd-consent__accept",
    "button.banner-lgpd-consent__accept",
    "button:has-text('OK')",
    "button:has-text('Ok')",
    "button:has-text('Aceitar')",
    "button:has-text('Aceito')",
    "button:has-text('Concordar')",
    "button:has-text('Accept')",
    "button:has-text('Agree')",
    "[data-testid='cookie-policy-dialog-accept-button']",
)
# Scripts de overlay/paywall que rodam DEPOIS do HTML da matéria já ter chegado.
BLOCK_RESOURCE_HOSTS = (
    "paywall.folha.uol.com.br",
    "cdn.tinypass.com",
    "www.tinypass.com",
    "checkout.tinypass.com",
    "experience.piano.io",
    "buy.tinypass.com",
)
CLEANUP_CSS = """
.banner-lgpd-consent,
.banner-lgpd-consent__accept,
.j-paywall,
.c-subscribe-wall,
#onetrust-banner-sdk,
#onetrust-consent-sdk,
.fc-consent-root,
[id*="cookie-banner"],
[class*="cookie-banner"],
[class*="CookieBanner"] {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
html, body { overflow: auto !important; position: static !important; }
"""


def should_block_resource(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in BLOCK_RESOURCE_HOSTS)


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _luma_stdev(path: Path) -> float:
    try:
        from PIL import Image
    except ImportError:
        return 99.0
    im = Image.open(path).convert("L").resize((64, 36))
    return float(statistics.pstdev(im.getdata()))


def _dismiss_cookies(page) -> None:
    for sel in COOKIE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=800)
                page.wait_for_timeout(400)
                return
        except Exception:
            continue
    try:
        btn = page.get_by_role("button", name=re.compile(r"^(OK|Ok|Aceitar|Aceito)$"))
        if btn.count():
            btn.first.click(timeout=800)
            page.wait_for_timeout(400)
    except Exception:
        pass


def _hide_overlays(page) -> None:
    page.add_style_tag(content=CLEANUP_CSS)
    page.evaluate(
        """() => {
          const skip = new Set([document.documentElement, document.body]);
          document.querySelectorAll('div,aside,section').forEach(el => {
            if (skip.has(el)) return;
            const t = (el.innerText || '').slice(0, 240).toLowerCase();
            if (!t) return;
            const st = getComputedStyle(el);
            const fixed = st.position === 'fixed' || st.position === 'sticky';
            const cookieish = t.includes('cookie') && (t.includes('ok') || t.includes('aceit'));
            const payish = t.includes('exclusiv') && t.includes('assinant');
            const adgate = t.includes('caro leitor') || t.includes('após o anúncio') || t.includes('apos o anuncio');
            if (!fixed && !cookieish && !adgate) return;
            if (!cookieish && !payish && !adgate && !fixed) return;
            if (!cookieish && !payish && !adgate) return;
            const tooBig = el.offsetHeight > innerHeight * 0.92 && el.offsetWidth > innerWidth * 0.92;
            if (tooBig && !fixed) return;
            el.style.setProperty('display', 'none', 'important');
          });
          document.documentElement.style.overflow = 'auto';
          if (document.body) document.body.style.overflow = 'auto';
        }"""
    )


def plan_scroll(
    total_s: float,
    article_bottom: float,
    footer_top: float | None,
    viewport_h: float,
    title_y: float = 0.0,
) -> tuple[float, float]:
    """Quanto tempo ficar no topo e até onde rolar (px), sem entrar no rodapé."""
    hold_s = max(2.5, min(total_s * 0.68, total_s - 1.0))
    limit = article_bottom
    if footer_top is not None and footer_top > 0:
        limit = min(limit, footer_top - 48)
    # só um nibble abaixo do título — o loop do vídeo recomeça no início
    cap = max(0.0, title_y) + viewport_h * 0.42
    max_y = max(0.0, min(limit - viewport_h * 0.88, cap))
    return hold_s, max_y


ARTICLE_METRIC_JS = """() => {
  const sels = [
    'article', '.c-news__body', '.news__content', '[itemprop="articleBody"]',
    '.content-text', 'main article', 'main'
  ];
  let el = null;
  for (const s of sels) { el = document.querySelector(s); if (el) break; }
  const footer = document.querySelector('footer, [role="contentinfo"], .c-footer, #footer');
  const h1 = document.querySelector('h1');
  let relatedY = null;
  for (const h of document.querySelectorAll('h2, h3, h4')) {
    const t = (h.innerText || '').toLowerCase();
    if (/not[ií]cias relacionadas|t[óo]picos|leia tamb[eé]m|mais lidas|coment[aá]rios/.test(t)) {
      relatedY = h.getBoundingClientRect().top + window.scrollY;
      break;
    }
  }
  const bottomEl = el || h1;
  const articleBottom = bottomEl
    ? bottomEl.getBoundingClientRect().bottom + window.scrollY
    : document.body.scrollHeight * 0.42;
  let footerTop = footer ? (footer.getBoundingClientRect().top + window.scrollY) : null;
  if (relatedY != null) footerTop = footerTop == null ? relatedY : Math.min(footerTop, relatedY);
  const titleY = (h1 || el)
    ? ((h1 || el).getBoundingClientRect().top + window.scrollY)
    : 0;
  return {articleBottom, footerTop, vh: window.innerHeight, titleY};
}"""


def _slow_scroll(page, seconds: float) -> None:
    metrics = page.evaluate(ARTICLE_METRIC_JS)
    hold_s, max_y = plan_scroll(
        seconds,
        float(metrics.get("articleBottom") or 0),
        metrics.get("footerTop"),
        float(metrics.get("vh") or 1080),
        float(metrics.get("titleY") or 0),
    )
    title_y = max(0.0, float(metrics.get("titleY") or 0) - 72)
    page.evaluate(f"window.scrollTo(0, {title_y})")
    page.wait_for_timeout(int(hold_s * 1000))
    if max_y <= title_y + 40:
        page.wait_for_timeout(int(max(0.0, seconds - hold_s) * 1000))
        return
    move_s = max(1.0, seconds - hold_s)
    steps = max(4, int(move_s * 2))
    delta = (max_y - title_y) / steps
    y = title_y
    for _ in range(steps):
        y = min(max_y, y + delta)
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(int(1000 * move_s / steps))


def capture_one(url: str, dest: Path, scroll_s: float, timeout_ms: int) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    shot = dest / "shot.png"
    rec = dest / "scroll.webm"
    result = {
        "url": url,
        "ok": False,
        "http_status": None,
        "path": None,
        "shot": None,
        "error": None,
        "kind": None,
    }
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except Exception as e:
        result["error"] = f"import: {e}"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport=DEFAULT_VIEWPORT,
                locale="pt-BR",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
                record_video_dir=str(dest),
                record_video_size=DEFAULT_VIEWPORT,
            )
            ctx.route(
                "**/*",
                lambda route: route.abort()
                if should_block_resource(route.request.url)
                else route.continue_(),
            )
            ctx.add_init_script(f"() => {{ const s=document.createElement('style'); s.textContent={CLEANUP_CSS!r}; document.documentElement.appendChild(s); }}")
            page = ctx.new_page()
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            result["http_status"] = resp.status if resp else None
            page.wait_for_timeout(1500)
            _dismiss_cookies(page)
            _hide_overlays(page)
            page.wait_for_timeout(400)
            try:
                metrics = page.evaluate(ARTICLE_METRIC_JS)
                title_y = max(0.0, float(metrics.get("titleY") or 0) - 72)
                page.evaluate(f"window.scrollTo(0, {title_y})")
            except Exception:
                pass
            page.wait_for_timeout(300)
            body = ""
            try:
                body = page.evaluate("document.body ? document.body.innerText.slice(0, 400) : ''")
            except Exception:
                body = ""
            blocked = result["http_status"] in {401, 403} or "403 Forbidden" in (body or "")
            page.screenshot(path=str(shot), type="png")
            result["shot"] = str(shot)
            if not blocked:
                _slow_scroll(page, scroll_s)
            page.close()
            video_src = None
            try:
                video_src = page.video.path() if page.video else None
            except Exception:
                video_src = None
            ctx.close()
            browser.close()
            if video_src and Path(video_src).exists() and Path(video_src).stat().st_size > 10_000:
                Path(video_src).replace(rec)
                result["path"] = str(rec)
                result["kind"] = "scroll"
            elif shot.exists():
                result["path"] = str(shot)
                result["kind"] = "shot"
            if blocked:
                result["error"] = f"blocked status={result['http_status']}"
                result["ok"] = False
            elif shot.exists() and _luma_stdev(shot) < 15:
                result["error"] = "blank-or-error-page"
                result["ok"] = False
            else:
                result["ok"] = bool(result["path"])
    except Exception as e:
        result["error"] = str(e)[:300]
        if shot.exists():
            result["shot"] = str(shot)
            result["path"] = result["path"] or str(shot)
            result["kind"] = result["kind"] or "shot"
    return result


def capture_timeline(timeline_path: Path, limit: int | None, scroll_s: float, force: bool) -> Path:
    data = json.loads(timeline_path.read_text(encoding="utf-8"))
    dest_root = timeline_path.parent / "captures"
    dest_root.mkdir(parents=True, exist_ok=True)
    urls: list[str] = []
    seen: set[str] = set()
    for c in data.get("clips") or []:
        u = c.get("url")
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    if limit:
        urls = urls[:limit]
    index_path = dest_root / "index.json"
    prev = {}
    if index_path.exists() and not force:
        try:
            prev = {r["url"]: r for r in json.loads(index_path.read_text(encoding="utf-8")).get("items", [])}
        except Exception:
            prev = {}
    items = []
    for i, url in enumerate(urls, 1):
        if url in prev and prev[url].get("ok") and not force:
            print(f"[{i}/{len(urls)}] reuse {url}")
            items.append(prev[url])
            continue
        print(f"[{i}/{len(urls)}] capture {url}")
        rec = capture_one(url, dest_root / url_key(url), scroll_s=scroll_s, timeout_ms=45000)
        print(f"    ok={rec['ok']} kind={rec['kind']} err={rec['error']}")
        items.append(rec)
        time.sleep(0.4)
    payload = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": items}
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in items if r.get("ok"))
    print(f"✅ captures {ok}/{len(items)} → {index_path}")
    return index_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Captura scroll das fontes")
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--scroll-seconds", type=float, default=12.0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    capture_timeline(Path(args.timeline), args.limit, args.scroll_seconds, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
