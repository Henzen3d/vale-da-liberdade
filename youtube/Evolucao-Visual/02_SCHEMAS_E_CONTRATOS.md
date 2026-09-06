# 02 — SCHEMAS E CONTRATOS DE DADOS
> **Especificação Formal de Interfaces e Tipos**  
> **Camada:** Comunicação Python ↔ HTML/GSAP ↔ Playwright  
> **Status:** Aprovado para Implementação  

---

## 1. O Novo `SceneBeat` v2 (Python Dataclass & JSON)

No pipeline atual ([`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py)), o `SceneBeat` apenas guardava `url`, `veiculo`, `kind: "source"|"broll"|"x-post"` e referências de arquivos.

Na versão 2, ele é estendido para **desacoplar a intenção narrativa da execução gráfica**:

```python
from __future__ import annotations
from dataclasses import asdict, dataclass, field
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

@dataclass
class SceneBeatV2:
    t0: float                                      # Início em segundos
    t1: float                                      # Fim em segundos
    semantic_role: SemanticRole                     # Intenção narrativa
    visual_component: VisualComponent              # Componente que renderiza
    visual_variant: str                            # Variante do componente (ex: highlight_zoom)
    visual_payload: dict[str, Any]                 # Dados estruturados do componente
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
```

---

## 2. Contrato do `VisualScenePlan`

O `VisualScenePlan` é o arquivo emitido por [`bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py) e gravado em `output/brasil_e_mundo/mockup_video/{video_id}/scene_plan.json`:

```json
{
  "$schema": "https://valedaliberdade.com.br/schemas/scene_plan_v2.json",
  "video_id": "yt_bm_20260905_01",
  "total_duration_s": 284.5,
  "strategy": {
    "dominant_style": "investigative",
    "presenter_density": 0.38,
    "source_density": 0.28,
    "graphic_density": 0.34
  },
  "beats": [
    {
      "t0": 0.0,
      "t1": 14.2,
      "semantic_role": "apresentacao_fato",
      "visual_component": "source",
      "visual_variant": "portal_clean",
      "url": "https://g1.globo.com/sc/santa-catarina/noticia/...",
      "veiculo": "G1 Santa Catarina",
      "shot": "src-00.png",
      "visual_payload": {
        "headline": "Obras na BR-470 avançam para nova fase",
        "lead": "DNIT detalha cronograma de liberação dos viadutos..."
      }
    },
    {
      "t0": 14.2,
      "t1": 27.8,
      "semantic_role": "declaracao_forte",
      "visual_component": "quote",
      "visual_variant": "card_gold",
      "url": "https://g1.globo.com/sc/santa-catarina/noticia/...",
      "veiculo": "G1",
      "visual_payload": {
        "author_name": "Superintendente do DNIT",
        "author_role": "Infraestrutura SC",
        "author_avatar": "/shots/avatar-dnit.jpg",
        "quote_text": "A expectativa é liberar o tráfego pesado até novembro sem interrupções.",
        "source_name": "Entrevista Coletiva",
        "date": "05/09/2026"
      }
    },
    {
      "t0": 27.8,
      "t1": 42.0,
      "semantic_role": "impacto_economico",
      "visual_component": "chart",
      "visual_variant": "stat_counter",
      "visual_payload": {
        "metric_value": 145.8,
        "metric_prefix": "R$ ",
        "metric_suffix": " mi",
        "metric_label": "INVESTIMENTO LIBERADO PELO GOVERNO FEDERAL",
        "trend": "up",
        "delta_text": "+18% em relação a 2025",
        "chart_type": "counter"
      }
    }
  ]
}
```

---

## 3. Schemas dos Payloads por Componente

Cada componente do [`mockup-brower.html`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/references/youtube/mockup-browser/mockup-brower.html) possui um payload tipado estrito:

### 3.1 `QuoteCard` (`visual_component: "quote"`)
```json
{
  "author_name": "string (nome completo do autor da frase)",
  "author_role": "string (cargo, instituição ou relação com o fato)",
  "author_avatar": "string (URL local '/shots/...' ou vazio para ícone fallback)",
  "quote_text": "string (frase marcante, 80 a 240 caracteres)",
  "source_name": "string (onde foi dito: 'Pronunciamento oficial', 'X/Twitter', 'TJSC')",
  "date": "string (data do fato: '05/09/2026')",
  "verified": "boolean (opcional, exibe selo dourado)"
}
```

### 3.2 `DocumentZoom` (`visual_component: "document"`)
```json
{
  "doc_type": "sentenca | despacho | diario_oficial | contrato | relatorio",
  "doc_title": "string (ex: 'DESPACHO JUDICIAL — PROCESSO Nº 500241-2026')",
  "doc_institution": "string (ex: 'Vara da Fazenda Pública de Blumenau')",
  "doc_image": "string (URL local do print do documento '/shots/doc-01.png')",
  "highlight_text": "string (trecho textual exato a ser grifado em amarelo)",
  "case_number": "string (opcional)",
  "zoom_level": "number (default: 1.35)"
}
```

### 3.3 `Timeline` (`visual_component: "timeline"`)
```json
{
  "timeline_title": "string (ex: 'CRONOGRAMA DE DECISÕES DA TARIFA DE ÔNIBUS')",
  "events": [
    {
      "date": "Fev/2026",
      "title": "Pedido de Reajuste",
      "description": "Consórcio solicita aumento de 14%",
      "active": false
    },
    {
      "date": "Mai/2026",
      "title": "Liminar Suspensa",
      "description": "TJSC derruba aumento em primeira instância",
      "active": false
    },
    {
      "date": "Hoje",
      "title": "Decisão Final",
      "description": "Tarifa é congelada por decisão colegiada",
      "active": true
    }
  ]
}
```

### 3.4 `DataChart / StatCounter` (`visual_component: "chart"`)
```json
{
  "metric_value": "number (valor numérico final a ser animado, ex: 5.7)",
  "metric_prefix": "string (ex: 'R$ ' ou '')",
  "metric_suffix": "string (ex: '%' ou ' bi')",
  "metric_label": "string (ex: 'INFLAÇÃO ACUMULADA EM 12 MESES')",
  "trend": "up | down | neutral",
  "delta_text": "string (ex: '+0,4 p.p. acima do teto da meta')",
  "chart_type": "counter | progress_bar | comparison_bars",
  "sub_items": [
    {"label": "Alimentos", "value": "8.2%"},
    {"label": "Combustíveis", "value": "-1.4%"}
  ]
}
```

### 3.5 `Comparison` (`visual_component: "comparison"`)
```json
{
  "comparison_title": "string (ex: 'PROMESSA DE CAMPANHA × EXECUÇÃO ORÇAMENTÁRIA')",
  "side_a": {
    "header": "PROMESSA (2024)",
    "highlight": "0% DE AUMENTO",
    "details": "Compromisso assinado em debate eleitoral de não elevar alíquota do IPTU.",
    "tag_status": "compromisso"
  },
  "side_b": {
    "header": "REALIDADE (2026)",
    "highlight": "+12,4% NO CARNÊ",
    "details": "Revisão da planta genérica de valores publicada no Diário Oficial de ontem.",
    "tag_status": "fato"
  }
}
```

---

## 4. Estrutura do `VisualOpportunity` (Detector de Oportunidades)

Quando o analisador varre o roteiro, ele agrupa as oportunidades encontradas no seguinte formato para permitir o cálculo de pesos:

```json
{
  "block_index": 2,
  "paragraph_text": "O superintendente garantiu que 'nenhuma obra será paralisada até a conclusão'.",
  "detected_opportunities": [
    {
      "opportunity_type": "strong_quote",
      "score": 0.88,
      "recommended_component": "quote",
      "recommended_variant": "card_gold",
      "extracted_data": {
        "quote_text": "nenhuma obra será paralisada até a conclusão",
        "author": "superintendente"
      }
    },
    {
      "opportunity_type": "source_context",
      "score": 0.45,
      "recommended_component": "source",
      "recommended_variant": "portal_clean"
    }
  ],
  "chosen_component": "quote"
}
```
