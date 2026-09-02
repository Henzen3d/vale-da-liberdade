#!/usr/bin/env python3
"""
Validador de Feeds RSS Candidatos — Web Jornal Vale da Liberdade.

Lê sources/feeds_candidates.json, testa cada feed individualmente
sem gravar em cache.json nem em sources.json, e gera um relatório
Markdown em logs/feeds_validation_{YYYY-MM-DD}.md com o resultado.

Reaproveita fetch_rss_source e clean_html de news_collector.py.
"""

import argparse
import datetime
import json
import logging
import sys
import time
import urllib3
from pathlib import Path

import requests
import feedparser

# Desabilitar avisos de SSL inseguro (comum em portais locais)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de caminhos
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CANDIDATES_JSON = PROJECT_ROOT / "sources" / "feeds_candidates.json"
LOGS_DIR = PROJECT_ROOT / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("validate-feeds")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_html(html_content):
    """Remove tags HTML e normaliza espaços (replicado de news_collector.py)."""
    if not html_content:
        return ""
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator=" ")
        return __import__("re").sub(r"\s+", " ", text).strip()
    except Exception:
        text = __import__("re").sub(r"<[^>]*>", " ", html_content)
        return __import__("re").sub(r"\s+", " ", text).strip()


def try_wordpress_api(base_url):
    """Tenta buscar artigos via WordPress REST API (replicado de news_collector.py)."""
    import re
    clean_url = re.sub(r"/feed/?$", "", base_url)
    api_url = f"{clean_url}/wp-json/wp/v2/posts?_embed&per_page=5"
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=8, verify=False)
        if response.status_code == 200:
            posts = response.json()
            articles = []
            for post in posts:
                title = post.get("title", {}).get("rendered", "")
                link = post.get("link", "")
                articles.append({"title": clean_html(title), "link": link})
            return articles
    except Exception:
        pass
    return None


def validate_feed(candidate):
    """Testa um feed RSS individual e retorna resultado detalhado."""
    result = {
        "id": candidate["id"],
        "name": candidate["name"],
        "url": candidate["url"],
        "tier": candidate.get("tier", "?"),
        "scope": candidate.get("scope", "?"),
        "editoria": candidate.get("editoria", "?"),
        "origem": candidate.get("origem", ""),
        "status": "UNKNOWN",
        "http_status": None,
        "items_count": 0,
        "first_title": "",
        "first_link": "",
        "duration_s": 0,
        "method_used": "",
        "error": ""
    }

    url = candidate["url"]
    start = time.time()

    # Adicionar pequeno jitter nos testes para simular concorrência realista
    import random
    time.sleep(random.uniform(0.05, 0.2))

    # 1. Tentar feedparser com pre-fetch via requests (com retry)
    feed = None
    for attempt in range(2):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            result["http_status"] = response.status_code
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                if feed.entries:
                    result["status"] = "APROVADO"
                    result["method_used"] = "feedparser_prefetched"
                    result["items_count"] = len(feed.entries)
                    result["first_title"] = clean_html(feed.entries[0].get("title", ""))
                    result["first_link"] = feed.entries[0].get("link", "")
                    break
        except Exception as e:
            log.warning(f"[{candidate['id']}] Pré-busca HTTP falhou (tentativa {attempt+1}/2): {e}")
            if attempt == 0:
                time.sleep(2)

    # Fallback caso a pré-busca falhe ou retorne feed vazio
    if not feed or not feed.entries:
        try:
            # 2. Tentar feedparser nativo (caso requests tenha algum problema específico)
            feed = feedparser.parse(url, agent=HEADERS["User-Agent"])
            if feed.entries:
                result["status"] = "APROVADO"
                result["method_used"] = "feedparser_native"
                result["items_count"] = len(feed.entries)
                result["first_title"] = clean_html(feed.entries[0].get("title", ""))
                result["first_link"] = feed.entries[0].get("link", "")
        except Exception as e:
            result["error"] = str(e)

    # Se ainda estiver reprovado/vazio, tentar WordPress API
    if result["status"] != "APROVADO":
        # 3. Fallback: WordPress REST API
        wp_articles = try_wordpress_api(url)
        if wp_articles:
            result["status"] = "APROVADO"
            result["method_used"] = "wordpress_api_fallback"
            result["items_count"] = len(wp_articles)
            result["first_title"] = wp_articles[0].get("title", "")
            result["first_link"] = wp_articles[0].get("link", "")
        else:
            # 4. Verificar HTTP status bruto se ainda não obtido
            if result["http_status"] is None:
                try:
                    resp = requests.head(url, headers=HEADERS, timeout=10,
                                         verify=False, allow_redirects=True)
                    result["http_status"] = resp.status_code
                except Exception:
                    try:
                        resp = requests.get(url, headers=HEADERS, timeout=10,
                                           verify=False, allow_redirects=True)
                        result["http_status"] = resp.status_code
                    except Exception as e:
                        result["error"] = f"Conexão falhou: {e}"
                        result["status"] = "REPROVADO"
                        result["duration_s"] = round(time.time() - start, 2)
                        return result

            if result["http_status"] and result["http_status"] < 400:
                result["status"] = "VAZIO"
                result["error"] = f"HTTP {result['http_status']} mas feedparser não encontrou entries"
            else:
                result["status"] = "REPROVADO"
                err_msg = f"HTTP {result['http_status'] or '?'}"
                # Verificar se a URL é recuperável via blocked-page-recovery
                if result.get("http_status") in (401, 403, 429) or not result.get("http_status"):
                    try:
                        from recover_page import recover_page
                        rec = recover_page(url, timeout=6.0, try_direct_first=False)
                        if rec.success:
                            err_msg += f" (Bloqueio WAF/403 detectado - Recuperável via {rec.method_used})"
                    except Exception:
                        pass
                result["error"] = err_msg

    result["duration_s"] = round(time.time() - start, 2)
    return result


def generate_report(results):
    """Gera relatório Markdown com os resultados da validação."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    now = datetime.datetime.now().strftime("%H:%M:%S")

    approved = [r for r in results if r["status"] == "APROVADO"]
    empty = [r for r in results if r["status"] == "VAZIO"]
    failed = [r for r in results if r["status"] == "REPROVADO"]

    lines = []
    lines.append(f"# Relatório de Validação de Feeds RSS — {today}")
    lines.append("")
    lines.append(f"Gerado em: {today} às {now}")
    lines.append(f"Total testado: {len(results)} | Aprovados: {len(approved)} | "
                 f"Vazios: {len(empty)} | Reprovados: {len(failed)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Resumo visual
    lines.append("## Resumo")
    lines.append("")
    for r in results:
        icon = "✅" if r["status"] == "APROVADO" else "⚠️" if r["status"] == "VAZIO" else "❌"
        lines.append(f"{icon} `{r['id']}` — **{r['name']}** | {r['items_count']} itens | "
                     f"{r['duration_s']}s | via {r['method_used'] or r['error']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detalhados aprovados
    if approved:
        lines.append(f"## ✅ Aprovados ({len(approved)})")
        lines.append("")
        lines.append("| # | ID | Nome | Itens | Método | Tempo | Primeira notícia |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, r in enumerate(approved, 1):
            title_short = r["first_title"][:60] + ("…" if len(r["first_title"]) > 60 else "")
            lines.append(f"| {i} | `{r['id']}` | {r['name']} | {r['items_count']} | "
                         f"{r['method_used']} | {r['duration_s']}s | {title_short} |")
        lines.append("")

    # Vazios
    if empty:
        lines.append(f"## ⚠️ Vazios ({len(empty)})")
        lines.append("")
        lines.append("| ID | Nome | HTTP | Erro |")
        lines.append("|---|---|---|---|")
        for r in empty:
            lines.append(f"| `{r['id']}` | {r['name']} | {r['http_status'] or '?'} | {r['error']} |")
        lines.append("")

    # Reprovados
    if failed:
        lines.append(f"## ❌ Reprovados ({len(failed)})")
        lines.append("")
        lines.append("| ID | Nome | Erro |")
        lines.append("|---|---|---|")
        for r in failed:
            lines.append(f"| `{r['id']}` | {r['name']} | {r['error']} |")
        lines.append("")

    # Bloco JSON para copiar-colar no sources.json (apenas aprovados)
    if approved:
        lines.append("---")
        lines.append("")
        lines.append("## JSON dos Aprovados (pronto para sources.json)")
        lines.append("")
        lines.append("```json")
        sources_list = []
        for r in approved:
            entry = {
                "id": r["id"],
                "name": r["name"],
                "url": r["url"],
                "method": "rss",
                "tier": r["tier"],
                "scope": r["scope"],
                "enabled": True,
                "_note": f"Editoria: {r['editoria']}. Validado {today} ({r['method_used']})."
            }
            sources_list.append(entry)
        lines.append(json.dumps(sources_list, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Valida feeds RSS candidatos")
    parser.add_argument("--input", type=str, default=str(CANDIDATES_JSON),
                        help="Caminho para o JSON de candidatos")
    parser.add_argument("--json-output", action="store_true",
                        help="Também gera logs/feeds_validation_{date}.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        log.error(f"Arquivo de candidatos não encontrado: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = data.get("candidates", [])
    if not candidates:
        log.error("Nenhum candidato encontrado no arquivo.")
        sys.exit(1)

    log.info(f"Validando {len(candidates)} feeds RSS candidatos...")
    print("=" * 70)

    results = []
    for cand in candidates:
        log.info(f"Testando: {cand['name']} ({cand['id']})...")
        result = validate_feed(cand)
        results.append(result)

        icon = "✅" if result["status"] == "APROVADO" else "⚠️" if result["status"] == "VAZIO" else "❌"
        print(f"  {icon} {result['status']} | {result['items_count']} itens | "
              f"{result['duration_s']}s | via {result['method_used'] or result['error']}")
        if result["first_title"]:
            print(f"     → '{result['first_title'][:80]}'")
        print("-" * 70)

    # Gerar relatório Markdown
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    report_path = LOGS_DIR / f"feeds_validation_{today}.md"
    report = generate_report(results)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n📄 Relatório salvo: {report_path}")

    # Opcional: JSON
    if args.json_output:
        json_path = LOGS_DIR / f"feeds_validation_{today}.json"
        json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📊 JSON salvo: {json_path}")

    # Resumo final
    approved = [r for r in results if r["status"] == "APROVADO"]
    empty = [r for r in results if r["status"] == "VAZIO"]
    failed = [r for r in results if r["status"] == "REPROVADO"]
    print(f"\n📊 Total: {len(results)} | ✅ Aprovados: {len(approved)} | "
          f"⚠️ Vazios: {len(empty)} | ❌ Reprovados: {len(failed)}")

    sys.exit(0)


if __name__ == "__main__":
    main()
