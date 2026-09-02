#!/usr/bin/env python3
"""Scraper cirúrgico para o Diário do Centro do Mundo / DCM (diariodocentrodomundo.com.br).

Arquitetura do site:
- CMS WordPress focado em notícias políticas e artigos de opinião.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.entry-content`` ou ``.td-post-content``.
- Sem paywall rígido, mas com:
  - Banners de anúncios laterais e entre parágrafos (tema tagDiv/Newspaper)
  - Popups de apoio/newsletter e avisos LGPD
- O cabeçalho com a marca/logo do DCM é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_DCM_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.post-title',
    'h1.title',
    'article h1',
    '.entry-content',
    '.td-post-content',
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
# JS cirúrgico de limpeza para DCM
# ---------------------------------------------------------------------------

_CLEANUP_DCM_JS = """() => {
  const removed = [];

  // 1. Remover banners de anúncios (tagDiv rec boxes, leaderboards e sidebars)
  const adSelectors = [
    '.td-a-rec',
    '.td-g-rec',
    '.td-header-rec-wrap',
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
      if (el.querySelector('article, h1, .entry-content, .td-post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modais de apoio, popups e avisos de cookies
  const modalSelectors = [
    '.td-popup',
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.c-push-notification',
  ];

  modalSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo DCM) estático e visível
  document.querySelectorAll('header, .header, .site-header, .td-header-template-wrap, nav').forEach(el => {
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
  document.querySelectorAll('article *, .entry-content *, .td-post-content *').forEach(el => {
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

@register("diariodocentrodomundo.com.br")
class DcmScraper(BaseScraper):
    """Handler cirúrgico para o Diário do Centro do Mundo (DCM)."""

    name = "dcm"
    domains = ("diariodocentrodomundo.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_DCM_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e popups do DCM."""
        try:
            result = page.evaluate(_CLEANUP_DCM_JS)
            return {"handler": "dcm", **result}
        except Exception as exc:
            return {"handler": "dcm", "error": str(exc)[:300]}
