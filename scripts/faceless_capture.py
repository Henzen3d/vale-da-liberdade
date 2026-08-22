#!/usr/bin/env python3
"""Captura um clipe curto de scroll por URL (Playwright). PNG só no fallback."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
COOKIE_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "button#onetrust-accept-btn-handler",
    "button:has-text('Aceitar')",
    "button:has-text('Aceito')",
    "button:has-text('Concordar')",
    "button:has-text('Accept')",
    "button:has-text('Agree')",
    "[data-testid='cookie-policy-dialog-accept-button']",
)


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


def _slow_scroll(page, seconds: float) -> None:
    steps = max(6, int(seconds * 3))
    for _ in range(steps):
        page.evaluate("window.scrollBy(0, Math.max(180, window.innerHeight * 0.28))")
        page.wait_for_timeout(int(1000 * seconds / steps))


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
            page = ctx.new_page()
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            result["http_status"] = resp.status if resp else None
            page.wait_for_timeout(2500)
            _dismiss_cookies(page)
            page.wait_for_timeout(800)
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
    ap.add_argument("--scroll-seconds", type=float, default=8.0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    capture_timeline(Path(args.timeline), args.limit, args.scroll_seconds, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
