#!/usr/bin/env python3
"""Scraper cirúrgico para o The Wall Street Journal (wsj.com).

Arquitetura do site:
- CMS Next.js / React com renderização editorial em alta precisão.
- Protegido por WAF PerimeterX (HUMAN Security) / Akamai Bot Manager, que bloqueia
  navegadores headless diretos com HTTP 401/403 e página de desafio/bloqueio
  ("O acesso está temporariamente restrito" / "Access Denied").
- Muros de assinatura (Paywall / Piano / cx-candybar / cx-sign-in-reminder).
- Barra de ticker no topo e banner de consentimento OneTrust.

Estratégia de captura:
- Tenta navegação direta; se bloqueado por 401/403/PerimeterX, consulta
  automaticamente espelhos de alta fidelidade (Archive.today / Archive.ph / Jina Reader)
  que preservam o DOM integral, estilos CSS e imagens editoriais autênticas.
- Injeta <base href> e remove scripts executáveis para impedir congelamentos de rede e reativação de barreiras.
- Higienização cirúrgica: remove réguas do archive, remove botões de assinatura/login no cabeçalho,
  elimina barra vazia de tickers e enquadra com elegância o clássico cabeçalho do WSJ, chapéu,
  título, autor com foto e imagem de capa da matéria.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import requests

from scripts.screenshots.base import (
    BaseScraper,
    DEFAULT_VIEWPORT,
    MIN_SHOT_BYTES,
    _is_blank,
    domain_from_url,
)
from scripts.screenshots.paywall import WafRecoveryMixin
from scripts.screenshots.sites import register

log = logging.getLogger("screenshots.wsj")


# ---------------------------------------------------------------------------
# JS de espera: aguarda título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_WSJ_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article h1',
    '[data-testid="headline"]',
    'article',
    'main',
    '#CONTENT',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para The Wall Street Journal
# ---------------------------------------------------------------------------

_CLEANUP_WSJ_JS = """() => {
  const removed = [];

  // 1. Remover barras de controle, cabeçalhos e réguas do Archive.today
  const archiveSels = [
    '#HEADER',
    '#DIVSHARE',
    '#DIVSHARE2',
    '#hashtags',
    'table#hashtags',
    '[id*="archive-banner"]',
    '#wm-ipp-base',
    '#wm-ipp',
  ];
  archiveSels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1, [id="CONTENT"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // Remover wrapper lateral de régua percentual do archive
  const ht = document.querySelector('table#hashtags');
  if (ht && ht.parentElement) {
    ht.parentElement.remove();
  }
  document.querySelectorAll('div').forEach(el => {
    const st = el.getAttribute('style') || '';
    if (st.includes('right:1028px') || st.includes('right: 1028px') || st.includes('z-index:99999999')) {
      el.remove();
    }
  });

  // 2. Destravar html e body com fundo 100% branco limpo
  const docEl = document.documentElement;
  docEl.style.setProperty('background-color', '#FFFFFF', 'important');
  docEl.style.setProperty('overflow', 'auto', 'important');
  docEl.style.setProperty('height', 'auto', 'important');
  docEl.style.setProperty('position', 'static', 'important');

  if (document.body) {
    document.body.style.setProperty('background-color', '#FFFFFF', 'important');
    document.body.style.setProperty('overflow', 'auto', 'important');
    document.body.style.setProperty('height', 'auto', 'important');
    document.body.style.setProperty('position', 'static', 'important');
  }

  // Ajustar containers do archive para remover bordas e fundos cinzas
  const solid = document.getElementById('SOLID');
  if (solid) {
    solid.style.setProperty('background-color', '#FFFFFF', 'important');
    solid.style.setProperty('box-shadow', 'none', 'important');
    solid.style.setProperty('border', 'none', 'important');
    solid.style.setProperty('padding', '0px', 'important');
  }

  const content = document.getElementById('CONTENT');
  if (content) {
    content.style.setProperty('border', 'none', 'important');
    content.style.setProperty('box-shadow', 'none', 'important');
    content.style.setProperty('margin', '0 auto', 'important');
    content.style.setProperty('width', '100%', 'important');
    content.style.setProperty('max-width', '1350px', 'important');
  }

  // 3. WSJ: remover ticker bar vazia, botões de assinatura/login, lembretes e anúncios
  const removeSels = [
    'button[aria-label="View Ticker Set Options"]',
    'button[aria-label*="Ticker"]',
    '#cx-candybar',
    '#cx-sign-in-reminder',
    '#cx-customer-nav-subscribe-btn',
    'a[href*="/client/login"]',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '[class*="subscribe-button"]',
    'button[data-testid="subscribe-button"]',
    '[class*="SnippetStrip"]',
    '[class*="paywall"]',
    '[class*="Paywall"]',
    '[id*="ad-"]',
    '[id*="google_ads"]',
    '.ad-container',
  ];

  removeSels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1')) return;
      if (sel.includes('Ticker') && el.closest('div[style*="min-height:32px"]')) {
        const topBar = el.closest('div[style*="min-height:32px"]');
        if (topBar && topBar.parentElement && topBar.parentElement.parentElement) {
          topBar.parentElement.parentElement.remove();
        } else {
          el.remove();
        }
      } else {
        el.remove();
      }
      removed.push(sel);
    });
  });

  // Remover faixa de ticker se remanescente
  document.querySelectorAll('div').forEach(el => {
    const st = el.getAttribute('style') || '';
    if (st.includes('min-height:32px') && st.includes('border-bottom-color:rgb(226, 226, 226)')) {
      el.remove();
    }
  });

  // Limpar fundos cinzas residuais do cabeçalho
  document.querySelectorAll('div').forEach(el => {
    const st = el.getAttribute('style') || '';
    if (st.includes('background-color:rgb(238, 238, 238)') || st.includes('background-color:#EEEEEE') || st.includes('background-color: #EEEEEE')) {
      el.style.setProperty('background-color', '#FFFFFF', 'important');
    }
  });

  // 4. Forçar carregamento e exibição de imagens
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    img.decoding = 'sync';
    img.style.setProperty('display', 'block', 'important');
    img.style.setProperty('visibility', 'visible', 'important');
  });

  return {removed, count: removed.length};
}"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@register("wsj.com", "online.wsj.com")
class WSJScraper(WafRecoveryMixin, BaseScraper):
    """Handler cirúrgico para The Wall Street Journal (wsj.com)."""

    name = "wsj"
    domains = ("wsj.com", "online.wsj.com")
    recovery_base_url = "https://www.wsj.com/"

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_WSJ_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, banners e botões do WSJ.

        Handler exclusivo e funcional — não delega para a camada genérica.
        """
        try:
            result = page.evaluate(_CLEANUP_WSJ_JS)
            return {"handler": "wsj", "skip_generic": True, **result}
        except Exception as exc:
            return {"handler": "wsj", "skip_generic": True, "error": str(exc)[:300]}

    def capture(self, url: str, dest: Path) -> dict:
        """Captura screenshot limpo do The Wall Street Journal.

        Se a navegação direta sofrer bloqueio WAF 401/403 / PerimeterX,
        recupera o HTML limpo da matéria via WafRecoveryMixin (Archive.today ->
        Jina Reader), renderiza o DOM com os estilos oficiais e executa a
        higienização visual com a tipografia e cabeçalhos do WSJ.
        """
        from scripts.screenshots.paywall import detect_block

        result: dict[str, Any] = {
            "url": url,
            "domain": domain_from_url(url),
            "handler": self.name,
            "ok": False,
            "path": None,
            "http_status": None,
            "error": None,
            "meta": {},
        }

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            result["error"] = f"playwright não instalado: {exc}"
            return result

        try:
            with sync_playwright() as pw:
                browser, ctx = self._launch_context(pw)
                page = ctx.new_page()
                self._apply_stealth(page)

                # 1. Tentar navegação direta inicial
                direct_blocked = False
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=min(self.timeout_ms, 20_000))
                    result["http_status"] = resp.status if resp else None
                    page_title = (page.title() or "").lower()
                    page_text = ""
                    try:
                        page_text = page.inner_text("body", timeout=2000).lower()
                    except Exception:
                        pass

                    if (
                        result["http_status"] in (401, 403, 429)
                        or "temporariamente restrito" in page_text
                        or "access denied" in page_text
                        or "perimeterx" in page_text
                        or "are you a robot" in page_text
                        or "just a moment..." in page_title
                        or "enable js" in page_title
                    ):
                        direct_blocked = True
                except Exception:
                    direct_blocked = True

                # 2. Se bloqueado por WAF/PerimeterX, usar recuperação de alta fidelidade
                if direct_blocked:
                    html, base_href = self.fetch_recovered_html(url)
                    if html:
                        clean_html = self.prepare_recovered_html(html, base_href)

                        def _restore_img_src(match: re.Match) -> str:
                            tag = match.group(0)
                            m_orig = re.search(r'currentsourceurl=["\'](https?://[^"\']+)["\']', tag, re.I)
                            if m_orig:
                                orig_url = m_orig.group(1)
                                tag = re.sub(r'\bsrc=["\'][^"\']+["\']', f'src="{orig_url}"', tag)
                            return tag

                        clean_html = re.sub(r"<img\b[^>]+>", _restore_img_src, clean_html, flags=re.I)
                        if base_href:
                            clean_html = re.sub(
                                r"<head\b[^>]*>",
                                f'<head><base href="{base_href}">',
                                clean_html,
                                count=1,
                                flags=re.IGNORECASE,
                            )
                        try:
                            page.goto("about:blank", timeout=5000)
                        except Exception:
                            pass
                        page.set_content(clean_html, wait_until="domcontentloaded")
                        result["http_status"] = 200
                        result["meta"]["retrieval_route"] = "archive_mirror"
                    else:
                        result["http_status"] = result["http_status"] or 403
                        result["error"] = f"HTTP {result['http_status']} (bloqueio WAF PerimeterX no The Wall Street Journal)"
                        page.close()
                        ctx.close()
                        browser.close()
                        return result

                # 3. Esperar conteúdo renderizar
                content_ok = self.wait_for_content(page)
                result["meta"]["content_found"] = content_ok

                # 4. Estilos e fontes
                self._wait_for_styles(page)

                # 5. Fechar cookies / consentimento
                cookie_sel = self._dismiss_cookies(page)
                result["meta"]["cookie_dismissed"] = cookie_sel

                # 6. Injetar CSS genérico
                self._inject_cleanup_css(page)

                # 7. Forçar lazy images
                self._force_lazy_images(page)

                # 8. Limpeza cirúrgica específica do WSJ
                cleanup_info = self.cleanup(page)
                result["meta"]["cleanup"] = cleanup_info

                # 9. Limpeza de placeholders
                self._clean_placeholders(page)

                # 10. Posicionar no topo / cabeçalho com conforto editorial
                h1 = page.query_selector("h1")
                if h1:
                    bb = h1.bounding_box()
                    if bb and bb["y"] > 350:
                        y = max(0, bb["y"] - 140)
                        page.evaluate(f"window.scrollTo(0, {y})")
                else:
                    title_info = self._scroll_to_title(page)
                    result["meta"]["title"] = title_info

                # 11. Pausa final para estabilização de layout
                page.wait_for_timeout(800)

                # 12. Capturar
                self._take_screenshot(page, dest)

                page.close()
                ctx.close()
                browser.close()

                # 13. Validar arquivo gerado
                if not dest.exists() or dest.stat().st_size < MIN_SHOT_BYTES:
                    result["error"] = "screenshot muito pequeno ou inexistente"
                elif _is_blank(dest):
                    result["error"] = "screenshot em branco (luminância uniforme)"
                else:
                    result["ok"] = True
                    result["path"] = str(dest)

        except Exception as exc:
            result["error"] = str(exc)[:500]
            if dest.exists() and dest.stat().st_size > MIN_SHOT_BYTES:
                result["path"] = str(dest)

        return result
