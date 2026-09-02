#!/usr/bin/env python3
"""Scraper cirúrgico para a Revista Piauí (piaui.uol.com.br).

Arquitetura do site:
- CMS WordPress / Custom com matérias e ensaios de fôlego.
- O texto integral da matéria vem no HTML original.
- Barra UOL (``#barrauol``), banner LGPD (``.banner-lgpd-consent-container``),
  barra de progresso e toolbars flutuantes (``.floating-toolbar``) são removidos.
- Arte/foto de destaque, manchete em caixa alta, subtítulo, autor e primeiros
  parágrafos da reportagem são perfeitamente preservados.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_PIAUI_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article',
    '.materia-conteudo',
    '.c-materia__conteudo',
    'main',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Revista Piauí
# ---------------------------------------------------------------------------

_CLEANUP_PIAUI_JS = """() => {
  const removed = [];

  // 1. Remover barra UOL, banners LGPD, progress bar e toolbars flutuantes
  const adSelectors = [
    '#barrauol',
    '.barrauol-container',
    '.banner-lgpd-consent-container',
    '#progress-bar-container',
    '.floating-toolbar',
    '.search_overlay',
    '.copy-feedback',
    '.backdrop-canvas',
    '.offcanvas-content',
    '[class*="banner"]',
    '[class*="ad-"]',
    '[class*="adv"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '#onetrust-banner-sdk',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o artigo, título ou foto/ilustração
      if (el.querySelector('article, h1, figure, main, .materia-conteudo')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modais e overlays de assinatura/paywall
  const paywallSelectors = [
    '[class*="paywall"]',
    '[id*="paywall"]',
    '[class*="assine"]',
    '[class*="bloqueio"]',
    '.modal-backdrop',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, figure, main, .materia-conteudo')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Garantir que o cabeçalho fique estático no topo
  document.querySelectorAll('header, nav').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 4. Forçar carregamento das ilustrações e fotos da matéria
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
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

  // 6. Garantir que o texto da matéria e imagens estejam visíveis
  document.querySelectorAll('article *, main *, figure *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("piaui.uol.com.br")
class PiauiScraper(BaseScraper):
    """Handler cirúrgico para a Revista Piauí."""

    name = "piaui"
    domains = ("piaui.uol.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_PIAUI_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de barra UOL, banners e overlays da Revista Piauí."""
        try:
            result = page.evaluate(_CLEANUP_PIAUI_JS)
            return {"handler": "piaui", **result}
        except Exception as exc:
            return {"handler": "piaui", "error": str(exc)[:300]}
