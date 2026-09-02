#!/usr/bin/env python3
"""Scraper cirúrgico para a Revista Veja (veja.abril.com.br).

Arquitetura do site:
- CMS: WordPress VIP / Abril Digital.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.content``, ``.article-content`` ou ``#content``.
- Paywall: Piano/Tinypass e wrappers locais da Editora Abril (modais, overlays com blur/overflow hidden).
- Ads: Banners de topo (leaderboard), anúncios in-content, Taboola/Outbrain e popups de newsletter.
- O cabeçalho com o logo da VEJA é preservado (tornando-o estático para não sobrepor a manchete).
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_VEJA_CONTENT_JS = """() => {
  const sels = [
    'h1.title',
    'h1.article-title',
    'h1.c-article__title',
    'article h1',
    '.article-content',
    '.entry-content',
    '#content',
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
# JS cirúrgico de limpeza para Veja
# ---------------------------------------------------------------------------

_CLEANUP_VEJA_JS = """() => {
  const removed = [];

  // 1. Remover modais, wrappers e overlays de paywall e assinatura (Abril/Piano)
  const paywallSelectors = [
    '#paywall-wrapper',
    '.paywall-wrapper',
    '.paywall',
    '.c-paywall',
    '[data-paywall]',
    '[data-paywall-wrapper]',
    '.piano-offer',
    '[id*="piano"]',
    '[class*="piano-"]',
    '.modal-paywall',
    '.c-subscribe-barrier',
    '.c-offer',
    '.barrier-wall',
    '.assine-banner',
    '[class*="assine-"]',
    '.banner-assine',
    '.newsletter-modal',
    '.c-modal',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .article-content, .entry-content, #content, .content-text')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover anúncios, banners e widgets de publicidade/taboola
  const adSelectors = [
    '.c-ad',
    '[class*="ad-container"]',
    '[class*="ads-container"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.publicidade',
    '[class*="publicidade"]',
    '.advertising',
    '.c-advertising',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '.c-banner-topo',
    '.banner-leaderboard',
    '.materia-banners',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .article-content, .entry-content, #content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras flutuantes, toolbars de compartilhamento e footers fixos
  const floatingSelectors = [
    '.c-floating-bar',
    '.floating-bar',
    '.c-share-bar--floating',
    '.sticky-footer',
    '.c-sticky-banner',
    '.c-push-notification',
    '[class*="newsletter-fixed"]',
    '.c-author-bio--sticky',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Garantir que o cabeçalho institucional (logo Veja) fique estático e visível
  document.querySelectorAll('header, .header, .site-header, .main-header, .c-header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 5. Destravar scroll, alturas e overflow no html, body e containers
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
  document.querySelectorAll('article *, .article-content *, .entry-content *, #content *, .content *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.maxHeight && el.style.maxHeight !== 'none') el.style.maxHeight = 'none';
    if (el.style.display === 'none') {
      // Se não for ad nem script, restaura
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

@register("veja.abril.com.br")
class VejaScraper(BaseScraper):
    """Handler cirúrgico para Veja (Editora Abril)."""

    name = "veja"
    domains = ("veja.abril.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_VEJA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, banners e overlays da Veja."""
        try:
            result = page.evaluate(_CLEANUP_VEJA_JS)
            return {"handler": "veja", **result}
        except Exception as exc:
            return {"handler": "veja", "error": str(exc)[:300]}
