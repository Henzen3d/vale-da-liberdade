#!/usr/bin/env python3
"""Scraper cirúrgico para o Portal Terra (terra.com.br).

Arquitetura do site:
- Atende tanto matérias textuais (/noticias/...) quanto páginas de vídeo (/noticias/videos/...).
- Em páginas de vídeo, o player principal (.t360-terratv--video--player-wrapper) fica no topo.
  A remoção do banner gigante de topo (#header-full-ad-container, 282px) permite que o player
  e a manchete caibam perfeitamente juntos no viewport de 1920x1080 com scroll em 0.
- Remove caixas de publicidade (``.card-ad``, ``[class*="terratv--ad"]``, ``.t360-ad``).
- Remove o bloco laranja invasivo "Meu Terra" (``.app-t360-user-table``, ``[class*="meu-terra"]``).
- Remove o mini-player flutuante (Picture-in-Picture) no canto inferior (``.video-main__floating``, ``[class*="pip"]``).
- Mantém o cabeçalho oficial do Terra (navbar com logo) no topo.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título ou player de vídeo carregar
# ---------------------------------------------------------------------------

_WAIT_TERRA_CONTENT_JS = """() => {
  const sels = [
    'h1',
    '.t360-terratv--video--player-wrapper',
    '.video-main__player',
    'article',
    '.article__content',
    'main',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para o Terra
# ---------------------------------------------------------------------------

_CLEANUP_TERRA_JS = """() => {
  const removed = [];

  // 1. Remover banner gigante de topo, taboola e anúncios
  const adSelectors = [
    '#header-full-ad-container',
    '#header-full-ad',
    '.breaking-news-bar',
    '.card-ad',
    '[class*="card-ad"]',
    '[class*="terratv--ad"]',
    '[class*="t360-ad"]',
    '.t360-terratv--bottom',
    '[class*="banner"]',
    '[class*="advertising"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '[id*="taboola"]',
    '[class*="tbl-feed"]',
    '#onetrust-banner-sdk',
    '.banner-lgpd',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o player de vídeo ou manchete
      if (el.querySelector('h1, video, iframe, .video-main__player, .t360-terratv--video--player-wrapper')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover bloco laranja invasivo "Meu Terra", popups e floating PiP player
  const clutterSelectors = [
    '.app-t360-user-table',
    '[class*="app-t360-user-table"]',
    '[class*="meu-terra"]',
    '#meu-terra',
    '[class*="card-meu-terra"]',
    '.video-main__floating',
    '[class*="pip"]',
    '[class*="floating-player"]',
    '.floating-toolbar',
    '[class*="modal"]',
  ];

  clutterSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Tornar navbars e cabeçalhos estáticos
  document.querySelectorAll('header, nav, .navbar, .t360-terratv--header').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 4. Forçar carregamento das imagens e posters de vídeo
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

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("terra.com.br")
class TerraScraper(BaseScraper):
    """Handler cirúrgico para o Portal Terra (matérias e vídeos)."""

    name = "terra"
    domains = ("terra.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo ou player carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_TERRA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners, bloco Meu Terra e floating PiP do Terra."""
        try:
            result = page.evaluate(_CLEANUP_TERRA_JS)
            return {"handler": "terra", **result}
        except Exception as exc:
            return {"handler": "terra", "error": str(exc)[:300]}

    def _scroll_to_title(self, page: Any) -> dict:
        """Posiciona o viewport: scroll 0 para vídeos com player no topo, ou H1 para matérias."""
        try:
            scroll_js = """() => {
                // Em páginas de vídeo (/videos/), mantemos scroll 0 para capturar
                // a barra oficial do Terra, o player com frame de vídeo e a manchete
                const isVideo = window.location.href.includes('/videos/') || !!document.querySelector('.t360-terratv, .video-main, video, [class*="terratv"]');
                if (isVideo) {
                    window.scrollTo(0, 0);
                    return {found: true, type: 'video_page', y: 0};
                }

                // Matéria padrão: posiciona no H1 se estiver abaixo do topo
                const h1 = document.querySelector('h1, .article__title');
                if (h1) {
                    let y = h1.getBoundingClientRect().top + window.scrollY - 24;
                    if (y < 240) y = 0;
                    window.scrollTo(0, Math.max(0, y));
                    return {found: true, type: 'h1', y: Math.max(0, y)};
                }

                window.scrollTo(0, 0);
                return {found: false, y: 0};
            }"""
            info = page.evaluate(scroll_js)
            return info
        except Exception as exc:
            return {"found": False, "error": str(exc)}
