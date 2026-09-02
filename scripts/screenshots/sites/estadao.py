#!/usr/bin/env python3
"""Scraper cirúrgico para o Estadão (estadao.com.br).

Arquitetura do site:
- Arc XP / Fusion Engine (React SPA)
- O conteúdo completo da matéria vem no HTML dentro de ``#fusion-app``
- A hidratação React ocorre APÓS DOMContentLoaded
- O paywall é um overlay ``position: fixed`` (geralmente ``<main class="background">``,
  ``.modal``, ou wrappers ``.spaceOffers``) que cobre o ``#fusion-app``
- Trackers infinitos impedem ``networkidle`` de resolver

Diagnóstico feito pelo Hermes Agent (2026-09):
- bodyHeight=0 aparece porque o React ainda não hidratou
- Remover ``<main>`` genérico destrói o artigo (está dentro de ``#fusion-app``)
- O CSS carrega normalmente (8 folhas, fonte Lato aplicada)
- O conteúdo real está dentro de ``#fusion-app article``
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o React hidratar e o artigo aparecer
# ---------------------------------------------------------------------------

_WAIT_CONTENT_JS = """() => {
  const sels = [
    '#fusion-app article',
    '#fusion-app .news-title',
    '#fusion-app h1',
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
# JS cirúrgico de remoção do paywall (não genérico!)
# ---------------------------------------------------------------------------

_CLEANUP_PAYWALL_JS = """() => {
  const removed = [];

  // 1. Identificar o modal/overlay do paywall
  //    No Estadão, o paywall é tipicamente:
  //    - <main class="background"> com position:fixed e z-index alto
  //    - Elementos com classe 'modal', 'spaceOffers', 'paywall'
  //    - Containers com texto "assine", "assinante", "plano digital", etc.

  // 1a. Remover modais de paywall por seletores conhecidos
  const paywallSelectors = [
    'main.background',
    '.modal-overlay',
    '.paywall-overlay',
    '.paywall',
    '.spaceOffers',
    '[data-paywall-wrapper]',
    '[data-zephr-protect]',
    '.container-assine-para-ler',
    '.assine-para-ler',
    '.exclusive-content',
    '.ReactModal__Overlay',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Não remover se for o próprio fusion-app ou seu ancestor
      if (el.id === 'fusion-app' || el.contains(document.getElementById('fusion-app'))) {
        return;
      }
      el.remove();
      removed.push(sel);
    });
  });

  // 1b. Detectar overlays fixed/sticky com texto de assinatura
  const keywords = [
    'assine', 'assinante', 'plano digital', 'acesso ilimitado',
    'lá a assinante', 'faça login', 'continue lendo',
    'assina já', 'oferta especial', 'aproveite', 'quero aproveitar',
    'caro leitor', 'após o anúncio', 'apos o anuncio', 'continue lendo'
  ];

  document.querySelectorAll('div, section, aside, article, main, span').forEach(el => {
    // Proteger o conteúdo principal
    if (el.id === 'fusion-app' || el.closest('#fusion-app article')) return;
    if (el.contains(document.getElementById('fusion-app'))) return;

    const t = (el.innerText || '').toLowerCase().slice(0, 300);
    if (!t) return;

    const match = keywords.some(k => t.includes(k));
    if (!match) return;

    const st = getComputedStyle(el);
    const isOverlay = st.position === 'fixed' || st.position === 'sticky';

    // Se é fixed/sticky E contém texto de paywall → remover
    if (isOverlay) {
      el.remove();
      removed.push('fixed-overlay-keyword');
      return;
    }

    // Se cobre >50% do viewport e está no overlay → remover
    const r = el.getBoundingClientRect();
    if (r.offsetWidth > window.innerWidth * 0.5 &&
        el.offsetHeight > window.innerHeight * 0.3 &&
        parseInt(st.zIndex) > 100) {
      el.remove();
      removed.push('large-overlay-keyword');
    }
  });

  // 2. Destravar scroll do body, html e fusion-app
  //    O Estadão define body{height:100%; overflow:hidden} que colapsa o body.
  //    Sem !important o CSS do site sobrescreve nossas correções.
  const force = (el, prop, val) => el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'height', 'auto');
  force(document.documentElement, 'position', 'static');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'height', 'auto');
    force(document.body, 'position', 'static');
  }
  const fusionApp = document.getElementById('fusion-app');
  if (fusionApp) {
    force(fusionApp, 'overflow', 'auto');
    force(fusionApp, 'position', 'static');
    force(fusionApp, 'height', 'auto');
  }

  // 3. Remover blur/opacity de parágrafos truncados pelo paywall
  const articleEls = document.querySelectorAll(
    '#fusion-app article *, .news-body *, .content-text *, [itemprop="articleBody"] *'
  );
  articleEls.forEach(el => {
    const st = el.style;
    if (st.filter && st.filter !== 'none') {
      st.filter = 'none';
    }
    if (st.opacity && st.opacity !== '1') {
      st.opacity = '1';
    }
    // Também verificar via computed style (classes CSS podem aplicar blur)
    const cs = getComputedStyle(el);
    if (cs.filter !== 'none') {
      el.style.setProperty('filter', 'none', 'important');
    }
    if (parseFloat(cs.opacity) < 1) {
      el.style.setProperty('opacity', '1', 'important');
    }
  });

  // 4. Garantir que conteúdo oculto pelo paywall esteja visível
  document.querySelectorAll('#fusion-app [style*="display: none"], #fusion-app [style*="visibility: hidden"]').forEach(el => {
    // Só revelar se estiver dentro do artigo (não reativar ads)
    if (el.closest('article, .news-body, .content-text, [itemprop="articleBody"]')) {
      el.style.display = '';
      el.style.visibility = '';
    }
  });

  // 5. Remover ads remanescentes dentro do conteúdo
  const adSelectors = [
    '.ads-container', '.ads-placeholder-wrapper', '.ads-placeholder-label',
    '[id*="google_ads"]', '[class*="ad-container"]', '[class*="publicidade"]',
    '.taboola-container', '.outbrain-container',
  ];
  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push('ad:' + sel);
    });
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("estadao.com.br")
class EstadaoScraper(BaseScraper):
    """Handler cirúrgico para o Estadão (Arc XP / Fusion React)."""

    name = "estadão"
    domains = ("estadao.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o React hidratar e o artigo aparecer no DOM.

        Tenta até 8 segundos (400ms × 20 tentativas) para encontrar
        ``#fusion-app article`` ou seletores equivalentes.
        """
        for _ in range(20):
            try:
                info = page.evaluate(_WAIT_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(400)
        # Último recurso: esperar mais 2s mesmo sem achar
        page.wait_for_timeout(2000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica do paywall Arc XP do Estadão.

        NÃO remove ``<main>`` genérico (destruiria o artigo).
        Remove apenas o overlay/modal do paywall e destrava o DOM.
        """
        try:
            result = page.evaluate(_CLEANUP_PAYWALL_JS)
            return {"handler": "estadao", **result}
        except Exception as exc:
            return {"handler": "estadao", "error": str(exc)[:300]}
