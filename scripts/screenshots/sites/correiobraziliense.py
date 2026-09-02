#!/usr/bin/env python3
"""Scraper cirúrgico para o Correio Braziliense (correiobraziliense.com.br).

Arquitetura do site:
- CMS dos Diários Associados focado em política e cobertura nacional/DF.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.cb-texto``, ``.cb-materia__texto`` ou ``.entry-content``.
- Paywall/Assinatura:
  - Modais de assinatura Diários Associados / Paywall metered
  - Desfoque/blur ou restrição de altura em parágrafos
- Ads & Overlays:
  - Banners de publicidade no topo (leaderboard) e laterais
  - Banners LGPD e push notifications
- O cabeçalho institucional com o logo do Correio Braziliense é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_CB_CONTENT_JS = """() => {
  const sels = [
    'h1.cb-title',
    'h1.entry-title',
    'h1.title',
    'article h1',
    '.cb-texto',
    '.cb-materia__texto',
    '.entry-content',
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
# JS cirúrgico de limpeza para Correio Braziliense
# ---------------------------------------------------------------------------

_CLEANUP_CB_JS = """() => {
  const removed = [];

  // 1. Remover modais e barreiras de paywall / assinatura
  const paywallSelectors = [
    '.cb-paywall',
    '[class*="paywall"]',
    '[id*="paywall"]',
    '.modal-assine',
    '.c-subscribe-wall',
    '.barrier-wall',
    '.modal-backdrop',
    '.ReactModal__Overlay',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .cb-texto, .cb-materia__texto, .entry-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover anúncios, leaderboards e sidebars
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '.cb-ad',
    '.ad-container',
    '.ads-container',
    '.banner-topo',
    '.taboola-container',
    '.outbrain-container',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .cb-texto, .cb-materia__texto, .entry-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras flutuantes e rodapés fixos
  const floatingSelectors = [
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '.c-push-notification',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Tornar o cabeçalho institucional (logo Correio Braziliense) estático e visível
  document.querySelectorAll('header, .header, .site-header, .cb-header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 5. Destravar scroll, alturas e overflow no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 6. Remover filtros de blur, restrições de max-height ou opacidade nos textos
  document.querySelectorAll('article *, .cb-texto *, .cb-materia__texto *, .entry-content *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.maxHeight && el.style.maxHeight !== 'none') el.style.maxHeight = 'none';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 7. Forçar imagens da matéria com eager loading
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

@register("correiobraziliense.com.br")
class CorreioBrazilienseScraper(BaseScraper):
    """Handler cirúrgico para o Correio Braziliense."""

    name = "correiobraziliense"
    domains = ("correiobraziliense.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_CB_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall e anúncios do Correio Braziliense."""
        try:
            result = page.evaluate(_CLEANUP_CB_JS)
            return {"handler": "correiobraziliense", **result}
        except Exception as exc:
            return {"handler": "correiobraziliense", "error": str(exc)[:300]}
