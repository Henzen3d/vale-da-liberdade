#!/usr/bin/env python3
"""
Módulo e CLI de Recuperação de Páginas Bloqueadas (blocked-page-recovery).
Padrão Hermes / Vale da Liberdade.

Recupera conteúdo de páginas web inacessíveis devido a erros HTTP (401, 403, 429),
WAFs (Akamai, Cloudflare Turnstile, PerimeterX), paywalls ou bot-walls.

Escada de Recuperação (Fallback Ladder):
  1. Wayback Machine (archive.org/wayback/available)
  2. Archive.today (archive.ph, archive.today, archive.is, archive.li, archive.md)
  3. Jina Reader (https://r.jina.ai/<url>)
  4. API-First Pivot (WordPress REST API, RSS/Atom feeds, rotas JSON desprotegidas)
  5. Real Headless Browser (Playwright + Stealth)

Regras de Proveniência:
  - Snapshots de arquivos (Wayback / Archive.today) SEMPRE registram data do snapshot
    (ex: 'Arquivado em DD/MM/AAAA') e nunca são apresentados como conteúdo ao vivo.
  - Validação estrita de corpo para evitar falsos positivos (páginas de erro retornando HTTP 200).

Uso via CLI:
  python scripts/recover_page.py "https://site.com/artigo-bloqueado" --json
  python scripts/recover_page.py "https://site.com/artigo-bloqueado" -o output.md
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import warnings
import requests
import urllib3
try:
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    BeautifulSoup = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(Path.home() / ".hermes" / ".env", override=False)
except ImportError:
    pass

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    urllib3.disable_warnings()
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("recover-page")

# Headers realistas de navegador
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Indicadores de bloqueio / anti-bot / WAF / paywall
BLOCK_MARKERS = [
    "access denied",
    "acesso negado",
    "acesso restrito",
    "errors.edgesuite.net",
    "perimeterx",
    "px-captcha",
    "are you a robot",
    "request blocked",
    "just a moment...",
    "cf-browser-verification",
    "cf-ray:",
    "cloudflare ray id",
    "turnstile",
    "attention required! | cloudflare",
    "enable javascript and cookies to continue",
    "verificação de segurança",
    "conteúdo exclusivo para assinantes",
    "assine para continuar lendo",
    "esta matéria é exclusiva",
    "paywall.folha.uol.com.br",
    "para continuar lendo, faça login",
    "você atingiu o limite de notícias",
    "internet archive: temporarily offline",
    "target url returned error 404",
    "target url returned error 500",
    "target url returned error 502",
    "target url returned error 503",
    "404 not found",
    "página não encontrada",
    "o endereço abaixo não existe",
]


@dataclass
class RecoveredPage:
    url: str
    success: bool
    title: str = ""
    content: str = ""
    method_used: str = "none"  # wayback | archive_today | jina_reader | api_pivot | browser | direct | none
    snapshot_date: Optional[str] = None  # YYYY-MM-DD ou ISO
    snapshot_url: Optional[str] = None
    snapshot_route: Optional[str] = None
    provenance: str = ""  # Descrição para citação / roteiro
    status_code: Optional[int] = None
    error: Optional[str] = None
    raw_html: Optional[str] = None

    def __post_init__(self):
        if not self.snapshot_route:
            self.snapshot_route = self.method_used

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _smart_text(resp: Any) -> str:
    """Decodifica a resposta HTTP inspecionando meta charset, UTF-8 e apparent_encoding para evitar mojibake."""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    content = getattr(resp, "content", None)
    if not content:
        return getattr(resp, "text", "") or ""
    
    # 1. Tentar UTF-8 estrito primeiro (padrão web moderno)
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 2. Inspecionar meta tag de charset nos bytes iniciais
    head_bytes = content[:2048]
    meta_m = re.search(rb'<meta[^>]+charset=["\']?([a-zA-Z0-9_-]+)', head_bytes, re.I)
    if meta_m:
        encoding_name = meta_m.group(1).decode("ascii", errors="ignore").lower()
        try:
            return content.decode(encoding_name)
        except Exception:
            pass

    # 3. Usar apparent_encoding da requests se disponível
    apparent = getattr(resp, "apparent_encoding", None)
    if apparent:
        try:
            return content.decode(apparent)
        except Exception:
            pass

    # 4. Fallback final com substituição de caracteres inválidos
    return content.decode("utf-8", errors="replace")


def clean_extracted_text(text: str) -> str:
    """Remove excesso de espaços e quebras em branco mantendo parágrafos."""
    if not text:
        return ""
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract_title_and_text_from_html(html: str) -> tuple[str, str]:
    """Extrai título e corpo principal de um HTML limpo."""
    if not html:
        return "", ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()

        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = str(og_title["content"]).strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text().strip()

        article_elem = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"content|post|article|noticia|materia|story", re.I))
        if article_elem:
            body_text = article_elem.get_text(separator="\n")
        else:
            body_text = soup.get_text(separator="\n")

        return title, clean_extracted_text(body_text)
    except Exception as exc:
        log.debug("Erro ao fazer parse de HTML com BeautifulSoup: %s", exc)
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else ""
        clean = re.sub(r"<[^>]+>", " ", html)
        return title, clean_extracted_text(clean)


def page_looks_blocked(text: str, status_code: Optional[int] = None) -> bool:
    """Verifica se o conteúdo ou status indica bloqueio/WAF/paywall/falso 200."""
    if status_code in (401, 403, 429):
        return True
    
    text_sample = (text or "")[:4000].lower()
    if not text_sample.strip() or len(text_sample.strip()) < 40:
        return True

    for marker in BLOCK_MARKERS:
        if marker in text_sample:
            return True

    return False


# ---------------------------------------------------------------------------
# Ladder 1: Wayback Machine (Internet Archive)
# ---------------------------------------------------------------------------
def _try_wayback(url: str, timeout: float = 12.0) -> Optional[RecoveredPage]:
    """Consulta a API do Wayback Machine para recuperar snapshot."""
    log.info("🪜 [Ladder 1/5] Tentando Wayback Machine para %s", url)
    api_url = "https://archive.org/wayback/available"
    try:
        r = requests.get(api_url, params={"url": url}, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
        closest = {}
        if r.status_code == 200:
            data = r.json()
            closest = data.get("archived_snapshots", {}).get("closest", {})

        # Se não encontrou, tentar alternar http/https
        if not closest or not closest.get("available"):
            alt_url = url.replace("https://", "http://") if url.startswith("https://") else url.replace("http://", "https://")
            r_alt = requests.get(api_url, params={"url": alt_url}, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
            if r_alt.status_code == 200:
                data_alt = r_alt.json()
                closest = data_alt.get("archived_snapshots", {}).get("closest", {})

        if not closest or not closest.get("available"):
            log.info("Wayback Machine: nenhum snapshot disponível.")
            return None

        raw_snapshot_url = closest.get("url")
        timestamp_str = closest.get("timestamp", "")  # YYYYMMDDhhmmss
        if not raw_snapshot_url:
            return None

        # Inserir id_ após o timestamp para obter o HTML original sem banner do archive.org
        raw_snapshot_url = raw_snapshot_url.replace("http://", "https://")
        snapshot_direct_url = re.sub(r"/web/(\d{8,14})/", r"/web/\1id_/", raw_snapshot_url)
        if "id_/" not in snapshot_direct_url:
            snapshot_direct_url = raw_snapshot_url

        fetch_resp = requests.get(snapshot_direct_url, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
        resp_text = _smart_text(fetch_resp)
        if fetch_resp.status_code != 200 or page_looks_blocked(resp_text, fetch_resp.status_code):
            return None

        snapshot_date = None
        provenance = "Arquivado via Wayback Machine"
        if len(timestamp_str) >= 8:
            try:
                dt = datetime.datetime.strptime(timestamp_str[:8], "%Y%m%d")
                snapshot_date = dt.strftime("%Y-%m-%d")
                provenance = f"Arquivado em {dt.strftime('%d/%m/%Y')} via Wayback Machine"
            except Exception:
                snapshot_date = timestamp_str[:8]

        title, content = extract_title_and_text_from_html(resp_text)
        if not content or len(content) < 30:
            return None

        return RecoveredPage(
            url=url,
            success=True,
            title=title,
            content=content,
            method_used="wayback",
            snapshot_date=snapshot_date,
            snapshot_url=snapshot_direct_url,
            snapshot_route="wayback",
            provenance=provenance,
            status_code=fetch_resp.status_code,
            raw_html=resp_text,
        )
    except Exception as exc:
        log.debug("Wayback falhou: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Ladder 2: Archive.today (archive.ph, archive.today, etc.)
# ---------------------------------------------------------------------------
def _try_archive_today(url: str, timeout: float = 6.0) -> Optional[RecoveredPage]:
    """Consulta espelhos Archive.today / Archive.ph para recuperar snapshot."""
    log.info("🪜 [Ladder 2/5] Tentando Archive.today / Archive.ph para %s", url)
    domains = ["archive.ph", "archive.today"]
    timeout_mirror = min(timeout, 6.0)
    
    for dom in domains:
        try:
            target = f"https://{dom}/newest/{url}"
            r = requests.get(target, headers=DEFAULT_HEADERS, timeout=timeout_mirror, verify=False, allow_redirects=True)
            resp_text = _smart_text(r)
            if r.status_code == 200 and not page_looks_blocked(resp_text, r.status_code):
                title, content = extract_title_and_text_from_html(resp_text)
                if content and len(content) >= 30:
                    date_m = re.search(r"archived\s+(\d{1,2}\s+[a-zA-Z]{3,4}\s+\d{4})", resp_text, re.I)
                    snapshot_date = date_m.group(1) if date_m else datetime.date.today().isoformat()
                    provenance = f"Arquivado via Archive.today ({snapshot_date})"

                    return RecoveredPage(
                        url=url,
                        success=True,
                        title=title,
                        content=content,
                        method_used="archive_today",
                        snapshot_date=snapshot_date,
                        snapshot_url=target,
                        snapshot_route="archive_today",
                        provenance=provenance,
                        status_code=r.status_code,
                        raw_html=resp_text,
                    )
        except Exception as exc:
            log.debug("Archive.today mirror %s falhou: %s", dom, exc)
            continue
    return None


# ---------------------------------------------------------------------------
# Ladder 3: Jina Reader (https://r.jina.ai/<url>)
# ---------------------------------------------------------------------------
def _try_jina_reader(url: str, timeout: float = 18.0) -> Optional[RecoveredPage]:
    """Renderiza a página via Jina Reader (server-side markdown reader)."""
    log.info("🪜 [Ladder 3/5] Tentando Jina Reader para %s", url)
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/plain, text/markdown, */*",
    }
    jina_key = os.environ.get("JINA_API_KEY")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    try:
        r = requests.get(jina_url, headers=headers, timeout=timeout, verify=False)
        if r.status_code == 200:
            text = _smart_text(r)
            if not page_looks_blocked(text, r.status_code) and len(text.strip()) >= 30:
                lines = text.strip().split("\n")
                title = ""
                for line in lines[:10]:
                    line_clean = line.strip()
                    if line_clean.lower().startswith("title:"):
                        title = line_clean[6:].strip()
                        break
                    elif line_clean.startswith("# "):
                        title = line_clean.removeprefix("# ").strip()
                        break

                cleaned = clean_extracted_text(text)
                return RecoveredPage(
                    url=url,
                    success=True,
                    title=title or "Artigo Recuperado",
                    content=cleaned,
                    method_used="jina_reader",
                    snapshot_date=None,
                    snapshot_url=jina_url,
                    snapshot_route="jina_reader",
                    provenance="Renderizado via Jina Reader (ao vivo)",
                    status_code=200,
                    raw_html=text,
                )
    except Exception as exc:
        log.debug("Jina Reader falhou: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Ladder 4: API-First Pivot & Feed Discovery
# ---------------------------------------------------------------------------
def _try_api_pivot(url: str, timeout: float = 10.0) -> Optional[RecoveredPage]:
    """Tenta descobrir endpoints de API (WordPress REST API, JSON, RSS) no domínio."""
    log.info("🪜 [Ladder 4/5] Tentando API Pivot / WordPress REST para %s", url)
    parsed = urllib.parse.urlsplit(url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"
    
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    slug = path_parts[-1] if path_parts else ""
    slug = re.sub(r"\.[a-zA-Z0-9]+$", "", slug)

    if slug and len(slug) >= 4:
        wp_api_url = f"{base_origin}/wp-json/wp/v2/posts?slug={slug}&_embed"
        try:
            r = requests.get(wp_api_url, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
            if r.status_code == 200:
                posts = r.json()
                if isinstance(posts, list) and posts:
                    post = posts[0]
                    title_raw = post.get("title", {}).get("rendered", "")
                    content_raw = post.get("content", {}).get("rendered", "") or post.get("excerpt", {}).get("rendered", "")
                    title, _ = extract_title_and_text_from_html(title_raw)
                    _, content = extract_title_and_text_from_html(content_raw)
                    
                    pub_date = post.get("date", "")
                    if title and content and len(content) >= 30:
                        return RecoveredPage(
                            url=url,
                            success=True,
                            title=title,
                            content=content,
                            method_used="api_pivot",
                            snapshot_date=pub_date[:10] if pub_date else None,
                            provenance="Coletado via WordPress REST API",
                            status_code=200,
                            raw_html=content_raw,
                        )
        except Exception as exc:
            log.debug("WordPress REST API pivot falhou: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Ladder 5: Real Headless Browser (Playwright + Stealth)
# ---------------------------------------------------------------------------
def _try_playwright_browser(url: str, timeout_ms: int = 35000) -> Optional[RecoveredPage]:
    """Tenta renderização completa via Playwright com stealth headers."""
    log.info("🪜 [Ladder 5/5] Tentando Playwright Browser para %s", url)
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        log.warning("Playwright ou playwright_stealth não disponíveis no ambiente.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                locale="pt-BR",
                viewport={"width": 1366, "height": 768},
                user_agent=DEFAULT_HEADERS["User-Agent"],
                extra_http_headers={k: v for k, v in DEFAULT_HEADERS.items() if k != "User-Agent"},
            )
            page = ctx.new_page()
            try:
                Stealth().apply_stealth_sync(page)
            except Exception:
                pass
            
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(3000)
            status = resp.status if resp else 200
            html = page.content()
            ctx.close()
            browser.close()

            if html and not page_looks_blocked(html, status):
                title, content = extract_title_and_text_from_html(html)
                if content and len(content) >= 30:
                    return RecoveredPage(
                        url=url,
                        success=True,
                        title=title,
                        content=content,
                        method_used="browser",
                        snapshot_date=None,
                        provenance="Capturado via Headless Browser (ao vivo)",
                        status_code=status,
                        raw_html=html,
                    )
    except Exception as exc:
        log.warning("Playwright falhou para %s: %s", url, exc)
    return None


# ---------------------------------------------------------------------------
# Função de Entrada Principal (Orquestrador da Escada)
# ---------------------------------------------------------------------------
def recover_page(
    url: str,
    *,
    timeout: float = 12.0,
    try_direct_first: bool = True,
    max_ladder_step: int = 5,
) -> RecoveredPage:
    """Executa a escada de recuperação para resgatar página bloqueada ou paywalled.
    
    Retorna sempre um objeto `RecoveredPage` com status, proveniência e texto limpo.
    """
    url = (url or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return RecoveredPage(
            url=url,
            success=False,
            error="URL inválida (deve iniciar com http:// ou https://)",
        )

    # Tentativa 0: Requisição Direta se solicitado
    if try_direct_first:
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
            resp_text = _smart_text(r)
            if r.status_code == 200 and not page_looks_blocked(resp_text, r.status_code):
                title, content = extract_title_and_text_from_html(resp_text)
                if content and len(content) >= 30:
                    return RecoveredPage(
                        url=url,
                        success=True,
                        title=title,
                        content=content,
                        method_used="direct",
                        snapshot_date=None,
                        snapshot_url=url,
                        snapshot_route="direct",
                        provenance="Página ao vivo (acesso direto)",
                        status_code=200,
                        raw_html=resp_text,
                    )
            log.warning("Acesso direto a %s falhou ou bloqueado (HTTP %s). Iniciando escada...", url, r.status_code)
        except Exception as exc:
            log.warning("Acesso direto a %s com erro: %s. Iniciando escada...", url, exc)

    # 1. Wayback Machine
    if max_ladder_step >= 1:
        res = _try_wayback(url, timeout=timeout)
        if res and res.success:
            log.info("✅ Recuperação BEM-SUCEDIDA via Wayback Machine!")
            return res

    # 2. Archive.today
    if max_ladder_step >= 2:
        res = _try_archive_today(url, timeout=timeout)
        if res and res.success:
            log.info("✅ Recuperação BEM-SUCEDIDA via Archive.today!")
            return res

    # 3. Jina Reader
    if max_ladder_step >= 3:
        res = _try_jina_reader(url, timeout=timeout + 4)
        if res and res.success:
            log.info("✅ Recuperação BEM-SUCEDIDA via Jina Reader!")
            return res

    # 4. API Pivot
    if max_ladder_step >= 4:
        res = _try_api_pivot(url, timeout=timeout)
        if res and res.success:
            log.info("✅ Recuperação BEM-SUCEDIDA via API Pivot!")
            return res

    # 5. Playwright Browser
    if max_ladder_step >= 5:
        res = _try_playwright_browser(url)
        if res and res.success:
            log.info("✅ Recuperação BEM-SUCEDIDA via Playwright Browser!")
            return res

    log.error("❌ Todas as etapas da escada de recuperação falharam para: %s", url)
    return RecoveredPage(
        url=url,
        success=False,
        error="Todas as rotas da escada de recuperação falharam (Wayback, Archive, Jina, API, Browser)",
    )


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Recuperador de páginas bloqueadas / paywall (Vale da Liberdade)")
    parser.add_argument("url", help="URL do artigo ou página a ser recuperada")
    parser.add_argument("--json", action="store_true", help="Retornar resultado em JSON formatado")
    parser.add_argument("-o", "--output", help="Caminho para salvar o conteúdo recuperado (.md ou .txt)")
    parser.add_argument("--timeout", type=float, default=12.0, help="Timeout por requisição em segundos")
    parser.add_argument("--no-direct", action="store_true", help="Pular tentativa direta e ir direto para os arquivos/proxies")
    args = parser.parse_args()

    res = recover_page(
        args.url,
        timeout=args.timeout,
        try_direct_first=not args.no_direct,
    )

    if args.output and res.success:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc = f"# {res.title}\n\n"
        doc += f"> Fonte: {res.url}\n"
        doc += f"> Proveniência: {res.provenance}\n"
        if res.snapshot_date:
            doc += f"> Data do Snapshot: {res.snapshot_date}\n"
        doc += f"\n---\n\n{res.content}\n"
        out_path.write_text(doc, encoding="utf-8")
        log.info("Arquivo gravado em: %s", out_path)

    if args.json:
        data = res.to_dict()
        data.pop("raw_html", None)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if res.success:
            print(f"\n=======================================================")
            print(f"✅ RECUPERADO COM SUCESSO via {res.method_used.upper()}")
            print(f"Título: {res.title}")
            print(f"Proveniência: {res.provenance}")
            if res.snapshot_date:
                print(f"Data do Snapshot: {res.snapshot_date}")
            print(f"Tamanho do Conteúdo: {len(res.content)} caracteres")
            print(f"=======================================================\n")
            print(res.content[:1500] + ("..." if len(res.content) > 1500 else ""))
        else:
            print(f"\n❌ FALHA NA RECUPERAÇÃO: {res.error}\n")
            sys.exit(1)


if __name__ == "__main__":
    main()
