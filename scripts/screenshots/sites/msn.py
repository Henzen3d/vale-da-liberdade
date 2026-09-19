#!/usr/bin/env python3
"""Scraper cirúrgico para MSN (msn.com).

Arquitetura do site:
- Microsoft News / MSN é uma Single Page Application (SPA) com Web Components
  (fluent-design-system-provider, views-header-wc, cp-article-reader, etc.).
- A manchete principal reside no cabeçalho do artigo (<views-header-wc> h1.viewsHeaderText).
- A foto de destaque (hero) reside dentro de <cp-article-image>.
- O banner de anúncio de topo (.consumption-page-banner-wrapper, [id*="views-banner-ad"])
  é removido cirurgicamente para elevar o cabeçalho institucional do MSN, a marca do veículo parceiro
  (ex.: Revista Fórum, Estadão, etc.) e a manchete para o topo do viewport.
- Remove a barra lateral de anúncios e links patrocinados (.consumption-page-gridarea_rail).
- Remove a barra flutuante de reações lateral (action-tray).
- Trata o botão "Continuar lendo" (.article-cont-read-button, #continuousReadingContainer),
  destravando a altura completa do leitor (cp-article-reader).
- Trata o modal/banner de consentimento de cookies da Microsoft (#cmp-accept-btn-handler, #mscmp-banner-container).
- Mantém o cabeçalho oficial do MSN no topo e centraliza elegantemente o conteúdo da notícia.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda os web components ou artigo do MSN hidratar
# ---------------------------------------------------------------------------

_WAIT_MSN_CONTENT_JS = """() => {
  // 1. Tentar aceitar cookie de imediato para liberar renderização
  try {
    const cmpBtn = document.querySelector('#cmp-accept-btn-handler, #cmp-reject-all-handler');
    if (cmpBtn) cmpBtn.click();
  } catch (e) {}

  // 2. Verificar seletores do MSN
  const sels = [
    'views-header-wc',
    'consumption-page',
    'cp-article-reader',
    'cp-article',
    'article.article-reader-container',
    '.consumption-page-content-wrapper',
    'desktop-article-content',
    'h1',
    'article',
  ];

  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && (el.offsetHeight > 0 || el.offsetWidth > 0 || (el.children && el.children.length > 0))) {
      return {found: true, selector: s};
    }
  }

  // 3. Fallback: verificar se há texto significativo no body
  const bodyText = (document.body ? document.body.innerText || '' : '').trim();
  if (bodyText.length > 150) {
    return {found: true, selector: 'body-text'};
  }

  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza e expansão para MSN
# ---------------------------------------------------------------------------

_CLEANUP_MSN_JS = """() => {
  const removed = [];

  // 1. Descartar modal e banner de privacidade/cookies Microsoft CMP
  try {
    const cmpBtn = document.querySelector('#cmp-accept-btn-handler, #cmp-reject-all-handler');
    if (cmpBtn) cmpBtn.click();
  } catch (e) {}

  const cookieSels = [
    '#mscmp-banner-container',
    '#cmp-banner-sdk',
    '#cmpbox',
    '.cmp-container',
    '[id*="cmp-"]',
  ];
  cookieSels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Expandir matéria ("Continuar lendo" / read more)
  try {
    const readMoreBtn = document.querySelector(
      '.article-cont-read-button, [id*="continue-reading"], #continuousReadingContainer button, fluent-button.article-cont-read-button'
    );
    if (readMoreBtn) {
      readMoreBtn.click();
    }
    const contContainer = document.querySelector('#continuousReadingContainer, .article-cont-read-container');
    if (contContainer) {
      contContainer.remove();
      removed.push('#continuousReadingContainer');
    }
  } catch (e) {}

  // Destravar altura máxima do leitor para exibir a matéria inteira
  document.querySelectorAll(
    '.article-reader-container, .article-page, cp-article-reader, [class*="article-content"], desktop-article-content'
  ).forEach(el => {
    el.style.setProperty('max-height', 'none', 'important');
    el.style.setProperty('overflow', 'visible', 'important');
  });

  // 3. Remover anúncios do topo, intra-artigo e trilhos laterais
  const adSelectors = [
    '.consumption-page-banner-wrapper',
    '[id*="views-banner-ad"]',
    '.consumption-page-banner-ad',
    'display-ads',
    'views-native-ad',
    '.articlePageIntraArticleFullWidth',
    '.ad-slot-placeholder',
    '[class*="intra-ad"]',
    '[class*="full-bleed-image-intra-ad"]',
    '.consumption-page-gridarea_rail',
    '[id*="ad-slot"]',
    '[class*="native-ad"]',
    '[id*="google_ads"]',
    '.taboola-container',
    '[id*="taboola"]',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o cabeçalho ou o leitor de artigo
      if (el.querySelector('views-header-wc, cp-article-reader, cp-article, .viewsHeaderText')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 4. Remover elementos flutuantes parasitas (ações/reações, comentários, feedback)
  const floatingSelectors = [
    'action-tray',
    '[class*="action-tray"]',
    '[class*="reactions"]',
    'homepage-footer',
    'footer.footer',
    'msn-feedback-link',
    '[class*="comments-button"]',
    '[id*="comments"]',
    'fluent-button.skip-to-link',
    '.consumption-page-feed-wrapper',
    '#floating-bottom-bar',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 5. Ajustar grid do MSN para centralizar o conteúdo do artigo com boa respiração
  const contentArea = document.querySelector('.consumption-page-gridarea_content');
  if (contentArea) {
    contentArea.style.setProperty('max-width', '1120px', 'important');
    contentArea.style.setProperty('margin', '0 auto', 'important');
    contentArea.style.setProperty('width', '100%', 'important');
  }

  const struct = document.querySelector('.consumption-page-structure');
  if (struct) {
    struct.style.setProperty('grid-template-columns', '1fr', 'important');
    struct.style.setProperty('justify-items', 'center', 'important');
  }

  // 6. Assegurar que a barra superior institucional do MSN seja estática
  document.querySelectorAll('header, nav, fluent-design-system-provider > header, .viewsHeaderWrapper').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
  });

  // 7. Forçar imagens a carregar eagerly (inclusive no shadow DOM)
  function eagerlyLoadImages(root = document) {
    if (!root) return;
    if (root.querySelectorAll) {
      root.querySelectorAll('img').forEach(img => {
        img.loading = 'eager';
        if (img.dataset.src && (!img.src || img.src.startsWith('data:'))) {
          img.src = img.dataset.src;
        }
        img.style.setProperty('display', 'block', 'important');
        img.style.setProperty('visibility', 'visible', 'important');
      });
    }
    if (root.shadowRoot) eagerlyLoadImages(root.shadowRoot);
    if (root.children) {
      for (const ch of root.children) {
        eagerlyLoadImages(ch);
      }
    }
  }
  eagerlyLoadImages(document);

  // 8. Destravar scroll no html e body
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

@register("msn.com", "www.msn.com")
class MsnScraper(BaseScraper):
    """Handler cirúrgico para MSN (msn.com)."""

    name = "msn"
    domains = ("msn.com", "www.msn.com")

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo e os web components do MSN carregarem no DOM."""
        for _ in range(20):
            try:
                info = page.evaluate(_WAIT_MSN_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1500)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners de topo, rails de anúncios, expansão do artigo e CMP."""
        try:
            result = page.evaluate(_CLEANUP_MSN_JS)
            return {"handler": "msn", **result}
        except Exception as exc:
            return {"handler": "msn", "error": str(exc)[:300]}

    def _scroll_to_title(self, page: Any) -> dict:
        """Posiciona o viewport no topo para enquadrar o logo MSN, veículo parceiro, manchete e hero."""
        try:
            scroll_js = """() => {
                // Com o banner de anúncio de topo removido pelo cleanup,
                // o topo (y = 0) já enquadra perfeitamente o cabeçalho do MSN,
                // a marca da fonte/parceiro, o título e o topo da imagem hero.
                window.scrollTo(0, 0);
                return {found: true, y: 0, handler: 'msn'};
            }"""
            return page.evaluate(scroll_js)
        except Exception as exc:
            return {"found": False, "error": str(exc)}
