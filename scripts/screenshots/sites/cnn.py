#!/usr/bin/env python3
"""Scraper cirúrgico para a CNN Brasil (cnnbrasil.com.br).

Arquitetura do site:
- CMS proprietário com renderização moderna em servidor e hidratação.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.single-content``, ``.post__content`` ou ``.content__body``.
- Sem paywall, mas com presença de:
  - Banners de publicidade pesados (super banners no topo, anúncios no meio do texto e laterais)
  - Player de vídeo ou transmissão ao vivo flutuante (sticky)
  - Módulos de recomendação (Taboola/Outbrain)
- O cabeçalho com a icônica marca vermelha da CNN Brasil é mantido no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_CNN_CONTENT_JS = """() => {
  const sels = [
    'h1.single-header__title',
    'h1.post__title',
    'h1.news__title',
    'article h1',
    '.single-content',
    '.post__content',
    '.content__body',
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
# JS cirúrgico de limpeza para CNN Brasil
# ---------------------------------------------------------------------------

_CLEANUP_CNN_JS = """() => {
  const removed = [];

  // 1. Remover banners de topo, anúncios in-content e widgets de publicidade
  const adSelectors = [
    '#header_ads',
    '[id*="header_ads"]',
    '[id^="ads-banner"]',
    '[id*="ads-banner"]',
    '[class*="ad__area"]',
    '[class*="ad-bg"]',
    '.banner-ad',
    '.header-ad',
    '[class*="leaderboard"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '#taboola-mid-article-thumbnails',
    '.ad-slot',
    '.ad-wrapper',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .single-content, .post__content, .content__body')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // Remover wrappers de anúncio com imagem de fundo ad-bg.png (barra cinza texturizada)
  document.querySelectorAll('div, section, aside').forEach(el => {
    if (el.querySelector('article, h1, .single-content, .post__content, .content__body')) return;
    const bg = window.getComputedStyle(el).backgroundImage || '';
    if (bg.includes('ad-bg.png')) {
      el.remove();
      removed.push('ad-bg-image');
    }
  });

  // 2. Remover players de vídeo flutuantes/sticky, modais e banners LGPD
  const floatingSelectors = [
    '.floating-player',
    '.video-sticky',
    '[class*="video-floating"]',
    '.c-share-bar--floating',
    '.sticky-footer',
    '.sticky-banner',
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

  // 3. Tornar o cabeçalho institucional (logo CNN Brasil) estático e visível
  document.querySelectorAll('header, .header, .site-header, .cnn-header, nav').forEach(el => {
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
  document.querySelectorAll('article *, .single-content *, .post__content *, .content__body *').forEach(el => {
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

@register("cnnbrasil.com.br")
class CnnBrasilScraper(BaseScraper):
    """Handler cirúrgico para a CNN Brasil."""

    name = "cnnbrasil"
    domains = ("cnnbrasil.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo da CNN Brasil carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_CNN_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios e players flutuantes da CNN Brasil."""
        try:
            result = page.evaluate(_CLEANUP_CNN_JS)
            return {"handler": "cnnbrasil", **result}
        except Exception as exc:
            return {"handler": "cnnbrasil", "error": str(exc)[:300]}
