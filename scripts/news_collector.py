#!/usr/bin/env python3
"""
Módulo Coletor de Notícias — Web Jornal Vale da Liberdade.

Este script é responsável por buscar notícias recentes das fontes configuradas,
filtrar duplicações usando um cache local e retornar a lista de artigos candidatos.
Usa execução paralela (ThreadPoolExecutor) para maior desempenho.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
import unicodedata
import urllib3
from pathlib import Path
import requests
import feedparser
from bs4 import BeautifulSoup
from minhash_dedup import DedupStore


_STOPWORDS_PT = {
    "de", "o", "a", "os", "as", "em", "para", "com", "que", "do", "da", "no", "na",
    "e", "um", "uma", "uns", "umas", "se", "por", "com", "como", "mais", "menos",
    "ao", "aos", "à", "às", "pelo", "pela", "pelos", "pelas", "num", "numa", "ante",
    "após", "até", "sob", "entre", "desde", "sem", "sob", "sobre", "trás", "sua",
    "seu", "suas", "seus", "já", "ainda", "também", "só", "apenas", "agora", "hoje",
    "ontem", "amanhã", "onde", "quando", "porque", "pois", "fazer", "ficar", "ter",
    "diz", "disse", "era", "foi", "ser", "está", "estava", "tem", "tinha", "mais",
    "muito", "bem", "assim", "então", "depois", "antes", "casa", "nova", "novo",
}


def _normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_intersection(text_a: str, text_b: str) -> float:
    a = _normalize_text(text_a)
    b = _normalize_text(text_b)
    tokens_a = {t for t in a.split(" ") if t and t not in _STOPWORDS_PT and len(t) > 2}
    tokens_b = {t for t in b.split(" ") if t and t not in _STOPWORDS_PT and len(t) > 2}
    if not tokens_a or not tokens_b:
        return 0.0
    inter = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(inter) / len(union)


def _keyword_overlap_score(text_a: str, text_b: str) -> float:
    return _token_intersection(text_a, text_b)

# Desabilitar avisos de SSL inseguro (comum em portais locais)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuração de caminhos
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCES_JSON = PROJECT_ROOT / "sources" / "sources.json"
CACHE_JSON = PROJECT_ROOT / "sources" / "cache.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("news-collector")

# User-Agent realista para evitar bloqueios HTTP
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def load_config():
    """Carrega fontes do sources.json."""
    if not SOURCES_JSON.exists():
        log.error(f"Configuração {SOURCES_JSON} não encontrada. Criando com valores padrão...")
        return {"sources": []}
    with open(SOURCES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cache():
    """Carrega o cache.json."""
    if not CACHE_JSON.exists():
        return {"schema_version": "1.0", "last_run": {}, "source_stats": {}, "url_cache": {}, "content_hashes": {}}
    try:
        with open(CACHE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Erro ao ler cache.json ({e}). Criando novo cache...")
        return {"schema_version": "1.0", "last_run": {}, "source_stats": {}, "url_cache": {}, "content_hashes": {}}


def save_cache(cache):
    """Grava o cache.json de forma segura."""
    try:
        # Limpar entradas antigas do cache de URLs (TTL de 7 dias = 168 horas)
        now = datetime.datetime.now()
        cleaned_url_cache = {}
        for url, timestamp_str in cache.get("url_cache", {}).items():
            try:
                ts = datetime.datetime.fromisoformat(timestamp_str)
                if (now - ts).days < 7:
                    cleaned_url_cache[url] = timestamp_str
            except Exception:
                pass
        cache["url_cache"] = cleaned_url_cache

        with open(CACHE_JSON, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Erro ao salvar cache.json: {e}")


def clean_html(html_content):
    """Remove tags HTML e normaliza espaços."""
    if not html_content:
        return ""
    # Se for string com HTML, usa BeautifulSoup
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator=" ")
        # Remover múltiplos espaços/quebras de linha
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        # Fallback regex simples
        text = re.sub(r"<[^>]*>", " ", html_content)
        return re.sub(r"\s+", " ", text).strip()


def is_recent(article_date, hours=48):
    """Verifica se a data do artigo está dentro do limite em horas."""
    if not article_date:
        return True  # Se não houver data, assume que é recente para não perder notícias
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if isinstance(article_date, datetime.datetime):
        # Normalizar para tz-aware se necessário
        if article_date.tzinfo is None:
            article_date = article_date.replace(tzinfo=datetime.timezone.utc)
        delta = now - article_date
        return delta.total_seconds() <= hours * 3600
        
    return True


def _content_fingerprint(title: str, content: str = "") -> str:
    """Gera fingerprint SHA-256 normalizado de título+início do conteúdo.

    Remove acentos, pontuação e normaliza whitespace para capturar a mesma
    notícia em portais diferentes com URLs distintas. Trunca o conteúdo aos
    primeiros 300 chars para focar no lead da notícia (onde a informação
    essencial está).
    """
    import unicodedata

    text = (title + " " + (content or "")[:300]).lower()
    # Remove acentos: á→a, ç→c, etc.
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Remove tudo que não é alfanumérico ou espaço
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # Colapsa whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def try_wordpress_api(base_url):
    """Tenta buscar artigos via WordPress REST API."""
    # Remover feed/ se presente no fim da url
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
                content_raw = post.get("content", {}).get("rendered", "") or post.get("excerpt", {}).get("rendered", "")
                content = clean_html(content_raw)
                
                # Parse data
                date_str = post.get("date_gmt", "") or post.get("date", "")
                pub_date = None
                if date_str:
                    try:
                        pub_date = datetime.datetime.fromisoformat(date_str).replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        pass
                
                articles.append({
                    "title": clean_html(title),
                    "link": link,
                    "published": pub_date,
                    "content": content
                })
            return articles
    except Exception as e:
        log.debug(f"WP-API falhou para {base_url}: {e}")
    return None


def fetch_rss_source(source, hours=48):
    """Busca notícias via RSS feed parser com retry e pre-fetching."""
    url = source["url"]
    log.info(f"[{source['id']}] Buscando feed RSS...")
    articles = []
    
    feed = None
    # 2 tentativas de requisição HTTP para tolerar instabilidades de rede e DNS
    for attempt in range(2):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                break
            else:
                log.warning(f"[{source['id']}] HTTP {response.status_code} ao buscar RSS (tentativa {attempt+1}/2).")
        except Exception as e:
            log.warning(f"[{source['id']}] Erro na requisição HTTP (tentativa {attempt+1}/2): {e}")
            if attempt == 0:
                time.sleep(2)  # Aguardar 2s antes de tentar novamente

    # Fallback caso a requisição HTTP direta falhe ou retorne não-200
    if not feed or not feed.entries:
        log.info(f"[{source['id']}] Tentando feedparser nativo como fallback...")
        try:
            feed = feedparser.parse(url, agent=HEADERS["User-Agent"])
        except Exception as e:
            log.warning(f"[{source['id']}] Fallback do feedparser nativo falhou: {e}")

    # Se ainda estiver sem entries, tenta o WordPress API como fallback
    if not feed or not feed.entries:
        log.info(f"[{source['id']}] Feed vazio ou falhou. Tentando WordPress API...")
        wp_articles = try_wordpress_api(url)
        if wp_articles:
            log.info(f"[{source['id']}] Sucesso via WordPress API! Coletados: {len(wp_articles)}")
            return wp_articles, True
        return [], False

    try:
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            
            # Tentar pegar conteúdo extendido se disponível
            content = summary
            if "content" in entry:
                content = entry.content[0].value
            
            # Data de publicação
            pub_date = None
            if "published_parsed" in entry and entry.published_parsed:
                try:
                    pub_date = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
                except Exception:
                    pass
            
            # Filtrar por recência
            if is_recent(pub_date, hours):
                articles.append({
                    "title": clean_html(title),
                    "link": link,
                    "published": pub_date,
                    "content": clean_html(content)
                })
        
        return articles, True
    except Exception as e:
        log.error(f"[{source['id']}] Erro ao processar feed parseado: {e}")
        # Tenta WordPress API no erro total
        wp_articles = try_wordpress_api(url)
        if wp_articles:
            return wp_articles, True
        return [], False



def fetch_scraping_source(source, hours=48):
    """Coleta notícias através de scraping básico de HTML."""
    url = source["url"]
    log.info(f"[{source['id']}] Scraping HTML...")
    articles = []
    
    # Tenta WordPress REST API primeiro, já que muitos sites locais usam WordPress
    wp_articles = try_wordpress_api(url)
    if wp_articles:
        log.info(f"[{source['id']}] WordPress REST API detectada na home! Artigos obtidos: {len(wp_articles)}")
        return wp_articles, True

    try:
        response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if response.status_code != 200:
            log.warning(f"[{source['id']}] Código de retorno: {response.status_code}")
            return [], False
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Scraping genérico: busca tags <a> com títulos dentro de headers ou artigos
        # Procura por seletores comuns em portais de notícias
        selectors = [
            "article a", "h2 a", "h1 a", "h3 a", ".post-title a", 
            ".entry-title a", ".card-title a", ".noticia a"
        ]
        
        candidates = []
        for sel in selectors:
            elements = soup.select(sel)
            if elements:
                candidates.extend(elements)
                
        # Filtrar e limpar candidatos
        seen_links = set()
        for a in candidates:
            title = a.get_text().strip()
            href = a.get("href")
            
            if not title or not href or len(title) < 15:
                continue
                
            # Normalizar URL
            if href.startswith("/"):
                # Obter base url
                parsed_url = requests.utils.urlparse(url)
                href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
            elif not href.startswith("http"):
                continue
                
            if href in seen_links or href == url:
                continue
                
            seen_links.add(href)
            
            articles.append({
                "title": clean_html(title),
                "link": href,
                "published": datetime.datetime.now(datetime.timezone.utc),  # Scraping home não tem data confiável
                "content": title  # Sem conteúdo estendido no scrape básico
            })
            
            # Limita a 10 artigos por fonte para evitar poluição
            if len(articles) >= 10:
                break
                
        return articles, True
    except Exception as e:
        log.error(f"[{source['id']}] Erro no scraping: {e}")
        return [], False


def fetch_browser_source(source, hours=48):
    """
    Coleta notícias via Playwright headless browser (Tier 3).
    Útil para sites com Cloudflare ou carregamento JS pesado.
    """
    url = source["url"]
    log.info(f"[{source['id']}] Iniciando Playwright browser...")
    articles = []
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning(f"[{source['id']}] Playwright não está instalado. Pulando para fallback HTTP...")
        return fetch_scraping_source(source, hours)
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Configurar user agent e viewport
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            
            # Ir para a URL com timeout
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            
            # Aguardar um momento para execução de JS
            page.wait_for_timeout(3000)
            
            # Extrair conteúdo HTML
            content = page.content()
            browser.close()
            
            # Analisar com BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")
            selectors = ["article a", "h2 a", "h1 a", "h3 a", ".post-title a", ".entry-title a", ".card-title a"]
            candidates = []
            for sel in selectors:
                candidates.extend(soup.select(sel))
                
            seen_links = set()
            for a in candidates:
                title = a.get_text().strip()
                href = a.get("href")
                if not title or not href or len(title) < 15:
                    continue
                if href.startswith("/"):
                    parsed_url = requests.utils.urlparse(url)
                    href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
                elif not href.startswith("http"):
                    continue
                if href in seen_links or href == url:
                    continue
                seen_links.add(href)
                articles.append({
                    "title": clean_html(title),
                    "link": href,
                    "published": datetime.datetime.now(datetime.timezone.utc),
                    "content": title
                })
                if len(articles) >= 10:
                    break
            return articles, True
    except Exception as e:
        log.error(f"[{source['id']}] Falha na execução do Playwright: {e}")
        log.info(f"[{source['id']}] Usando fallback de scraping HTTP...")
        return fetch_scraping_source(source, hours)


def fetch_source_wrapper(source, hours=48):
    """Wrapper para despachar a coleta com base no método da fonte."""
    # Adicionar jitter aleatório mais espaçado para evitar concorrência e problemas de resolução de DNS
    import random
    time.sleep(random.uniform(0.2, 1.0))

    start_time = time.time()
    method = source.get("method", "rss")
    
    items, success = [], False
    try:
        if method == "rss":
            items, success = fetch_rss_source(source, hours)
        elif method == "browser":
            items, success = fetch_browser_source(source, hours)
        else:  # scraping
            items, success = fetch_scraping_source(source, hours)
            
        # Garantir que todos os itens tenham a referência correta do source_id
        for item in items:
            item["source_id"] = source["id"]
    except Exception as e:
        log.error(f"[{source['id']}] Erro crítico/inesperado na coleta: {e}")
        
    duration = time.time() - start_time
    return {
        "id": source["id"],
        "name": source["name"],
        "success": success,
        "items": items,
        "duration": duration
    }



def sync_registry_metrics(cache: dict) -> None:
    """Sincroniza artigos coletados/scrape-error do cache.json para o registry.

    O registry (sources_registry.json) é a base de governança; o collector
    grava estatísticas em cache.json (source_stats). Esta função copia essas
    contagens para o registry para alimentar o período probatório.
    """
    reg_path = PROJECT_ROOT / "sources" / "sources_registry.json"
    if not reg_path.exists():
        return
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return
    stats = cache.get("source_stats", {})
    changed = False
    for s in reg.get("sources", []):
        sid = s.get("id")
        st = stats.get(sid)
        if not st:
            continue
        m = s.setdefault("metrics", {})
        m["articles_collected"] = m.get("articles_collected", 0) + st.get("count", 0)
        total = st.get("total_fetches", 0)
        success = st.get("success_count", 0)
        m["scrape_error_rate"] = round(1 - (success / total), 3) if total else None
        m["last_scored_at"] = datetime.datetime.now().isoformat()
        changed = True
    if changed:
        reg["last_updated"] = datetime.datetime.now().isoformat()
        try:
            reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning(f"Falha ao sincronizar registry: {exc}")


def collect_all_news(hours=48, parallel=True):
    """Executa a coleta de notícias de todas as fontes habilitadas."""
    config = load_config()
    cache = load_cache()
    
    active_sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    log.info(f"Iniciando coleta de {len(active_sources)} fontes habilitadas...")
    
    collected_articles = []
    sources_used = []
    stats_updates = {}
    
    # Execução Paralela ou Serial (reduzida para max_workers=5 para evitar gargalos e erros DNS no Windows)
    if parallel and len(active_sources) > 1:
        workers = min(5, len(active_sources))
        log.info(f"Executando coleta em paralelo (ThreadPoolExecutor com {workers} workers)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Enviar tarefas
            futures = {executor.submit(fetch_source_wrapper, src, hours): src for src in active_sources}
            # Coletar resultados
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                sources_used.append(res["id"])
                stats_updates[res["id"]] = {
                    "success": res["success"],
                    "duration": res["duration"],
                    "count": len(res["items"])
                }
                if res["success"]:
                    collected_articles.extend(res["items"])
    else:
        log.info("Executando coleta de forma sequencial...")
        for src in active_sources:
            res = fetch_source_wrapper(src, hours)
            sources_used.append(res["id"])
            stats_updates[res["id"]] = {
                "success": res["success"],
                "duration": res["duration"],
                "count": len(res["items"])
            }
            if res["success"]:
                collected_articles.extend(res["items"])

    # Deduplicação baseada no cache.json
    now_str = datetime.datetime.now().isoformat()
    url_cache = cache.setdefault("url_cache", {})
    content_hashes = cache.setdefault("content_hashes", {})
    # Normaliza entradas antigas do cache (hash → url) para o novo formato
    # hash → {url, title, first_seen, source}.
    for fp, value in list(content_hashes.items()):
        if isinstance(value, str):
            content_hashes[fp] = {
                "url": value,
                "title": "",
                "first_seen": None,
                "source": "unknown"
            }
    
    unique_articles = []
    duplicates_count = 0
    content_dup_count = 0
    semantic_dup_count = 0
    dedup_store = DedupStore(window=50, threshold=0.80)
    filtered_signatures: list[tuple[str, tuple[int, ...]]] = []
    max_signature_window = 50

    for art in collected_articles:
        link = art["link"]
        if link in url_cache:
            duplicates_count += 1
            continue

        fp = _content_fingerprint(art.get("title", ""), art.get("content", ""))
        if fp in content_hashes:
            content_dup_count += 1
            log.debug(f"Content dedup: '{art.get('title', '')[:60]}' (hash={fp[:12]}…)")
            continue

        title = art.get("title", "") or ""

        if dedup_store.is_duplicate(title):
            semantic_dup_count += 1
            log.debug(f"MinHash dedup: '{title[:60]}' considerado duplicata semântica.")
            continue

        recent_titles = [t for t, _ in filtered_signatures[-max_signature_window:]]
        for prev_title in recent_titles:
            score = _keyword_overlap_score(title, prev_title)
            if score >= 0.70:
                semantic_dup_count += 1
                log.debug(
                    f"Keyword dedup: '{title[:60]}' similar a '{prev_title[:60]}' (score={score:.2f})"
                )
                break
        else:
            unique_articles.append(art)
            sig = dedup_store.hasher.signature(title) if title.strip() else ()
            filtered_signatures.append((title, sig))

        content_hashes[fp] = {
            "url": link,
            "title": title,
            "first_seen": now_str,
            "source": art.get("source_id", "unknown"),
        }

    log.info(
        f"Coleta concluída. Total bruto: {len(collected_articles)} | "
        f"URL-duplicados: {duplicates_count} | Content-duplicados: {content_dup_count} | "
        f"MinHash-duplicados: {semantic_dup_count} | Candidatos únicos: {len(unique_articles)}"
    )
    
    # Atualizar estatísticas no cache
    source_stats = cache.setdefault("source_stats", {})
    for src_id, update in stats_updates.items():
        stats = source_stats.setdefault(src_id, {
            "total_fetches": 0, "success_count": 0, "avg_items_per_fetch": 0, "last_fetch": None
        })
        stats["total_fetches"] += 1
        if update["success"]:
            stats["success_count"] += 1
        stats["last_fetch"] = now_str
        # Média móvel simples para itens
        stats["avg_items_per_fetch"] = round(
            (stats["avg_items_per_fetch"] * 0.7) + (update["count"] * 0.3), 1
        )
        
    cache["last_run"] = {
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "duration_seconds": int(sum(u["duration"] for u in stats_updates.values())),
        "items_collected": len(collected_articles),
        "sources_used": sources_used,
        "url_duplicates": duplicates_count,
        "content_duplicates": content_dup_count,
        "semantic_duplicates": semantic_dup_count,
    }
    
    save_cache(cache)
    sync_registry_metrics(cache)
    
    # Converter datas para strings serializáveis em JSON
    for art in unique_articles:
        if isinstance(art["published"], datetime.datetime):
            art["published"] = art["published"].isoformat()
            
    return unique_articles


def test_sources():
    """Verifica e exibe a saúde de todas as fontes sem salvar no cache real."""
    print("\n🔍 Testando conectividade e parsing de fontes...")
    print("=" * 70)
    config = load_config()
    sources = config.get("sources", [])
    
    for src in sources:
        print(f"Fonte: {src['name']} ({src['id']}) - Método: {src['method']}")
        res = fetch_source_wrapper(src, hours=48)
        status = "✅ SUCESSO" if res["success"] else "❌ FALHA"
        print(f"  Status: {status} (tempo: {res['duration']:.2f}s)")
        print(f"  Notícias coletadas: {len(res['items'])}")
        if res["items"]:
            print(f"  Primeira notícia: '{res['items'][0]['title']}'")
            print(f"  Link: {res['items'][0]['link']}")
        print("-" * 70)


def main():
    parser = argparse.ArgumentParser(description="Coletor de notícias do Web Jornal")
    parser.add_argument("--test-sources", action="store_true", help="Testar fontes e sair")
    parser.add_argument("--hours", type=int, default=48, help="Janela de tempo em horas para buscar notícias")
    args = parser.parse_args()
    
    if args.test_sources:
        test_sources()
        sys.exit(0)
        
    articles = collect_all_news(hours=args.hours)
    print(json.dumps(articles, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
