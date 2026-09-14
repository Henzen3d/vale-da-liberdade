#!/usr/bin/env python3
"""Scraper cirúrgico para a Bloomberg (bloomberg.com).

Arquitetura do site:
- CMS Next.js / React com renderização em servidor e hidratação no cliente.
- CDN Fastly + WAF PerimeterX (HUMAN Security), que bloqueia navegadores
  headless diretos com HTTP 403 e desafio anti-robô ("Are you a robot?").
- Muro de assinatura "Fortress" (#fortress-container-root, #slidingBanner, ._columnWall_*).
- Modal de termos e consentimento (#cmp-consent-modal).
- Barra dupla de navegação (desktop + mobile injetadas juntas no DOM).
- Variáveis CSS no <html> que inserem padding vazio de leaderboard (--leaderboard-ad-height: 320px).

Estratégia de captura:
- Tenta navegação direta; se bloqueado por 403/PerimeterX, utiliza o proxy leitor
  (Jina Reader com X-Return-Format: html) para obter o HTML autêntico da matéria com seus estilos e imagens de assets.bwbx.io.
- Remove scripts executáveis para impedir travamentos de rede e ativação de paywalls.
- Aplica limpeza cirúrgica dos modais, paywall e anúncios, preservando o logotipo
  institucional e o enquadramento editorial (chapéu Opinion, título H1, data, foto e autor).
"""
from __future__ import annotations

import logging
import os
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

log = logging.getLogger("screenshots.bloomberg")


# ---------------------------------------------------------------------------
# JS de espera: aguarda título e corpo da matéria
# ---------------------------------------------------------------------------

_WAIT_BLOOMBERG_CONTENT_JS = """() => {
  const sels = [
    'h1',
    'article h1',
    '[data-testid="headline"]',
    'article',
    '[class*="articleLayout"]',
    '[class*="gridLayout"]',
    'main',
  ];
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.offsetHeight > 0) return {found: true, selector: s};
  }
  return {found: false, selector: null};
}"""


# ---------------------------------------------------------------------------
# JS cirúrgico de limpeza para Bloomberg
# ---------------------------------------------------------------------------

_CLEANUP_BLOOMBERG_JS = """() => {
  const removed = [];

  // 1. Remover modais de consentimento, termos e paywall da Bloomberg
  const paywallSelectors = [
    '#fortress-container-root',
    '#cmp-consent-modal',
    '#slidingBanner',
    '[class*="_sheet_"]',
    '[class*="_banner_"]',
    '[class*="Wall_"]',
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.ReactModal__Overlay',
    '[class*="Nav__mobile"]',
    '[class*="NavMobile"]',
    '[class*="nav-ui-NavMobile"]',
    '[id*="google_ads"]',
    '[id*="ad-"]',
    '.ad-container',
  ];

  paywallSelectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      // Segurança: NUNCA remover se contiver a matéria principal ou o título
      if (el.querySelector('article, h1, main, [class*="articleLayout"]')) return;
      el.remove();
      removed.push(sel);
    });
  });

  // 2. Destravar estilos de scroll, altura e compensação de anúncio no html e body
  const docEl = document.documentElement;
  docEl.className = '';
  docEl.style.removeProperty('--leaderboard-ad-height');
  docEl.style.removeProperty('--nav-offset');
  docEl.style.setProperty('overflow', 'auto', 'important');
  docEl.style.setProperty('height', 'auto', 'important');
  docEl.style.setProperty('position', 'static', 'important');

  if (document.body) {
    document.body.className = '';
    document.body.style.setProperty('overflow', 'auto', 'important');
    document.body.style.setProperty('height', 'auto', 'important');
    document.body.style.setProperty('position', 'static', 'important');
  }

  // 3. Tornar o cabeçalho institucional da Bloomberg estático e visível
  document.querySelectorAll('nav[class*="nav-ui-Nav"], .nav-ui-Nav__desktop__TmF2X').forEach(el => {
    el.style.setProperty('position', 'static', 'important');
    el.style.setProperty('display', 'block', 'important');
    el.style.setProperty('visibility', 'visible', 'important');
  });

  // 4. Esconder slots vazios de publicidade no topo sem remover containers pai da matéria
  document.querySelectorAll(
    '[class*="LeaderboardAd_adSlot"], [class*="LeaderboardAd_stickyWrapper"], [class*="pub_"]'
  ).forEach(el => {
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('height', '0px', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
  });

  // 5. Garantir que parágrafos, imagens e legendas estejam 100% visíveis
  document.querySelectorAll('article *, main *, [class*="articleLayout"] *').forEach(el => {
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
    img.decoding = 'sync';
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

@register("bloomberg.com")
class BloombergScraper(BaseScraper):
    """Handler cirúrgico para a Bloomberg (bloomberg.com)."""

    name = "bloomberg"
    domains = ("bloomberg.com",)

    def wait_for_content(self, page: Any) -> bool:
        """Espera o artigo carregar no DOM."""
        for _ in range(15):
            try:
                info = page.evaluate(_WAIT_BLOOMBERG_CONTENT_JS)
                if info.get("found"):
                    return True
            except Exception:
                pass
            page.wait_for_timeout(300)
        page.wait_for_timeout(1000)
        return False

    def cleanup(self, page: Any) -> dict:
        """Remoção cirúrgica de modais, paywall e anúncios da Bloomberg."""
        try:
            result = page.evaluate(_CLEANUP_BLOOMBERG_JS)
            return {"handler": "bloomberg", **result}
        except Exception as exc:
            return {"handler": "bloomberg", "error": str(exc)[:300]}

    def _fetch_article_html(self, url: str) -> str | None:
        """Recupera o HTML da matéria da Bloomberg via leitor para contornar WAF PerimeterX."""
        reader_url = f"https://r.jina.ai/{url}"
        headers: dict[str, str] = {
            "X-Return-Format": "html",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        api_key = os.getenv("JINA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.get(reader_url, headers=headers, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 40_000:
                low = resp.text[:2000].lower()
                if "are you a robot?" not in low and "px-captcha" not in low:
                    return resp.text
        except Exception as exc:
            log.warning("Falha ao recuperar HTML da Bloomberg via leitor: %s", exc)
        return None

    def capture(self, url: str, dest: Path) -> dict:
        """Captura screenshot limpo da Bloomberg.

        Se a navegação direta sofrer bloqueio WAF 403 / PerimeterX,
        recupera o HTML limpo da matéria, renderiza o DOM estático
        e executa a higienização visual com os estilos e imagens oficiais.
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
                    if result["http_status"] in (401, 403, 429) or "are you a robot?" in page_title:
                        direct_blocked = True
                except Exception:
                    direct_blocked = True

                # 2. Se bloqueado pelo PerimeterX / HTTP 403, usar o leitor de alta fidelidade
                if direct_blocked:
                    html = self._fetch_article_html(url)
                    if html:
                        # Remove scripts executáveis para prevenir travamento de rede e reativação de bloqueios
                        clean_html = re.sub(
                            r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
                            "",
                            html,
                            flags=re.IGNORECASE,
                        )
                        page.set_content(clean_html, wait_until="load")
                        result["http_status"] = 200
                        result["meta"]["retrieval_route"] = "jina_html"
                    else:
                        result["http_status"] = result["http_status"] or 403
                        result["error"] = f"HTTP {result['http_status']} (bloqueio WAF PerimeterX na Bloomberg)"
                        page.close()
                        ctx.close()
                        browser.close()
                        return result

                # 3. Esperar conteúdo renderizar
                content_ok = self.wait_for_content(page)
                result["meta"]["content_found"] = content_ok

                # 4. Estilos e fontes
                self._wait_for_styles(page)

                # 5. Fechar cookies / LGPD
                cookie_sel = self._dismiss_cookies(page)
                result["meta"]["cookie_dismissed"] = cookie_sel

                # 6. Injetar CSS genérico
                self._inject_cleanup_css(page)

                # 7. Forçar lazy images
                self._force_lazy_images(page)

                # 8. Limpeza cirúrgica específica da Bloomberg
                cleanup_info = self.cleanup(page)
                result["meta"]["cleanup"] = cleanup_info

                # 9. Limpeza de placeholders
                self._clean_placeholders(page)

                # 10. Posicionar no título H1
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
