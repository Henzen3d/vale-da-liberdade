#!/usr/bin/env python3
"""
Screenshot limpo de matéria: remove paywall + overlays + ads via JS,
aguarda carregamento completo, tira print.
"""
import argparse, sys
from pathlib import Path

STATELESS_PAYWALL_JS = """() => {
  // 1. O ESTADÃO (Fusion/React): o modal de paywall é um <main class="background">
  //    fixed cobrindo a tela. O conteúdo real está em #fusion-app (mais alto).
  const modal = document.querySelector('main.background, .modal, .spaceOffers');
  if (modal) {
    // remove o modal e seus ancestrais que sejam exclusivamente do paywall
    let el = modal;
    for (let i = 0; i < 4; i++) {
      const parent = el.parentElement;
      if (!parent || parent === document.body || parent.id === 'fusion-app') break;
      // só remove se o ancestral for o wrapper do paywall (flex/fixed, sem conteúdo próprio)
      const cls = (typeof parent.className === 'string' ? parent.className : '');
      if (parent.classList.contains('background') || /paywall|modal|offer/i.test(cls)) {
        el = parent;
      } else break;
    }
    el.style.setProperty('display', 'none', 'important');
  }

  // 2. Remove qualquer elemento fixed/sticky que contenha texto de paywall
  document.querySelectorAll('*').forEach(node => {
    const st = getComputedStyle(node);
    if (st.position !== 'fixed' && st.position !== 'sticky') return;
    if (node.innerText && node.innerText.length < 500) {
      const t = node.innerText.toLowerCase();
      if (/assin|assinar|oferta especial|quero aproveitar|91% off|acesso ilimitado|já é assinante|faça login|entrar/.test(t)) {
        // evita remover a navbar (ELEIÇÕES, PULSA...) — só se tiver texto de paywall claro
        if (/assin|oferta|aproveitar|91% off|acesso ilimitado/.test(t)) {
          node.style.setProperty('display', 'none', 'important');
        }
      }
    }
  });

  // 3. Restaura scroll e overflow no html/body
  document.documentElement.style.overflow = 'auto';
  document.documentElement.style.position = 'static';
  document.documentElement.style.height = 'auto';
  if (document.body) {
    document.body.style.overflow = 'auto';
    document.body.style.position = 'static';
    document.body.style.height = 'auto';
  }

  // 4. Restaura o artigo principal
  const app = document.querySelector('#fusion-app');
  if (app) {
    app.style.setProperty('opacity', '1', 'important');
    app.style.setProperty('visibility', 'visible', 'important');
    app.style.setProperty('overflow', 'visible', 'important');
    app.style.setProperty('height', 'auto', 'important');
    app.style.setProperty('max-height', 'none', 'important');
  }

  const h1 = document.querySelector('h1');
  return h1 ? h1.innerText : '(sem h1)';
}"""

CLEANUP_CSS = """
.banner-lgpd-consent, .banner-lgpd-consent__accept,
.j-paywall, .c-subscribe-wall,
#onetrust-banner-sdk, #onetrust-consent-sdk,
.fc-consent-root,
[id*="cookie-banner"], [class*="cookie-banner"], [class*="CookieBanner"],
[class*="tp-modal"], [class*="tp-backdrop"],
[class*="piano-modal"], [data-testid*="paywall"],
[class*="ad-"], [id*="ad-"], [class*="advertisement"], [class*="ads"],
[class*="Ads"], [class*="banner-"], [class*="Banner-"],
iframe[src*="doubleclick"], iframe[src*="googlead"]
{ display: none !important; visibility: hidden !important; pointer-events: none !important; }
html, body { overflow: auto !important; position: static !important; }
"""


def clean_screenshot(url: str, output_path: str, timeout_ms: int = 60000) -> dict:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    result = {"ok": False, "path": None, "error": None, "h1": None}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="pt-BR",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass

            # Navega — domcontentloaded (networkidle travaria em sites com ads infinitos)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            http_status = resp.status if resp else None
            # Espera generosa pra JS/CSS/ads tardios carregarem
            page.wait_for_timeout(5000)

            # Aplica CSS de cleanup primeiro
            page.add_style_tag(content=CLEANUP_CSS)
            page.wait_for_timeout(300)

            # Remove paywall via JS
            h1 = page.evaluate(STATELESS_PAYWALL_JS)
            page.wait_for_timeout(500)

            # Scroll para a posição do título
            try:
                title_y = page.evaluate(
                    """() => {
                        const h1 = document.querySelector('h1');
                        const article = document.querySelector('article, main, [role="main"]');
                        const el = h1 || article;
                        return el ? el.getBoundingClientRect().top + window.scrollY - 80 : 0;
                    }"""
                )
                if title_y > 0:
                    page.evaluate(f"window.scrollTo(0, {title_y})")
                    page.wait_for_timeout(300)
            except Exception:
                pass

            # Tira o screenshot
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), type="png", full_page=False)

            # Verifica se não foi bloqueado
            body = ""
            try:
                body = page.evaluate("document.body ? document.body.innerText.slice(0, 400) : ''")
            except Exception:
                body = ""
            blocked = http_status in {401, 403} or "403 Forbidden" in (body or "")

            ctx.close()
            browser.close()

            if blocked:
                result["error"] = f"blocked status={http_status}"
            elif out.exists() and out.stat().st_size > 2000:
                result["ok"] = True
                result["path"] = str(out)
                result["h1"] = h1
            else:
                result["error"] = "screenshot vazio ou muito pequeno"

    except Exception as e:
        result["error"] = str(e)[:300]

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Screenshot limpo de matéria")
    ap.add_argument("url", help="URL da matéria")
    ap.add_argument("--output", "-o", default="/tmp/materia.png", help="Path do PNG")
    ap.add_argument("--timeout", type=int, default=60000, help="Timeout ms")
    args = ap.parse_args()

    result = clean_screenshot(args.url, args.output, args.timeout)
    print(f"ok={result['ok']}  h1={result['h1']}  path={result['path']}  err={result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())