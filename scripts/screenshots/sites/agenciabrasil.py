#!/usr/bin/env python3
"""Scraper cirúrgico para Agência Brasil e EBC (agenciabrasil.ebc.com.br, ebc.com.br).

Arquitetura do site:
- Portal público da Empresa Brasil de Comunicação (EBC) baseado em Drupal.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.content-news``,
  ``.field--name-body`` ou ``.news-body``.
- Sem paywall comercial, mas com:
  - Barra de acessibilidade e governo federal (#barra-brasil, VLibras)
  - Botões de compartilhamento flutuantes
  - Banner de consentimento LGPD / cookies
  - Módulos de "leia também" e podcasts institucionais
- O cabeçalho com o logo da Agência Brasil / EBC é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_AGENCIA_CONTENT_JS = """() => {
  const sels = [
    'h1.title',
    'h1.page-title',
    'article h1',
    'h1',
    '.content-news',
    '.field--name-body',
    'article',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Agência Brasil / EBC
# ---------------------------------------------------------------------------

_CLEANUP_AGENCIA_JS = """() => {
  const removed = [];

  // 1. Remover barras de governo e acessibilidade que ocupam topo excessivo
  const overlaySelectors = [
    '.search-container',
    '#barra-brasil',
    '.barra-brasil',
    '.vlibras',
    '[vw]',
    '[vw-access-button]',
    '#vlibras-widget',
    '.access-button',
    '.banner-lgpd',
    '.banner-lgpd-consent',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.c-share-bar--floating',
    '.share-bar-floating',
    '.sticky-share',
    '.floating-tools',
  ];

  overlaySelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover anúncios ou blocos promocionais órfãos se existirem
  const promoSelectors = [
    '.publicidade',
    '.ads-container',
    '.banner-container',
    '[id*="google_ads"]',
    '.taboola-container',
  ];

  promoSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .field--name-body')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Garantir que o cabeçalho com a logo da Agência Brasil fique estático e visível
  document.querySelectorAll('header, .header, .navbar, .header-site, .region-header').forEach(el => {
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
  document.querySelectorAll('article *, .content-news *, .field--name-body *').forEach(el => {
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

@register("agenciabrasil.ebc.com.br", "ebc.com.br")
class AgenciaBrasilScraper(BaseScraper):
    """Handler cirúrgico para a Agência Brasil e EBC."""

    name = "agenciabrasil"
    domains = ("agenciabrasil.ebc.com.br", "ebc.com.br")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo da Agência Brasil carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_AGENCIA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de barras de governo, modais e acessibilidade."""
        try:
            result = page.evaluate(_CLEANUP_AGENCIA_JS)
            return {"handler": "agenciabrasil", **result}
        except Exception as exc:
            return {"handler": "agenciabrasil", "error": str(exc)[:300]}
