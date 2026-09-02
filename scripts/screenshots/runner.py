#!/usr/bin/env python3
"""Despachante de screenshots — recebe URL e despacha para o handler correto.

Uso::

    # URL única
    python -m scripts.screenshots.runner --url "https://www.estadao.com.br/..."

    # Batch (arquivo com URLs, uma por linha)
    python -m scripts.screenshots.runner --urls-file urls.txt

    # Saída customizada
    python -m scripts.screenshots.runner --url "..." --output ./meus-prints/

    # Full page (scroll até o fim)
    python -m scripts.screenshots.runner --url "..." --full-page

    # Viewport customizado
    python -m scripts.screenshots.runner --url "..." --viewport 1280x720

Também pode ser usado como módulo::

    from scripts.screenshots.runner import capture
    result = capture("https://www.estadao.com.br/...", output_dir="output/screenshots")
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

# Garante UTF-8 no stdout do Windows (evita crash com emojis em cp1252)
if sys.platform == "win32" and not os.environ.get("PYTHONIOENCODING"):
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass

from scripts.screenshots.base import (
    ROOT,
    BaseScraper,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    domain_from_url,
    slug_from_url,
)
from scripts.screenshots.sites import get_scraper, list_registered


# ---------------------------------------------------------------------------
# Diretório padrão de saída
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = ROOT / "output" / "screenshots"


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def capture(
    url: str,
    output_dir: str | Path | None = None,
    full_page: bool = False,
    viewport: dict[str, int] | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    filename: str | None = None,
    dest: str | Path | None = None,
) -> dict:
    """Captura screenshot limpo de uma URL de notícia.

    Args:
        url: URL da matéria.
        output_dir: Diretório base de saída.
            Default: ``output/screenshots/``.
            O arquivo será salvo em ``<output_dir>/<dominio>/<data>_<slug>.png``.
        full_page: Se True, captura a página inteira (scroll).
        viewport: Dict ``{"width": W, "height": H}``. Default: 1920×1080.
        timeout_ms: Timeout de navegação em ms. Default: 45000.
        filename: Nome do arquivo (sem extensão). Se None, gera automaticamente.
        dest: Caminho completo do PNG. Se informado, ignora output_dir/filename
            (pipeline de vídeo BM grava em ``src-NN.png``).

    Returns:
        Dict com resultado: ``{ok, path, url, domain, handler, error, meta}``.
    """
    out = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    domain = domain_from_url(url)

    if dest is None:
        if filename:
            fname = filename if filename.endswith(".png") else f"{filename}.png"
        else:
            date_prefix = time.strftime("%Y-%m-%d")
            slug = slug_from_url(url)
            fname = f"{date_prefix}_{slug}.png"
        dest = out / domain / fname
    else:
        dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Encontrar o handler correto para o domínio
    scraper = get_scraper(domain)
    if scraper is None:
        # Fallback genérico
        scraper = BaseScraper(
            viewport=viewport,
            timeout_ms=timeout_ms,
            full_page=full_page,
        )
    else:
        # Aplicar parâmetros ao scraper específico
        scraper.viewport = viewport or dict(DEFAULT_VIEWPORT)
        scraper.timeout_ms = timeout_ms
        scraper.full_page = full_page

    result = scraper.capture(url, dest)
    return result


def capture_batch(
    urls: list[str],
    output_dir: str | Path | None = None,
    full_page: bool = False,
    viewport: dict[str, int] | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    delay_s: float = 1.0,
) -> list[dict]:
    """Captura screenshots de múltiplas URLs.

    Args:
        urls: Lista de URLs.
        output_dir: Diretório base de saída.
        full_page: Se True, captura página inteira.
        viewport: Viewport customizado.
        timeout_ms: Timeout de navegação.
        delay_s: Pausa entre capturas (evita rate-limiting).

    Returns:
        Lista de dicts com resultado de cada captura.
    """
    results = []
    total = len(urls)

    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url or url.startswith("#"):
            continue

        print(f"[{i}/{total}] {url}")
        result = capture(
            url,
            output_dir=output_dir,
            full_page=full_page,
            viewport=viewport,
            timeout_ms=timeout_ms,
        )
        status = "✅" if result["ok"] else "❌"
        handler = result.get("handler", "?")
        error = result.get("error", "")
        print(f"  {status} handler={handler} err={error}")
        results.append(result)

        if i < total:
            time.sleep(delay_s)

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"Resultado: {ok}/{len(results)} capturas OK")
    if ok < len(results):
        print("Falhas:")
        for r in results:
            if not r["ok"]:
                print(f"  ❌ {r['url']}: {r['error']}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_viewport(s: str) -> dict[str, int]:
    """Parseia '1920x1080' → {'width': 1920, 'height': 1080}."""
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Viewport inválido: '{s}'. Use WxH (ex: 1920x1080)")
    try:
        return {"width": int(parts[0]), "height": int(parts[1])}
    except ValueError:
        raise argparse.ArgumentTypeError(f"Viewport inválido: '{s}'. Use WxH (ex: 1920x1080)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="📸 Captura screenshot limpo de portais de notícias",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            '  python -m scripts.screenshots.runner --url "https://www.estadao.com.br/..."\n'
            '  python -m scripts.screenshots.runner --urls-file urls.txt --full-page\n'
            '  python -m scripts.screenshots.runner --list-sites\n'
        ),
    )
    ap.add_argument("--url", help="URL única para capturar")
    ap.add_argument("--urls-file", help="Arquivo com URLs (uma por linha)")
    ap.add_argument(
        "--output", "-o",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Diretório de saída (default: {DEFAULT_OUTPUT_DIR})",
    )
    ap.add_argument("--full-page", action="store_true", help="Captura página inteira (scroll)")
    ap.add_argument(
        "--viewport",
        type=_parse_viewport,
        default=None,
        help="Viewport WxH (default: 1920x1080)",
    )
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS, help="Timeout em ms")
    ap.add_argument("--filename", help="Nome do arquivo de saída (sem extensão)")
    ap.add_argument("--delay", type=float, default=1.0, help="Pausa entre capturas em batch (s)")
    ap.add_argument("--list-sites", action="store_true", help="Lista sites com handler dedicado")
    ap.add_argument("--json", action="store_true", help="Saída em JSON")

    args = ap.parse_args()

    # Listar sites registrados
    if args.list_sites:
        sites = list_registered()
        if sites:
            print("Sites com handler dedicado:")
            for s in sites:
                print(f"  • {s}")
        else:
            print("Nenhum site registrado (todos usarão fallback genérico).")
        return 0

    # Validar que temos URL(s)
    if not args.url and not args.urls_file:
        ap.error("Forneça --url ou --urls-file")

    # URL única
    if args.url:
        result = capture(
            args.url,
            output_dir=args.output,
            full_page=args.full_page,
            viewport=args.viewport,
            timeout_ms=args.timeout,
            filename=args.filename,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["ok"]:
                print(f"✅ Screenshot salvo: {result['path']}")
            else:
                print(f"❌ Falha: {result['error']}")
                if result.get("path"):
                    print(f"   (arquivo parcial: {result['path']})")
        return 0 if result["ok"] else 1

    # Batch
    if args.urls_file:
        urls_path = Path(args.urls_file)
        if not urls_path.exists():
            print(f"❌ Arquivo não encontrado: {urls_path}", file=sys.stderr)
            return 1
        urls = [
            line.strip()
            for line in urls_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not urls:
            print("⚠️  Nenhuma URL encontrada no arquivo.")
            return 0

        results = capture_batch(
            urls,
            output_dir=args.output,
            full_page=args.full_page,
            viewport=args.viewport,
            timeout_ms=args.timeout,
            delay_s=args.delay,
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))

        ok = sum(1 for r in results if r["ok"])
        return 0 if ok == len(results) else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
