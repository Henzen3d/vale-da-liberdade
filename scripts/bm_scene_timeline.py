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

# Componentes visuais suportados no mockup-brower.html
VisualComponent = Literal[
    "source",           # Browser com matéria jornalística
    "x-post",           # Card interativo do X com animação de Like
    "quote",            # Card editorial de citação
    "document",         # Visualizador de documento oficial com zoom/grifo
    "timeline",         # Linha do tempo com marcos temporais
    "chart",            # Big Number / Indicador / Gráfico vetorial
    "comparison",       # Split-Screen de confronto
    "broll",            # Vídeo curto de respiro
]

_LEGACY_KINDS = frozenset({"source", "broll", "x-post"})


@dataclass
class SceneBeat:
    t0: float
    t1: float
    url: str
    veiculo: str
    kind: str  # "source" | "broll" | "x-post"
    shot: str | None = None
    video: str | None = None
    broll_file: str | None = None
    x_post: dict | None = None
    semantic_role: SemanticRole = "apresentacao_fato"
    visual_component: VisualComponent = "source"
    visual_variant: str = ""
    visual_payload: dict[str, Any] = field(default_factory=dict)

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
    video: str | None = None                       # Vídeo/clipe auxiliar (se houver)
    broll_file: str | None = None                  # Arquivo de b-roll local

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
            video=self.video,
            broll_file=self.broll_file,
            x_post=None,
            semantic_role=self.semantic_role,
            visual_component=self.visual_component,
            visual_variant=self.visual_variant,
            visual_payload=self.visual_payload,
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
            "video": beat.video,
            "broll_file": beat.broll_file,
        }
        base.update(overrides)
        return cls(**base)


# ---------------------------------------------------------------------------
# REGRAS E DETECTOR DE OPORTUNIDADES VISUAIS (NÍVEL 0 — HEURÍSTICA PURA)
# Contrato: youtube/Evolucao-Visual/02_SCHEMAS_E_CONTRATOS.md §4
# ---------------------------------------------------------------------------

QUOTE_PATTERNS = [
    re.compile(r'["“]([^"”]{12,300})["”]', re.U),
    re.compile(
        r'(?:afirmou|disse|declarou|ressaltou|garantiu|destacou)\s*:\s*["“]?([^"”\n.]{12,300})["”]?',
        re.I | re.U,
    ),
    re.compile(
        r'(?:afirmou|disse|declarou|ressaltou|garantiu|destacou)\s+(?:que\s+)?["“](.+?)["”]',
        re.I | re.U,
    ),
    re.compile(r'em\s+nota(?:,\s+afirmou\s+que)?:\s*["“]?([^.\n]{15,300})["”]?', re.I | re.U),
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

_VARIANT_BY_COMPONENT = {
    "quote": "card_gold",
    "document": "highlight_zoom",
    "chart": "stat_counter",
    "timeline": "progressive_nodes",
    "comparison": "split_screen",
    "source": "portal_clean",
}

_BASE_SCORE = {
    "quote": 0.75,
    "document": 0.80,
    "chart": 0.70,
    "timeline": 0.65,
    "comparison": 0.70,
    "source": 0.50,
}

_OPPORTUNITY_TYPE = {
    "quote": "strong_quote",
    "document": "official_document",
    "chart": "economic_stat",
    "timeline": "chronology",
    "comparison": "confrontation",
    "source": "source_context",
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
        candidates["quote"] = {
            "opportunity_type": _OPPORTUNITY_TYPE["quote"],
            "score": round(score, 2),
            "recommended_component": "quote",
            "recommended_variant": _VARIANT_BY_COMPONENT["quote"],
            "extracted_data": {
                "quote_text": quote_text,
                "author": author,
                "author_name": author or "Autoridade",
                "source_name": veiculo_s or "Declaração Oficial",
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


MIN_SCENE_DURATION_S = 8.0
MAX_SCENE_DURATION_S = 22.0
DEFAULT_BROLL_DUR_S = 1.2
TARGET_MIN_BEATS_5MIN = 10


def count_words(text: str) -> int:
    return len((text or "").split())


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
    - Garante piso de pelo menos 8s por cena de fonte externa.
    - Insere transições de b-roll (0.8–1.5s) em mudanças de matéria se houver clipes disponíveis.
    - Garante ritmo dinâmico com pelo menos 10 telas/beats em episódios de 5 minutos (~300s).
    """
    total_dur = max(total_duration_s, 10.0)
    if not scenes:
        scenes = [{"veiculo": "Vale da Liberdade", "url": "https://news.mob.tec.br", "shot": None, "video": None}]

    # 1. Coletar falas em ordem sequencial com seus blocos e fonte_url
    blocks: list[dict] = []
    for section_name in ("abertura", "desenvolvimento", "fechamento"):
        for item in episode.get(section_name) or []:
            txt = (item.get("texto") or "").strip()
            if not txt:
                continue
            blocks.append({
                "section": section_name,
                "texto": txt,
                "words": max(1, count_words(txt)),
                "fonte_url": item.get("fonte_url") or "",
            })

    if not blocks:
        blocks = [{
            "section": "desenvolvimento",
            "texto": episode.get("titulo") or "Comentário",
            "words": 100,
            "fonte_url": "",
        }]

    total_words = sum(b["words"] for b in blocks)
    available_broll = load_broll_clips(broll_index_path)

    # 2. Mapeamento de cenas por URL
    scene_by_url = {s["url"]: s for s in scenes if s.get("url")}
    scene_queue = list(scenes)
    scene_ptr = 0

    # 3. Construção dos beats preliminares com detecção de oportunidades
    raw_beats: list[dict] = []
    current_t = 0.0

    for idx, b in enumerate(blocks):
        dur_block = (b["words"] / total_words) * total_dur
        target_url = b.get("fonte_url")
        scene_item = None

        if target_url and target_url in scene_by_url:
            scene_item = scene_by_url[target_url]
        else:
            scene_item = scene_queue[scene_ptr % len(scene_queue)]

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
                    "video": None,
                    "broll_file": clip.get("file"),
                    "semantic_role": "transicao_broll",
                    "visual_component": "broll",
                    "visual_variant": "",
                    "visual_payload": {},
                })
                current_t = broll_end
                t_end = min(total_dur, current_t + dur_block)

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
            "kind": scene_item.get("kind") or (chosen_comp if chosen_comp in _LEGACY_KINDS else "source"),
            "shot": scene_item.get("shot"),
            "video": scene_item.get("video"),
            "broll_file": None,
            "x_post": scene_item.get("x_post"),
            "semantic_role": semantic_role,
            "visual_component": chosen_comp,
            "visual_variant": variant,
            "visual_payload": payload,
        })
        scene_ptr += 1
        current_t = t_end

    # 4. Agregação e aplicação de piso mínimo de 8.0s por cena de fonte
    final_beats: list[SceneBeat] = []
    i = 0
    while i < len(raw_beats):
        rb = raw_beats[i]
        kind = rb["kind"]
        url = rb["url"]
        veic = rb["veiculo"]
        shot = rb["shot"]
        video = rb["video"]
        broll_file = rb["broll_file"]
        x_post = rb.get("x_post")
        sem_role = rb.get("semantic_role") or "apresentacao_fato"
        vis_comp = rb.get("visual_component") or "source"
        vis_var = rb.get("visual_variant") or ""
        vis_pay = rb.get("visual_payload") or {}
        t0 = rb["t0"]
        t1 = rb["t1"]

        # Agrupar beats consecutivos idênticos
        while (i + 1 < len(raw_beats) 
               and raw_beats[i + 1]["kind"] == kind 
               and raw_beats[i + 1]["url"] == url 
               and raw_beats[i + 1].get("visual_component") == vis_comp):
            t1 = raw_beats[i + 1]["t1"]
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
            video=video,
            broll_file=broll_file,
            x_post=x_post,
            semantic_role=sem_role,
            visual_component=vis_comp,
            visual_variant=vis_var,
            visual_payload=vis_pay,
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
                video=old_first.video,
                x_post=old_first.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
            )
            b0_b = SceneBeat(
                t0=cut1,
                t1=cut2,
                url=alt_scene.get("url") or old_first.url,
                veiculo=alt_scene.get("veiculo") or old_first.veiculo,
                kind=alt_scene.get("kind") or "source",
                shot=alt_scene.get("shot") or old_first.shot,
                video=alt_scene.get("video") or old_first.video,
                x_post=alt_scene.get("x_post") or old_first.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
            )
            b0_c = SceneBeat(
                t0=cut2,
                t1=old_first.t1,
                url=old_first.url,
                veiculo=old_first.veiculo,
                kind="source",
                shot=old_first.shot,
                video=old_first.video,
                x_post=old_first.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
            )
            final_beats[0:1] = [b0_a, b0_b, b0_c]

    # 6. Dinamismo: quebra beats longos (> 22s) alternando entre cenas
    expanded_beats: list[SceneBeat] = []
    cycle_ptr = 1
    for beat in final_beats:
        dur = beat.t1 - beat.t0
        if dur > MAX_SCENE_DURATION_S and len(scene_queue) > 1 and beat.visual_component == "source":
            num_sub = int(dur // 15.0) + 1
            step = dur / num_sub
            sub_t0 = beat.t0
            for s_idx in range(num_sub):
                sub_t1 = round(beat.t0 + (s_idx + 1) * step, 2)
                if s_idx == num_sub - 1:
                    sub_t1 = beat.t1
                alt_scene = scene_queue[cycle_ptr % len(scene_queue)]
                cycle_ptr += 1
                expanded_beats.append(SceneBeat(
                    t0=round(sub_t0, 2),
                    t1=round(sub_t1, 2),
                    url=alt_scene.get("url") or beat.url,
                    veiculo=alt_scene.get("veiculo") or beat.veiculo,
                    kind=alt_scene.get("kind") or "source",
                    shot=alt_scene.get("shot") or beat.shot,
                    video=alt_scene.get("video") or beat.video,
                    broll_file=None,
                    x_post=alt_scene.get("x_post") or beat.x_post,
                    semantic_role=beat.semantic_role,
                    visual_component=beat.visual_component,
                    visual_variant=beat.visual_variant,
                    visual_payload=beat.visual_payload,
                ))
                sub_t0 = sub_t1
        else:
            expanded_beats.append(beat)

    # 7. Garantia de Piso de Telas: assegura pelo menos 10 beats em vídeos longos (>= 180s)
    if total_dur >= 180.0 and len(expanded_beats) < TARGET_MIN_BEATS_5MIN and len(scene_queue) > 1:
        while len(expanded_beats) < TARGET_MIN_BEATS_5MIN:
            longest_idx = max(range(len(expanded_beats)), key=lambda idx: (expanded_beats[idx].t1 - expanded_beats[idx].t0))
            b_target = expanded_beats[longest_idx]
            b_dur = b_target.t1 - b_target.t0
            if b_dur < 12.0:
                break
            half = round(b_target.t0 + b_dur / 2.0, 2)
            alt_scene = scene_queue[cycle_ptr % len(scene_queue)]
            cycle_ptr += 1
            b1 = SceneBeat(
                t0=b_target.t0,
                t1=half,
                url=b_target.url,
                veiculo=b_target.veiculo,
                kind=b_target.kind,
                shot=b_target.shot,
                video=b_target.video,
                broll_file=b_target.broll_file,
                x_post=b_target.x_post,
                semantic_role=b_target.semantic_role,
                visual_component=b_target.visual_component,
                visual_variant=b_target.visual_variant,
                visual_payload=b_target.visual_payload,
            )
            b2 = SceneBeat(
                t0=half,
                t1=b_target.t1,
                url=alt_scene.get("url") or b_target.url,
                veiculo=alt_scene.get("veiculo") or b_target.veiculo,
                kind=alt_scene.get("kind") or "source",
                shot=alt_scene.get("shot") or b_target.shot,
                video=alt_scene.get("video") or b_target.video,
                broll_file=None,
                x_post=alt_scene.get("x_post") or b_target.x_post,
                semantic_role="apresentacao_fato",
                visual_component="source",
                visual_variant="portal_clean",
            )
            expanded_beats[longest_idx:longest_idx + 1] = [b1, b2]

    final_beats = expanded_beats

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
