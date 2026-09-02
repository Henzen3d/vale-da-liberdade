#!/usr/bin/env python3
"""Scraper cirúrgico para a Revista Oeste (revistaoeste.com).

Arquitetura do site:
- CMS WordPress focado em reportagens, artigos de opinião e colunas exclusivas.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.entry-content`` ou ``.post-content``.
- Paywall/Assinatura:
  - Modais de assinatura e incentivo para ser assinante (``.modal-assine``, banners de bloqueio)
  - Desfoque/blur ou restrição de altura em parágrafos para não assinantes
- Ads & Overlays:
  - Banners de publicidade no topo e laterais
  - Barras fixas e popups de newsletter
- O cabeçalho com a logo da Revista Oeste é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_OESTE_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.title',
    'h1.post-title',
    'article h1',
    '.entry-content',
    '.post-content',
    '.materia-conteudo',
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
# JS cirúrgico de limpeza para Revista Oeste
# ---------------------------------------------------------------------------

_CLEANUP_OESTE_JS = """() => {
  const removed = [];

  // 1. Remover modais, overlays e barreiras de paywall / assinatura
  const paywallSelectors = [
    '.modal-assine',
    '.modal-paywall',
    '[class*="paywall"]',
    '[id*="paywall"]',
    '[class*="assine-para-ler"]',
    '.barrier-wall',
    '.c-subscribe-wall',
    '.subscribe-overlay',
    '.modal-backdrop',
    '.ReactModal__Overlay',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .entry-content, .post-content, .materia-conteudo')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover banners de anúncios, leaderboards e sidebars de publicidade
  const adSelectors = [
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
      if (el.querySelector('article, h1, .entry-content, .post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras flutuantes e botões sticky
  const floatingSelectors = [
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '.c-push-notification',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Tornar o cabeçalho institucional (logo Oeste) estático e visível
  document.querySelectorAll('header, .header, .site-header, .header-main, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 5. Destravar scroll, alturas e overflow no html e body
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
  document.querySelectorAll('article *, .entry-content *, .post-content *, .materia-conteudo *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.maxHeight && el.style.maxHeight !== 'none') el.style.maxHeight = 'none';
    if (el.style.display === 'none') {
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

@register("revistaoeste.com")
class OesteScraper(BaseScraper):
    """Handler cirúrgico para a Revista Oeste."""

    name = "oeste"
    domains = ("revistaoeste.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo da Revista Oeste carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_OESTE_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, banners e popups da Revista Oeste."""
        try:
            result = page.evaluate(_CLEANUP_OESTE_JS)
            return {"handler": "oeste", **result}
        except Exception as exc:
            return {"handler": "oeste", "error": str(exc)[:300]}
