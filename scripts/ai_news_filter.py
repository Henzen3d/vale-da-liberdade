#!/usr/bin/env python3
"""
Módulo de Filtragem e Categorização Determinística — Web Jornal Vale da Liberdade.

Este módulo produz:
  - Scoring programático: geo_score, credibility_score, recency_decay, burst_score
  - Categorização por palavras-chave ponderadas
  - Ranking final (relevance_score composto)
  - candidates-{date}.json (input para o Hermes Agent)
  - fallback_heuristic_filter() permanece como filtro offline (sem Hermes)
"""

import json
import logging
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

# Configuração de caminhos e logging
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("news-filter")

# ---------------------------------------------------------------------------
# Schema de Saída Estruturada (Pydantic) — contratos de dados preservados
# ---------------------------------------------------------------------------

class NewsItem(BaseModel):
    title: str = Field(description="Título da notícia em português, limpo e direto.")
    url: str = Field(description="Link/URL original da notícia.")
    summary: str = Field(
        description=(
            "Resumo conciso da notícia em 2 a 4 frases. DEVE ser escrito usando voz ativa e focar em "
            "resultados e impactos reais para o cidadão/ouvinte local (evitando jargões e tom passivo)."
        )
    )
    key_points: List[str] = Field(
        description=(
            "Lista de EXATAMENTE 3 pontos principais detalhando a notícia. Cada ponto DEVE conter dados "
            "específicos, valores financeiros (R$), porcentagens, datas concretas ou nomes de órgãos/"
            "entidades envolvidas. EVITE generalizações."
        )
    )
    category: str = Field(
        description="Categoria/quadro da notícia. DEVE ser um de: seguranca, saude, educacao, politica, esportes, rapidinhas"
    )
    quality_score: int = Field(
        description="Nota de 1 a 5 de relevância e interesse público (5 = excelente/alta relevância)."
    )


class NewsAnalysis(BaseModel):
    selected_items: List[NewsItem] = Field(
        description="Lista de notícias selecionadas após filtragem e avaliação de qualidade."
    )


# ---------------------------------------------------------------------------
# Dicionários de scoring determinístico
# ---------------------------------------------------------------------------

# Entidades geo com peso — Blumenau=1.0, região Alto Vale=0.8, SC=0.5,
# nacional-com-impacto=0.3. Múltiplas entidades: score máximo.
GEO_WEIGHTS: dict[str, float] = {
    # Blumenau
    "blumenau": 1.0, "blumenauense": 1.0, "blumenauenses": 1.0,
    "rua xv de novembro": 1.0, "victor konder": 1.0, "parque vila germânica": 1.0,
    # Alto Vale e Região
    "rio do sul": 0.9, "indaial": 0.85, "pomerode": 0.85, "timbó": 0.85,
    "apiúna": 0.8, "ibirama": 0.8, "presidente getúlio": 0.8, "pouso redondo": 0.8,
    "taió": 0.8, "agronômica": 0.8, "ituporanga": 0.8, "petrolândia": 0.8,
    "lontras": 0.8, "mirim doce": 0.8, "dona emma": 0.8, "dr pedrinho": 0.8,
    "gaspar": 0.85, "brusque": 0.75, "itajaí": 0.75,
    "vale do itajaí": 0.9, "alto vale": 0.9, "médio vale": 0.85,
    # Santa Catarina (estado)
    "santa catarina": 0.5, "alesc": 0.5, "florianópolis": 0.45,
    "joinville": 0.4, "chapecó": 0.4, "criciúma": 0.4, "lages": 0.4,
    "casan": 0.5, "celesc": 0.5,
    # Nacional com impacto local
    "brasil": 0.3, "federal": 0.25, "senado": 0.25, "câmara federal": 0.25,
}

# Palavras-chave de categorização por quadro (ordenar do mais específico para o mais geral)
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "seguranca": [
        "policia", "polícia", "crime", "assalto", "roubo", "furto", "homicídio",
        "homicidio", "acidente", "batida", "colisão", "colisao", "atropelamento",
        "bombeiros", "resgate", "ocorrência", "ocorrencia", "prisão", "prisao",
        "preso", "detento", "droga", "tráfico", "trafico", "violência", "violencia",
        "agressão", "agressao", "feminicídio", "feminicidio", "trânsito", "transito",
        "bloqueio", "interdição", "interdicao"
    ],
    "saude": [
        "saúde", "saude", "hospital", "upa", "sus", "médico", "medico", "enfermeiro",
        "dengue", "covid", "gripe", "vacina", "vacinação", "vacinacao", "leito",
        "internação", "internacao", "cirurgia", "emergência", "emergencia", "pronto-socorro",
        "vigilância sanitária", "vigilancia sanitaria", "epidemia", "endemia", "surto",
        "consulta", "exame", "farmácia", "farmacia", "postos de saúde"
    ],
    "educacao": [
        "escola", "colégio", "colegio", "creche", "educação", "educacao", "aluno",
        "professor", "greve", "furb", "enem", "vestibular", "matrícula", "matricula",
        "merenda", "transporte escolar", "universidade", "faculdade", "ensino",
        "aprendizagem", "pedagógico", "pedagogico", "secretaria de educação"
    ],
    "politica": [
        "prefeito", "vereador", "câmara", "camara", "prefeitura", "licitação", "licitacao",
        "contrato", "imposto", "iptu", "issqn", "icms", "tributo", "taxa", "decreto",
        "lei municipal", "lei estadual", "orçamento", "orcamento", "gasto", "investimento",
        "governador", "deputado", "senador", "eleição", "eleicao", "candidato",
        "partido", "gestão", "gestao", "administração", "administracao", "secretaria",
        "corrupção", "corrupcao", "desvio", "fraude", "irregular", "auditoria",
        "tce", "tcu", "ministério público", "mp"
    ],
    "esportes": [
        "futebol", "voleibol", "vôlei", "basquete", "atletismo", "esporte", "time",
        "campeonato", "copa", "torneio", "estádio", "ginásio", "ginasio", "arena",
        "treino", "jogo", "partida", "gol", "título", "titulo", "festival",
        "cultura", "evento", "festa", "comunidade", "associação", "associacao",
        "bairro", "lazer", "praça", "praca", "parque"
    ],
    "rapidinhas": [
        "absurdo", "burocracia", "regulamentação", "regulamentacao", "decreto bizarro",
        "proibido", "multa", "fiscalização", "fiscalizacao", "inusitado", "polêmica",
        "polemica", "imposto novo", "taxa nova", "licença", "licenca", "alvará",
        "exigência", "exigencia", "obrigatório", "obrigatorio"
    ],
}

# Termos de urgência / breaking-news
URGENCY_TERMS: list[str] = [
    "urgente", "breaking", "ao vivo", "agora", "momento", "alerta", "atenção",
    "atencao", "emergência", "emergencia", "morte", "morto", "vítima", "vitima",
    "explosão", "explosao", "incêndio", "incendio", "desabamento", "enchente",
    "alagamento", "inundação", "inundacao"
]

# Fonte → tier (complementa sources.json sem depender de leitura em cada call)
DEFAULT_TIER_SCORE: dict[int, float] = {1: 1.0, 2: 0.7, 3: 0.4}
RELEVANCE_WEIGHTS = {
    "geo": 0.35,
    "cred": 0.20,
    "recency": 0.20,
    "urgency": 0.10,
    "engagement": 0.15,
}


# ---------------------------------------------------------------------------
# Funções de scoring determinístico
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normaliza para comparação: minúsculas, sem acentos básicos."""
    text = text.lower()
    # Manter acentos para matching (dicionário já tem acentuado e sem acento)
    return text


def geo_score(title: str, content: str) -> float:
    """Calcula score geográfico com base em entidades encontradas no texto."""
    text = _normalize_text(f"{title} {content[:500]}")
    max_weight = 0.0
    for entity, weight in GEO_WEIGHTS.items():
        if entity in text:
            max_weight = max(max_weight, weight)
    return max_weight


def categorize_article(title: str, content: str) -> str:
    """Categoriza o artigo no quadro mais provável por contagem de keywords."""
    text = _normalize_text(f"{title} {content[:500]}")
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > 0:
            scores[category] = count

    if not scores:
        return "politica"  # default
    return max(scores, key=lambda c: scores[c])


def recency_decay(published_str: str | None) -> float:
    """Score de recência: 1.0 para notícias < 6h, decai exponencialmente até 0.1 em 48h."""
    if not published_str:
        return 0.5  # sem data → neutro
    try:
        pub = datetime.fromisoformat(published_str)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        hours_ago = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        # f(h) = exp(-0.05 * h): 0h→1.0, 6h→0.74, 24h→0.30, 48h→0.09
        return round(max(0.05, math.exp(-0.05 * hours_ago)), 3)
    except Exception:
        return 0.5


def urgency_boost(title: str, content: str) -> float:
    """Boost se houver termos de urgência: 0.3 extra (cap 1.0 total)."""
    text = _normalize_text(f"{title} {content[:200]}")
    return 0.3 if any(term in text for term in URGENCY_TERMS) else 0.0


def detect_burst(articles: List[dict], window_hours: int = 6) -> set[str]:
    """
    Marca artigos como breaking quando:
    - contêm termos de urgência explícitos, OU
    - o mesmo tópico (palavras-chave compartilhadas) aparece em 2+ fontes
      independentes dentro da janela de tempo.
    """
    if len(articles) < 2:
        return set()

    topic_stop = {
        "de", "o", "a", "os", "as", "em", "para", "com", "que", "do", "da", "no", "na",
        "e", "um", "uma", "uns", "umas", "se", "por", "como", "mais", "menos",
    }

    def topic_words(title: str) -> set[str]:
        text = _normalize_text(title)
        tokens = re.findall(r"\w{3,}", text)
        return {t for t in tokens if t not in topic_stop}

    def parse_pub(art: dict):
        pub = art.get("published")
        if not pub:
            return None
        try:
            dt = datetime.fromisoformat(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    # Agrupa por tópico (interseção de palavras)
    topic_groups: list[list[dict]] = []
    assigned: set[int] = set()
    for i, art in enumerate(articles):
        if i in assigned:
            continue
        words_i = topic_words(art.get("title", ""))
        if not words_i:
            continue
        group = [art]
        assigned.add(i)
        for j, other in enumerate(articles):
            if j in assigned:
                continue
            words_j = topic_words(other.get("title", ""))
            if words_i.intersection(words_j):
                group.append(other)
                assigned.add(j)
        topic_groups.append(group)

    now = datetime.now(timezone.utc)
    breaking_ids: set[str] = set()

    for group in topic_groups:
        sources = {art.get("source_id") or art.get("url", "") for art in group}
        if len(sources) < 2:
            continue
        times = [parse_pub(art) for art in group if parse_pub(art) is not None]
        if len(times) < 2:
            continue
        newest = max(times)
        oldest = min(times)
        if (newest - oldest).total_seconds() <= window_hours * 3600:
            for art in group:
                breaking_ids.add(id(art))

    # Também marca urgência textual
    for art in articles:
        if urgency_boost(art.get("title", ""), art.get("content", "")) > 0:
            breaking_ids.add(id(art))

    return breaking_ids


def credibility_score(tier: int, source_id: str = "", stats: dict = None) -> float:
    """Converte tier da fonte em score de credibilidade, ponderando com estatísticas históricas."""
    base_score = DEFAULT_TIER_SCORE.get(tier, 0.5)
    if source_id and stats and source_id in stats:
        s = stats[source_id]
        total = s.get("total_fetches", 0)
        success = s.get("success_count", 0)
        if total >= 2:
            success_rate = success / total
            # Penaliza mais fortemente fontes instáveis: 30% base + 70% taxa de sucesso
            # Se success_rate < 0.5, credibilidade cai proporcionalmente.
            return round(base_score * 0.3 + success_rate * base_score * 0.7, 4)
    return base_score


def x_engagement_score(article: dict) -> float:
    """Extrai sinal de engajamento do artigo quando for um tweet do X."""
    content = article.get("content", "") or ""
    title = article.get("title", "") or ""
    source_id = article.get("source_id", "") or ""
    url = article.get("link", "") or article.get("url", "") or ""

    is_x = source_id == "x_twitter" or "x.com/" in url
    if not is_x:
        return 0.0

    likes = 0
    retweets = 0
    views = 0

    text = f"{title} | {content}"
    m_like = re.search(r"likes[:\s]*([0-9]+)", text, re.I)
    m_rt = re.search(r"RTs[:\s]*([0-9]+)", text, re.I)
    m_view = re.search(r"views[:\s]*([0-9]+)", text, re.I)
    if m_like:
        likes = int(m_like.group(1))
    if m_rt:
        retweets = int(m_rt.group(1))
    if m_view:
        views = int(m_view.group(1))

    engagement = likes + 2 * retweets + 0.1 * views
    if engagement <= 0:
        return 0.0

    # Escala logarítmica suave para não inflar posts virais extremos
    # 1000 engajamento => ~0.6, 100 => ~0.3, 10 => ~0.15
    return round(min(1.0, math.log10(engagement + 1) / 4.0), 4)


def compute_relevance(
    article: dict,
    source_tier: int = 2,
    source_id: str = "",
    stats: dict = None,
    is_breaking: bool = False,
) -> float:
    """
    Fórmula de relevância composta:
    relevance = w1*geo + w2*cred + w3*recency + w4*urgency + w5*engagement
    """
    title = article.get("title", "")
    content = article.get("content", "") or ""
    pub = article.get("published")
    if isinstance(pub, datetime):
        pub = pub.isoformat()

    g = geo_score(title, content)
    c = credibility_score(source_tier, source_id, stats)
    r = recency_decay(pub)
    u = urgency_boost(title, content)
    e = x_engagement_score(article)

    score = (
        RELEVANCE_WEIGHTS["geo"] * g
        + RELEVANCE_WEIGHTS["cred"] * c
        + RELEVANCE_WEIGHTS["recency"] * r
        + RELEVANCE_WEIGHTS["urgency"] * u
        + RELEVANCE_WEIGHTS["engagement"] * e
    )
    # Anti-clickbait: penaliza se o título contiver padrões clickbait
    clickbait_pattern = r"(entenda o caso|veja o vídeo|saiba mais|inacreditável|você não vai acreditar|choca a internet|descubra|veja fotos|vaza|revelado)"
    if re.search(clickbait_pattern, title.lower()):
        score -= 0.15

    # Fase 2.3 — boost temporário para breaking news detectadas por burst
    if is_breaking:
        score += 0.15

    return round(max(0.0, min(1.0, score)), 4)


def score_to_quality(relevance: float) -> int:
    """Converte relevance (0-1) em quality_score (1-5) compatível com o schema."""
    if relevance >= 0.75:
        return 5
    elif relevance >= 0.55:
        return 4
    elif relevance >= 0.35:
        return 3
    elif relevance >= 0.15:
        return 2
    return 1


def cluster_articles(articles: List[dict], threshold: float = 0.3) -> List[dict]:
    """
    Agrupa notícias similares em clusters.
    Cada cluster é representado pela notícia com maior relevância/qualidade,
    e herda referências/URLs das outras fontes (multi-source correlation).
    Aplica também cross-validation contra fake news (Fase 2.6).
    """
    def get_words(title: str) -> set[str]:
        words = re.findall(r"\w{4,}", title.lower())
        return set(words)

    clusters: list[list[dict]] = []
    
    for art in articles:
        art_words = get_words(art.get("title", ""))
        if not art_words:
            clusters.append([art])
            continue
            
        matched_cluster = None
        for cluster in clusters:
            rep_words = get_words(cluster[0].get("title", ""))
            intersection = art_words.intersection(rep_words)
            union = art_words.union(rep_words)
            similarity = len(intersection) / len(union) if union else 0.0
            
            if similarity >= threshold:
                matched_cluster = cluster
                break
                
        if matched_cluster is not None:
            matched_cluster.append(art)
        else:
            clusters.append([art])
            
    representative_articles = []
    for cluster in clusters:
        cluster.sort(key=lambda x: (x.get("quality_score", 3), len(x.get("summary", ""))), reverse=True)
        rep = cluster[0]
        
        if len(cluster) > 1:
            urls = [item.get("url") for item in cluster]
            rep["_correlated_urls"] = urls
            log.info(f"Cluster detectado: '{rep['title'][:50]}' correlacionado em {len(cluster)} fontes.")
            if len(cluster) >= 3:
                rep["quality_score"] = min(5, rep["quality_score"] + 1)
                log.info(f"  → Boost de tendência aplicado para '{rep['title'][:50]}'")
        else:
            if rep.get("quality_score", 3) <= 3:
                rep["_single_source_warning"] = True
                
        representative_articles.append(rep)
        
    return representative_articles


def filter_and_categorize_news(articles: List[dict], target_count: int = 20) -> List[dict]:
    """
    Filtra e categoriza notícias usando scoring determinístico (sem LLM).

    - Fase 2.3: detecção de breaking news por burst (2+ fontes em janela curta)
    Cotas por scope (Fase 3.1):
      - Local: até target_count notícias
      - Nacional: exatamente 1 notícia (categoria 'brasil')
      - Internacional: exatamente 1 notícia (categoria 'mundo')
    """
    if not articles:
        log.warning("Nenhum artigo recebido para filtragem.")
        return []

    breaking_ids = detect_burst(articles)

    # Carregar config de fontes e estatísticas do cache
    source_config = _load_source_config()

    cache_json = PROJECT_ROOT / "sources" / "cache.json"
    cache_stats = {}
    try:
        if cache_json.exists():
            with open(cache_json, "r", encoding="utf-8") as f:
                cache_stats = json.load(f).get("source_stats", {})
    except Exception:
        pass

    local_scored: list[dict] = []
    nacional_scored: list[dict] = []
    internacional_scored: list[dict] = []

    for art in articles:
        url = art.get("link", "") or art.get("url", "")
        title = art.get("title", "")
        content = art.get("content", "") or ""

        # Inferir tier, scope e id da fonte pela URL ou ID
        art_source_id = art.get("source_id", "")
        source_id = _infer_id_from_config(url, source_config, source_id=art_source_id)
        tier = _infer_tier_from_config(url, source_config, source_id=source_id)
        scope = _infer_scope_from_config(url, source_config, source_id=source_id)

        is_breaking = id(art) in breaking_ids

        # Calcular relevância
        relevance = compute_relevance(
            art,
            source_tier=tier,
            source_id=source_id,
            stats=cache_stats,
            is_breaking=is_breaking,
        )

        # Para fontes locais: filtrar por geo_score mínimo
        if scope == "local":
            g_score = geo_score(title, content)
            if g_score < 0.15:
                log.debug(f"Descartado local (geo_score={g_score:.2f}): {title[:60]}")
                continue
            category = categorize_article(title, content)
        elif scope == "nacional":
            category = "brasil"
        else:
            category = "mundo"

        quality = score_to_quality(relevance)

        summary = content[:250].strip() if content else title
        if summary and not summary.endswith("."):
            summary += "."

        key_points = [title]
        if content:
            sentences = [s.strip() for s in re.split(r"[.!?]", content) if len(s.strip()) > 20]
            key_points = sentences[:3] if sentences else [title, title, title]
        while len(key_points) < 3:
            key_points.append(key_points[-1] if key_points else title)

        item = {
            "title": title,
            "url": url,
            "summary": summary,
            "key_points": key_points[:3],
            "category": category,
            "quality_score": quality,
            "_relevance": relevance,
            "_scope": scope,
            "_is_breaking": is_breaking,
        }

        if scope == "local":
            local_scored.append(item)
        elif scope == "nacional":
            nacional_scored.append(item)
        else:
            internacional_scored.append(item)

    # Ordenar breaking primeiro dentro de cada escopo
    local_scored.sort(key=lambda x: (x["_is_breaking"], x["_relevance"]), reverse=True)
    nacional_scored.sort(key=lambda x: (x["_is_breaking"], x["_relevance"]), reverse=True)
    internacional_scored.sort(key=lambda x: (x["_is_breaking"], x["_relevance"]), reverse=True)

    # Aplicar clustering de eventos e cross-validation
    local_scored = cluster_articles(local_scored)

    # Ordenar novamente: breaking primeiro, depois por qualidade e relevância
    local_scored.sort(key=lambda x: (x["_is_breaking"], x["quality_score"], x["_relevance"]), reverse=True)
    nacional_scored.sort(key=lambda x: (x["_is_breaking"], x["_relevance"]), reverse=True)
    internacional_scored.sort(key=lambda x: (x["_is_breaking"], x["_relevance"]), reverse=True)

    # Aplicar cotas de diversidade de categorias (local)
    MAX_PER_CATEGORY = 5
    result: list[dict] = []
    category_counts: dict[str, int] = {}
    for item in local_scored:
        cat = item["category"]
        if category_counts.get(cat, 0) < MAX_PER_CATEGORY:
            result.append(item)
            category_counts[cat] = category_counts.get(cat, 0) + 1
        if len(result) >= target_count:
            break

    # Adicionar 1 nacional e 1 internacional
    if nacional_scored:
        best_nacional = nacional_scored[0]
        result.append(best_nacional)
        log.info(f"Nacional selecionado: {best_nacional['title'][:60]}")
    else:
        log.warning("Nenhuma notícia nacional encontrada nas fontes habilitadas.")

    if internacional_scored:
        best_internacional = internacional_scored[0]
        result.append(best_internacional)
        log.info(f"Internacional selecionado: {best_internacional['title'][:60]}")
    else:
        log.warning("Nenhuma notícia internacional encontrada nas fontes habilitadas.")

    # Remover campos internos
    for item in result:
        item.pop("_relevance", None)
        item.pop("_scope", None)

    log.info(
        f"Filtro determinístico: {len(articles)} brutos → "
        f"{len(local_scored)} locais agrupados + {len(nacional_scored)} nacionais + "
        f"{len(internacional_scored)} internacionais → {len(result)} selecionados"
    )
    return result


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _load_source_config() -> dict[str, dict]:
    """Carrega mapeamento url→{id, tier, scope} do sources.json."""
    sources_json = PROJECT_ROOT / "sources" / "sources.json"
    config_map: dict[str, dict] = {}
    try:
        with open(sources_json, "r", encoding="utf-8") as f:
            config = json.load(f)
        for src in config.get("sources", []):
            url = src.get("url", "")
            if url:
                config_map[url] = {
                    "id": src.get("id", ""),
                    "tier": src.get("tier", 2),
                    "scope": src.get("scope", "local"),
                }
    except Exception as e:
        log.warning(f"Não foi possível carregar sources.json: {e}")
    return config_map


def _load_source_tiers() -> dict[str, int]:
    """Retro-compat: carrega apenas tier (para chamadas legadas)."""
    return {url: cfg["tier"] for url, cfg in _load_source_config().items()}


def _infer_tier_from_config(article_url: str, source_config: dict[str, dict], source_id: str = "") -> int:
    """Infere tier de uma notícia pelo domínio da URL ou ID."""
    return _match_source_field(article_url, source_config, "tier", default=2, source_id=source_id)


def _infer_scope_from_config(article_url: str, source_config: dict[str, dict], source_id: str = "") -> str:
    """Infere scope (local/nacional/internacional) de uma notícia pelo domínio ou ID."""
    return _match_source_field(article_url, source_config, "scope", default="local", source_id=source_id)


def _infer_id_from_config(article_url: str, source_config: dict[str, dict], source_id: str = "") -> str:
    """Infere o id de uma notícia pelo domínio da URL ou ID."""
    return _match_source_field(article_url, source_config, "id", default="", source_id=source_id)


def _match_source_field(article_url: str, source_config: dict[str, dict], field: str, default, source_id: str = ""):
    """Helper genérico: casa URL da notícia com URL da fonte por domínio ou ID."""
    # 1. Se temos um ID de fonte, tenta buscar diretamente na configuração
    if source_id:
        for cfg in source_config.values():
            if cfg.get("id") == source_id:
                return cfg.get(field, default)

    # 2. Caso contrário, tenta casar por domínio
    try:
        from urllib.parse import urlparse
        art_domain = urlparse(article_url).netloc.lstrip("www.").lower()
        for src_url, cfg in source_config.items():
            src_domain = urlparse(src_url).netloc.lstrip("www.").lower()
            if not src_domain or not art_domain:
                continue
            
            # Caso especial para BBC
            is_art_bbc = "bbc" in art_domain
            is_src_bbc = "bbc" in src_domain
            if is_art_bbc and is_src_bbc:
                # Distinguir bbc_brasil de bbc_world pela URL do artigo
                is_art_portuguese = "portuguese" in article_url.lower() or "brasil" in article_url.lower()
                is_src_portuguese = "portuguese" in src_url.lower() or "brasil" in src_url.lower()
                if is_art_portuguese == is_src_portuguese:
                    return cfg.get(field, default)
                continue

            # Casamento por domínio padrão
            art_norm = art_domain.replace("bbci.", "bbc.")
            src_norm = src_domain.replace("bbci.", "bbc.")
            if src_norm in art_norm or art_norm in src_norm:
                return cfg.get(field, default)
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Fallback heurístico — modo offline (sem Hermes Agent disponível)
# ---------------------------------------------------------------------------

def fallback_heuristic_filter(articles: List[dict], target_count: int) -> List[dict]:
    """
    Filtro heurístico de fallback para quando o Hermes Agent não está disponível.
    Usa apenas correspondência de palavras-chave geográficas sem scoring composto.
    """
    log.info("Executando filtro heurístico de fallback (modo offline)...")
    keywords = [
        "blumenau", "rio do sul", "indaial", "pomerode", "vale do itajaí", "alto vale",
        "itajaí", "sc", "santa catarina", "prefeitura", "polícia", "vereador",
        "gaspar", "brusque", "timbó", "ibirama"
    ]
    selected = []
    for art in articles:
        title_lower = art.get("title", "").lower()
        content_lower = art.get("content", "").lower()

        has_kw = any(kw in title_lower or kw in content_lower for kw in keywords)
        if has_kw:
            category = categorize_article(art.get("title", ""), art.get("content", ""))
            selected.append({
                "title": art.get("title", ""),
                "url": art.get("link", "") or art.get("url", ""),
                "summary": art.get("title", ""),
                "key_points": [art.get("title", ""), art.get("title", ""), art.get("title", "")],
                "category": category,
                "quality_score": 3,
            })
        if len(selected) >= target_count:
            break
    return selected


# ---------------------------------------------------------------------------
# Exportar candidatos para Hermes Agent
# ---------------------------------------------------------------------------

def export_candidates(articles: List[dict], date: str) -> Path:
    """
    Exporta os candidatos ranqueados para episodes/_candidates-{date}.json.
    O Hermes Agent lê este arquivo para fazer a seleção editorial e enriquecimento.
    """
    episodes_dir = PROJECT_ROOT / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    path = episodes_dir / f"_candidates-{date}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": date, "candidates": articles}, f, ensure_ascii=False, indent=2)
    log.info(f"Candidatos exportados para: {path}")
    return path


# ---------------------------------------------------------------------------
# CLI e testes
# ---------------------------------------------------------------------------

def run_dummy_test():
    """Executa um teste simulado do filtro determinístico."""
    print("\n🧪 Executando teste do filtro determinístico...")
    dummy_articles = [
        {
            "title": "Vereadores de Blumenau aprovam aumento de 5% no IPTU para 2027",
            "link": "https://www.informeblumenau.com/iptu-2027",
            "content": "A Câmara Municipal de Blumenau aprovou em segunda votação o projeto de lei que reajusta a planta genérica de valores e aumenta o IPTU em 5% no próximo ano.",
            "published": datetime.now(timezone.utc).isoformat(),
        },
        {
            "title": "Carro cai de ribanceira na BR-470 em Indaial e deixa dois feridos",
            "link": "https://mesorregional.com.br/acidente-br470",
            "content": "O Corpo de Bombeiros Voluntários de Indaial atendeu a uma ocorrência de queda de veículo de ribanceira na tarde deste domingo na BR-470.",
            "published": datetime.now(timezone.utc).isoformat(),
        },
        {
            "title": "Nova IA da OpenAI resolve equações matemáticas complexas",
            "link": "https://techcrunch.com/openai-math",
            "content": "A startup OpenAI revelou hoje um novo modelo de inteligência artificial voltado para raciocínio matemático avançado.",
            "published": datetime.now(timezone.utc).isoformat(),
        },
    ]

    results = filter_and_categorize_news(dummy_articles)
    print(f"Resultado do Teste ({len(results)} selecionados):")
    for r in results:
        print(f"  [{r['category']}] score={r['quality_score']} | {r['title'][:60]}")

    assert len(results) <= 2, "Notícia internacional (OpenAI) não deveria ter sido selecionada"
    assert any("Blumenau" in r["title"] or "Indaial" in r["title"] for r in results), \
        "Notícias regionais devem estar presentes"
    print("✅ Teste passado!")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_dummy_test()
    else:
        run_dummy_test()


if __name__ == "__main__":
    main()
