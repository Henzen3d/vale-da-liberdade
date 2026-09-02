#!/usr/bin/env python3
"""Motor compartilhado de captura Playwright para screenshots de notícias.

Fornece ``BaseScraper`` — classe base com toda a infra pesada:
- Chromium headless + Stealth
- Bloqueio de hosts de ads / trackers / paywall engines
- Fechamento de cookie banners (LGPD / GDPR)
- CSS genérico para esconder overlays conhecidos
- Detecção de screenshot em branco (luminância)
- Forçar carregamento de imagens lazy-loaded
- Posicionamento do viewport no título da matéria

Cada site herda ``BaseScraper`` e sobrescreve ``cleanup(page)`` com
lógica cirúrgica própria.
"""
from __future__ import annotations

import hashlib
import re
import statistics
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent  # web-jornal-vale-da-liberdade/

DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
DEFAULT_TIMEOUT_MS = 45_000
BLANK_SHOT_STDDEV = 6.0    # abaixo disso → print em branco (alinhado com bm_mockup_video.py)
MIN_SHOT_BYTES = 20_000    # abaixo disso → captura falhou

# User-agent real (Chrome 124 Windows)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---- Hosts bloqueados (ads, trackers, paywall engines) --------------------
# Impede networkidle de travar e elimina overlays de assinatura.
BLOCK_HOSTS: tuple[str, ...] = (
    # Paywall engines
    "cdn.tinypass.com",
    "www.tinypass.com",
    "checkout.tinypass.com",
    "experience.piano.io",
    "buy.tinypass.com",
    "paywall.folha.uol.com.br",
    # Ad networks — Google
    "doubleclick.net",
    "securepubads.g.doubleclick.net",
    "pagead2.googlesyndication.com",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "tpc.googlesyndication.com",
    # Ad networks — terceiros
    "static.criteo.net",
    "bidswitch.net",
    "cdn.taboola.com",
    "taboola.com",
    "outbrain.com",
    "widgets.outbrain.com",
    "ib.adnxs.com",
    "ads.yahoo.com",
    # Trackers / analytics
    "www.googletagmanager.com",
    "www.google-analytics.com",
    "analytics.google.com",
    "connect.facebook.net",
    "pixel.facebook.com",
    "bat.bing.com",
    "sb.scorecardresearch.com",
    "cdn.permutive.com",
    "cdn.amplitude.com",
    "tags.tiqcdn.com",
    "cdn.branch.io",
    "sentry.io",
)

# ---- Seletores de cookie banner ------------------------------------------
COOKIE_SELECTORS: tuple[str, ...] = (
    "#onetrust-accept-btn-handler",
    "button#onetrust-accept-btn-handler",
    ".banner-lgpd-consent__accept",
    "button.banner-lgpd-consent__accept",
    "button:has-text('OK')",
    "button:has-text('Ok')",
    "button:has-text('Aceitar')",
    "button:has-text('Aceito')",
    "button:has-text('Concordar')",
    "button:has-text('Accept')",
    "button:has-text('Agree')",
    "button:has-text('Accept all')",
    "button:has-text('Aceitar todos')",
    "[data-testid='cookie-policy-dialog-accept-button']",
)

# ---- CSS injetado para esconder overlays genéricos ------------------------
CLEANUP_CSS = """\
.banner-lgpd-consent,
.banner-lgpd-consent__accept,
.j-paywall,
.c-subscribe-wall,
#onetrust-banner-sdk,
#onetrust-consent-sdk,
.fc-consent-root,
[id*="cookie-banner"],
[class*="cookie-banner"],
[class*="CookieBanner"],
.ReactModal__Overlay,
.newsletter-flutuante,
.sticky-banner,
.floating-ad {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
html, body {
  overflow: auto !important;
  position: static !important;
}
"""

# JS que detecta o H1 mais relevante e retorna sua posição Y.
_FIND_TITLE_JS = """() => {
  const h1s = Array.from(document.querySelectorAll('h1')).sort(
    (a, b) => ((b.innerText || '').trim().length) - ((a.innerText || '').trim().length)
  );
  const h1 = h1s[0] || document.querySelector('[role="main"] h1, article h1, .c-content-head__title, .c-main-headline__title');
  if (!h1) return {found: false, y: 0, sticky: 0};

  let sticky = 0;
  document.querySelectorAll('header, nav, [class*="header"], [class*="top-bar"], [class*="topbar"], [class*="nav"], [class*="navbar"]').forEach(el => {
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if ((st.position === 'fixed' || st.position === 'sticky') && r.top < 90 && r.height < 160) {
      sticky = Math.max(sticky, r.bottom);
    }
  });

  const rH1 = h1.getBoundingClientRect();
  const absTop = rH1.top + window.scrollY;

  // Se o H1 já fica visível e confortável no topo do viewport (até 480px),
  // mantém y = 0 para preservar o logotipo e identidade institucional do jornal
  if (absTop < 480) {
    return {found: true, y: 0, sticky};
  }

  // Senão, posiciona com respiro de 24px acima do H1, descontando headers fixos
  let y = absTop - sticky - 24;
  if (y < 420) y = 0;
  return {found: true, y: Math.max(0, y), sticky};
}"""

# JS para forçar lazy-load de imagens (dispara IntersectionObserver).
_FORCE_LAZY_JS = """async () => {
  // Substituir data-src / data-pagespeed-lazy-src / data-src-retina → src
  document.querySelectorAll('img').forEach(img => {
    const ds = img.dataset.src ||
               img.getAttribute('data-pagespeed-lazy-src') ||
               img.getAttribute('data-src-retina') ||
               img.getAttribute('data-original');
    if (ds && (!img.src || img.src.startsWith('data:'))) {
      img.src = ds;
    }
    img.loading = 'eager';
    img.decoding = 'sync';
  });
  // Scroll rápido para disparar observers, volta ao topo
  const max = Math.min(document.body.scrollHeight, 2400);
  for (let y = 0; y < max; y += 600) {
    window.scrollTo(0, y);
  }
  window.scrollTo(0, 0);

  // Aguarda decodificação de imagens do topo da página
  try {
    const topImgs = Array.from(document.querySelectorAll('img')).filter(im => {
      const r = im.getBoundingClientRect();
      return r.top < 1400 && im.src && !im.src.startsWith('data:');
    });
    await Promise.all(topImgs.map(im => (im.decode ? im.decode().catch(() => {}) : Promise.resolve())));
  } catch (e) {}
}"""

# JS para limpar placeholders vazios (hero cinza/branco) e faixas "PUBLICIDADE" sem anúncio
_CLEAN_PLACEHOLDERS_JS = """() => {
  const hide = (el) => {
    if (!el) return;
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
    el.style.setProperty('pointer-events', 'none', 'important');
  };

  // 1. Placeholders de mídia vazios (hero cinza/branco sem imagem carregada)
  // Segurança: se contiver uma tag img com src válido que não seja data:, NÃO esconde
  document.querySelectorAll(
    'figure, picture, [data-testid="image"], [data-component="image-block"], .content-media, .content-featured-image, [class*="media-container"], [class*="hero-image"]'
  ).forEach(el => {
    const img = el.tagName === 'IMG' ? el : el.querySelector('img');
    const r = el.getBoundingClientRect();
    const hasValidSrc = img && img.src && !img.src.startsWith('data:') && img.src.length > 15;
    const emptyImg = !img || (img.complete && img.naturalWidth === 0 && !hasValidSrc);
    if (r.height > 60 && emptyImg && el.tagName !== 'IMG') hide(el);
  });

  // 2. Rótulos "PUBLICIDADE" / "PROPAGANDA" órfãos (sem criativo)
  document.querySelectorAll('div, section, aside, span, p, label, small').forEach(el => {
    const t = (el.innerText || '').trim().toLowerCase();
    if (t === 'publicidade' || t === 'propaganda' || t === 'advertisement') {
      const img = el.querySelector('img');
      const iframe = el.querySelector('iframe');
      if (!img && !iframe) hide(el);
    }
  });

  // 3. Blocos vazios gigantes acima do H1 (ex: slots de banners que não carregaram)
  const h1 = document.querySelector('h1, [role="main"] h1, article h1');
  if (h1) {
    const ty = h1.getBoundingClientRect().top;
    document.querySelectorAll('div, figure, section, aside').forEach(el => {
      // Segurança: NUNCA esconder cabeçalhos, logos ou navegação institucional
      if (el.closest('header, nav, [role="banner"], [class*="header"], [class*="topbar"], [class*="navbar"]')) return;
      if (el.contains(h1) || h1.contains(el)) return;
      const r = el.getBoundingClientRect();
      if (r.height < 60 || r.width < 240) return;
      if (r.bottom <= 8 || r.top >= ty - 4) return;
      const txt = (el.innerText || '').trim();
      if (txt.length > 40) return;
      const svg = el.querySelector('svg');
      if (svg) return;
      const img = el.querySelector('img');
      if (img && img.naturalWidth > 10) return;
      hide(el);
    });
  }
}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_block(url: str) -> bool:
    """True se a URL deve ser abortada (ad/tracker/paywall)."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in BLOCK_HOSTS)


def _is_blank(path: Path, threshold: float = BLANK_SHOT_STDDEV) -> bool:
    """True se o PNG tiver desvio padrão de luminância muito baixo (tela em branco)."""
    try:
        from PIL import Image
    except ImportError:
        return False
    im = Image.open(path).convert("L").resize((64, 36))
    return float(statistics.pstdev(im.getdata())) < threshold


def slug_from_url(url: str, max_len: int = 60) -> str:
    """Gera um slug filesystem-safe a partir da URL."""
    parts = urlsplit(url)
    path = (parts.path or "").strip("/").replace("/", "-")
    # Remove extensões comuns
    path = re.sub(r"\.(html?|php|aspx?)$", "", path, flags=re.IGNORECASE)
    # Só caracteres seguros
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", path)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        slug = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return slug[:max_len]


def domain_from_url(url: str) -> str:
    """Extrai domínio limpo (sem www.) de uma URL."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return "unknown"
    return host.removeprefix("www.")


# ---------------------------------------------------------------------------
# BaseScraper
# ---------------------------------------------------------------------------

class BaseScraper:
    """Motor genérico de captura. Subclasses sobrescrevem ``cleanup()``."""

    # Nome legível do site (subclasse define)
    name: str = "genérico"
    # Domínios que este scraper atende (subclasse define)
    domains: tuple[str, ...] = ()
    # Permite desabilitar stealth se causar distorção de layout (ex.: Claudio Dantas)
    stealth_enabled: bool = True

    def __init__(
        self,
        viewport: dict[str, int] | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        full_page: bool = False,
    ):
        self.viewport = viewport or dict(DEFAULT_VIEWPORT)
        self.timeout_ms = timeout_ms
        self.full_page = full_page

    # -- Métodos que subclasses podem sobrescrever --------------------------

    def cleanup(self, page: Any) -> dict:
        """Lógica de limpeza específica do site (paywall, ads, etc.).

        Retorna dict com metadados do que foi removido.
        A implementação base aplica apenas o CSS genérico e dismiss de cookies.
        """
        return {"handler": "generic"}

    def prepare_page(self, page: Any, url: str) -> None:
        """Hook para inicialização pré-navegação (ex: pré-aquecer cookies de sessão)."""
        pass

    def wait_for_content(self, page: Any) -> bool:
        """Espera o conteúdo principal renderizar.

        Retorna True se o conteúdo foi encontrado. A implementação base
        aguarda 2s após DOMContentLoaded (suficiente para sites estáticos).
        """
        page.wait_for_timeout(2000)
        return True

    # -- Infra compartilhada (não sobrescrever normalmente) -----------------

    def _launch_context(self, pw: Any) -> tuple:
        """Cria browser + context com stealth, bloqueio e viewport."""
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport=self.viewport,
            locale="pt-BR",
            user_agent=USER_AGENT,
        )
        # Bloqueia ads/trackers na camada de rede
        ctx.route("**/*", lambda route: (
            route.abort() if _should_block(route.request.url) else route.continue_()
        ))
        return browser, ctx

    def _apply_stealth(self, page: Any) -> None:
        """Aplica playwright-stealth se disponível e habilitado."""
        if not getattr(self, "stealth_enabled", True):
            return
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass

    def _dismiss_cookies(self, page: Any) -> str | None:
        """Tenta fechar banners de cookie/LGPD. Retorna seletor clicado."""
        for sel in COOKIE_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible(timeout=800):
                    loc.click(timeout=800)
                    page.wait_for_timeout(400)
                    return sel
            except Exception:
                continue
        # Fallback: botão por role + texto
        try:
            btn = page.get_by_role(
                "button",
                name=re.compile(r"^(OK|Ok|Aceitar|Aceito|Concordar|Accept)$"),
            )
            if btn.count():
                btn.first.click(timeout=800)
                page.wait_for_timeout(400)
                return "role-button-fallback"
        except Exception:
            pass
        return None

    def _inject_cleanup_css(self, page: Any) -> None:
        """Injeta CSS para esconder overlays genéricos."""
        page.add_style_tag(content=CLEANUP_CSS)

    def _clean_placeholders(self, page: Any) -> None:
        """Limpa placeholders de mídia vazios (hero cinza) e rótulos de publicidade órfãos."""
        try:
            page.evaluate(_CLEAN_PLACEHOLDERS_JS)
        except Exception:
            pass

    def _scroll_to_title(self, page: Any) -> dict:
        """Posiciona o viewport no H1 da matéria."""
        try:
            info = page.evaluate(_FIND_TITLE_JS)
            if info.get("found"):
                page.evaluate(f"window.scrollTo(0, {info['y']})")
            return info
        except Exception as exc:
            return {"found": False, "error": str(exc)}

    def _force_lazy_images(self, page: Any) -> None:
        """Força carregamento de imagens lazy-loaded."""
        try:
            page.evaluate(_FORCE_LAZY_JS)
            page.wait_for_timeout(800)
        except Exception:
            pass

    def _take_screenshot(self, page: Any, dest: Path) -> Path:
        """Tira o PNG e retorna o caminho."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(dest), full_page=self.full_page, type="png")
        return dest

    # -- Método principal de captura ----------------------------------------

    def capture(self, url: str, dest: Path) -> dict:
        """Captura screenshot limpo de uma URL.

        Args:
            url: URL da matéria.
            dest: Caminho completo do PNG de saída.

        Returns:
            Dict com resultado: {ok, path, url, domain, error, meta}.
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
        except ImportError as e:
            result["error"] = f"playwright não instalado: {e}"
            return result

        try:
            with sync_playwright() as pw:
                browser, ctx = self._launch_context(pw)
                page = ctx.new_page()
                self._apply_stealth(page)

                # 0. Preparação pré-navegação (se necessária)
                self.prepare_page(page, url)

                # 1. Navegar (domcontentloaded, nunca networkidle)
                resp = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )
                result["http_status"] = resp.status if resp else None

                # 2. Esperar conteúdo renderizar (site-specific)
                content_ok = self.wait_for_content(page)
                result["meta"]["content_found"] = content_ok

                # 3. Fechar cookies
                cookie_sel = self._dismiss_cookies(page)
                result["meta"]["cookie_dismissed"] = cookie_sel

                # 4. Injetar CSS genérico
                self._inject_cleanup_css(page)

                # 5. Limpeza específica do site (paywall, ads, overlays)
                cleanup_info = self.cleanup(page)
                result["meta"]["cleanup"] = cleanup_info

                # 6. Limpeza de placeholders vazios e ads órfãos
                self._clean_placeholders(page)

                # 7. Forçar imagens lazy
                self._force_lazy_images(page)

                # 8. Re-executar limpeza de placeholders pós-lazy
                self._clean_placeholders(page)

                # 9. Posicionar no título
                title_info = self._scroll_to_title(page)
                result["meta"]["title"] = title_info

                # 10. Pausa final para renderização
                page.wait_for_timeout(500)

                # 11. Capturar
                self._take_screenshot(page, dest)

                page.close()
                ctx.close()
                browser.close()

                # 12. Validar
                if not dest.exists() or dest.stat().st_size < MIN_SHOT_BYTES:
                    result["error"] = "screenshot muito pequeno ou inexistente"
                elif _is_blank(dest):
                    result["error"] = "screenshot em branco (luminância uniforme)"
                else:
                    result["ok"] = True
                    result["path"] = str(dest)

        except Exception as exc:
            result["error"] = str(exc)[:500]
            # Se conseguiu tirar o print mesmo com erro, registra
            if dest.exists() and dest.stat().st_size > MIN_SHOT_BYTES:
                result["path"] = str(dest)

        return result
