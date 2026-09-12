#!/usr/bin/env python3
"""Scraper cirúrgico para a Jovem Pan (jovempan.com.br).

Arquitetura do site:
- CMS WordPress com tema customizado (42-framework).
- O texto integral e imagens da matéria vêm no HTML dentro de ``article``,
  ``.wp-block-post-content`` e containers de post.
- Os contêineres de anúncio do 42-framework (``wp-block-fortytwo-ads-section``,
  ``fortytwo-ads-bg``, ``fortytwo-ad-fullbleed``) possuem imagem de fundo
  com textura diagonal cinza (``ads-bg.webp``) e alturas fixas reservadas
  (266px no topo, 296px na sidebar). Quando os anúncios externos são bloqueados,
  essas faixas cinzas vazias precisam ser removidas cirurgicamente.
- O cabeçalho institucional com o logotipo da Jovem Pan e o player/ticker
  é mantido no topo.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_JOVEMPAN_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article',
    '.wp-block-post-content',
    '[class*="single-post"]',
    '[class*="entry-content"]',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Jovem Pan
# ---------------------------------------------------------------------------

_CLEANUP_JOVEMPAN_JS = """() => {
  const removed = [];

  // 1. Remover contêineres e blocos de anúncios do 42-framework (faixas cinzas)
  const adSelectors = [
    '[class*="fortytwo-ad"]',
    '[class*="ads-section"]',
    '[class*="ads-bg"]',
    '[data-ad-format]',
    '[id*="leaderboard"]',
    '[id*="quadrado"]',
    '[id*="halfpage"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '#taboola-below-article-thumbnails',
    '[class*="taboola"]',
    '.outbrain-container',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o artigo ou título
      if (el.querySelector('article, h1, .wp-block-post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover avisos de LGPD, cookies e newsletters flutuantes
  const overlaySelectors = [
    '.banner-lgpd',
    '[class*="cookie"]',
    '[id*="cookie"]',
    '#onetrust-banner-sdk',
    '.fc-consent-root',
    '[class*="newsletter-modal"]',
  ];

  overlaySelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Garantir cabeçalho institucional estático e sem sobrepor a manchete
  document.querySelectorAll('header, [role="banner"], [class*="header"]').forEach(el => {
    if (el.querySelector('article, h1')) return;
    el.style.setProperty('position', 'static', 'important');
  });

  // 4. Forçar carregamento das fotos da matéria
  document.querySelectorAll('img').forEach(img => {
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
    img.loading = 'eager';
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  // 5. Destravar scroll no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("jovempan.com.br")
class JovemPanScraper(BaseScraper):
    """Handler cirúrgico para a Jovem Pan."""

    name = "jovempan"
    domains = ("jovempan.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_JOVEMPAN_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios 42-framework, faixas cinzas e overlays da Jovem Pan."""
        try:
            result = page.evaluate(_CLEANUP_JOVEMPAN_JS)
            return {"handler": "jovempan", **result}
        except Exception as exc:
            return {"handler": "jovempan", "error": str(exc)[:300]}
