#!/usr/bin/env python3
"""Scraper cirúrgico para o Portal Metrópoles (metropoles.com).

Arquitetura do site:
- CMS WordPress com tema customizado de alta velocidade.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.single-content``, ``.c-article__content`` ou ``.entry-content``.
- Sem paywall rígido, mas com presença de:
  - Banners publicitários no topo, laterais e inseridos entre parágrafos
  - Widgets de recomendação (Taboola)
  - Barra de compartilhamento flutuante e modais de newsletter/push
- O cabeçalho com a marca/logo do Metrópoles é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_METROPOLES_CONTENT_JS = """() => {
  const sels = [
    'h1.c-article__title',
    'h1.title',
    'h1.entry-title',
    'article h1',
    '.single-content',
    '.c-article__content',
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
# JS cirúrgico de limpeza para Metrópoles
# ---------------------------------------------------------------------------

_CLEANUP_METROPOLES_JS = """() => {
  const removed = [];

  // 1. Remover banners de topo, anúncios in-content, leaderboards e sidebars
  const adSelectors = [
    '.c-header-ad',
    '.c-ad-top',
    '.c-leaderboard',
    '.ad-container',
    '.ads-container',
    '[class*="c-ad"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.publicidade',
    '[class*="publicidade"]',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '#taboola-mid-article-thumbnails',
    '.c-banner-materia',
    '.materia-publicidade',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .single-content, .c-article__content, .entry-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modais, popups, newsletter e barras de consentimento LGPD
  const modalSelectors = [
    '.c-newsletter-modal',
    '.c-push-notification',
    '.c-modal',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.lgpd-consent',
    '.c-floating-share',
    '.c-share-bar--floating',
    '.c-fixed-bar',
    '.c-bottom-ad',
    '.c-footer-ad',
    '.c-floating-video',
  ];

  modalSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo Metrópoles) estático e visível
  document.querySelectorAll('header, .c-header, .site-header, .header-metropoles, nav').forEach(el => {
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

  // 5. Garantir que parágrafos, fotos e assinaturas estejam 100% visíveis
  document.querySelectorAll('article *, .single-content *, .c-article__content *, .entry-content *').forEach(el => {
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

@register("metropoles.com")
class MetropolesScraper(BaseScraper):
    """Handler cirúrgico para o Metrópoles."""

    name = "metropoles"
    domains = ("metropoles.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo do Metrópoles carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_METROPOLES_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e barras flutuantes do Metrópoles."""
        try:
            result = page.evaluate(_CLEANUP_METROPOLES_JS)
            return {"handler": "metropoles", **result}
        except Exception as exc:
            return {"handler": "metropoles", "error": str(exc)[:300]}
