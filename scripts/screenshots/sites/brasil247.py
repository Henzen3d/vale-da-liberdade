#!/usr/bin/env python3
"""Scraper cirúrgico para o Brasil 247 (brasil247.com).

Arquitetura do site:
- CMS WordPress FSE (Full Site Editing) com blocos Gutenberg.
- O texto integral da matéria vem no HTML original (dentro de ``.entry-content`` ou ``article``).
- Banners de anúncios laterais (``[class*="sidebar-shell"]``, ``[class*="sidebar-sticky"]``),
  barra de topo (``#b247-anchor-wrapper``) e popups de newsletter são removidos.
- Foto de destaque (``.wp-block-post-featured-image img``) e autoria são preservadas.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_247_CONTENT_JS = """() => {
  const sels = [
    'h1.wp-block-post-title',
    'h1',
    '.entry-content',
    'article',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Brasil 247
# ---------------------------------------------------------------------------

_CLEANUP_247_JS = """() => {
  const removed = [];

  // 1. Remover barras de anúncios, popups, sidebars pesadas e modais
  const adSelectors = [
    '#b247-anchor-wrapper',
    '.b247-sidebar-shell',
    '.b247-sidebar-sticky-group',
    '#b247-mobile-deck',
    '#b247-video-overlay',
    '#b247-search-modal',
    '#b247-newsletter-modal',
    '.jetpack-instant-search',
    '.tbl-em-backdrop',
    '[class*="banner"]',
    '[class*="ad-"]',
    '[class*="adv"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '#onetrust-banner-sdk',
    '.banner-lgpd',
    '.b247-newsletter-form',
    '.b247-support-box',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o artigo, título ou foto principal
      if (el.querySelector('article, h1, .wp-block-post-featured-image, .entry-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Configurar cabeçalho como estático para não sobrepor o H1
  document.querySelectorAll('.b247-header-brand, header').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 3. Forçar carregamento das imagens da matéria (desativa lazy loading)
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  // 4. Destravar scroll no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 5. Garantir que o texto da matéria e imagens estejam visíveis
  document.querySelectorAll('article *, .entry-content *, .wp-block-post-featured-image *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("brasil247.com")
class Brasil247Scraper(BaseScraper):
    """Handler cirúrgico para o Brasil 247."""

    name = "brasil247"
    domains = ("brasil247.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_247_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners e sidebars do Brasil 247."""
        try:
            result = page.evaluate(_CLEANUP_247_JS)
            return {"handler": "brasil247", **result}
        except Exception as exc:
            return {"handler": "brasil247", "error": str(exc)[:300]}
