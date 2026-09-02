#!/usr/bin/env python3
"""Scraper cirúrgico para o The New York Times (nytimes.com).

Arquitetura do site:
- CMS NYT Scoop / React SPA com renderização em servidor.
- O texto integral da matéria vem no HTML dentro de ``article``, ``section[name="articleBody"]`` ou ``.StoryBodyCompanionColumn``.
- Paywall/Gateway:
  - Modais de assinatura internacional e gateways (``#gateway-content``, ``[data-testid="expanded-dock"]``, ``[data-testid="sheet-container"]``)
  - Desfoque/blur ou restrição de scroll
- O cabeçalho institucional com a clássica tipografia gótica do The New York Times é mantido no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_NYT_CONTENT_JS = """() => {
  const sels = [
    'h1[data-testid="headline"]',
    'h1.headline',
    'article h1',
    'section[name="articleBody"]',
    '.StoryBodyCompanionColumn',
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
# JS cirúrgico de limpeza para The New York Times
# ---------------------------------------------------------------------------

_CLEANUP_NYT_JS = """() => {
  const removed = [];

  // 1. Remover gateways e modais de paywall/assinatura do NYT
  const paywallSelectors = [
    '#gateway-content',
    '#expanded-dock-wrapper',
    '[data-testid="expanded-dock"]',
    '[data-testid="sheet-container"]',
    '[data-testid="inline-message"]',
    '.css-mcm29f',
    '.dock-bottom',
    '[class*="paywall"]',
    '[class*="gateway"]',
    '.modal-backdrop',
    '.ReactModal__Overlay',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, section[name="articleBody"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover slots de anúncios
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="ad-"]',
    '[data-testid="ad-placeholder"]',
    '.ad-container',
    '.ads-container',
    '.taboola-container',
    '.outbrain-container',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, section[name="articleBody"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar o cabeçalho institucional (logo The New York Times) estático e visível
  document.querySelectorAll('header, [data-testid="masthead"], .site-header, nav').forEach(el => {
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

  // 5. Garantir que parágrafos, fotos e legendas estejam 100% visíveis
  document.querySelectorAll('article *, section[name="articleBody"] *, .StoryBodyCompanionColumn *').forEach(el => {
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

@register("nytimes.com")
class NytimesScraper(BaseScraper):
    """Handler cirúrgico para o The New York Times."""

    name = "nytimes"
    domains = ("nytimes.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_NYT_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de gateway de paywall e anúncios do NYT."""
        try:
            result = page.evaluate(_CLEANUP_NYT_JS)
            return {"handler": "nytimes", **result}
        except Exception as exc:
            return {"handler": "nytimes", "error": str(exc)[:300]}
