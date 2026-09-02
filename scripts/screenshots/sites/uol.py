#!/usr/bin/env python3
"""Scraper cirúrgico para o Portal UOL (uol.com.br, noticias.uol.com.br, economia.uol.com.br, etc.).

Arquitetura do site:
- CMS proprietário UOL com renderização de HTML no servidor.
- O texto integral da matéria vem no HTML original dentro de ``article``, ``.c-news__body``, ``.text`` ou ``.news-body``.
- Sem paywall rígido no Notícias/Economia, mas com presença pesada de:
  - Barra UOL no topo (``#barrauol``, ``.barrauol-container``)
  - Anúncios DFP/Google, Taboola e Outbrain
  - Banners LGPD e push notifications
  - Players de vídeo flutuantes e botões fixos de download de app
- O cabeçalho institucional com o logo do UOL ou do canal é mantido e fixado como estático.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_UOL_CONTENT_JS = """() => {
  const sels = [
    'h1.c-news__title',
    'h1.title',
    'article h1',
    '.c-news__body',
    '.text .news-body',
    '.news-content',
    '.article-content',
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
# JS cirúrgico de limpeza para UOL
# ---------------------------------------------------------------------------

_CLEANUP_UOL_JS = """() => {
  const removed = [];

  // 1. Remover barras de serviços e barras de topo de publicidade
  const topSelectors = [
    '#barrauol',
    '.barrauol',
    '.barrauol-container',
    '.c-top-bar',
    'nav.menu-services',
    'nav.menu-products',
    '.banner-uol',
    '.uol-advertising-leaderboard',
    '.c-advertising-top',
  ];

  topSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .c-news__body, .text')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover anúncios, blocos de publicidade, Taboola/Outbrain e popups
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="ad-"]',
    '[id*="banner-"]',
    '[class*="advertising"]',
    '[class*="publicidade"]',
    '.c-advertising',
    '.ad-placeholder',
    '.ad-slot',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '#taboola-mid-article-thumbnails',
    '.c-app-download',
    '.c-app-banner',
    '.c-push-notification',
    '.banner-lgpd-consent-container',
    '.banner-lgpd-consent',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, .c-news__body, .text, .news-body')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barras flutuantes, vídeos sticky e footers promocionais
  const floatingSelectors = [
    '.c-floating-video',
    '.floating-video',
    '.c-floating-bar',
    '.c-share-bar--floating',
    '.c-bottom-fixed',
    '[class*="bottom-bar"]',
    '[class*="fixed-footer"]',
    '.footer-fixed',
    '.c-newsletter-box--floating',
    '#banner_touch_point_bottom',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Configurar cabeçalho institucional (logo UOL / canal) como estático e limpo
  document.querySelectorAll('header, .header, .c-header, .site-header, nav.menu-uol').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
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

  // 6. Garantir que parágrafos, fotos e assinaturas estejam 100% visíveis
  document.querySelectorAll('article *, .c-news__body *, .text *, .news-body *').forEach(el => {
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

@register("uol.com.br", "noticias.uol.com.br", "economia.uol.com.br", "congressoemfoco.uol.com.br", "splash.uol.com.br", "educacao.uol.com.br")
class UolScraper(BaseScraper):
    """Handler cirúrgico para o Portal UOL."""

    name = "uol"
    domains = (
        "uol.com.br",
        "noticias.uol.com.br",
        "economia.uol.com.br",
        "congressoemfoco.uol.com.br",
        "splash.uol.com.br",
        "educacao.uol.com.br",
    )

    def prepare_page(self, page: Any, url: str) -> None:
        """Inicializa sessão a partir do domínio raiz do UOL para evitar 403 em subdomínios."""
        try:
            page.goto("https://www.uol.com.br/", wait_until="domcontentloaded", timeout=12000)
            page.wait_for_timeout(300)
        except Exception:
            pass

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo do UOL carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_UOL_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de barra UOL, anúncios e overlays do UOL."""
        try:
            result = page.evaluate(_CLEANUP_UOL_JS)
            return {"handler": "uol", **result}
        except Exception as exc:
            return {"handler": "uol", "error": str(exc)[:300]}
