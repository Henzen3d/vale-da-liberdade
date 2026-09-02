#!/usr/bin/env python3
"""Scraper cirúrgico para G1 e família Globo (g1.globo.com, oglobo.globo.com, valor.globo.com, ge.globo.com).

Arquitetura do site:
- CMS da Globo com renderização de HTML no servidor (rotas .ghtml).
- O texto integral da matéria vem no HTML original (dentro de ``.content-text`` ou ``.article__content``).
- Sem paywall no G1/GE; paywalls residuais em O Globo / Valor são botões e modais de assinatura.
- Banners e placeholders de ads no topo (``#ad-container-top-placeholder``, ``.glb-mc-banner-top``)
  são removidos para posicionar o cabeçalho com logo do jornal e manchete no topo.
- Foto de destaque (``.content-featured-image`` dentro de ``.content-featured-figure``) é preservada
  e carregada com eager loading.
- Barra fixa do rodapé (``.mobiliarioFooter`` com newsletter) e barras flutuantes são removidas.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_GLOBO_CONTENT_JS = """() => {
  const sels = [
    'h1.content-head__title',
    'h1.article__title',
    'h1.title',
    '.content-text',
    '.article__content',
    '.mc-body',
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
# JS cirúrgico de limpeza para G1 e família Globo
# ---------------------------------------------------------------------------

_CLEANUP_GLOBO_JS = """() => {
  const removed = [];

  // 1. Remover banners e placeholders de publicidade do topo/laterais
  const adSelectors = [
    '#ad-container-top-placeholder',
    '#mc-container-top',
    '.ad-background-center',
    '[id*="ad-container"]',
    '[id*="mc-container"]',
    '[class*="ad-background"]',
    '.glb-mc-banner-top',
    'glb-ad',
    '.tag-manager-publicidade-container',
    '.publicidade',
    '[class*="glb-skeleton-box"]',
    '.glb-grid-publicidade',
    '.native-ad',
    '[id*="google_ads"]',
    '.banner-materia_topo',
    '.advertising-container',
    '.taboola-container',
    '.banner',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou foto principal
      if (el.querySelector('.content-text, .article__content, .mc-body, h1, .content-featured-image, figure')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover barras flutuantes, rodapés de newsletter e banners LGPD/cookies
  const floatingSelectors = [
    '.floating-bar',
    '.glb-bar-navegador',
    '#glb-cookie-banner',
    '.banner-lgpd',
    '.glb-menu-globocom',
    '.header-navigator',
    '.mobiliarioFooter',
    '#banner_touch_point_bottom',
    '.naoBarreiraOnboarding',
    '#audio-player',
    '[class*="newsletter"]',
    '.c-newsletter',
    '#newsletter-banner',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover botões e overlays de paywall (O Globo / Valor Econômico)
  const paywallSelectors = [
    '.button-subscribe',
    '.paywall-news-exclusive',
    '.barrier-wall',
    '[data-paywall-wrapper]',
    '.modal-paywall',
    '.paywall-wrapper',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('.content-text, .article__content, .mc-body, h1, .content-featured-image, figure')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Garantir que o cabeçalho institucional (logo do jornal) fique visível no topo
  document.querySelectorAll('.site-header, .glb-header, header').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 5. Forçar carregamento da foto de destaque e imagens (evita placeholder cinza)
  document.querySelectorAll('img').forEach(img => {
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
    img.loading = 'eager';
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  // 6. Destravar scroll no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 7. Garantir que parágrafos e mídias estejam visíveis
  document.querySelectorAll('.content-text *, .article__content *, .mc-body *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("g1.globo.com", "oglobo.globo.com", "valor.globo.com", "ge.globo.com", "globo.com")
class G1Scraper(BaseScraper):
    """Handler cirúrgico para G1 e família Globo."""

    name = "g1"
    domains = ("g1.globo.com", "oglobo.globo.com", "valor.globo.com", "ge.globo.com", "globo.com")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_GLOBO_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners de topo, skeletons e overlays da Globo."""
        try:
            result = page.evaluate(_CLEANUP_GLOBO_JS)
            return {"handler": "g1", **result}
        except Exception as exc:
            return {"handler": "g1", "error": str(exc)[:300]}
