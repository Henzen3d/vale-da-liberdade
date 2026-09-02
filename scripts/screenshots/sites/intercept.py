#!/usr/bin/env python3
"""Scraper cirúrgico para o The Intercept Brasil (theintercept.com, intercept.com.br).

Arquitetura do site:
- CMS focado em jornalismo investigativo independente.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.ArticleBody`` ou ``.entry-content``.
- Sem paywall comercial, mas com:
  - Banners e popups de captação de doações/apoio recorrente
  - Modais de newsletter e avisos de cookies
- O cabeçalho institucional com o logo do The Intercept é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_INTERCEPT_CONTENT_JS = """() => {
  const sels = [
    'h1.PromoHeadline',
    'h1.entry-title',
    'h1.title',
    'article h1',
    '.ArticleBody',
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
# JS cirúrgico de limpeza para The Intercept
# ---------------------------------------------------------------------------

_CLEANUP_INTERCEPT_JS = """() => {
  const removed = [];

  // 1. Remover banners de doação/fundraising, popups e anúncios
  const adSelectors = [
    '[class*="donation"]',
    '[class*="fundraising"]',
    '[class*="membership"]',
    '.c-newsletter-modal',
    '.newsletter-signup',
    '[id*="google_ads"]',
    '.ad-container',
    '.ads-container',
    '.taboola-container',
    '.outbrain-container',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .ArticleBody, .entry-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover barras flutuantes e modais de cookies LGPD/GDPR
  const floatingSelectors = [
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.c-push-notification',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo Intercept) estático e visível
  document.querySelectorAll('header, .header, .site-header, .InterceptHeader, nav').forEach(el => {
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
  document.querySelectorAll('article *, .ArticleBody *, .entry-content *').forEach(el => {
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

@register("theintercept.com", "intercept.com.br")
class InterceptScraper(BaseScraper):
    """Handler cirúrgico para o The Intercept Brasil."""

    name = "intercept"
    domains = ("theintercept.com", "intercept.com.br")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_INTERCEPT_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners de apoio e anúncios do The Intercept."""
        try:
            result = page.evaluate(_CLEANUP_INTERCEPT_JS)
            return {"handler": "intercept", **result}
        except Exception as exc:
            return {"handler": "intercept", "error": str(exc)[:300]}
