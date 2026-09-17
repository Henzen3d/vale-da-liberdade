#!/usr/bin/env python3
"""Scraper cirúrgico para o Financial Times (ft.com).

Arquitetura do site:
- CMS com tipografia editorial característica (Financier Display / Metric VF).
- Fundo icônico salmão/pêssego institucional (#fff1e5 / #fdf0e6).
- Muro de paywall rígido com barreiras modais e de conteúdo
  (#barrier-content, .barrier, [data-trackable="barrier"], .barrier__content).
- Banners de cookies/consentimento (#onetrust-banner-sdk, .o-cookie-message).

Estratégia de captura:
- Tenta navegação direta; se detectar barreira de paywall (#barrier-content)
  ou bloqueio HTTP (401/403), consulta automaticamente espelhos de alta
  fidelidade (Archive.today / Archive.li / Archive.md / Jina Reader) que
  preservam o DOM integral, estilos CSS e imagens editoriais autênticas.
- Injeta <base href> e remove scripts executáveis para impedir bloqueios dinâmicos.
- Higienização cirúrgica: remove réguas e cabeçalhos do archive, elimina toolbars
  flutuantes de compartilhamento (#DIVSHARE, #article-progress), botões de myFT e
  assinatura/login, garantindo o fundo uniforme clássico (#fff1e5) e enquadrando
  com perfeição o cabeçalho do Financial Times, chapéu, título, fotografia e créditos.
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
from scripts.screenshots.sites import register

log = logging.getLogger("screenshots.ft")


# ---------------------------------------------------------------------------
# JS de espera: aguarda título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_FT_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article h1',
    '[data-trackable="headline"]',
    '.article__title',
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
# JS cirúrgico de limpeza para o Financial Times
# ---------------------------------------------------------------------------

_CLEANUP_FT_JS = """() => {
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
      el.remove();
      removed.push(sel);
    });
  });

  // Remove wrapper lateral de régua do archive
  document.querySelectorAll('div').forEach(el => {
    const st = el.getAttribute('style') || '';
    if (st.includes('right:1028px') || st.includes('right: 1028px') || st.includes('z-index: 1000000000')) {
      el.remove();
    }
  });

  // 2. Remover barreiras de paywall, banners de consentimento e modais do FT
  const barrierSels = [
    '#barrier-content',
    '.barrier',
    '[data-trackable="barrier"]',
    '.barrier__content',
    '.o-banner',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.o-cookie-message',
    '[class*="paywall"]',
    '[class*="subscribe-barrier"]',
    '#article-progress',
    '#share-modal-horizontal',
    '[data-trackable*="share"]',
    '[class*="article__tools"]',
  ];
  barrierSels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 3. Remover botões institucionais supérfluos (Subscribe, Sign In, Save, Add to myFT)
  document.querySelectorAll('button, a').forEach(el => {
    const t = (el.innerText || '').trim();
    if (t === 'Save' || t === 'Sign In' || t === 'Subscribe' || t.includes('Add to myFT') || t.includes('myFT')) {
      const parentUl = el.closest('ul');
      if (parentUl) {
        if (parentUl.parentElement && parentUl.parentElement.tagName === 'DIV') {
          parentUl.parentElement.remove();
        } else {
          parentUl.remove();
        }
      } else {
        el.remove();
      }
    }
  });

  // 4. Corrigir containers do archive (#SOLID / #CONTENT) para fundo limpo FT
  ['#SOLID', '#CONTENT'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.style.setProperty('background-color', '#fff1e5', 'important');
      el.style.setProperty('box-shadow', 'none', 'important');
      el.style.setProperty('border', 'none', 'important');
    }
  });

  // Remover fundos pretos/cinzas residuais de seções de wrapper
  document.querySelectorAll('*').forEach(el => {
    const bg = window.getComputedStyle(el).backgroundColor;
    if (bg === 'rgb(0, 0, 0)' || bg === 'black' || bg === 'rgb(34, 34, 34)') {
      if (el.tagName !== 'BUTTON' && !el.querySelector('img')) {
        el.style.setProperty('background-color', '#fff1e5', 'important');
      }
    }
  });

  // 5. Destravar html e body com fundo FT institucional (#fff1e5)
  const force = (el, prop, val) => el && el.style.setProperty(prop, val, 'important');
  force(document.documentElement, 'background-color', '#fff1e5');
  force(document.documentElement, 'overflow', 'auto');
  force(document.documentElement, 'height', 'auto');
  force(document.documentElement, 'position', 'static');

  if (document.body) {
    force(document.body, 'background-color', '#fff1e5');
    force(document.body, 'overflow', 'auto');
    force(document.body, 'height', 'auto');
    force(document.body, 'position', 'static');
  }

  // 6. Cabeçalho principal estático e visível
  document.querySelectorAll('header, [class*="o-header"]').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('background-color', '#fff1e5', 'important');
  });

  // 7. Forçar imagens visíveis com eager loading
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

@register("ft.com")
class FTScraper(BaseScraper):
    """Handler cirúrgico para o Financial Times (ft.com)."""

    name = "ft"
    domains = ("ft.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_FT_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de paywall, banners e barras do Financial Times."""
        try:
            result = page.evaluate(_CLEANUP_FT_JS)
            return {"handler": "ft", "skip_generic": True, **result}
        except Exception as exc:
            return {"handler": "ft", "skip_generic": True, "error": str(exc)[:300]}

    def _fetch_article_html(self, url: str) -> tuple[str | None, str | None]:
        """Recupera HTML autêntico da matéria via espelhos de arquivo ou Jina Reader.

        Returns:
            Tupla (html_content, base_href) ou (None, None).
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # 1. Tentar espelhos do Archive.today (archive.li, archive.md, archive.is, etc.)
        for mirror in ("archive.li", "archive.md", "archive.is", "archive.today", "archive.ph"):
            try:
                target = f"https://{mirror}/newest/{url}"
                r = requests.get(target, headers=headers, timeout=12, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 30_000:
                    low = r.text[:2000].lower()
                    if "just a moment..." not in low and "complete a captcha" not in low and "502 bad gateway" not in low:
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
            if resp.status_code == 200 and len(resp.text) > 25_000:
                low = resp.text[:2000].lower()
                if "just a moment..." not in low and "please enable js" not in low:
                    return resp.text, "https://www.ft.com/"
        except Exception as exc:
            log.warning("Jina Reader falhou para %s: %s", url, exc)

        return None, None

    def capture(self, url: str, dest: Path) -> dict:
        """Captura screenshot limpo do Financial Times.

        Se a navegação direta sofrer bloqueio WAF 401/403 ou paywall (#barrier-content),
        recupera o HTML limpo da matéria, renderiza o DOM com a tipografia e estilos
        oficiais e executa a higienização com o fundo salmão icônico do FT.
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
                    page.wait_for_timeout(1500)

                    # Verifica se o FT exibiu a barreira de paywall / oferta de assinatura
                    body_text = ""
                    try:
                        body_text = (page.inner_text("body", timeout=3000) or "").lower()
                    except Exception:
                        pass

                    has_barrier = (
                        "subscribe to unlock" in body_text
                        or "standard digital" in body_text
                        or "explore more offers" in body_text
                        or "exclusive for subscribers" in body_text
                        or bool(page.query_selector("#barrier-content, .barrier, [data-trackable='barrier'], [data-trackable*='paywall']"))
                    )
                    if result["http_status"] in (401, 403, 429) or has_barrier:
                        direct_blocked = True
                except Exception:
                    direct_blocked = True

                # 2. Se bloqueado ou com paywall, usar espelho de alta fidelidade
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
                        result["error"] = f"HTTP {result['http_status']} (paywall / bloqueio no Financial Times)"
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

                # 8. Limpeza cirúrgica específica do Financial Times
                cleanup_info = self.cleanup(page)
                result["meta"]["cleanup"] = cleanup_info

                # 9. Limpeza de placeholders
                self._clean_placeholders(page)

                # 10. Posicionar no título H1 com margem de respiro superior
                h1 = page.query_selector("h1")
                if h1:
                    bb = h1.bounding_box()
                    if bb and bb["y"] > 250:
                        y = max(0, bb["y"] - 120)
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
