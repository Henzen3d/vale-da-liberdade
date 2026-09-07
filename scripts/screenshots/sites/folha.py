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

  // 2. Desativar classes de paywall SEM remover containers de conteúdo
  //    (A Folha envolve o artigo em <div class="container j-paywall">)
  document.querySelectorAll('.j-paywall').forEach(el => {
    el.classList.remove('j-paywall');
    removed.push('class:j-paywall');
  });

  // 3. Remover o espaçador elástico (responsável por 206px de espaço morto vazio no topo)
  document.querySelectorAll('.js-c-elastic-header').forEach(el => {
    el.remove();
    removed.push('elastic-header-spacer');
  });

  // 4. Remover barras de assinatura/ofertas, popups e login-bars (topo e rodapé)
  const bannerSelectors = [
    '.c-subscribe-wall',
    '#paywall-banner',
    '.c-news-login-wall',
    '.banner-lgpd-consent',
    '#lgpd-banner',
    '.c-push-notification',
    '.c-top-bar',
    '.c-bottom-fixed',
    '.c-top-signup',
    '[class*="top-signup"]',
    '[class*="login-bar"]',
    '[class*="bottom-bar"]',
    '.c-accessibility',
    '[class*="skip-link"]',
    'a[href^="#conteudo"]',
    'a[href^="#menu"]',
    'a[href^="#rodape"]',
  ];
  document.querySelectorAll(bannerSelectors.join(', ')).forEach(el => {
    if (el.closest('header, .l-header') || el.querySelector('.c-news__body, .c-signature, h1')) return;
    el.remove();
    removed.push(el.className || 'subscription-banner');
  });

  // 5. Limpar faixas de oferta secundárias DENTRO do header sem remover o logo/menu
  document.querySelectorAll('.l-header > div').forEach(div => {
    if (div.classList.contains('l-header__wrapper') && !div.classList.contains('u-no-print')) {
      return; // Preserva a barra principal da logo e do menu
    }
    const t = (div.innerText || '').toLowerCase();
    if (t.includes('oferta especial') || t.includes('benefício do assinante') || div.classList.contains('u-no-print')) {
      div.remove();
      removed.push('header-offer-subbar');
    }
  });

  // 6. Remover faixas de texto de assinatura / oferta (NUNCA remover o cabeçalho)
  document.querySelectorAll('div, section, aside').forEach(el => {
    if (el.closest('header, .l-header')) return;
    if (el.querySelector('article, h1, .c-news__body, [itemprop="articleBody"]')) return;
    const t = (el.innerText || '').trim().toLowerCase();
    if ((t.includes('oferta especial') && t.includes('assine')) || t.includes('já é assinante?')) {
      el.remove();
      removed.push('text-offer-banner');
    }
  });

  // 7. Garantir que o cabeçalho oficial com a logo da Folha fique estático e visível
  const header = document.querySelector('header, .l-header');
  if (header) {
    header.style.setProperty('position', 'static', 'important');
    header.style.setProperty('display', 'block', 'important');
    header.style.setProperty('visibility', 'visible', 'important');
    header.style.setProperty('opacity', '1', 'important');
    header.style.setProperty('height', 'auto', 'important');
  }

  // 8. Remover publicidades conhecidas e blocos vazios acima/dentro da matéria
  document.querySelectorAll('.c-top-banner, .banner--leaderboard, .banner--super, .banner--halfpage, .c-advertising-placeholder, .c-advertising, [id*="google_ads"], .taboola-container').forEach(e => {
    const parentBlock = e.closest('.block') || e;
    if (!parentBlock.querySelector('.c-news__body, .c-signature, h1')) {
      parentBlock.remove();
      removed.push('ad-block');
    }
  });

  // 9. Remover barras flutuantes de download/share
  document.querySelectorAll('.c-share-bar--floating, .c-more-options--sticky, .c-app-download-banner, .c-floating-video').forEach(el => {
    el.remove();
    removed.push('floating-bar');
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

  // 7. Garantir que parágrafos e assinaturas estejam 100% visíveis
  document.querySelectorAll('.c-news__body *, [itemprop="articleBody"] *, .c-signature *').forEach(el => {
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
