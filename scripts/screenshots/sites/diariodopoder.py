#!/usr/bin/env python3
"""Scraper cirúrgico para o Diário do Poder (diariodopoder.com.br).

Arquitetura do site:
- CMS WordPress com tema de notícias (Newspaper / TagDiv).
- O texto integral da matéria vem no HTML dentro de ``article``, ``.td-post-content``, ``.entry-content`` ou ``.post-content``.
- Sem paywall rígido, mas com presença de:
  - Banners de publicidade no topo (header ad), laterais e entre parágrafos (``td-a-rec``)
  - Módulos de recomendação (Taboola / Outbrain)
  - Barras flutuantes de compartilhamento e avisos LGPD
- O cabeçalho com o logo/marca do Diário do Poder é mantido no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_DP_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.td-post-title',
    'h1.title',
    'article h1',
    '.td-post-content',
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
# JS cirúrgico de limpeza para Diário do Poder
# ---------------------------------------------------------------------------

_CLEANUP_DP_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade (tagDiv ad boxes, leaderboards, sidebars)
  const adSelectors = [
    '.td-header-rec-wrap',
    '.td-a-rec',
    '.td-g-rec',
    '.td-ad-container',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.ad-container',
    '.ads-container',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .td-post-content, .entry-content, .post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modais, popups, avisos de cookie e barras flutuantes
  const floatingSelectors = [
    '.td-popup',
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.lgpd-consent',
    '.c-push-notification',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo Diário do Poder) estático e visível
  document.querySelectorAll('header, .header, .site-header, .td-header-template-wrap, .td-main-menu-wrap, nav').forEach(el => {
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
  document.querySelectorAll('article *, .td-post-content *, .entry-content *, .post-content *').forEach(el => {
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

@register("diariodopoder.com.br")
class DiarioDoPoderScraper(BaseScraper):
    """Handler cirúrgico para o Diário do Poder."""

    name = "diariodopoder"
    domains = ("diariodopoder.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo do Diário do Poder carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_DP_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e barras do Diário do Poder."""
        try:
            result = page.evaluate(_CLEANUP_DP_JS)
            return {"handler": "diariodopoder", **result}
        except Exception as exc:
            return {"handler": "diariodopoder", "error": str(exc)[:300]}
