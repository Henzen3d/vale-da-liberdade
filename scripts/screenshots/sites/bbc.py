#!/usr/bin/env python3
"""Scraper cirúrgico para a BBC (bbc.com, bbc.co.uk).

Arquitetura do site:
- CMS BBC Simorgh / Morph / WebCore com HTML semântico e acessível.
- O texto integral da matéria vem no HTML dentro de ``article[role="main"]``, ``main#main-content`` ou blocos ``[data-component="text-block"]``.
- Sem paywall comercial, mas com:
  - Banners de consentimento de cookies GDPR / LGPD (``#bbcprivacy-modal``, ``#bbccookies-banner``)
  - Promos internas e módulos de "Leia mais"
  - Banners de download de app BBC News
- O cabeçalho institucional (blocos BBC / BBC News) é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_BBC_CONTENT_JS = """() => {
  const sels = [
    'h1#main-heading',
    'h1[data-testid="headline"]',
    'article[role="main"] h1',
    'main h1',
    'article h1',
    'div[data-component="text-block"]',
    'article',
    'h1',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para BBC
# ---------------------------------------------------------------------------

_CLEANUP_BBC_JS = """() => {
  const removed = [];

  // 1. Remover banners e modais de cookies/privacidade GDPR da BBC
  const cookieSelectors = [
    '#bbcprivacy-modal',
    '#bbccookies-banner',
    '#bbccookies-prompt',
    '[data-testid="cookie-banner"]',
    '[data-testid="privacy-banner"]',
    '.bbc-privacy-modal',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  cookieSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover anúncios comerciais (BBC Global/Internacional tem ads) e promoções
  const adSelectors = [
    '[id*="dotcom-ad"]',
    '[class*="ad-slot"]',
    '[class*="ad-container"]',
    '[id*="google_ads"]',
    '.bbccom_slot',
    '[data-testid="ad-slot"]',
    '[data-component="ad-block"]',
    '.taboola-container',
    '.outbrain-container',
    '.app-banner',
    '[data-testid="app-download-banner"]',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, [data-component="text-block"], main#main-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo BBC) estático e visível
  document.querySelectorAll('header, [role="banner"], [data-testid="header"], .bbc-header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 4. Destravar scroll, alturas e overflow no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 5. Garantir que parágrafos, fotos e legendas estejam 100% visíveis
  document.querySelectorAll('article *, main#main-content *, [data-component="text-block"] *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 6. Forçar imagens da matéria com eager loading
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("bbc.com", "bbc.co.uk")
class BbcScraper(BaseScraper):
    """Handler cirúrgico para a BBC (bbc.com e bbc.co.uk)."""

    name = "bbc"
    domains = ("bbc.com", "bbc.co.uk")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo da BBC carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_BBC_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners e cookies da BBC."""
        try:
            result = page.evaluate(_CLEANUP_BBC_JS)
            return {"handler": "bbc", **result}
        except Exception as exc:
            return {"handler": "bbc", "error": str(exc)[:300]}
