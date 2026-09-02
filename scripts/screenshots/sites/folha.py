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

  // 3. Remover barras de assinatura/ofertas e login-bars (topo e rodapé)
  document.querySelectorAll('.c-subscribe-wall, #paywall-banner, .c-news-login-wall, .banner-lgpd-consent, #lgpd-banner, .c-push-notification, .c-top-bar, .c-bottom-fixed, [class*="login-bar"], [class*="bottom-bar"]').forEach(el => {
    if (el.querySelector('.c-news__body, .c-signature, h1')) return;
    el.remove();
    removed.push(el.className || 'subscription-banner');
  });

  // Remover faixas de texto de assinatura / oferta
  document.querySelectorAll('div, section, aside, header').forEach(el => {
    if (el.querySelector('article, h1, .c-news__body')) return;
    const t = (el.innerText || '').trim().toLowerCase();
    if ((t.includes('oferta especial') && t.includes('assine')) || t.includes('já é assinante?')) {
      el.remove();
      removed.push('text-offer-banner');
    }
  });

  // 4. Remover publicidades conhecidas e blocos vazios acima/dentro da matéria
  document.querySelectorAll('.c-top-banner, .banner--leaderboard, .banner--super, .banner--halfpage, .c-advertising-placeholder, .c-advertising, [id*="google_ads"], .taboola-container').forEach(e => {
    const parentBlock = e.closest('.block') || e;
    if (!parentBlock.querySelector('.c-news__body, .c-signature, h1')) {
      parentBlock.remove();
      removed.push('ad-block');
    }
  });

  // 5. Remover barras flutuantes de download/share
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
