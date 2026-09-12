#!/usr/bin/env python3
"""Scraper cirúrgico para a Folha do Estado (folhadoestado.com.br).

Arquitetura do site:
- CMS PHP / Bootstrap com renderização server-side.
- Cabeçalho institucional azul com logotipo "FOLHA DO ESTADO" no topo.
- Possui modais de anúncios e offerwalls intrusivos (Clever Ads / Superbet, #modalpopup, SweetAlert2)
  que aplicam blur e backdrop sobre todo o conteúdo.
- Banners de publicidade e barra lateral "Mais Lidas" ocupam espaço e poluem a notícia.
- O enquadramento em y = 0 garante exibição permanente do cabeçalho institucional,
  título, subtítulo, autor e imagem principal da matéria.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


_CLEANUP_CSS = """\
/* 1. Modais, popups e offerwalls (Clever Ads, Superbet, Bootstrap, SweetAlert2) */
[id*="clever"],
[class*="clever"],
[id*="Offerwall"],
#modalpopup,
.modal-backdrop,
.modal,
#POPUP,
.popupHtml,
.swal2-container,
.swal2-popup,
[class*="swal"],
.VIpgJd-ZVi9od-aZ2wEe-wOHMyf {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
  pointer-events: none !important;
}

/* 2. Remover blur, filtros e destravar body */
body, html, * {
  filter: none !important;
  -webkit-filter: none !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
body.modal-open {
  overflow: auto !important;
  position: static !important;
}

/* 3. Banners de publicidade e placeholders de anúncios */
[class*="box-banner"],
#bannerinterna,
.bannerResult,
[class*="ad-"],
[class*="publicidade"],
[id*="google_ads"],
.ad-lead-bottom {
  display: none !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}

/* 4. Flags de tradução do Google no topo */
img[src*="icon-capa-"],
#google_translate_element,
.flags {
  display: none !important;
}

/* 5. Esconder barra lateral "Mais Lidas" e expandir notícia para 100% */
aside.index-bloco-2,
.index-bloco-2 {
  display: none !important;
}
.index-bloco-1 {
  width: 100% !important;
  max-width: 100% !important;
  flex: 0 0 100% !important;
}
"""

_CLEANUP_JS = """() => {
  const removed = [];

  // Remover elementos intrusivos do DOM
  const selectors = [
    '[id*="clever"]',
    '[class*="clever"]',
    '[id*="Offerwall"]',
    '#modalpopup',
    '.modal-backdrop',
    '#POPUP',
    '.popupHtml',
    '.swal2-container',
    '.swal2-popup',
    '[class*="box-banner"]',
    '#bannerinterna',
    '.bannerResult',
  ];

  selectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // Limpar classes de bloqueio do body
  if (document.body) {
    document.body.classList.remove('modal-open');
    document.body.style.overflow = 'auto';
  }
  document.documentElement.style.overflow = 'auto';

  // Forçar carregamento imediato das imagens da matéria
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    img.decoding = 'sync';
    const ds = img.dataset.src || img.getAttribute('data-original');
    if (ds && (!img.src || img.src.startsWith('data:'))) {
      img.src = ds;
    }
  });

  window.scrollTo(0, 0);
  return {removed, count: removed.length};
}"""


@register("folhadoestado.com.br")
class FolhaDoEstadoScraper(BaseScraper):
    """Scraper cirúrgico para a Folha do Estado (folhadoestado.com.br)."""

    name = "folhadoestado"
    domains = ("folhadoestado.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Aguarda a matéria carregar no DOM."""
        try:
            page.wait_for_selector("h1", timeout=12000)
            return True
        except Exception:
            return False

    def cleanup(self, page: Any) -> dict:
        """Aplica limpeza de offerwalls, anúncios e ajusta enquadramento."""
        try:
            page.add_style_tag(content=_CLEANUP_CSS)
            result = page.evaluate(_CLEANUP_JS)
            return {"handler": "folhadoestado", **result}
        except Exception as exc:
            return {"handler": "folhadoestado", "error": str(exc)[:300]}

    def _scroll_to_title(self, page: Any) -> dict:
        """Mantém y = 0 para exibir o cabeçalho institucional com logo e menu."""
        try:
            page.evaluate("() => window.scrollTo(0, 0)")
            h1 = page.evaluate("() => !!document.querySelector('h1')")
            return {"found": bool(h1), "y": 0, "sticky": 0}
        except Exception as exc:
            return {"found": False, "error": str(exc), "y": 0}
