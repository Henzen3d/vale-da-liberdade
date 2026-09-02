#!/usr/bin/env python3
"""Scraper cirúrgico para o Aos Fatos (aosfatos.org).

Arquitetura do site:
- Plataforma de checagem de fatos e jornalismo investigativo de dados.
- O texto integral da checagem vem no HTML original dentro de ``article`` ou ``.entry-content``.
- Sem paywall comercial, com caixas de apoio financeiro e checagens multimídia.
- O cabeçalho com o logo do Aos Fatos é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_AOSFATOS_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.title',
    'article h1',
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
# JS cirúrgico de limpeza para Aos Fatos
# ---------------------------------------------------------------------------

_CLEANUP_AOSFATOS_JS = """() => {
  const removed = [];

  // 1. Remover banners de apoio e anúncios
  const adSelectors = [
    '[class*="apoio"]',
    '[class*="apoie"]',
    '[id*="google_ads"]',
    '.ad-container',
    '.ads-container',
    '.banner-topo',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .entry-content')) return;
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

  // 3. Tornar o cabeçalho institucional (logo Aos Fatos) estático e visível
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

  // 5. Garantir que parágrafos, fotos e selos de checagem estejam 100% visíveis
  document.querySelectorAll('article *, .entry-content *').forEach(el => {
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

@register("aosfatos.org")
class AosFatosScraper(BaseScraper):
    """Handler cirúrgico para o Aos Fatos."""

    name = "aosfatos"
    domains = ("aosfatos.org",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_AOSFATOS_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners e modais do Aos Fatos."""
        try:
            result = page.evaluate(_CLEANUP_AOSFATOS_JS)
            return {"handler": "aosfatos", **result}
        except Exception as exc:
            return {"handler": "aosfatos", "error": str(exc)[:300]}
