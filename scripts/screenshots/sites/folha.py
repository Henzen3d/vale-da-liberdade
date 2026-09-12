#!/usr/bin/env python3
"""Scraper cirúrgico para a Folha de S.Paulo (folha.uol.com.br / folha.com.br).

Arquitetura do site:
- CMS tradicional com renderização de HTML no servidor (não é SPA).
- O texto integral da matéria vem no HTML original dentro de ``.c-news__body``.
- ATENÇÃO: A Folha envolve o artigo dentro de ``<div class="container j-paywall">``.
  NUNCA remova elementos com classe ``j-paywall`` (isso apagaria o artigo inteiro!).
  Apenas remova a classe CSS ``j-paywall`` e exclua modais/overlays reais.
- O paywall externo é injetado via script do host ``paywall.folha.uol.com.br`` (já bloqueado no BaseScraper).
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_FOLHA_CONTENT_JS = """() => {
  const sels = [
    'h1.c-content-head__title',
    'h1.c-main-headline__title',
    '.c-news__body',
    'article.c-news',
    'h1',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza da Folha de S.Paulo
# ---------------------------------------------------------------------------

_CLEANUP_FOLHA_JS = """() => {
  const removed = [];

  // 1. Remover barra UOL do topo e menus de produtos
  document.querySelectorAll('#barrauol, .barrauol, .barrafolha, nav.menu-products, nav.menu-services').forEach(el => {
    el.remove();
    removed.push('uol-top-bar');
  });

  // 2. Remover banner de oferta do topo da Folha (faixa de R$ 1,90)
  document.querySelectorAll('#c-top-signup-inner, .c-top-signup-inner, .c-top-signup, #top-signup-close').forEach(el => {
    el.remove();
    removed.push('top-signup-offer');
  });

  // 3. Desativar classes de paywall SEM remover containers de conteúdo
  //    (A Folha envolve o artigo em <div class="container j-paywall">)
  document.querySelectorAll('.j-paywall').forEach(el => {
    el.classList.remove('j-paywall');
    removed.push('class:j-paywall');
  });

  // 4. Remover overlays e modais de paywall reais (preservando #paywall-content que é o wrapper do artigo)
  const paywallSelectors = [
    '#paywall-fill',
    '#paywall-screen',
    '#paywall-flutuante',
    '#paywall-banner',
    '.paywall-active',
    '.c-subscribe-wall',
    '.c-news-login-wall',
    '.banner-lgpd-consent',
    '.banner-lgpd-consent-container',
    '#lgpd-banner',
    '.c-push-notification',
    '.c-bottom-fixed',
    '[class*="login-wall"]',
  ];
  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.id === 'paywall-content') return;
      if (el.closest('.l-header, header')) return;
      if (el.querySelector('article, h1, .l-header, header, .c-news__body')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 5. Remover faixas soltas de texto de assinatura / oferta (NUNCA tocar em header ou dentro dele)
  document.querySelectorAll('div, section, aside').forEach(el => {
    if (el.closest('.l-header, header')) return;
    if (el.querySelector('article, h1, .c-news__body, .c-signature')) return;
    const t = (el.innerText || '').trim().toLowerCase();
    if ((t.includes('oferta especial') && t.includes('assine')) || (t.includes('já é assinante?') && !t.includes('folha'))) {
      el.remove();
      removed.push('text-offer-banner');
    }
  });

  // 6. Remover publicidades conhecidas e o super banner do topo (.block--pub-super)
  const adSelectors = [
    '.block--pub-super',
    '[class*="pub-super"]',
    '[class*="block--pub"]',
    '.c-top-banner',
    '.banner--leaderboard',
    '.banner--super',
    '.banner--halfpage',
    '.c-advertising-placeholder',
    '.c-advertising',
    '[id*="google_ads"]',
    '.taboola-container',
  ];
  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(e => {
      if (e.closest('.l-header, header')) return;
      const parentBlock = e.closest('.block') || e;
      if (!parentBlock.querySelector('.c-news__body, .c-signature, h1, .l-header, header')) {
        parentBlock.remove();
        removed.push(sel);
      }
    });
  });

  // 7. Remover barras flutuantes, botões de IA e downloads
  document.querySelectorAll('.c-share-bar--floating, .c-more-options--sticky, .c-app-download-banner, .c-floating-video, .c-ai-bar, [data-ai-bar], .c-floater-ask-ai, [class*="sparkle"]').forEach(el => {
    el.remove();
    removed.push('floating-widget');
  });

  // 8. Garantir que o cabeçalho institucional (.l-header) fique estático, visível e no topo
  document.querySelectorAll('.l-header, header').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
    el.style.setProperty('opacity', '1', 'important');
    el.style.setProperty('height', 'auto', 'important');
    el.style.setProperty('top', '0px', 'important');
  });
  document.querySelectorAll('.js-c-elastic-header').forEach(el => {
    el.style.setProperty('height', 'auto', 'important');
  });

  // 9. Destravar scroll no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 10. Garantir que corpo da notícia, títulos e assinaturas estejam 100% visíveis
  document.querySelectorAll('.c-news__body, .c-news__body *, [itemprop="articleBody"] *, .c-signature *, .c-content-head *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("folha.uol.com.br", "www1.folha.uol.com.br", "folha.com.br", "datafolha.folha.uol.com.br")
class FolhaScraper(BaseScraper):
    """Handler cirúrgico para a Folha de S.Paulo e Datafolha."""

    name = "folha"
    domains = ("folha.uol.com.br", "www1.folha.uol.com.br", "folha.com.br", "datafolha.folha.uol.com.br")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo da Folha carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_FOLHA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, banners e barras flutuantes da Folha."""
        try:
            result = page.evaluate(_CLEANUP_FOLHA_JS)
            return {"handler": "folha", **result}
        except Exception as exc:
            return {"handler": "folha", "error": str(exc)[:300]}

    def _scroll_to_title(self, page: Any) -> dict:
        """Na Folha, posiciona no topo absoluto (y = 0) para preservar o logotipo icônico e a autoria."""
        try:
            page.evaluate("window.scrollTo(0, 0)")
            return {"found": True, "y": 0, "header_preserved": True}
        except Exception as exc:
            return {"found": False, "error": str(exc)}
