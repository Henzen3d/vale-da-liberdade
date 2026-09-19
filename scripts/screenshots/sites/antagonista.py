#!/usr/bin/env python3
"""Scraper cirúrgico para O Antagonista (oantagonista.com.br).

Arquitetura do site:
- CMS WordPress customizado focado em cobertura e análises políticas.
- O texto integral da matéria vem no HTML dentro de ``article``, ``.post-interna``,
  ``.col-lg-9`` ou ``.entry-content``.
- Sem paywall impeditivo no editorial padrão, mas com presença de:
  - Sidebar lateral direita ("Mais lidas" / ``.post-interna__aside``) que empurra e espreme
    o conteúdo do artigo em resoluções menores ou viewports de estúdio.
  - Barra lateral de compartilhamento flutuante (WhatsApp / redes sociais) que recua o texto.
  - Modal/card de consentimento de cookies flutuante no rodapé (``.card-cookies`` com botão "FECHAR").
  - Anúncios de topo, in-content e widgets de recomendação (Taboola/Outbrain).
  - Menu off-canvas (``#sidebar``) posicionado em ``left: -100%``.
- O cabeçalho com a marca "o antagonista" é mantido no topo em posição estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_ANTAGONISTA_CONTENT_JS = """() => {
  const sels = [
    'h1.post-interna__title',
    'h1.entry-title',
    'h1.title',
    'article h1',
    '.post-interna',
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
# JS cirúrgico de limpeza para O Antagonista
# ---------------------------------------------------------------------------

_CLEANUP_ANTAGONISTA_JS = """() => {
  const removed = [];

  // 1. Remover banners de anúncios, publicidade e widgets de recomendação
  const adSelectors = [
    '[id*="google_ads"]',
    '[id*="dfp-"]',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '#taboola-mid-article-thumbnails',
    '.ad-slot',
    '.banner-topo',
    '.banner-floating',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, img, picture, figure, .col-lg-9')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover modal/banner de cookies e LGPD (card-cookies com botão FECHAR)
  const cookieSelectors = [
    '.card-cookies',
    '[class*="card-cookies"]',
    '#cookieBanner-24120356',
    '.banner-lgpd',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
  ];

  cookieSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover sidebar lateral "Mais Lidas" que empurra o artigo e distorce o layout
  const sidebarSelectors = [
    '.post-interna__aside',
    '.mais-lidas-single',
    '[class*="mais-lidas"]',
    'aside',
  ];

  sidebarSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('h1, article p')) return;
      el.remove();
      removed.push('sidebar:' + sel);
    });
  });

  // 4. Remover barra flutuante de compartilhamento (WhatsApp) e menu offcanvas (#sidebar)
  const floatingSelectors = [
    '.post-interna__content__compartilhamento',
    '[class*="compartilhamento"]',
    '.c-floating-share',
    '.floating-share',
    '.share-buttons',
    '#sidebar',
    '.sticky-footer',
    '.floating-bar',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('h1, article p')) return;
      el.remove();
      removed.push('floating:' + sel);
    });
  });

  // 5. Expandir a coluna do artigo (.col-lg-9) para 100% da largura, centralizando o conteúdo
  document.querySelectorAll('.col-lg-9').forEach(el => {
    el.style.setProperty('width', '100%', 'important');
    el.style.setProperty('max-width', '100%', 'important');
    el.style.setProperty('flex', '0 0 100%', 'important');
  });

  // 6. Harmonizar largura do container do artigo
  document.querySelectorAll('.post-interna .container, .container').forEach(el => {
    el.style.setProperty('max-width', '1320px', 'important');
    el.style.setProperty('margin', '0 auto', 'important');
  });

  // 7. Manter o cabeçalho institucional ("o antagonista") estático e visível
  document.querySelectorAll('.custom-header-container, .custom-header-wrapper, header').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 8. Destravar scroll e evitar overflow horizontal
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow-x', 'hidden');
  force(document.documentElement, 'overflow-y', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow-x', 'hidden');
    force(document.body, 'overflow-y', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 9. Garantir que o texto, fotos e legendas do artigo estejam 100% visíveis
  document.querySelectorAll('article *, .post-interna *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 10. Forçar imagens com eager loading
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

@register("oantagonista.com.br", "oantagonista.com", "antagonista.com.br")
class AntagonistaScraper(BaseScraper):
    """Handler cirúrgico para O Antagonista."""

    name = "antagonista"
    domains = ("oantagonista.com.br", "oantagonista.com", "antagonista.com.br")

    def wait_for_content(self, page: Any) -> bool:
        """Espera a matéria do Antagonista carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_ANTAGONISTA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de anúncios, sidebars e centralização do artigo."""
        try:
            result = page.evaluate(_CLEANUP_ANTAGONISTA_JS)
            return {"handler": "antagonista", **result}
        except Exception as exc:
            return {"handler": "antagonista", "error": str(exc)[:300]}
