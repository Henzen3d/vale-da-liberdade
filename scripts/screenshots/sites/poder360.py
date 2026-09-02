#!/usr/bin/env python3
"""Scraper cirúrgico para o Poder360 (poder360.com.br).

Arquitetura do site:
- CMS WordPress VIP focado em jornalismo político e econômico.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.box-text``, ``.entry-content`` ou ``.post-content``.
- Sem paywall rígido, mas com presença de:
  - Banners de publicidade no topo (leaderboard) e entre parágrafos
  - Modais de assinatura de newsletters do Poder360 (Drive, etc.)
  - Barras flutuantes e rodapés de ofertas
- O cabeçalho com a marca/logo do Poder360 é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_PODER360_CONTENT_JS = """() => {
  const sels = [
    'h1.box-title__title',
    'h1.entry-title',
    'h1.title',
    'article h1',
    '.box-text',
    '.entry-content',
    '.post-content',
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
# JS cirúrgico de limpeza para Poder360
# ---------------------------------------------------------------------------

_CLEANUP_PODER360_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade, leaderboards e sidebars
  const adSelectors = [
    '.box-advertising',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.banner-topo',
    '.banner-floating',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .box-text, .entry-content, .post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modais de newsletter/drive, popups de assinatura e banners LGPD
  const modalSelectors = [
    '.modal-newsletter',
    '.c-modal-subscribe',
    '.box-newsletter-fixed',
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '[class*="paywall"]',
    '[class*="piano"]',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  modalSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo Poder360) estático e visível
  document.querySelectorAll('header, .header, .site-header, nav').forEach(el => {
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
  document.querySelectorAll('article *, .box-text *, .entry-content *, .post-content *').forEach(el => {
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

@register("poder360.com.br")
class Poder360Scraper(BaseScraper):
    """Handler cirúrgico para o Poder360."""

    name = "poder360"
    domains = ("poder360.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo do Poder360 carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_PODER360_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e popups do Poder360."""
        try:
            result = page.evaluate(_CLEANUP_PODER360_JS)
            return {"handler": "poder360", **result}
        except Exception as exc:
            return {"handler": "poder360", "error": str(exc)[:300]}
