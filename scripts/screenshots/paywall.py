#!/usr/bin/env python3
"""Módulo de apoio para recuperação de bloqueios, WAF e paywalls.

Fornece WafRecoveryMixin, detectores de bloqueio e utilitários compartilhados
entre os scrapers cirúrgicos (WSJ, FT, Economist, Bloomberg, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Any
import requests

log = logging.getLogger("screenshots.paywall")

_GENERIC_PAYWALL_JS = """() => {
  const removed = [];
  const sels = [
    '#onetrust-banner-sdk',
    '#onetrust-consent-sdk',
    '.cookie-banner',
    '[class*="paywall"]',
    '[class*="subscribe-barrier"]',
  ];
  sels.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      if (el.querySelector('article, h1')) return;
      el.remove();
      removed.push(sel);
    });
  });
  return {removed, count: removed.length};
}"""


try:
    from bm_video.constants import _BLOCK_TEXT_MARKERS
except Exception:
    try:
        from scripts.bm_video.constants import _BLOCK_TEXT_MARKERS
    except Exception:
        _BLOCK_TEXT_MARKERS = (
            "access denied", "you don't have permission to access",
            "voce nao tem permissao", "você não tem permissão",
            "acesso restrito", "errors.edgesuite.net", "request blocked",
            "attention required", "just a moment", "are you a robot",
            "perimeterx", "http error 403", "403 forbidden",
            "temporarily offline", "turnstile", "verify you are human",
            "verifique se você é humano", "enable javascript and cookies to continue",
            "página não encontrada", "404 not found", "erro 404",
            "checking your browser before accessing",
        )


def detect_block(page: Any, http_status: int | None = None) -> str | None:
    """Detecta se uma página carregada é um desafio de robô, WAF ou bloqueio de acesso."""
    if http_status in (401, 403, 429, 451):
        return f"http_{http_status}"
    try:
        title = (page.title() or "").lower()
        if any(marker in title for marker in ("just a moment", "attention required", "enable js", "turnstile", "verify you are human", "robot")):
            return "cloudflare"
        text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 3000).toLowerCase() : ''")
        for marker in _BLOCK_TEXT_MARKERS:
            if marker in text:
                return f"block:{marker}"
        if "access denied" in text or "temporariamente restrito" in text or "are you a robot" in text or "perimeterx" in text:
            return "waf_block"
    except Exception:
        pass
    return None



def record_capture_telemetry(result: dict, duration_s: float) -> None:
    """Hook para telemetria de captura (no-op seguro quando desabilitado)."""
    pass


class WafRecoveryMixin:
    """Mixin para scrapers que utilizam recuperação de alta fidelidade via Archive.today ou Jina Reader."""

    recovery_base_url: str = ""

    def fetch_recovered_html(self, url: str) -> tuple[str | None, str | None]:
        """Consulta espelhos de arquivo e gateways de leitura limpos.

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

        # 1. Tentar espelhos do Archive.today (archive.ph, archive.today, archive.is, archive.li)
        for mirror in ("archive.ph", "archive.today", "archive.is", "archive.li"):
            try:
                target = f"https://{mirror}/newest/{url}"
                r = requests.get(target, headers=headers, timeout=12, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 30_000:
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
            if resp.status_code == 200 and len(resp.text) > 20_000:
                low = resp.text[:2000].lower()
                if "just a scraper" not in low and "please enable js" not in low:
                    base = getattr(self, "recovery_base_url", "") or "https://www.ft.com/"
                    return resp.text, base
        except Exception as exc:
            log.warning("Jina Reader falhou para %s: %s", url, exc)

        return None, None

    def prepare_recovered_html(self, html: str, base_href: str | None = None) -> str:
        """Remove scripts potencialmente destrutivos do snapshot arquivado."""
        return re.sub(
            r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
            "",
            html,
            flags=re.IGNORECASE,
        )
