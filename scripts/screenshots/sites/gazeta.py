#!/usr/bin/env python3
"""Scraper cirúrgico para a Gazeta do Povo (gazetadopovo.com.br).

Arquitetura do site:
- Aplicação React / Next.js com SCSS Modules (classes com hash gerado).
- O texto integral da matéria vem no HTML original (dentro de ``article`` e ``[class*="postBody"]``).
- Paywall baseado em Piano.io / Tinypass (bloqueado em nível de rede no BaseScraper e limpo no DOM).
- Banners fixos de topo (``[class*="topBannerAd"]``), laterais (``[class*="adBanner"]``) e rodapé
  (``[class*="adsFooter"]``) precisam ser removidos cirurgicamente.
- A barra flutuante de compartilhamento na lateral esquerda (``[class*="postMidiasShare"]``) é ocultada.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_GAZETA_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article',
    '[class*="postContent"]',
    '[class*="postBody"]',
    '[class*="articleBody"]',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Gazeta do Povo
# ---------------------------------------------------------------------------

_CLEANUP_GAZETA_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade fixos, laterais e rodapé
  const adSelectors = [
    '[class*="topBannerAd"]',
    '[class*="adBanner"]',
    '[class*="adsFooter"]',
    '[class*="postAsideBanner"]',
    '[class*="adContainer"]',
    '#tribunaVideoSlider',
    '[id*="google_ads"]',
    '.taboola-container',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o artigo
      if (el.querySelector('article, h1, [class*="postBody"], [class*="postContent"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover elementos e modais de paywall (Piano.io / Tinypass / Assine)
  const paywallSelectors = [
    '[class*="pianoCTA"]',
    '[class*="pianoRecommender"]',
    '#pianoCTAHeader',
    '.tp-modal',
    '.tp-backdrop',
    '[class*="modalWrapper"]',
    '[class*="assineBar"]',
    '[class*="pushNotification"]',
    '#onetrust-banner-sdk',
    '.banner-lgpd',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, [class*="postBody"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover barra flutuante de compartilhamento na lateral esquerda
  document.querySelectorAll('[class*="postMidiasShare"]').forEach(el => {
    el.remove();
    removed.push('floating-share-bar');
  });

  // 4. Configurar cabeçalho como static para não sobrepor o H1
  document.querySelectorAll('header, #header-gp-sticky, [class*="headerGp"]').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 5. Forçar carregamento das fotos da matéria
  document.querySelectorAll('img').forEach(img => {
    if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
      img.src = img.dataset.src;
    }
    img.loading = 'eager';
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
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

  // 7. Garantir que parágrafos e corpo da matéria estejam visíveis
  document.querySelectorAll('article *, [class*="postBody"] *, [class*="postContent"] *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') el.style.display = '';
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("gazetadopovo.com.br")
class GazetaDoPovoScraper(BaseScraper):
    """Handler cirúrgico para a Gazeta do Povo."""

    name = "gazetadopovo"
    domains = ("gazetadopovo.com.br",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_GAZETA_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall Piano, banners e overlays da Gazeta do Povo."""
        try:
            result = page.evaluate(_CLEANUP_GAZETA_JS)
            return {"handler": "gazetadopovo", **result}
        except Exception as exc:
            return {"handler": "gazetadopovo", "error": str(exc)[:300]}
