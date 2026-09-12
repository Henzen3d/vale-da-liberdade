#!/usr/bin/env python3
"""Scraper cirúrgico para o Terra Brasil Notícias (terrabrasilnoticias.com).

Arquitetura do site:
- CMS WordPress com tema JNews (.jeg_*).
- O texto integral da matéria vem no HTML dentro de ``article``, ``.entry-content`` ou ``.content-inner``.
- Manchete em ``h1.jeg_post_title``.
- Sem paywall rígido, mas com presença de:
  - Banners de publicidade no topo, laterais e entre parágrafos (.jeg_ad, .ads-wrapper, Taboola)
  - Botão flutuante de WhatsApp/Telegram ("Receba nossas notícias", .jeg_share_button, .share-float)
  - Barra de compartilhamento lateral/inferior (.jeg_sticky_share)
  - Rótulos órfãos de anúncios ("Anúncios", "Publicidade")
- O cabeçalho com a marca/logo do Terra Brasil Notícias é preservado no topo de forma estática.
"""
from __future__ import annotations

from typing import Any

from scripts.screenshots.base import BaseScraper
from scripts.screenshots.sites import register


# ---------------------------------------------------------------------------
# JS de espera: aguarda o título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_TBN_CONTENT_JS = """() => {
  const sels = [
    'h1.jeg_post_title',
    'h1.entry-title',
    'h1',
    'article h1',
    '.entry-content',
    '.content-inner',
    'article',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Terra Brasil Notícias
# ---------------------------------------------------------------------------

_CLEANUP_TBN_JS = """() => {
  const removed = [];

  // 1. Remover banners de publicidade (JNews ad slots, leaderboards, Taboola, Clever)
  const adSelectors = [
    '.jeg_ad',
    '.jeg_ad_top',
    '.jnews_header_top_ads',
    '.jnews_header_bottom_ads',
    '.jnews_article_bottom_ads',
    '.jnews_article_top_ads',
    '.code-block',
    '[class*="code-block"]',
    '#clever-core',
    '[id*="clever"]',
    '[class*="clever"]',
    '.ads-wrapper',
    '.ads_code',
    '[class*="publicidade"]',
    '[class*="advertising"]',
    '[id*="google_ads"]',
    '[id*="ad_"]',
    '[id*="dfp-"]',
    '.taboola-container',
    '.outbrain-container',
    '#taboola-below-article-thumbnails',
    '.ad-slot',
    '.trc_rbox_container',
    '.trc_exclude_overlay',
  ];

  adSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: nunca remover se contiver o corpo do artigo ou título
      if (el.querySelector('article, h1, .entry-content, .content-inner')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Remover sidebar com botão flutuante e widgets, scroll-to-top, Taboola fly-in e sticky shares
  const floatingSelectors = [
    '.jeg_sidebar',
    '.jeg_sticky_sidebar',
    '.theiaStickySidebar',
    '.jegStickyHolder',
    '.jscroll-to-top',
    '.jeg_scroll_top',
    '.share-float',
    '.jeg_sticky_share',
    '.jeg_share_button.share-float',
    '.jeg_btn-whatsapp',
    '[class*="btn-whatsapp"]',
    '[class*="trc_spotlight"]',
    '[class*="tbl-next"]',
    '.sticky-footer',
    '.floating-bar',
    '.c-share-bar--floating',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.banner-lgpd',
    '.lgpd-consent',
    '.c-push-notification',
  ];

  floatingSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      el.remove();
      removed.push(sel);
    });
  });

  // 2.1 Alargar a coluna do artigo para 100% após a remoção da barra lateral
  const mainContent = document.querySelector('.jeg_main_content');
  if (mainContent) {
    mainContent.classList.remove('col-md-8');
    mainContent.classList.add('col-md-12');
  }

  // 2.2 Limpar rótulos textuais órfãos "Anúncios" / "Publicidade"
  document.querySelectorAll('p, span, div').forEach(el => {
    const t = (el.innerText || '').trim().toLowerCase();
    if (t === 'anúncios' || t === 'anuncios' || t === 'publicidade') {
      if (!el.querySelector('img, video, iframe')) {
        el.remove();
        removed.push('text-ad-label');
      }
    }
  });

  // 3. Tornar o cabeçalho institucional (logo Terra Brasil Notícias) estático e visível
  document.querySelectorAll('header, .header, .jeg_header, .jeg_header_wrapper, .jeg_topbar').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // Desativar comportamentos sticky da barra do tema JNews
  document.querySelectorAll('.jeg_stickybar, .jeg_navbar_wrapper').forEach(el => {
    el.classList.remove('jeg_stickybar');
    el.style.setProperty('position', 'static', 'important');
  });

  // 4. Destravar scroll, alturas e overflow no html e body
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'position', 'static');
  force(document.documentElement, 'height', 'auto');
  if (document.body) {
    force(document.body, 'overflow', 'auto');
    force(document.body, 'position', 'static');
    force(document.body, 'height', 'auto');
  }

  // 5. Garantir que parágrafos, fotos e legendas estejam 100% visíveis
  document.querySelectorAll('article *, .entry-content *, .content-inner *').forEach(el => {
    if (el.style.filter && el.style.filter !== 'none') el.style.filter = 'none';
    if (el.style.opacity && el.style.opacity !== '1') el.style.opacity = '1';
    if (el.style.display === 'none') {
      if (!el.matches?.('script, style, [class*="ad"], [class*="banner"]')) {
        el.style.display = '';
      }
    }
  });

  // 6. Forçar imagens da matéria com eager loading
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

@register("terrabrasilnoticias.com")
class TerraBrasilNoticiasScraper(BaseScraper):
    """Handler cirúrgico para o Terra Brasil Notícias."""

    name = "terrabrasilnoticias"
    domains = ("terrabrasilnoticias.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo do Terra Brasil Notícias carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_TBN_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de banners, botões de WhatsApp flutuantes e anúncios."""
        try:
            page.add_style_tag(content="""
                .share-float, .jeg_sticky_share, .jeg_btn-whatsapp, [class*="btn-whatsapp"], [class*="share-float"],
                .theiaStickySidebar, .jeg_sticky_sidebar, .jscroll-to-top, .jeg_scroll_top,
                [class*="trc_spotlight"], [class*="tbl-next"],
                .jeg_ad_top, .jnews_header_top_ads, .jnews_header_bottom_ads, .code-block, [class*="code-block"],
                #clever-core, [id*="clever"], [class*="clever"] {
                    display: none !important;
                    visibility: hidden !important;
                    opacity: 0 !important;
                    pointer-events: none !important;
                    height: 0 !important;
                }
            """)
        except Exception:
            pass
        try:
            result = page.evaluate(_CLEANUP_TBN_JS)
            return {"handler": "terrabrasilnoticias", **result}
        except Exception as exc:
            return {"handler": "terrabrasilnoticias", "error": str(exc)[:300]}

    def _scroll_to_title(self, page: Any) -> dict:
        """No Terra Brasil Notícias, o cabeçalho institucional e a matéria cabem em y=0."""
        page.evaluate("window.scrollTo(0, 0)")
        return {"found": True, "y": 0, "sticky": 0}
