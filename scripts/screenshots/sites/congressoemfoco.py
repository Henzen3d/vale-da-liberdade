#!/usr/bin/env python3
"""Scraper cirúrgico para o Congresso em Foco (congressoemfoco.com.br, congressoemfoco.uol.com.br).

Arquitetura do site:
- CMS focado em cobertura legislativa, Congresso Nacional e política brasileira.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.entry-content`` ou ``.post-content``.
- Sem paywall rígido, com banners de publicidade e prêmio Congresso em Foco.
- O cabeçalho com o logo do Congresso em Foco é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_CONGRESSO_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.title',
    'article h1',
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
# JS cirúrgico de limpeza para Congresso em Foco
# ---------------------------------------------------------------------------

_CLEANUP_CONGRESSO_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade, barra UOL se presente e sidebars
  const adSelectors = [
    '#barrauol',
    '.barrauol',
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

  // 2. Remover barras flutuantes e modais de cookies LGPD
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

  // 3. Tornar o cabeçalho institucional (logo Congresso em Foco) estático e visível
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
  document.querySelectorAll('article *, .entry-content *, .post-content *').forEach(el => {
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

@register("congressoemfoco.com.br", "congressoemfoco.uol.com.br")
class CongressoEmFocoScraper(BaseScraper):
    """Handler cirúrgico para o Congresso em Foco."""

    name = "congressoemfoco"
    domains = ("congressoemfoco.com.br", "congressoemfoco.uol.com.br")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_CONGRESSO_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios do Congresso em Foco."""
        try:
            result = page.evaluate(_CLEANUP_CONGRESSO_JS)
            return {"handler": "congressoemfoco", **result}
        except Exception as exc:
            return {"handler": "congressoemfoco", "error": str(exc)[:300]}
