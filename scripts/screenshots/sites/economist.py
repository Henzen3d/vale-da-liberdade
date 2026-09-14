#!/usr/bin/env python3
"""Scraper cirúrgico para o The Economist (economist.com).

Arquitetura do site:
- CMS com tipografia Economist Serif e layout editorial clássico.
- Protegido por WAF Cloudflare + DataDome, que bloqueia navegadores headless
  diretos com HTTP 403 e desafio de verificação ("Just a moment..." / "Please enable JS").
- Barreiras de paywall e assinatura (.subscribe-barrier, [class*="paywall"]).
- Banners de cookies (#onetrust-banner-sdk).

Estratégia de captura:
- Tenta navegação direta; se bloqueado por 403/Cloudflare/DataDome, consulta
  automaticamente espelhos e arquivos de alta fidelidade (Archive.today / Archive.ph / Jina Reader)
  que preservam o DOM integral, estilos CSS e ilustrações originais.
- Injeta <base href> e remove scripts executáveis para impedir congelamentos de rede e ativação de barreiras.
- Higienização cirúrgica: remove barras do arquivo, remove bordas cinzas, garante fundo limpo,
  preserva a marca icônica vermelha (The Economist) e enquadra perfeitamente o título e a ilustração.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from scripts.screenshots.base import (
    BaseScraper,
    DEFAULT_VIEWPORT,
    MIN_SHOT_BYTES,
    _is_blank,
    domain_from_url,
)
from scripts.screenshots.sites import register

log = logging.getLogger("screenshots.economist")


# ---------------------------------------------------------------------------
# JS de espera: aguarda título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_ECONOMIST_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article h1',
    '[data-testid="headline"]',
    '#new-article-template',
    'article',
    'main',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para The Economist
# ---------------------------------------------------------------------------

_CLEANUP_ECONOMIST_JS = """() => {
  const removed = [];

  // 1. Remover barras de controle e réguas do Archive.today (se recuperado via espelho)
  const archiveSels = [
    '#HEADER',
    '#DIVSHARE',
    '#hashtags',
    'table#hashtags',
    '[id*="archive-banner"]',
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
    if (st.includes('right:1028px') || st.includes('right: 1028px')) {
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
    content.style.setProperty('max-width', '1400px', 'important');
  }

  // 3. Tornar o cabeçalho institucional (The Economist) estático e visível
  document.querySelectorAll('header, nav, [class*="masthead"], [class*="header"]').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 4. Remover overlays e modais de paywall/cookies
  const removeSels = [
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '[class*="paywall"]',
    '[class*="subscribe-barrier"]',
    '[class*="advert"]',
    '[id*="ad-"]',
    '[id*="google_ads"]',
    '.ad-container',
  ];
  removeSels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 5. Forçar imagens visíveis com eager loading
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

@register("economist.com")
class EconomistScraper(BaseScraper):
    """Handler cirúrgico para The Economist (economist.com)."""

    name = "economist"
    domains = ("economist.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_ECONOMIST_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de modais, paywall e anúncios do The Economist."""
        try:
            result = page.evaluate(_CLEANUP_ECONOMIST_JS)
            return {"handler": "economist", **result}
        except Exception as exc:
            return {"handler": "economist", "error": str(exc)[:300]}

    def _fetch_article_html(self, url: str) -> tuple[str | None, str | None]:
        """Recupera HTML autêntico da matéria via Archive.today ou Jina Reader.

        Returns:
            Tupla (html_content, base_href) ou (None, None).
        """
        # 1. Tentar espelhos do Archive.today (archive.ph, archive.today)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        for mirror in ("archive.ph", "archive.today", "archive.is"):
            try:
                target = f"https://{mirror}/newest/{url}"
                r = requests.get(target, headers=headers, timeout=12, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 40_000:
                    low = r.text[:2000].lower()
                    if "just a moment..." not in low and "complete a captcha" not in low:
                        return r.text, f"https://{mirror}/"
            except Exception as exc:
                log.debug("Espelho %s falhou para %s: %s", mirror, url, exc)

        # 2. Fallback: Jina Reader com formato HTML
        try:
            reader_url = f"https://r.jina.ai/{url}"
            resp = requests.get(
                reader_url,
                headers={"X-Return-Format": "html", "Accept": "text/html"},
                timeout=20,
            )
            if resp.status_code == 200 and len(resp.text) > 40_000:
                low = resp.text[:2000].lower()
                if "just a moment..." not in low and "please enable js" not in low:
                    return resp.text, "https://www.economist.com/"
        except Exception as exc:
            log.warning("Jina Reader falhou para %s: %s", url, exc)

        return None, None

    def capture(self, url: str, dest: Path) -> dict:
        """Captura screenshot limpo do The Economist.

        Se a navegação direta sofrer bloqueio WAF 403 / Cloudflare / DataDome,
        recupera o HTML limpo da matéria, renderiza o DOM com os estilos oficiais
        e executa a higienização visual com a tipografia e cabeçalhos do Economist.
        """
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
                    if (
                        result["http_status"] in (401, 403, 429)
                        or "just a moment..." in page_title
                        or "enable js" in page_title
                    ):
                        direct_blocked = True
                except Exception:
                    direct_blocked = True

                # 2. Se bloqueado por WAF/DataDome, usar recuperação de alta fidelidade
                if direct_blocked:
                    html, base_href = self._fetch_article_html(url)
                    if html:
                        clean_html = re.sub(
                            r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
                            "",
                            html,
                            flags=re.IGNORECASE,
                        )
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
                        result["error"] = f"HTTP {result['http_status']} (bloqueio WAF DataDome/Cloudflare no The Economist)"
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

                # 8. Limpeza cirúrgica específica do The Economist
                cleanup_info = self.cleanup(page)
                result["meta"]["cleanup"] = cleanup_info

                # 9. Limpeza de placeholders
                self._clean_placeholders(page)

                # 10. Posicionar no título H1
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
