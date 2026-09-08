#!/usr/bin/env python3
"""Scraper para Polymarket (SPA React). Mercado de previsão, não portal de notícia.

O HTML inicial é um shell; odds e título hidratam depois. Sem wait de app
o print sai sem CSS (6lZdp_xTADA).
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


_WAIT_POLY_JS = """() => {
  const text = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ');
  if (text.length < 80) return {found: false};
  const sels = [
    'h1',
    '[data-testid]',
    'main',
    '#__next',
    '#root',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 40 && (el.innerText || '').trim().length > 8) {
      return {found: true, selector: s};
    }
  }
  return {found: text.length > 200};
}"""


_CLEANUP_POLY_JS = """() => {
  const removed = [];
  const sels = [
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '[class*="cookie"]',
    '[class*="Cookie"]',
    '[id*="cookie"]',
    '[class*="modal"]',
    '[role="dialog"]',
  ];
  sels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('h1, main, [data-testid]')) return;
      el.remove();
      removed.push(sel);
    });
  });
  document.querySelectorAll('header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });
  return {removed, count: removed.length};
}"""


@register("polymarket.com")
class PolymarketScraper(BaseScraper):
    """Handler para mercados Polymarket (SPA)."""

    name = "polymarket"
    domains = ("polymarket.com",)

    def wait_for_content(self, page: Any) -> bool:
        for _ in range(20):
            try:
                info = page.evaluate(_WAIT_POLY_JS)
                if info.get("found"):
                    page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
            page.wait_for_timeout(400)
        return super().wait_for_content(page)

    def cleanup(self, page: Any) -> dict:
        try:
            result = page.evaluate(_CLEANUP_POLY_JS)
            return {"handler": "polymarket", **result}
        except Exception as exc:
            return {"handler": "polymarket", "error": str(exc)[:300]}
