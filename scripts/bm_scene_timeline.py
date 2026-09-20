#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timeline de Cenas — Pipeline Brasil e Mundo.

Calcula a distribuição temporal das cenas de fontes, transições de b-roll
e componentes procedurais de broadcast (quote, document, chart, timeline, comparison),
sincronizadas com o áudio do episódio (baseado na contagem de palavras das falas).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit


# Papéis semânticos editoriais
SemanticRole = Literal[
    "apresentacao_fato",        # Fato principal ancorado pelo veículo
    "evidencia_documental",     # Sentença, diário oficial, contrato, ofício
    "declaracao_forte",         # Citação em primeira pessoa ou nota oficial
    "contexto_cronologico",     # Linha do tempo de fatos antecedentes
    "impacto_economico",        # Números, inflação, gasto público, percentual
    "confronto_posicoes",       # Antes x Depois, Promessa x Realidade
    "repercussao_social",       # Postagem viral no X ou comentário público
    "transicao_broll",          # Clipes de respiro e ritmo visual
]

# Componentes visuais suportados no mockup-browser.html
VisualComponent = Literal[
    "source",           # Browser com matéria jornalística
    "x-post",           # Card interativo do X com animação de Like
    "quote",            # Card editorial de citação
    "document",         # Visualizador de documento oficial com zoom/grifo
    "timeline",         # Linha do tempo com marcos temporais
    "chart",            # Big Number / Indicador / Gráfico vetorial
    "comparison",       # Split-Screen de confronto
    "broll",            # Vídeo curto de respiro
    "person-photo",     # Foto editorial com efeito Ken Burns
    "transition",       # Transição de corte / wipe broadcast
]

_LEGACY_KINDS = frozenset({"source", "broll", "x-post", "person-photo", "transition"})


@dataclass
class SceneBeat:
    t0: float
    t1: float
    url: str
    veiculo: str
    kind: str  # "source" | "broll" | "x-post"
    shot: str | None = None
    shot_long: str | None = None
    highlight_box: dict | None = None
    video: str | None = None
    broll_file: str | None = None
    x_post: dict | None = None
    semantic_role: SemanticRole = "apresentacao_fato"
    visual_component: VisualComponent = "source"
    visual_variant: str = ""
    visual_payload: dict[str, Any] = field(default_factory=dict)
    abertura_fim: float = 0.0  # FASE 3 — t1 da abertura ampla; beats com t0 < abertura_fim são rotação livre
    aligned_by: str = "proporcao"  # FASE 4 — "proporcao" | "whisper"
    # Proveniência Direta (Fase 4.1)
    fala_indices: list[int] = field(default_factory=list)
    texto_origem: str = ""
    fonte_url_fala: str | None = None
    provenance_type: str = "none"  # "explicit" | "inherited" | "fallback" | "broll" | "person_photo" | "transition" | "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SceneBeatV2:
    t0: float                                      # Início em segundos
    t1: float                                      # Fim em segundos
    semantic_role: SemanticRole                     # Intenção narrativa
    visual_component: VisualComponent              # Componente que renderiza
    visual_variant: str                            # Variante do componente (ex: card_gold)
    visual_payload: dict[str, Any] = field(default_factory=dict)  # Dados estruturados
    url: str = ""                                  # URL de referência
    veiculo: str = ""                              # Nome do veículo/fonte
    shot: str | None = None                        # Screenshot estático (se houver)
    shot_long: str | None = None                   # Screenshot longo estático (se houver)
    highlight_box: dict | None = None              # Coordenadas do box de grifo
    video: str | None = None                       # Vídeo/clipe auxiliar (se houver)
    broll_file: str | None = None                  # Arquivo de b-roll local
    x_post: dict | None = None                     # Dados estruturados do post no X (Modo 8)
    # Proveniência Direta (Fase 4.1)
    fala_indices: list[int] = field(default_factory=list)
    texto_origem: str = ""
    fonte_url_fala: str | None = None
    provenance_type: str = "none"

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_legacy_beat(self) -> SceneBeat:
        """Converte para SceneBeat legado compatível com o pipeline atual."""
        kind = self.visual_component if self.visual_component in _LEGACY_KINDS else "source"
        return SceneBeat(
            t0=self.t0,
            t1=self.t1,
            url=self.url,
            veiculo=self.veiculo,
            kind=kind,
            shot=self.shot,
            shot_long=self.shot_long,
            highlight_box=self.highlight_box,
            video=self.video,
            broll_file=self.broll_file,
            x_post=self.x_post,
            semantic_role=self.semantic_role,
            visual_component=self.visual_component,
            visual_variant=self.visual_variant,
            visual_payload=self.visual_payload,
            fala_indices=list(self.fala_indices or []),
            texto_origem=self.texto_origem,
            fonte_url_fala=self.fonte_url_fala,
            provenance_type=self.provenance_type,
        )

    @classmethod
    def from_legacy(cls, beat: SceneBeat, **overrides: Any) -> SceneBeatV2:
        """Promove SceneBeat legado para SceneBeatV2 com defaults seguros."""
        kind = (beat.kind or "source").strip() or "source"
        if kind == "broll":
            semantic_role: SemanticRole = "transicao_broll"
            visual_component: VisualComponent = "broll"
        elif kind == "x-post":
            semantic_role = "repercussao_social"
            visual_component = "x-post"
        elif kind in ("quote", "document", "timeline", "chart", "comparison"):
            role_map = {
                "quote": "declaracao_forte",
                "document": "evidencia_documental",
                "timeline": "contexto_cronologico",
                "chart": "impacto_economico",
                "comparison": "confronto_posicoes",
            }
            semantic_role = role_map.get(kind, "apresentacao_fato")
            visual_component = kind
        else:
            semantic_role = getattr(beat, "semantic_role", "apresentacao_fato")
            visual_component = getattr(beat, "visual_component", "source")

        base: dict[str, Any] = {
            "t0": beat.t0,
            "t1": beat.t1,
            "semantic_role": semantic_role,
            "visual_component": visual_component,
            "visual_variant": getattr(beat, "visual_variant", ""),
            "visual_payload": dict(getattr(beat, "visual_payload", {}) or {}),
            "url": beat.url or "",
            "veiculo": beat.veiculo or "",
            "shot": beat.shot,
            "shot_long": getattr(beat, "shot_long", None),
            "highlight_box": getattr(beat, "highlight_box", None),
            "video": beat.video,
            "broll_file": beat.broll_file,
            "x_post": getattr(beat, "x_post", None),
            "fala_indices": list(getattr(beat, "fala_indices", []) or []),
            "texto_origem": getattr(beat, "texto_origem", ""),
            "fonte_url_fala": getattr(beat, "fonte_url_fala", None),
            "provenance_type": getattr(beat, "provenance_type", "none"),
        }
        base.update(overrides)
        return cls(**base)


# ---------------------------------------------------------------------------
# REGRAS E DETECTOR DE OPORTUNIDADES VISUAIS (NÍVEL 0 — HEURÍSTICA PURA)
# Contrato: youtube/Evolucao-Visual/02_SCHEMAS_E_CONTRATOS.md §4
# ---------------------------------------------------------------------------

QUOTE_PATTERNS = [
    re.compile(r'["“\'‘]([^"”\'’]{12,300})["”\'’]', re.U),
    re.compile(
        r'(?:afirmou|disse|declarou|ressaltou|garantiu|destacou)(?:\s+(?:no\s+x|no\s+twitter|em\s+nota|à\s+imprensa))?\s*:\s*["“\'‘]?([^"”\'’\n.]{12,300})["”\'’]?',
        re.I | re.U,
    ),
    re.compile(
        r'(?:afirmou|disse|declarou|ressaltou|garantiu|destacou)\s+(?:que\s+)?["“\'‘](.+?)["”\'’]',
        re.I | re.U,
    ),
    re.compile(r'em\s+nota(?:,\s+afirmou\s+que)?:\s*["“\'‘]?([^.\n]{15,300})["”\'’]?', re.I | re.U),
]

CHART_PATTERNS = [
    re.compile(r'R\$\s*([0-9.,]+)\s*(milhões|milhão|bilhões|bilhão|bi|mi|mil)?', re.I | re.U),
    re.compile(r'([0-9]+(?:,[0-9]+)?)\s*%', re.I),
    re.compile(
        r'(?:alta|queda|recuo|avanço|crescimento|inflação)\s+de\s+([0-9]+(?:,[0-9]+)?)\s*(?:%|pontos|p\.p\.)',
        re.I | re.U,
    ),
]

DOC_PATTERNS = [
    re.compile(r'(?:processo|autos)\s+n[ºo°]?\s*([0-9.-]+)', re.I | re.U),
    re.compile(
        r'(?:decisão|liminar|despacho|sentença|acórdão)\s+(?:do|da|de)\s+([A-Za-zÀ-ÿ\s]{3,35})',
        re.I | re.U,
    ),
    re.compile(r'(?:publicado|consta)\s+no\s+(?:diário\s+oficial|portal\s+da\s+transparência)', re.I | re.U),
    re.compile(r'(?:decreto|portaria|lei\s+complementar)\s+n[ºo°]?\s*([0-9]+)', re.I | re.U),
]

TIMELINE_PATTERNS = [
    re.compile(
        r'(?:em\s+)?(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(202[0-9])',
        re.I | re.U,
    ),
    re.compile(r'(?:em|desde)\s+(201[8-9]|202[0-6])', re.I | re.U),
    re.compile(r'(?:meses\s+depois|semanas\s+após|na\s+sequência|posteriormente|anos\s+antes)', re.I | re.U),
]

COMPARISON_PATTERNS = [
    re.compile(
        r'(?:prometeu|anunciou|havia\s+dito)\s+.*?\s+(?:mas|porém|contudo|no\s+entanto|todavia)',
        re.I | re.U,
    ),
    re.compile(
        r'(?:antes\s+era|em\s+202[0-4]\s+era)\s+.*?\s+(?:agora|hoje|em\s+202[5-6])',
        re.I | re.U,
    ),
    re.compile(r'(?:enquanto\s+o\s+governo\s+diz|de\s+um\s+lado\s+.*?\s+de\s+outro)', re.I | re.U),
]

_AUTHORITY_RE = re.compile(
    r'\b('
    r'prefeito|prefeita|governador|governadora|presidente|ministr[oa]|'
    r'secretári[oa]|superintendente|vereador|vereadora|deputad[oa]|'
    r'senador|senadora|juiz|juíza|desembargador|desembargadora|'
    r'promotor|promotora|procurador|procuradora|comandante|diretor[a]?'
    r')\b',
    re.I | re.U,
)

_PROPER_NAME_RE = re.compile(
    r'\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){0,3})\b',
    re.U,
)

_ECONOMIC_THEME_RE = re.compile(
    r'\b(?:orçamento|inflação|pib|economia|tributo|iptu|icms|iss|dívida|'
    r'receita|despesa|investimento|taxa|juros|salário|reajuste|aumento)\b',
    re.I | re.U,
)

_CHRONO_CONNECTOR_RE = re.compile(
    r'\b(?:depois|em\s+seguida|na\s+sequência|posteriormente|meses\s+depois|'
    r'semanas\s+após|anos\s+antes)\b',
    re.I | re.U,
)

_CONTRAST_DATES_RE = re.compile(
    r'(?:202[0-4]).{0,80}(?:202[5-6])|(?:202[5-6]).{0,80}(?:202[0-4])',
    re.I | re.S | re.U,
)

_OFFICIAL_DOMAIN_RE = re.compile(
    r'(?:jus\.br|stf\.jus\.br|stj\.jus\.br|tse\.jus\.br|sc\.gov\.br|'
    r'gov\.br|planalto\.gov\.br|in\.gov\.br)',
    re.I,
)

X_POST_PATTERNS = [
    re.compile(r'\b(?:no\s+x|no\s+twitter|pelo\s+x|pelo\s+twitter)\b', re.I | re.U),
    re.compile(r'\b(?:tuitou|twitou|publicou\s+no\s+x|postou\s+no\s+x|escreveu\s+no\s+x)\b', re.I | re.U),
    re.compile(r'em\s+(?:publicação|postagem|post)\s+no\s+(?:x|twitter)', re.I | re.U),
    re.compile(r'(@[a-zA-Z0-9_]{3,20})', re.I),
]

_VARIANT_BY_COMPONENT = {
    "quote": "card_gold",
    "document": "highlight_zoom",
    "chart": "stat_counter",
    "timeline": "progressive_nodes",
    "comparison": "split_screen",
    "source": "portal_clean",
    "x-post": "x_card",
    "person-photo": "ken_burns",
    "transition": "wipe_gold",
}

_BASE_SCORE = {
    "quote": 0.75,
    "document": 0.80,
    "chart": 0.70,
    "timeline": 0.65,
    "comparison": 0.70,
    "source": 0.50,
    "x-post": 0.82,
}

_OPPORTUNITY_TYPE = {
    "quote": "strong_quote",
    "document": "official_document",
    "chart": "economic_stat",
    "timeline": "chronology",
    "comparison": "confrontation",
    "source": "source_context",
    "x-post": "social_post",
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _first_quote_match(text: str):
    for pat in QUOTE_PATTERNS:
        m = pat.search(text or "")
        if m:
            return m
    return None


def _extract_quote_author(text: str, quote_span=None) -> str:
    """Heurística: autoridade ou nome próprio próximos à citação."""
    src = text or ""
    window = src
    if quote_span:
        start = max(0, quote_span[0] - 120)
        window = src[start:quote_span[0]]
    cargo_m = _AUTHORITY_RE.search(window)
    name_m = None
    name_candidates = list(_PROPER_NAME_RE.finditer(window))
    if name_candidates:
        name_m = name_candidates[-1]
    parts = []
    if cargo_m:
        parts.append(cargo_m.group(1).strip().capitalize())
    if name_m:
        nm = name_m.group(1).strip()
        if not _AUTHORITY_RE.fullmatch(nm):
            parts.append(nm)
    if parts:
        seen = set()
        uniq = []
        for p in parts:
            key = p.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        return " ".join(uniq)
    return ""


def _collect_pattern_hits(patterns, text: str):
    hits = []
    for pat in patterns:
        hits.extend(pat.finditer(text or ""))
    return hits


def detect_visual_opportunities(
    text: str,
    url: str = "",
    veiculo: str = "",
    *,
    block_index: int | None = None,
) -> dict[str, Any]:
    """Detecta oportunidades visuais (Nível 0) e escolhe o componente líder.

    Retorno no formato VisualOpportunity (02_SCHEMAS_E_CONTRATOS.md §4).
    """
    paragraph = text or ""
    url_s = url or ""
    veiculo_s = veiculo or ""

    candidates: dict[str, dict[str, Any]] = {}

    # --- source (baseline) ---
    source_score = _BASE_SCORE["source"]
    if url_s.strip():
        source_score = _clamp01(source_score + 0.10)
    candidates["source"] = {
        "opportunity_type": _OPPORTUNITY_TYPE["source"],
        "score": round(source_score, 2),
        "recommended_component": "source",
        "recommended_variant": _VARIANT_BY_COMPONENT["source"],
        "extracted_data": {"url": url_s, "veiculo": veiculo_s} if (url_s or veiculo_s) else {},
    }

    # --- quote ---
    quote_m = _first_quote_match(paragraph)
    if quote_m:
        quote_text = (quote_m.group(1) or "").strip().strip('"“”')
        score = _BASE_SCORE["quote"]
        author = _extract_quote_author(paragraph, quote_m.span())
        if author or _AUTHORITY_RE.search(paragraph):
            score = _clamp01(score + 0.15)
        # Se for citação com menção ao X/Twitter, registra no source_name mas mantém como quote editorial
        has_x_mention = bool(_collect_pattern_hits(X_POST_PATTERNS, paragraph))
        quote_source = veiculo_s or ("X (antigo Twitter)" if has_x_mention else "Declaração Oficial")
        if has_x_mention and veiculo_s and "x" not in veiculo_s.lower() and "twitter" not in veiculo_s.lower():
            quote_source = f"{veiculo_s} (via X)"
        candidates["quote"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["quote"],
            "score": round(score, 2),
            "recommended_component": "quote",
            "recommended_variant": _VARIANT_BY_COMPONENT["quote"],
            "extracted_data": {
                "quote_text": quote_text,
                "author": author,
                "author_name": author or "Autoridade",
                "source_name": quote_source,
            },
        }

    # --- document ---
    doc_hits = _collect_pattern_hits(DOC_PATTERNS, paragraph)
    if doc_hits:
        score = _BASE_SCORE["document"]
        if _OFFICIAL_DOMAIN_RE.search(url_s):
            score = _clamp01(score + 0.20)
        extracted: dict[str, Any] = {}
        for h in doc_hits:
            if h.lastindex and h.group(1):
                extracted["ref"] = h.group(1).strip()
                extracted["case_number"] = h.group(1).strip()
                break
        extracted["match_count"] = len(doc_hits)
        extracted["statement"] = paragraph[:200]
        candidates["document"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["document"],
            "score": round(score, 2),
            "recommended_component": "document",
            "recommended_variant": _VARIANT_BY_COMPONENT["document"],
            "extracted_data": extracted,
        }

    # --- chart ---
    chart_hits = _collect_pattern_hits(CHART_PATTERNS, paragraph)
    if chart_hits:
        score = _BASE_SCORE["chart"]
        if _ECONOMIC_THEME_RE.search(paragraph):
            score = _clamp01(score + 0.15)
        extracted_chart: dict[str, Any] = {"match_count": len(chart_hits)}
        first = chart_hits[0]
        if first.lastindex and first.group(1):
            extracted_chart["value"] = first.group(1)
            extracted_chart["metric_value"] = first.group(1)
            if first.lastindex >= 2 and first.group(2):
                extracted_chart["unit"] = first.group(2)
                extracted_chart["metric_suffix"] = f" {first.group(2).upper()}"
        candidates["chart"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["chart"],
            "score": round(score, 2),
            "recommended_component": "chart",
            "recommended_variant": _VARIANT_BY_COMPONENT["chart"],
            "extracted_data": extracted_chart,
        }

    # --- timeline (exige 2+ referências temporais distintas) ---
    timeline_hits = _collect_pattern_hits(TIMELINE_PATTERNS, paragraph)
    distinct_markers = set()
    for h in timeline_hits:
        distinct_markers.add(h.group(0).lower().strip())
    if len(distinct_markers) >= 2 or (len(timeline_hits) >= 2 and len(distinct_markers) >= 1):
        score = _BASE_SCORE["timeline"]
        if _CHRONO_CONNECTOR_RE.search(paragraph):
            score = _clamp01(score + 0.15)
        candidates["timeline"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["timeline"],
            "score": round(score, 2),
            "recommended_component": "timeline",
            "recommended_variant": _VARIANT_BY_COMPONENT["timeline"],
            "extracted_data": {
                "markers": sorted(distinct_markers),
                "match_count": len(timeline_hits),
            },
        }

    # --- comparison ---
    comparison_hits = _collect_pattern_hits(COMPARISON_PATTERNS, paragraph)
    if comparison_hits:
        score = _BASE_SCORE["comparison"]
        if _CONTRAST_DATES_RE.search(paragraph):
            score = _clamp01(score + 0.20)
        candidates["comparison"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["comparison"],
            "score": round(score, 2),
            "recommended_component": "comparison",
            "recommended_variant": _VARIANT_BY_COMPONENT["comparison"],
            "extracted_data": {"match_count": len(comparison_hits)},
        }

    # --- x-post (social / X / Twitter) ---
    # Uso estrito e exclusivo: só recomenda componente x-post (Modo 8) se a URL
    # de origem for comprovadamente do X/Twitter com post_id ou dados de tweet.
    # Citações no roteiro mencionando o X sem post real usam o componente quote.
    is_x_url = bool(url_s and ("twitter.com" in url_s.lower() or "x.com" in url_s.lower()))
    x_hits = _collect_pattern_hits(X_POST_PATTERNS, paragraph)
    if is_x_url:
        score = _BASE_SCORE["x-post"]
        score = _clamp01(score + 0.10)
        extracted_x: dict[str, Any] = {
            "source_name": "X (antigo Twitter)",
            "match_count": len(x_hits),
        }
        handle_m = re.search(r'(@[a-zA-Z0-9_]{3,20})', paragraph)
        if handle_m:
            extracted_x["handle"] = handle_m.group(1)
        auth = _extract_quote_author(paragraph)
        if auth:
            extracted_x["author_name"] = auth
            extracted_x["speaker_name"] = auth
        elif veiculo_s and "twitter" not in veiculo_s.lower() and veiculo_s.lower().strip() != "x":
            extracted_x["author_name"] = veiculo_s
            extracted_x["speaker_name"] = veiculo_s
        else:
            extracted_x["author_name"] = "Autoridade"
            extracted_x["speaker_name"] = "Autoridade"

        if auth or handle_m or _AUTHORITY_RE.search(paragraph):
            score = _clamp01(score + 0.10)

        quote_m = _first_quote_match(paragraph)
        if quote_m:
            extracted_x["text"] = (quote_m.group(1) or "").strip().strip('"“”')
        else:
            extracted_x["text"] = paragraph[:280]

        candidates["x-post"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["x-post"],
            "score": round(score, 2),
            "recommended_component": "x-post",
            "recommended_variant": _VARIANT_BY_COMPONENT["x-post"],
            "extracted_data": extracted_x,
        }

    ranked = sorted(
        candidates.values(),
        key=lambda c: (-float(c["score"]), str(c["recommended_component"])),
    )

    leader = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    leader_score = float(leader["score"])
    second_score = float(second["score"]) if second else 0.0
    advantage = leader_score - second_score

    needs_gemini_tiebreak = False
    if leader_score >= 0.75 and advantage >= 0.20:
        chosen = str(leader["recommended_component"])
    elif leader_score < 0.75:
        chosen = "source"
    else:
        chosen = str(leader["recommended_component"])
        needs_gemini_tiebreak = True

    detected = []
    for c in ranked:
        item = {
            "opportunity_type": c["opportunity_type"],
            "score": c["score"],
            "recommended_component": c["recommended_component"],
            "recommended_variant": c["recommended_variant"],
        }
        ed = c.get("extracted_data") or {}
        if ed:
            item["extracted_data"] = ed
        detected.append(item)

    result: dict[str, Any] = {
        "paragraph_text": paragraph,
        "detected_opportunities": detected,
        "chosen_component": chosen,
    }
    if block_index is not None:
        result["block_index"] = block_index
    if needs_gemini_tiebreak:
        result["needs_gemini_tiebreak"] = True
        tied = [
            c["recommended_component"]
            for c in ranked
            if abs(float(c["score"]) - leader_score) < 0.20 and float(c["score"]) >= 0.75
        ]
        result["tiebreak_candidates"] = tied

    return result


MIN_SCENE_DURATION_S = 5.0
MAX_SCENE_DURATION_S = 10.0
DEFAULT_BROLL_DUR_S = 1.2
TARGET_MIN_BEATS_5MIN = 18
_PORTAL_VARIANTS_CYCLE = ["portal_hero", "portal_zoom", "portal_scroll", "portal_highlight"]


def count_words(text: str) -> int:
    return len((text or "").split())


def _host_of(url: str) -> str:
    """Domínio normalizado para matching de fontes (strip www)."""
    try:
        netloc = urlsplit(url or "").netloc.lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})",
    re.I,
)


def youtube_id_from_episode(episode: dict) -> str:
    """YouTube ID do episódio: chave explícita, id especial-*, ou URL YouTube."""
    for key in ("video_id", "id"):
        raw = str(episode.get(key) or "").strip()
        if raw.startswith("especial-"):
            raw = raw[len("especial-"):]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
            return raw
    blob = " ".join(str(episode.get(k) or "") for k in ("fonte_url", "youtube_url"))
    m = _YT_ID_RE.search(blob)
    return m.group(1) if m else ""


def load_broll_clips(broll_index_path: Path | None = None) -> list[dict]:
    if not broll_index_path or not broll_index_path.is_file():
        return []
    try:
        data = json.loads(broll_index_path.read_text(encoding="utf-8"))
        return data.get("clips", [])
    except Exception:
        return []


def build_scene_timeline(
    episode: dict,
    total_duration_s: float,
    scenes: list[dict],
    broll_index_path: Path | None = None,
    return_v2: bool = False,
) -> list[SceneBeat] | list[SceneBeatV2]:
    """Gera lista de SceneBeat sincronizados com o áudio falado.

    - Distribui o tempo total do áudio proporcionalmente à contagem de palavras de cada fala.
    - Se a fala tiver `fonte_url`, sincroniza com a cena correspondente.
    - Detecta oportunidades editoriais para componentes procedurais (quote, document, chart, etc.).
    - Garante piso de pelo menos 5s por cena de fonte externa.
    - Insere transições de b-roll (0.8–1.5s) em mudanças de matéria se houver clipes disponíveis.
    - Garante ritmo dinâmico com pelo menos 18 telas/beats em episódios de 5 minutos (~300s).
    """
    total_dur = max(total_duration_s, 10.0)
    if not scenes:
        scenes = [{"veiculo": "Vale da Liberdade", "url": "https://news.mob.tec.br", "shot": None, "video": None}]

    # 1. Coletar falas em ordem sequencial com seus blocos e fonte_url
    blocks: list[dict] = []
    fala_counter = 0
    for section_name in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(section_name) or []:
            txt = (item.get("texto") or "").strip()
            if not txt:
                continue
            raw_fu = (item.get("fonte_url") or "").strip()
            blocks.append({
                "fala_index": fala_counter,
                "section": section_name,
                "texto": txt,
                "words": max(1, count_words(txt)),
                "fonte_url": raw_fu,
                "fonte_url_raw": raw_fu,
                "provenance_type": "explicit" if raw_fu else "none",
            })
            fala_counter += 1

    if not blocks:
        blocks = [{
            "fala_index": 0,
            "section": "desenvolvimento",
            "texto": episode.get("titulo") or "Comentário",
            "words": 100,
            "fonte_url": "",
            "fonte_url_raw": "",
            "provenance_type": "none",
        }]

    total_words = sum(b["words"] for b in blocks)
    available_broll = load_broll_clips(broll_index_path)

    # FASE 0.2 — Herança de fonte por janela
    # O condensador marca fonte_url só no primeiro bloco de cada matéria (o
    # prompt trata o campo como opcional). Blocos de transição/opinião que
    # continuam comentando a mesma matéria chegam sem a marca e caíam no
    # round-robin cego, mostrando a matéria errada no fundo.
    # Regra: um bloco sem fonte herda a última fonte conhecida. O
    # fechamento não herda (síntese/opinião final, não comenta a matéria).
    _last_fonte = ""
    _inherited = 0
    for b in blocks:
        fu = (b.get("fonte_url") or "").strip()
        if fu:
            _last_fonte = fu
            b["provenance_type"] = "explicit"
        elif _last_fonte and b.get("section") != "fechamento":
            b["fonte_url"] = _last_fonte
            b["provenance_type"] = "inherited"
            _inherited += 1
        else:
            b["provenance_type"] = "none"
    if _inherited:
        try:
            print(f"  🔗 fonte_url herdada por {_inherited} bloco(s)")
        except UnicodeEncodeError:
            print(f"  [fonte_url] herdada por {_inherited} bloco(s)")

    # 2. Mapeamento de cenas por URL e por domínio (cascata de matching)
    scene_by_url = {s["url"]: s for s in scenes if s.get("url")}
    scene_by_host: dict[str, list[dict]] = {}
    for s in scenes:
        if s.get("url"):
            scene_by_host.setdefault(_host_of(s["url"]), []).append(s)
    scene_queue = list(scenes)
    scene_ptr = 0

    # FASE 2 — Log de diagnóstico: qual nível da cascata casou cada bloco
    match_stats: dict[str, int] = {}

    # 3. Construção dos beats preliminares com detecção de oportunidades
    raw_beats: list[dict] = []
    current_t = 0.0

    for idx, b in enumerate(blocks):
        dur_block = (b["words"] / total_words) * total_dur
        target_url = (b.get("fonte_url") or "").strip()
        scene_item = None
        match_level = ""

        # Nivel 1 — match exato de URL (mantem comportamento original)
        if target_url and target_url in scene_by_url:
            scene_item = scene_by_url[target_url]
            match_level = "exato"
        # Nivel 2 — match por dominio (cobre normalizacao de URL: www,
        # parametros de tracking, paths diferentes do mesmo veiculo)
        elif target_url and _host_of(target_url) in scene_by_host:
            scene_item = scene_by_host[_host_of(target_url)][0]
            match_level = "dominio"
        # Nivel 3 — fallback: round-robin (apenas aqui, depois da cascata)
        else:
            scene_item = scene_queue[scene_ptr % len(scene_queue)]
            match_level = "round_robin"

        match_stats[match_level] = match_stats.get(match_level, 0) + 1

        t_end = min(total_dur, current_t + dur_block)

        # Inserção de b-roll na transição entre matérias se houver clipes
        if available_broll and raw_beats and raw_beats[-1]["url"] != scene_item.get("url"):
            if total_dur - current_t > 15.0:
                clip = available_broll[len(raw_beats) % len(available_broll)]
                clip_dur = float(clip.get("dur_s", DEFAULT_BROLL_DUR_S))
                broll_end = min(total_dur - 5.0, current_t + clip_dur)
                raw_beats.append({
                    "t0": round(current_t, 2),
                    "t1": round(broll_end, 2),
                    "url": "",
                    "veiculo": "Transição",
                    "kind": "broll",
                    "shot": None,
                    "shot_long": None,
                    "highlight_box": None,
                    "video": None,
                    "broll_file": clip.get("file"),
                    "x_post": None,
                    "semantic_role": "transicao_broll",
                    "visual_component": "broll",
                    "visual_variant": "",
                    "visual_payload": {},
                    "fala_indices": [],
                    "texto_origem": "",
                    "fonte_url_fala": None,
                    "provenance_type": "broll",
                })
                current_t = broll_end
                t_end = min(total_dur, current_t + dur_block)

        # Se a cena for nativa do X (Modo 8), prioriza o componente x-post
        is_x_post = (scene_item.get("kind") == "x-post") or bool(scene_item.get("x_post"))
        if is_x_post:
            chosen_comp = "x-post"
            semantic_role = "repercussao_social"
            variant = "x_card"
            payload = {"x_post": scene_item.get("x_post")} if scene_item.get("x_post") else {}
        else:
            # Detecta componente visual adequado para o parágrafo
            opp = detect_visual_opportunities(
                b["texto"],
                scene_item.get("url") or "",
                scene_item.get("veiculo") or "",
                block_index=idx,
            )
            chosen_comp = opp.get("chosen_component") or "source"

            # Atribui dados estruturados se componente especial foi escolhido
            payload: dict[str, Any] = {}
            variant = _VARIANT_BY_COMPONENT.get(chosen_comp, "portal_clean")
            role_map = {
                "quote": "declaracao_forte",
                "document": "evidencia_documental",
                "timeline": "contexto_cronologico",
                "chart": "impacto_economico",
                "comparison": "confronto_posicoes",
                "x-post": "repercussao_social",
                "source": "apresentacao_fato",
            }
            semantic_role = role_map.get(chosen_comp, "apresentacao_fato")

            if chosen_comp != "source":
                for op_item in opp.get("detected_opportunities") or []:
                    if op_item.get("recommended_component") == chosen_comp:
                        payload = dict(op_item.get("extracted_data") or {})
                        variant = op_item.get("recommended_variant") or variant
                        break

        raw_beats.append({
            "t0": round(current_t, 2),
            "t1": round(t_end, 2),
            "url": scene_item.get("url") or "",
            "veiculo": scene_item.get("veiculo") or "Fonte",
            "kind": "x-post" if (is_x_post or chosen_comp == "x-post") else (scene_item.get("kind") or (chosen_comp if chosen_comp in _LEGACY_KINDS else "source")),
            "shot": scene_item.get("shot"),
            "shot_long": scene_item.get("shot_long"),
            "highlight_box": scene_item.get("highlight_box"),
            "video": scene_item.get("video"),
            "broll_file": None,
            "x_post": scene_item.get("x_post") or (payload if (is_x_post or chosen_comp == "x-post") else None),
            "semantic_role": semantic_role,
            "visual_component": chosen_comp,
            "visual_variant": variant,
            "visual_payload": payload,
            "fala_indices": [b["fala_index"]] if "fala_index" in b else [idx],
            "texto_origem": b.get("texto") or "",
            "fonte_url_fala": b.get("fonte_url") or None,
            "provenance_type": b.get("provenance_type") or "none",
        })
        # O ponteiro do round-robin só avança quando o fallback é usado.
        # Se a cascata casou (exato/domínio), rotacionar por bloco
        # sobrescreveria a sincronia que acabamos de resolver.
        if match_level == "round_robin":
            scene_ptr += 1
        current_t = t_end

    # 4. Agregação e aplicação de piso mínimo de duração por cena de fonte
    # Diagnóstico FASE 2 — termômetro da sincronia: quantos blocos casaram
    # em cada nível da cascata. "round_robin" alto = cobertura de fonte
    # ainda baixa; a Fase 0.2 (herança) deve reduzir esse número.
    if match_stats:
        total_blocks = sum(match_stats.values())
        parts = ", ".join(f"{k}={v}" for k, v in sorted(match_stats.items()))
        try:
            print(f"  🎯 sincronia de fonte: {parts} ({total_blocks} blocos)")
        except UnicodeEncodeError:
            print(f"  [sincronia] fonte: {parts} ({total_blocks} blocos)")
    final_beats: list[SceneBeat] = []
    i = 0
    while i < len(raw_beats):
        rb = raw_beats[i]
        kind = rb["kind"]
        url = rb["url"]
        veic = rb["veiculo"]
        shot = rb["shot"]
        shot_long = rb.get("shot_long")
        highlight_box = rb.get("highlight_box")
        video = rb["video"]
        broll_file = rb["broll_file"]
        x_post = rb.get("x_post")
        sem_role = rb.get("semantic_role") or "apresentacao_fato"
        vis_comp = rb.get("visual_component") or "source"
        vis_var = rb.get("visual_variant") or ""
        vis_pay = rb.get("visual_payload") or {}
        t0 = rb["t0"]
        t1 = rb["t1"]
        merged_fala_indices = list(rb.get("fala_indices") or [])
        merged_textos = [rb["texto_origem"]] if rb.get("texto_origem") else []
        fonte_url_fala = rb.get("fonte_url_fala")
        prov_type = rb.get("provenance_type") or "none"

        # Agrupar beats consecutivos idênticos (mas preserva separação de fechamento/sem fonte)
        while (i + 1 < len(raw_beats) 
               and raw_beats[i + 1]["kind"] == kind 
               and raw_beats[i + 1]["url"] == url 
               and raw_beats[i + 1].get("visual_component") == vis_comp
               and not (prov_type == "none" and raw_beats[i + 1].get("provenance_type") in ("explicit", "inherited"))
               and not (prov_type in ("explicit", "inherited") and raw_beats[i + 1].get("provenance_type") == "none")):
            next_rb = raw_beats[i + 1]
            t1 = next_rb["t1"]
            for fi in next_rb.get("fala_indices") or []:
                if fi not in merged_fala_indices:
                    merged_fala_indices.append(fi)
            if next_rb.get("texto_origem"):
                merged_textos.append(next_rb["texto_origem"])
            if not fonte_url_fala and next_rb.get("fonte_url_fala"):
                fonte_url_fala = next_rb["fonte_url_fala"]
            if prov_type != "explicit" and next_rb.get("provenance_type") == "explicit":
                prov_type = "explicit"
            elif prov_type == "none" and next_rb.get("provenance_type") in ("inherited", "fallback"):
                prov_type = next_rb.get("provenance_type")
            i += 1

        # Garantir piso mínimo de 8s para source se não for o último beat
        if kind == "source" and (t1 - t0) < MIN_SCENE_DURATION_S and i + 1 < len(raw_beats):
            t1 = min(total_dur, t0 + MIN_SCENE_DURATION_S)

        final_beats.append(SceneBeat(
            t0=round(t0, 2),
            t1=round(t1, 2),
            url=url,
            veiculo=veic,
            kind=kind,
            shot=shot,
            shot_long=shot_long,
            highlight_box=highlight_box,
            video=video,
            broll_file=broll_file,
            x_post=x_post,
            semantic_role=sem_role,
            visual_component=vis_comp,
            visual_variant=vis_var,
            visual_payload=vis_pay,
            fala_indices=merged_fala_indices,
            texto_origem=" ".join(merged_textos),
            fonte_url_fala=fonte_url_fala,
            provenance_type=prov_type,
        ))
        i += 1

    # 5. Gancho dos Primeiros 15 Segundos (Visual Hook)
    if total_dur >= 120.0 and len(final_beats) > 1 and len(scene_queue) > 1:
        if final_beats[0].t1 >= 14.0 and final_beats[0].visual_component == "source":
            old_first = final_beats[0]
            cut1 = 5.0
            cut2 = 9.0
            alt_scene = scene_queue[1 % len(scene_queue)]
            b0_a = SceneBeat(
                t0=0.0,
                t1=cut1,
                url=old_first.url,
                veiculo=old_first.veiculo,
                kind="source",
                shot=old_first.shot,
                shot_long=old_first.shot_long,
                highlight_box=old_first.highlight_box,
                video=old_first.video,
                x_post=old_first.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
                fala_indices=list(old_first.fala_indices),
                texto_origem=old_first.texto_origem,
                fonte_url_fala=old_first.fonte_url_fala,
                provenance_type=old_first.provenance_type,
            )
            alt_is_x = (alt_scene.get("kind") == "x-post") or bool(alt_scene.get("x_post"))
            b0_b = SceneBeat(
                t0=cut1,
                t1=cut2,
                url=alt_scene.get("url") or old_first.url,
                veiculo=alt_scene.get("veiculo") or old_first.veiculo,
                kind="x-post" if alt_is_x else (alt_scene.get("kind") or "source"),
                shot=alt_scene.get("shot") or old_first.shot,
                shot_long=alt_scene.get("shot_long") or old_first.shot_long,
                highlight_box=alt_scene.get("highlight_box") or old_first.highlight_box,
                video=alt_scene.get("video") or old_first.video,
                x_post=alt_scene.get("x_post") or old_first.x_post,
                semantic_role="repercussao_social" if alt_is_x else "apresentacao_fato",
                visual_component="x-post" if alt_is_x else "source",
                visual_variant="x_card" if alt_is_x else "portal_clean",
                fala_indices=list(old_first.fala_indices),
                texto_origem=old_first.texto_origem,
                fonte_url_fala=old_first.fonte_url_fala,
                provenance_type=old_first.provenance_type,
            )
            b0_c = SceneBeat(
                t0=cut2,
                t1=old_first.t1,
                url=old_first.url,
                veiculo=old_first.veiculo,
                kind="source",
                shot=old_first.shot,
                shot_long=old_first.shot_long,
                highlight_box=old_first.highlight_box,
                video=old_first.video,
                x_post=old_first.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
                fala_indices=list(old_first.fala_indices),
                texto_origem=old_first.texto_origem,
                fonte_url_fala=old_first.fonte_url_fala,
                provenance_type=old_first.provenance_type,
            )
            final_beats[0:1] = [b0_a, b0_b, b0_c]

    # FASE 3 — Abertura ampla, corpo sincronizado
    # Os primeiros segundos mantêm a rotação ampla de fontes (passo 5 acima é o
    # gancho de retenção: 3 cortes rápidos 0→5→9→fim do primeiro beat). A
    # cascata da Fase 2 só passa a valer a partir do primeiro bloco de
    # desenvolvimento. Marcamos esse corte no campo `abertura_fim` de cada beat
    # para que render.py e diagnósticos saibam que ali ainda é rotação livre.
    abertura_fim = 0.0
    if total_dur >= 120.0 and final_beats:
        # abertura = duração do(s) beat(s) do início até o primeiro beat de
        # desenvolvimento (semantic_role != apresentacao_fato) ou, no máximo,
        # os ~15s do gancho visual.
        for b in final_beats:
            if b.semantic_role in ("apresentacao_fato", "gancho"):
                abertura_fim = b.t1
                if abertura_fim >= 15.0:
                    break
            else:
                break
        abertura_fim = min(abertura_fim, 15.0)
    for b in final_beats:
        b.abertura_fim = round(abertura_fim, 2)

    # 6. Dinamismo e Pacing Inteligente Anti-Monotonia (Fase 4.3):
    # Quebra beats longos (> MAX_SCENE_DURATION_S) mantendo a fonte sincronizada,
    # calibrando o ritmo pela velocidade da fala (palavras/segundo) e alternando
    # variantes ópticas (hero -> zoom -> scroll -> highlight), criando cortes ópticos dinâmicos a cada 5-8s.
    expanded_beats: list[SceneBeat] = []
    cycle_ptr = 1
    for beat in final_beats:
        dur = beat.t1 - beat.t0
        if dur > MAX_SCENE_DURATION_S and len(scene_queue) > 1 and beat.visual_component == "source":
            # Calibração adaptativa por velocidade de fala
            words = count_words(beat.texto_origem)
            wps = words / max(1.0, dur) if words > 0 else 2.3
            step_target = 6.0 if wps >= 2.6 else (7.5 if wps >= 2.0 else 8.5)
            num_sub = max(2, int(dur // step_target) + 1)
            step = dur / num_sub
            sub_t0 = beat.t0
            # candidatos alternativos SÓ da mesma fonte (multi-shot)
            same_src = [s for s in scene_queue
                        if s.get("url") and s.get("url") == beat.url and s.get("shot") != beat.shot]
            for s_idx in range(num_sub):
                sub_t1 = round(beat.t0 + (s_idx + 1) * step, 2)
                if s_idx == num_sub - 1:
                    sub_t1 = beat.t1
                # alterna dentro do multi-shot da mesma fonte, se houver;
                # senão mantém o próprio beat (fonte correta preservada)
                if same_src:
                    alt_scene = same_src[s_idx % len(same_src)]
                else:
                    alt_scene = {"url": beat.url, "veiculo": beat.veiculo,
                                 "kind": beat.kind, "shot": beat.shot,
                                 "shot_long": beat.shot_long,
                                 "highlight_box": beat.highlight_box,
                                 "video": beat.video, "x_post": beat.x_post}

                # Alternância dinâmica de variantes de câmera evitando repetição consecutiva
                last_var = expanded_beats[-1].visual_variant if expanded_beats else ""
                avail_vars = [v for v in _PORTAL_VARIANTS_CYCLE if v != last_var]
                sub_variant = avail_vars[s_idx % len(avail_vars)] if avail_vars else _PORTAL_VARIANTS_CYCLE[s_idx % len(_PORTAL_VARIANTS_CYCLE)]

                sub_roles = ["apresentacao_fato", "detalhe_factual", "leitura_contexto", "destaque_editorial"]
                sub_role = sub_roles[s_idx % len(sub_roles)]

                expanded_beats.append(SceneBeat(
                    t0=round(sub_t0, 2),
                    t1=round(sub_t1, 2),
                    url=alt_scene.get("url") or beat.url,
                    veiculo=alt_scene.get("veiculo") or beat.veiculo,
                    kind=alt_scene.get("kind") or "source",
                    shot=alt_scene.get("shot") or beat.shot,
                    shot_long=alt_scene.get("shot_long") or beat.shot_long,
                    highlight_box=alt_scene.get("highlight_box") or beat.highlight_box,
                    video=alt_scene.get("video") or beat.video,
                    broll_file=None,
                    x_post=alt_scene.get("x_post") or beat.x_post,
                    semantic_role=sub_role,
                    visual_component=beat.visual_component,
                    visual_variant=sub_variant,
                    visual_payload=beat.visual_payload,
                    fala_indices=list(beat.fala_indices),
                    texto_origem=beat.texto_origem,
                    fonte_url_fala=beat.fonte_url_fala,
                    provenance_type=beat.provenance_type,
                ))
                sub_t0 = sub_t1
        else:
            expanded_beats.append(beat)

    # 7. Garantia de Piso de Telas: assegura pelo menos TARGET_MIN_BEATS_5MIN beats em vídeos longos (>= 180s)
    # O corte divide o beat ao meio, mantendo a fonte e alternando variantes visuais
    if total_dur >= 180.0 and len(expanded_beats) < TARGET_MIN_BEATS_5MIN and len(scene_queue) > 1:
        while len(expanded_beats) < TARGET_MIN_BEATS_5MIN:
            longest_idx = max(range(len(expanded_beats)), key=lambda idx: (expanded_beats[idx].t1 - expanded_beats[idx].t0))
            b_target = expanded_beats[longest_idx]
            b_dur = b_target.t1 - b_target.t0
            if b_dur < 10.0:
                break
            half = round(b_target.t0 + b_dur / 2.0, 2)
            alt_scene = scene_queue[cycle_ptr % len(scene_queue)]
            cycle_ptr += 1
            b1_variant = b_target.visual_variant or "portal_hero"
            b1 = SceneBeat(
                t0=b_target.t0,
                t1=half,
                url=b_target.url,
                veiculo=b_target.veiculo,
                kind=b_target.kind,
                shot=b_target.shot,
                shot_long=b_target.shot_long,
                highlight_box=b_target.highlight_box,
                video=b_target.video,
                broll_file=b_target.broll_file,
                x_post=b_target.x_post,
                semantic_role=b_target.semantic_role,
                visual_component=b_target.visual_component,
                visual_variant=b1_variant,
                visual_payload=b_target.visual_payload,
                fala_indices=list(b_target.fala_indices),
                texto_origem=b_target.texto_origem,
                fonte_url_fala=b_target.fonte_url_fala,
                provenance_type=b_target.provenance_type,
            )
            alt_is_x = (alt_scene.get("kind") == "x-post") or bool(alt_scene.get("x_post"))
            same_source = bool(alt_scene.get("url")) and alt_scene.get("url") == b_target.url
            b2_url = (alt_scene.get("url") or b_target.url) if (alt_is_x or same_source) else b_target.url
            b2_veic = (alt_scene.get("veiculo") or b_target.veiculo) if (alt_is_x or same_source) else b_target.veiculo
            b2_shot = (alt_scene.get("shot") or b_target.shot) if same_source else b_target.shot
            b2_shot_long = (alt_scene.get("shot_long") or b_target.shot_long) if same_source else b_target.shot_long
            b2_highlight_box = (alt_scene.get("highlight_box") or b_target.highlight_box) if same_source else b_target.highlight_box
            b2_variant = "x_card" if alt_is_x else ("portal_zoom" if b1_variant in ("portal_hero", "portal_clean") else "portal_scroll")
            b2 = SceneBeat(
                t0=half,
                t1=b_target.t1,
                url=b2_url,
                veiculo=b2_veic,
                kind="x-post" if alt_is_x else (b_target.kind if not same_source else (alt_scene.get("kind") or "source")),
                shot=b2_shot,
                shot_long=b2_shot_long,
                highlight_box=b2_highlight_box,
                video=alt_scene.get("video") or b_target.video,
                broll_file=None,
                x_post=alt_scene.get("x_post") or b_target.x_post,
                semantic_role="repercussao_social" if alt_is_x else ("detalhe_factual" if b2_variant == "portal_zoom" else b_target.semantic_role),
                visual_component="x-post" if alt_is_x else b_target.visual_component,
                visual_variant=b2_variant,
                visual_payload=b_target.visual_payload,
                fala_indices=list(b_target.fala_indices),
                texto_origem=b_target.texto_origem,
                fonte_url_fala=b_target.fonte_url_fala,
                provenance_type=b_target.provenance_type,
            )
            expanded_beats[longest_idx:longest_idx + 1] = [b1, b2]

    final_beats = expanded_beats

    # 7.1 Inserção de Foto Editorial (Person-Photo com Ken Burns)
    # A thumbnail/capa gerada por IA para YouTube/site NÃO deve ser usada no meio do vídeo.
    # Apenas foto editorial legítima de personagem (person_photo / foto_editorial) ou
    # resolução semântica de personalidades citadas no roteiro é aceita.
    editorial_photo = episode.get("person_photo") or episode.get("foto_editorial") or episode.get("editorial_image")
    person_info = None

    if not editorial_photo:
        try:
            from person_resolver import resolve_person_for_text
            for b_item in blocks:
                if b_item.get("section") == "fechamento":
                    continue
                person_info = resolve_person_for_text(b_item.get("texto") or "", auto_download=False)
                if person_info:
                    editorial_photo = person_info["photo_src"]
                    break
        except Exception:
            pass

    src_path = Path(str(editorial_photo)) if editorial_photo else None
    if src_path is not None and not src_path.is_file():
        editorial_photo = None
        src_path = None

    if editorial_photo and src_path is not None and len(final_beats) > 4:
        # Encontra o beat mais longo do terço médio do vídeo para exibir a foto
        mid_start = max(1, len(final_beats) // 4)
        mid_end = min(len(final_beats) - 1, (len(final_beats) * 3) // 4)
        best_cand_idx = -1
        best_cand_dur = 0.0
        for idx in range(mid_start, mid_end):
            b = final_beats[idx]
            b_dur = b.t1 - b.t0
            if b.visual_component == "source" and b_dur > best_cand_dur:
                best_cand_dur = b_dur
                best_cand_idx = idx

        if best_cand_idx >= 0 and best_cand_dur >= 4.5:
            target = final_beats[best_cand_idx]
            photo_name = f"editorial-{src_path.name}"
            person_name = (person_info["name"] if person_info else None) or episode.get("speaker_name") or episode.get("titulo", "")[:45]
            if best_cand_dur >= 9.0:
                photo_dur = min(6.5, best_cand_dur * 0.5)
                photo_t0 = round(target.t1 - photo_dur, 2)
                target.t1 = photo_t0
                photo_beat = SceneBeat(
                    t0=photo_t0,
                    t1=round(photo_t0 + photo_dur, 2),
                    url=target.url,
                    veiculo=target.veiculo,
                    kind="person-photo",
                    shot=target.shot,
                    video=None,
                    broll_file=None,
                    x_post=None,
                    semantic_role="destaque_editorial",
                    visual_component="person-photo",
                    visual_variant="ken_burns",
                    visual_payload={
                        "photo": f"/shots/{photo_name}",
                        "photo_src": str(src_path.resolve()),
                        "name": person_name,
                        "veiculo": target.veiculo or "Registro Editorial Oficial",
                        "tag": "PERSONAGEM EM FOCO",
                    },
                    fala_indices=list(target.fala_indices),
                    texto_origem=target.texto_origem,
                    fonte_url_fala=target.fonte_url_fala,
                    provenance_type="person_photo",
                )
                final_beats.insert(best_cand_idx + 1, photo_beat)
            else:
                # Converte o beat existente respeitando o piso e mantendo continuidade
                target.kind = "person-photo"
                target.semantic_role = "destaque_editorial"
                target.visual_component = "person-photo"
                target.visual_variant = "ken_burns"
                target.visual_payload = {
                    "photo": f"/shots/{photo_name}",
                    "photo_src": str(src_path.resolve()),
                    "name": person_name,
                    "veiculo": target.veiculo or "Registro Editorial Oficial",
                    "tag": "PERSONAGEM EM FOCO",
                }
                target.provenance_type = "person_photo"

    # 7.2 Inserção de Transições Dinâmicas de Bloco / Pauta (Wipe, Dissolve, Flash)
    if total_dur >= 60.0 and len(final_beats) > 3:
        trans_styles = ["wipe_gold", "dissolve_brand", "flash_cut"]
        trans_count = 0
        new_beats: list[SceneBeat] = []
        for idx, b in enumerate(final_beats):
            new_beats.append(b)
            # Verifica se há transição de pauta no próximo beat (apenas fora do gancho inicial de 14s)
            if idx < len(final_beats) - 1 and trans_count < 3 and b.t0 >= 14.0:
                next_b = final_beats[idx + 1]
                is_section_change = (b.t0 < 30.0 and next_b.t0 >= 20.0) or (next_b.t0 >= (total_dur * 0.78))
                is_url_change = bool(b.url and next_b.url and b.url != next_b.url and b.visual_component == "source" and next_b.visual_component == "source")
                if (is_section_change or is_url_change) and (b.t1 - b.t0) >= 4.5:
                    t_trans = 0.8
                    trans_start = round(b.t1 - t_trans, 2)
                    b.t1 = trans_start
                    trans_beat = SceneBeat(
                        t0=trans_start,
                        t1=round(trans_start + t_trans, 2),
                        url=next_b.url,
                        veiculo="Vale da Liberdade",
                        kind="transition",
                        shot=next_b.shot,
                        shot_long=next_b.shot_long,
                        highlight_box=next_b.highlight_box,
                        video=None,
                        broll_file=None,
                        x_post=None,
                        semantic_role="transicao_broll",
                        visual_component="transition",
                        visual_variant=trans_styles[trans_count % len(trans_styles)],
                        visual_payload={},
                        fala_indices=[],
                        texto_origem="",
                        fonte_url_fala=None,
                        provenance_type="transition",
                    )
                    new_beats.append(trans_beat)
                    trans_count += 1
        final_beats = [b for b in new_beats if b.t1 > b.t0 + 0.05]

    # 8. Ajustar continuidade estrita dos timestamps
    for j in range(len(final_beats) - 1):
        if final_beats[j].t1 != final_beats[j + 1].t0:
            final_beats[j + 1].t0 = final_beats[j].t1

    if final_beats:
        final_beats[0].t0 = 0.0
        final_beats[-1].t1 = round(total_dur, 2)

    if return_v2:
        return [SceneBeatV2.from_legacy(b) for b in final_beats]

    return final_beats
