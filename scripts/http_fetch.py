#!/usr/bin/env python3
"""Camada HTTP compartilhada anti-antibot para os coletores do Vale.

Uso:
    from http_fetch import fetch_html, BROWSER_HEADERS, is_bot_sensitive

Decisões de projeto (aprovadas 2026-08-24):
- Domínios em BOT_SENSITIVE_DOMAINS usam Playwright+stealth como ROTA PRIMÁRIA
  (não como fallback pós-403), garantindo execução real de JS.
- 403/"Access Denied"/"acesso restrito" é tratado como erro TRANSITÓRIO com
  backoff exponencial limitado (máx. BOT_MAX_ATTEMPTS tentativas) — nunca trava
  o pipeline: quem chama recebe (None, status) e segue adiante.
- nytimes.com está em BEST_EFFORT_DOMAINS: sem proxy configurado, faz UMA única
  tentativa e falha graciosamente (sem retry agressivo que piore a reputação).
- Proxy residencial: respeita env HTTP_FETCH_PROXY se definido no .env.
"""
from __future__ import annotations

import logging
import os
import random
import time
import urllib.parse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger("http-fetch")

# ---------------------------------------------------------------------------
# Headers completos de navegador real
# ---------------------------------------------------------------------------
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
}

# ---------------------------------------------------------------------------
# Domínios sensíveis a bot detection — Playwright+stealth é rota PRIMÁRIA
# ---------------------------------------------------------------------------
BOT_SENSITIVE_DOMAINS = {
    "uol.com.br",
    "folha.uol.com.br",
    "www1.folha.uol.com.br",
    "economia.uol.com.br",
}

# Melhor esforço: IP do VPS já marcado no PerimeterX. Sem proxy, uma única
# tentativa e falha graciosa (sem retry agressivo).
BEST_EFFORT_DOMAINS = {
    "nytimes.com",
    "www.nytimes.com",
}

# Delay/jitter humano entre requisições ao MESMO domínio
DELAY_MIN_S = 2.0
DELAY_MAX_S = 6.0

# Backoff para bloqueios antibot (transitório)
BOT_BACKOFF_BASE_S = 2.0
BOT_MAX_ATTEMPTS = 3          # teto absoluto; best-effort usa 1
BOT_ATTEMPT_TIMEOUT_S = 20.0  # timeout por requisição

_last_hit_by_domain: dict[str, float] = {}


def domain_of(url: str) -> str:
    return (urllib.parse.urlparse(url).netloc or "").lower()


def _matches(url_domain: str, domains: set[str]) -> bool:
    return any(url_domain == d or url_domain.endswith("." + d) for d in domains)


def is_bot_sensitive(url: str) -> bool:
    """True se o domínio exige rota Playwright+stealth PRIMÁRIA."""
    return _matches(domain_of(url), BOT_SENSITIVE_DOMAINS)


def is_best_effort(url: str) -> bool:
    """True se o domínio só vale uma tentativa única e graciosa."""
    return _matches(domain_of(url), BEST_EFFORT_DOMAINS)


def human_delay(url: str) -> None:
    """Delay/jitter humano (2–6s) desde a última requisição ao mesmo domínio."""
    d = domain_of(url)
    last = _last_hit_by_domain.get(d)
    wait = random.uniform(DELAY_MIN_S, DELAY_MAX_S)
    if last is not None:
        elapsed = time.time() - last
        wait = max(0.0, wait - elapsed)
    if wait > 0:
        time.sleep(wait)
    _last_hit_by_domain[d] = time.time()


def _looks_like_block(status: int | None, text: str) -> bool:
    if status in (401, 403, 429):
        return True
    low = (text or "")[:4000].lower()
    markers = ("access denied", "acesso restrito", "perimeterx",
               "edgesuite", "are you a robot", "request blocked")
    return any(m in low for m in markers)


def fetch_html(
    url: str,
    *,
    referer: str | None = None,
    max_attempts: int | None = None,
    timeout: float = BOT_ATTEMPT_TIMEOUT_S,
    proxy: str | None = None,
) -> tuple[str | None, int | None]:
    """GET HTTP com headers reais, delay humano e backoff antibot.

    Retorna (html|None, http_status|None). Nunca levanta exceção — falha
    graciosa para não travar pipelines (B&M incluído).

    - Best-effort (nytimes): 1 tentativa, sem retry.
    - Proxy: proxy explícito ou env HTTP_FETCH_PROXY.
    """
    attempts = 1 if is_best_effort(url) else (max_attempts or BOT_MAX_ATTEMPTS)
    headers = dict(BROWSER_HEADERS)
    if not referer:
        parsed = urllib.parse.urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
    headers["Referer"] = referer
    headers["Sec-Fetch-Site"] = "same-origin"

    proxies = None
    proxy = proxy or os.environ.get("HTTP_FETCH_PROXY")
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    status: int | None = None
    for attempt in range(1, attempts + 1):
        human_delay(url)
        try:
            r = requests.get(url, headers=headers, timeout=timeout,
                             verify=False, proxies=proxies)
            status = r.status_code
            if r.status_code == 200 and not _looks_like_block(None, r.text[:2000]):
                return r.text, 200
        except Exception as exc:
            log.warning("http_fetch erro %s (tentativa %s/%s): %s",
                        domain_of(url), attempt, attempts, str(exc)[:120])
            status = None

        if _looks_like_block(status, "") or status in (401, 403, 429):
            log.warning("http_fetch bloqueio antibot %s em %s "
                        "(tentativa %s/%s)", status, domain_of(url),
                        attempt, attempts)
        if attempt < attempts:
            # Backoff exponencial com cap: 2s, 4s, 8s... máx 30s
            time.sleep(min(BOT_BACKOFF_BASE_S * (2 ** (attempt - 1)), 30))

    log.warning("http_fetch FALHA GRACIOSA: %s (status=%s)", url, status)
    return None, status


def fetch_html_browser(
    url: str,
    *,
    wait_ms: int = 4000,
    timeout_ms: int = 40000,
) -> tuple[str | None, int | None]:
    """Rota PRIMÁRIA para domínios sensíveis: Playwright + stealth.

    Executa JS real com fingerprint legítimo. Falha graciosa: retorna
    (None, status). Não há loop infinito — uma única passagem por chamada;
    o retry/backoff fica a cargo do chamador via fetch_html se quiser.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError as exc:
        log.warning("Playwright indisponível (%s); caindo para HTTP.", exc)
        return fetch_html(url)

    html: str | None = None
    status: int | None = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                locale="pt-BR",
                viewport={"width": 1366, "height": 768},
                user_agent=BROWSER_HEADERS["User-Agent"],
                extra_http_headers={k: v for k, v in BROWSER_HEADERS.items()
                                    if k != "User-Agent"},
            )
            page = ctx.new_page()
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass
            resp = page.goto(url, wait_until="domcontentloaded",
                             timeout=timeout_ms)
            status = resp.status if resp else None
            page.wait_for_timeout(wait_ms)
            html = page.content()
            ctx.close()
            browser.close()
    except Exception as exc:
        log.warning("fetch_html_browser falhou %s: %s",
                    domain_of(url), str(exc)[:150])
        return None, status

    body = ""
    if html:
        try:
            from bs4 import BeautifulSoup
            body = BeautifulSoup(html, "html.parser").get_text(" ")[:2000]
        except Exception:
            body = html[:2000]
    if _looks_like_block(status, body):
        log.warning("fetch_html_browser: página de bloqueio detectada em %s",
                    domain_of(url))
        return None, status
    return html, status


def smart_fetch(url: str, **kw) -> tuple[str | None, int | None]:
    """Entrada única: domínio sensível → browser primeiro; resto → HTTP.

    Se o browser falhar num domínio sensível, NÃO martela: uma tentativa
    HTTP de cortesia e desiste (best-effort embutido no fluxo).
    """
    if is_bot_sensitive(url):
        html, status = fetch_html_browser(url, **{
            k: v for k, v in kw.items() if k in ("wait_ms", "timeout_ms")})
        if html:
            return html, status
        return fetch_html(url, max_attempts=1)
    return fetch_html(url, **{k: v for k, v in kw.items()
                              if k in ("referer", "max_attempts",
                                       "timeout", "proxy")})


def fetch_with_recovery(
    url: str,
    *,
    allow_recovery: bool = True,
    **kw,
) -> tuple[str | None, int | None, dict]:
    """Busca HTML com fallback inteligente para blocked-page-recovery.

    Retorna tupla (html_ou_texto, status_code, metadata_dict)
    onde metadata_dict contém chaves como:
      - method: "direct" | "browser" | "wayback" | "archive_today" | "jina_reader" | "api_pivot"
      - provenance: str
      - snapshot_date: str | None
      - title: str
    """
    html, status = smart_fetch(url, **kw)
    if html and not _looks_like_block(status, html[:2000]):
        return html, status or 200, {
            "method": "browser" if is_bot_sensitive(url) else "direct",
            "provenance": "Ao vivo (acesso direto)",
            "snapshot_date": None,
            "title": "",
        }

    if not allow_recovery:
        return html, status, {
            "method": "direct",
            "provenance": "Falha sem recuperação",
            "snapshot_date": None,
            "title": "",
        }

    # Ativar escada blocked-page-recovery
    try:
        from recover_page import recover_page
        rec = recover_page(url, try_direct_first=False)
        if rec.success:
            log.info("fetch_with_recovery: Recuperado com sucesso via %s para %s", rec.method_used, url)
            return rec.content, rec.status_code or 200, {
                "method": rec.method_used,
                "provenance": rec.provenance,
                "snapshot_date": rec.snapshot_date,
                "title": rec.title,
            }
    except Exception as exc:
        log.warning("fetch_with_recovery falhou na escada para %s: %s", url, exc)

    return None, status, {
        "method": "none",
        "provenance": "Falha total",
        "snapshot_date": None,
        "title": "",
    }


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else \
        "https://economia.uol.com.br/noticias/redacao/2026/08/21/jf-dos-irmaos-batista-compra-100-da-avibras.ghtm"
    logging.basicConfig(level=logging.INFO)
    h, s, meta = fetch_with_recovery(target)
    print("status:", s, "| bytes:", len(h) if h else 0, "| method:", meta.get("method"))

