#!/usr/bin/env python3
"""Scraper cirúrgico para o Portal R7 / Record (r7.com, noticias.r7.com, etc.).

Arquitetura do site:
- CMS proprietário do Grupo Record / R7.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.article-content``, ``.news-content`` ou ``.content-text``.
- Sem paywall, mas com presença de:
  - Banners de publicidade pesados (super banners no topo e laterais)
  - Players de vídeo flutuantes (PlayPlus / transmissão ao vivo)
  - Módulos Taboola/Outbrain
- O cabeçalho institucional com o logo do R7 é mantido no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_R7_CONTENT_JS = """() => {
  const sels = [
    'h1.title',
    'h1.news-title',
    'h1.article-title',
    'article h1',
    '.article-content',
    '.news-content',
    '.content-text',
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
# JS cirúrgico de limpeza para R7
# ---------------------------------------------------------------------------

_CLEANUP_R7_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade, leaderboards e sidebars
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '.ad-container',
    '.ads-container',
    '.banner-topo',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '.ad-slot',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .article-content, .news-content, .content-text')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover vídeos flutuantes, popups de app e cookies LGPD
  const floatingSelectors = [
    '.floating-video',
    '.video-floating',
    '.c-app-download',
    '.c-share-bar--floating',
    '.sticky-footer',
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

  // 3. Tornar o cabeçalho institucional (logo R7) estático e visível
  document.querySelectorAll('header, .header, .site-header, .r7-header, nav').forEach(el => {
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
  document.querySelectorAll('article *, .article-content *, .news-content *, .content-text *').forEach(el => {
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

@register("r7.com", "noticias.r7.com", "record.r7.com")
class R7Scraper(BaseScraper):
    """Handler cirúrgico para o Portal R7 / Record."""

    name = "r7"
    domains = ("r7.com", "noticias.r7.com", "record.r7.com")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_R7_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e players flutuantes do R7."""
        try:
            result = page.evaluate(_CLEANUP_R7_JS)
            return {"handler": "r7", **result}
        except Exception as exc:
            return {"handler": "r7", "error": str(exc)[:300]}
