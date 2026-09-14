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

# ---------------------------------------------------------------------------
# JS de espera: aguarda o React hidratar e o artigo aparecer
# ---------------------------------------------------------------------------

_WAIT_CONTENT_JS = """() => {
  const sels = [
    '#fusion-app article',
    '#fusion-app .news-body',
    '#fusion-app h1',
    '#content',
    'h1',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de remoção do paywall e higienização visual do Estadão
# ---------------------------------------------------------------------------

_CLEANUP_PAYWALL_JS = """() => {
  const removed = [];

  // 1. Restaurar o corpo da matéria se o script de paywall do cliente substituiu o conteúdo
  const content = document.getElementById('content') || document.querySelector('.news-body');
  if (content && window._originalArticleContent) {
    const isPaywalled = content.querySelector('main.background, .spaceOffers, .modal') ||
                        !content.querySelector('.paragraph, .template-reportagem');
    if (isPaywalled) {
      content.innerHTML = window._originalArticleContent;
      removed.push('restored-original-article');
    }
  }

  // 2. Remover modais e overlays do paywall por seletores cirúrgicos
  //    NUNCA remover [data-paywall-wrapper], pois é o container da própria matéria no Estadão!
  //    NUNCA remover header, nav, navbar ou menu institucional.
  const paywallSelectors = [
    'main.background',
    '.modal-overlay',
    '.paywall-overlay',
    '.paywall',
    '.spaceOffers',
    '[data-zephr-protect]',
    '.container-assine-para-ler',
    '.assine-para-ler',
    '.exclusive-content',
    '.ReactModal__Overlay',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.id === 'fusion-app' || el.closest('header, nav, [class*="navbar"], [class*="menu"], [class*="header"], .logo-estadao')) {
        return;
      }
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover overlays fixed/sticky com texto de assinatura, protegendo header/menu/logo
  const keywords = [
    'assine', 'assinante', 'plano digital', 'acesso ilimitado',
    'faça login', 'continue lendo', 'assina já', 'oferta especial',
    'aproveite', 'quero aproveitar'
  ];

  document.querySelectorAll('div, section, aside, main, span').forEach(el => {
    // Proteger explicitamente o header, menu desktop, logo e barra de navegação
    if (el.closest('header, nav, [class*="navbar"], [class*="menu"], [class*="header"], .logo-estadao, [class*="logo"]')) return;
    if (el.id === 'fusion-app' || el.closest('#content, .news-body')) return;

    const t = (el.innerText || '').toLowerCase().slice(0, 300);
    if (!t) return;

    const match = keywords.some(k => t.includes(k));
    if (!match) return;

    const st = getComputedStyle(el);
    const isOverlay = st.position === 'fixed' || st.position === 'sticky';

    if (isOverlay) {
      el.remove();
      removed.push('fixed-overlay-keyword');
      return;
    }

    const r = el.getBoundingClientRect();
    if (r.offsetWidth > window.innerWidth * 0.5 &&
        el.offsetHeight > window.innerHeight * 0.3 &&
        parseInt(st.zIndex) > 100) {
      el.remove();
      removed.push('large-overlay-keyword');
    }
  });

  // 4. Remover seções solicitadas pelo usuário: Compartilhar, Siga nas redes e Tudo Sobre
  const userRequestedRemovals = [
    '#social-media-lower',
    '.social-media-lower',
    '[class*="SocialMediaLowerStyled"]',
    '.subfooter',
    '#tudo-sobre-noticia',
    '.news-tags',
    '[class*="NewsTagsStyled"]',
    '.header-comentarios',
    '.container-comentarios',
    '.comentarios',
    '[class*="AudioPlayerStyled"]',
    '.audio-player',
    '.corrections',
    '[class*="AssineButton"]',
    'button[title*="Assine"]',
    '.botão-assine',
    'img.assine-img',
  ];
  userRequestedRemovals.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push('user-clean:' + sel);
    });
  });

  // 5. Destravar scroll do body, html e fusion-app
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
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

  // 6. Garantir que a barra de menu e header institucional estejam visíveis
  document.querySelectorAll('header, nav, [class*="navbar"], [class*="menu-desktop"], .container-fixed').forEach(el => {
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
    el.style.setProperty('opacity', '1', 'important');
  });

  // 7. Remover blur/opacity de parágrafos
  const articleEls = document.querySelectorAll(
    '#fusion-app article *, .news-body *, .content-text *, [itemprop="articleBody"] *'
  );
  articleEls.forEach(el => {
    const st = el.style;
    if (st.filter && st.filter !== 'none') st.filter = 'none';
    if (st.opacity && st.opacity !== '1') st.opacity = '1';
    const cs = getComputedStyle(el);
    if (cs.filter !== 'none') el.style.setProperty('filter', 'none', 'important');
    if (parseFloat(cs.opacity) < 1) el.style.setProperty('opacity', '1', 'important');
  });

  // 8. Garantir que conteúdo oculto pelo paywall esteja visível
  document.querySelectorAll('#fusion-app [style*="display: none"], #fusion-app [style*="visibility: hidden"]').forEach(el => {
    if (el.closest('article, .news-body, .content-text, [itemprop="articleBody"]')) {
      el.style.display = '';
      el.style.visibility = '';
    }
  });

  // 9. Remover ads remanescentes e iframes vazios de publicidade
  const adSelectors = [
    '.ads-container', '.ads-placeholder-wrapper', '.ads-placeholder-label',
    '[id*="google_ads"]', '[class*="ad-container"]', '[class*="ad-placeholder"]',
    '[class*="publicidade"]', '.taboola-container', '.outbrain-container',
  ];
  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push('ad:' + sel);
    });
  });
  document.querySelectorAll('iframe').forEach(ifr => {
    if (!ifr.closest('.container-video-noticia, figure, article')) {
      ifr.remove();
    }
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

    def prepare_page(self, page: Any, url: str) -> None:
        """Preserva o HTML original da matéria gerado no SSR antes da hidratação do paywall."""
        page.add_init_script("""
            window._originalArticleContent = null;
            document.addEventListener('DOMContentLoaded', () => {
                const content = document.getElementById('content') || document.querySelector('.news-body');
                if (content && content.innerHTML.length > 2000) {
                    window._originalArticleContent = content.innerHTML;
                }
            });
        """)

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
        """Remoção cirúrgica do paywall Arc XP do Estadão e preservação do layout editorial.

        NÃO remove ``<main>`` genérico nem ``[data-paywall-wrapper]`` (destruiria o artigo).
        Restaura o corpo da matéria se tiver sido esvaziado pelo formulário de paywall.
        Remove as seções de compartilhar, siga nas redes e tudo sobre conforme solicitado.
        Garante a integridade do menu superior e barra institucional.
        """
        try:
            result = page.evaluate(_CLEANUP_PAYWALL_JS)
            return {"handler": "estadao", **result}
        except Exception as exc:
            return {"handler": "estadao", "error": str(exc)[:300]}
