#!/usr/bin/env python3
"""Scraper cirúrgico para a Quaest Consultoria e Pesquisa (quaest.com.br).

Arquitetura do site:
- Site institucional e de publicações de pesquisas de opinião pública e mercado.
- O texto e gráficos das pesquisas vêm no HTML original dentro de ``article``, ``main`` ou ``.entry-content``.
- Sem paywall, com foco em relatórios e gráficos.
- O cabeçalho institucional com o logo da Quaest é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_QUAEST_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article h1',
    'main h1',
    '.entry-content',
    'article',
    'main',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Quaest
# ---------------------------------------------------------------------------

_CLEANUP_QUAEST_JS = """() => {
  const removed = [];

  // 1. Remover modais de contato e avisos de cookies
  const modalSelectors = [
    '.modal-backdrop',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.floating-bar',
  ];

  modalSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Tornar o cabeçalho institucional (logo Quaest) estático e visível
  document.querySelectorAll('header, .header, .site-header, nav').forEach(el => {
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

  // 4. Forçar imagens da matéria com eager loading
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

@register("quaest.com.br")
class QuaestScraper(BaseScraper):
    """Handler cirúrgico para a Quaest."""

    name = "quaest"
    domains = ("quaest.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera a pesquisa carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_QUAEST_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de overlays da Quaest."""
        try:
            result = page.evaluate(_CLEANUP_QUAEST_JS)
            return {"handler": "quaest", **result}
        except Exception as exc:
            return {"handler": "quaest", "error": str(exc)[:300]}
