#!/usr/bin/env python3
"""Scraper cirúrgico para o Portal Claudio Dantas (claudiodantas.com.br).

Arquitetura do site:
- CMS WordPress focado em notícias políticas e análises de bastidores.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.entry-content``, ``.post-content`` ou ``.td-post-content``.
- Presença marcante de:
  - Anúncio âncora fixo no rodapé (Google Anchor Ad: ``ins[id*="as_claudiodantas_desk_anchor"]`` / ``ins[id*="gpt_unit_"]`` com z-index máximo)
  - Banners in-content e laterais (Google DFP/AdSense)
  - Popups e modais de newsletter
- O cabeçalho com o logo/marca do Claudio Dantas é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_CLAUDIO_CONTENT_JS = """() => {
  const sels = [
    'h1.entry-title',
    'h1.post-title',
    'h1.title',
    'article h1',
    '.entry-content',
    '.post-content',
    '.td-post-content',
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
# JS cirúrgico de limpeza para Claudio Dantas
# ---------------------------------------------------------------------------

_CLEANUP_CLAUDIO_JS = """() => {
  const removed = [];

  // 1. Remover anúncio âncora fixo no rodapé (Google Anchor Ad / GPT Unit)
  const anchorSelectors = [
    'ins[id*="as_claudiodantas_desk_anchor"]',
    'ins[id*="gpt_unit_"]',
    'div[id*="as_claudiodantas_desk_anchor"]',
    'div[id*="google_ads_iframe"]',
    '[class*="grippy-host"]',
    'ins.ee',
  ];

  anchorSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push('anchor-ad:' + sel);
    });
  });

  // 2. Remover outros banners de publicidade, sidebars e slots de anúncios
  const adSelectors = [
    'aside.cd-ad',
    '.cd-ad',
    '[class*="cd-ad"]',
    '[id*="google_ads"]',
    '[class*="td-a-rec"]',
    '[class*="td-g-rec"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '.ad-container',
    '.ads-container',
    '.banner-topo',
    '.taboola-container',
    '.outbrain-container',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .entry-content, .post-content, .td-post-content')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras fixas e banners de consentimento/cookie
  const floatingSelectors = [
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.lgpd-consent',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Tornar o cabeçalho institucional (logo Claudio Dantas) estático e visível
  document.querySelectorAll('header, .header, .site-header, .td-header-template-wrap, nav').forEach(el => {
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

  // 6. Garantir que parágrafos, fotos e assinaturas estejam 100% visíveis
  document.querySelectorAll('article *, .entry-content *, .post-content *, .td-post-content *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 7. Forçar imagens da matéria com eager loading
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    const ds = img.dataset.src || img.getAttribute('data-pagespeed-lazy-src');
    if (ds && (!img.src || img.src.startsWith('data:'))) {
      img.src = ds;
    }
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("claudiodantas.com.br")
class ClaudioDantasScraper(BaseScraper):
    """Handler cirúrgico para o Portal Claudio Dantas."""

    name = "claudiodantas"
    domains = ("claudiodantas.com.br",)
    # Desativa stealth pois o tema do site quebra a largura do layout com mockings de tela
    stealth_enabled = False

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_CLAUDIO_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica do anchor ad e anúncios do site do Claudio Dantas."""
        try:
            result = page.evaluate(_CLEANUP_CLAUDIO_JS)
            return {"handler": "claudiodantas", **result}
        except Exception as exc:
            return {"handler": "claudiodantas", "error": str(exc)[:300]}
