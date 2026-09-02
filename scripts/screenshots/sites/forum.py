#!/usr/bin/env python3
"""Scraper cirúrgico para a Revista Fórum (revistaforum.com.br).

Arquitetura do site:
- CMS WordPress com layout responsivo.
- O texto integral da matéria vem no HTML original (dentro de ``article`` ou ``.post-content``).
- Banners de anúncios (``[class*="banner"]``, ``[class*="ad-"]``, ``#fueradepagina``), widgets
  de newsletter e barra lateral são removidos.
- Cabeçalho com logo vermelha "Fórum" é mantido com ``position: relative`` no topo da página.
- Foto de destaque (``.s-heading__img img``) é preservada e carregada com eager loading.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_FORUM_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article',
    '.s-heading__img',
    '.post-content',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Revista Fórum
# ---------------------------------------------------------------------------

_CLEANUP_FORUM_JS = """() => {
  const removed = [];

  // 1. Manter header com position: relative para que a logo absoluta fique ancorada nele
  document.querySelectorAll('header, .header').forEach(el => {
    el.style.setProperty('position', 'relative', 'important');
  });

  // 2. Remover banners de publicidade, popups e scripts de terceiros
  const adSelectors = [
    '#fueradepagina',
    '.tbl-em-backdrop',
    '[class*="banner"]',
    '[class*="ad-"]',
    '[class*="adv"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '#onetrust-banner-sdk',
    '.banner-lgpd',
    '.google-link',
    '[class*="floating"]',
    '[class*="modal"]',
    'aside',
    '.l-sidebar',
    '.sidebar-ad',
    '[class*="newsletter"]',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o artigo, título, logo ou foto principal
      if (el.querySelector('article, h1, .s-heading__img, .logo, .header__logo, .post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Forçar carregamento da logo e fotos da matéria (desativa lazy loading)
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
  document.querySelectorAll('article *, .post-content *, .s-heading__img *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("revistaforum.com.br")
class RevistaForumScraper(BaseScraper):
    """Handler cirúrgico para a Revista Fórum."""

    name = "revistaforum"
    domains = ("revistaforum.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_FORUM_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners e widgets da Revista Fórum."""
        try:
            result = page.evaluate(_CLEANUP_FORUM_JS)
            return {"handler": "revistaforum", **result}
        except Exception as exc:
            return {"handler": "revistaforum", "error": str(exc)[:300]}
