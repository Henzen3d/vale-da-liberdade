#!/usr/bin/env python3
"""Scraper cirúrgico para a CartaCapital (cartacapital.com.br).

Arquitetura do site:
- CMS WordPress VIP com matérias e colunas políticas/econômicas.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.entry-content`` ou ``.article-content``.
- Paywall/Assinatura:
  - Modais de incentivo à assinatura e overlays de paywall (``.modal-assine``, ``[class*="paywall"]``)
  - Desfoque/blur ou restrição de altura em parágrafos para não assinantes
- Ads & Overlays:
  - Banners de publicidade no topo e laterais
  - Popups de newsletter e avisos LGPD
- O cabeçalho institucional com o logo vermelho da CartaCapital é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_CARTACAPITAL_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.title',
    'article h1',
    '.entry-content',
    '.article-content',
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
# JS cirúrgico de limpeza para CartaCapital
# ---------------------------------------------------------------------------

_CLEANUP_CARTACAPITAL_JS = """() => {
  const removed = [];

  // 1. Remover modais e barreiras de assinatura/paywall
  const paywallSelectors = [
    '.modal-assine',
    '.c-subscribe-wall',
    '[class*="paywall"]',
    '[id*="paywall"]',
    '[class*="assine-para-ler"]',
    '.barrier-wall',
    '.subscribe-overlay',
    '.modal-backdrop',
    '.ReactModal__Overlay',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .entry-content, .article-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover banners de anúncios e widgets de recomendação
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '.ad-container',
    '.ads-container',
    '.banner-topo',
    '.taboola-container',
    '.outbrain-container',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .entry-content, .article-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras flutuantes e botões sticky
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

  // 4. Tornar o cabeçalho institucional (logo CartaCapital) estático e visível
  document.querySelectorAll('header, .header, .site-header, nav').forEach(el => {
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
  document.querySelectorAll('article *, .entry-content *, .article-content *').forEach(el => {
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

@register("cartacapital.com.br")
class CartaCapitalScraper(BaseScraper):
    """Handler cirúrgico para a CartaCapital."""

    name = "cartacapital"
    domains = ("cartacapital.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_CARTACAPITAL_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, anúncios e popups da CartaCapital."""
        try:
            result = page.evaluate(_CLEANUP_CARTACAPITAL_JS)
            return {"handler": "cartacapital", **result}
        except Exception as exc:
            return {"handler": "cartacapital", "error": str(exc)[:300]}
