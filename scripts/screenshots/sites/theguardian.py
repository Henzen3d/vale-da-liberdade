#!/usr/bin/env python3
"""Scraper cirúrgico para o The Guardian (theguardian.com).

Arquitetura do site:
- CMS Guardian Frontend com renderização rápida e tipografia de alto nível.
- O texto integral da matéria vem no HTML dentro de ``article``, ``div[data-gu-name="body"]`` ou ``.content__article-body``.
- Sem paywall comercial, mas com:
  - Banners pesados de apoio ao leitor (Epic support banners, ``[data-component="reader-revenue-epic"]``)
  - Modais de consentimento de privacidade GDPR/UK
- O cabeçalho institucional com a marca/logo do The Guardian é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_GUARDIAN_CONTENT_JS = """() => {
  const sels = [
    'h1[data-gu-name="headline"]',
    'h1.content__headline',
    'article h1',
    'div[data-gu-name="body"]',
    '.content__article-body',
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
# JS cirúrgico de limpeza para The Guardian
# ---------------------------------------------------------------------------

_CLEANUP_GUARDIAN_JS = """() => {
  const removed = [];

  // 1. Remover banners de contribuição (Epic banners, reader revenue) e modais GDPR
  const adSelectors = [
    '[data-component="reader-revenue-epic"]',
    '[data-component="support-banner"]',
    '.site-message',
    '.site-message--banner',
    '.site-message--support',
    '[class*="contributions-banner"]',
    '[class*="reader-revenue"]',
    '[id*="dfp-ad"]',
    '[data-name="ad-slot"]',
    '[id*="google_ads"]',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, div[data-gu-name="body"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Tornar o cabeçalho institucional (logo The Guardian) estático e visível
  document.querySelectorAll('header, [data-component="header"], .dcr-header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 3. Destravar scroll, alturas e overflow no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 4. Garantir que parágrafos, fotos e legendas estejam 100% visíveis
  document.querySelectorAll('article *, div[data-gu-name="body"] *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 5. Forçar imagens da matéria com eager loading
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

@register("theguardian.com")
class GuardianScraper(BaseScraper):
    """Handler cirúrgico para o The Guardian."""

    name = "theguardian"
    domains = ("theguardian.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_GUARDIAN_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners de apoio e anúncios do The Guardian."""
        try:
            result = page.evaluate(_CLEANUP_GUARDIAN_JS)
            return {"handler": "theguardian", **result}
        except Exception as exc:
            return {"handler": "theguardian", "error": str(exc)[:300]}
