# 01 — VISUAL ARCHITECTURE V2
> **Documento de Arquitetura Técnica Consolidada**  
> **Sistema:** Web Jornal Vale da Liberdade — Motor de Direção Visual Procedural  
> **Status:** Aprovado para Implementação  
> **Referência:** `Plano_Evolucao_Visual_Vale_da_Liberdade.md` + Ajustes Arquiteturais V2  

---

## 1. Visão Geral e Princípios Fundamentais

A arquitetura **Visual V2** transforma o pipeline de produção do Vale da Liberdade de um *template fixo automatizado* para um **sistema de direção visual procedural**, consciente do conteúdo jornalístico de cada pauta.

### Os 4 Pilares da V2
1. **Aproveitamento Total da Infraestrutura Existente:** Não construir um novo motor de vídeo. O projeto já opera com [`mockup-brower.html`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/references/youtube/mockup-browser/mockup-brower.html) (HTML/CSS + GSAP 3.14.2), [`bm_mockup_video.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py) (Playwright 1080p + Intel VA-API `h264_vaapi`) e [`bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py). A evolução ocorre dentro desse motor.
2. **Separação Rígida entre Semântica e Componente Gráfico:** O `SceneBeat` passa a distinguir o *papel narrativo* (`semantic_role`), o *componente visual* (`visual_component`), a *variante de exibição* (`visual_variant`) e o *payload de dados* (`visual_payload`).
3. **Decisão Visual em Múltiplos Níveis (Sem Pedágio de IA em cada frame):** Heurísticas determinísticas extraem candidatos a custo zero; modelos leves do Gemini (`gemini_client.py`) atuam apenas no desempate de oportunidades; o modelo avançado atua somente no laboratório de criação e pautas complexas.
4. **Controle Estrito de Ritmo e Densidade:** Evitar o "carnaval digital". O sistema calibra a proporção de tempo em que o apresentador Peter Albuquerque fica em destaque, o tempo de telas de fontes e a quantidade de gráficos dinâmicos.

---

## 2. Diagrama do Pipeline Ponta a Ponta

```text
                           FONTES / PAUTA JORNALÍSTICA
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │   ROTEIRO ESTRUTURADO    │
                           │   especial-{id}.json     │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ scripts/bm_scene_timeline.py         │
                     │                                      │
                     │ 1. Visual Opportunity Detector       │
                     │    (regex: %, R$, datas, aspas, pdf) │
                     │ 2. Matriz de Candidatos & Scoring    │
                     │ 3. Regra Anti-Fadiga (last_videos)   │
                     │ 4. Refinamento Opcional (Gemini)     │
                     │ 5. Cálculo de Beats por Palavras     │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │    VISUAL SCENE PLAN     │
                           │    (SceneBeat v2[])      │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ references/youtube/mockup-browser/   │
                     │ mockup-brower.html (HTML5+SVG+GSAP)  │
                     │                                      │
                     │ • Presenter (Âncora Oficial)         │
                     │ • Source (Páginas capturadas/Clean)  │
                     │ • X-Card (Post do X animado)         │
                     │ • QuoteCard [NOVO]                   │
                     │ • DocumentZoom [NOVO]                │
                     │ • Timeline [NOVO]                    │
                     │ • DataChart / StatCounter [NOVO]     │
                     │ • Comparison [NOVO]                  │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ scripts/bm_mockup_video.py           │
                     │ • Playwright headless grava 1080p    │
                     │ • Mux FFmpeg VA-API (Intel HD 630)   │
                     │ • Overlay Peter Loop + Lower Third   │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
                           ┌──────────────────────────┐
                           │     VÍDEO FINAL (MP4)    │
                           └────────────┬─────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ QA VISUAL LEVE                       │
                     │ Extração de 4 a 6 frames chave       │
                     │ (contraste, texto, ausência preto)   │
                     └──────────────┬───────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                      APROVA                 ALERTA
             (YouTube Uploader)       (Registra log para revisão)
```

---

## 3. Os Três Níveis de Inteligência Visual

Para manter o custo de API baixo e o tempo de execução previsível no agendamento do cron a cada 20 minutos:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ NÍVEL 0: DETERMINÍSTICO (Custo Zero | Executa em todos os vídeos)          │
│ • Detectores Regex no roteiro: %, R$, datas, aspas, links .pdf, domínios    │
│ • Extração de entidades e números-chave                                     │
│ • Mapeamento de fontes oficiais (STF, Diário Oficial, prefeituras)          │
│ • Geração inicial de candidatos com notas de probabilidade (scoring)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Se houver ambiguidade
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ NÍVEL 1: REFINAMENTO SEMÂNTICO (Gemini 2.5 / Flash via gemini_client.py)   │
│ • Chamado quando há empate de candidatos ou texto editorial denso           │
│ • Pergunta pontual: "Qual oportunidade visual melhor ancora este trecho?"   │
│ • Retorna JSON enxuto refinando o `visual_payload`                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Em pautas complexas ou auditoria
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ NÍVEL 2: DIRETOR CRIATIVO AVANÇADO (Astra / Modelo Especializado)          │
│ • Utilizado em especiais investigativos e pautas com múltiplos personagens  │
│ • Auditoria quinzenal do canal: análise de repetição e fadiga               │
│ • Proposição de novos componentes para o `mockup-brower.html`               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Registro Central de Componentes Visuais (`VISUAL_COMPONENTS`)

O sistema mantém um catálogo formal de componentes registrados para que o seletor visual e a IA conheçam exatamente o que o estúdio é capaz de renderizar:

```python
VISUAL_COMPONENTS = {
    "source": {
        "renderer": "browserMockup",
        "weight_cost": 1.0,
        "best_for": ["materia_jornalistica", "artigo", "portal"],
        "max_consecutive_s": 24.0,
        "requires_asset": "screenshot",
    },
    "x-post": {
        "renderer": "xCard",
        "weight_cost": 1.1,
        "best_for": ["declaracao_social", "reacao_rapida", "post_x"],
        "max_consecutive_s": 16.0,
        "requires_asset": "x_post_data",
    },
    "quote": {
        "renderer": "quoteCard",
        "weight_cost": 1.0,
        "best_for": ["declaracao_forte", "frase_chave", "discurso"],
        "max_consecutive_s": 14.0,
        "requires_asset": "quote_text",
    },
    "document": {
        "renderer": "documentZoom",
        "weight_cost": 1.2,
        "best_for": ["decisao_judicial", "despacho", "diario_oficial", "contrato"],
        "max_consecutive_s": 18.0,
        "requires_asset": "document_image_or_pdf",
    },
    "chart": {
        "renderer": "dataChartCard",
        "weight_cost": 1.1,
        "best_for": ["estatistica", "inflacao", "orcamento", "pesquisa"],
        "max_consecutive_s": 15.0,
        "requires_asset": "numeric_data",
    },
    "timeline": {
        "renderer": "timelineCard",
        "weight_cost": 1.3,
        "best_for": ["cronologia", "sucessao_de_fatos", "crise_politica"],
        "max_consecutive_s": 20.0,
        "requires_asset": "events_list",
    },
    "comparison": {
        "renderer": "comparisonCard",
        "weight_cost": 1.2,
        "best_for": ["antes_depois", "promessa_vs_fato", "confronto_declaracoes"],
        "max_consecutive_s": 16.0,
        "requires_asset": "two_sides_data",
    },
}
```

---

## 5. Estratégia Visual & Controle de Densidade

Para garantir sobriedade jornalística e evitar excesso de cortes ou distrações visuais:

### Parâmetros de Densidade Visual
* **`presenter_density` (30% a 45%):** Tempo em que o apresentador Peter Albuquerque fica com presença âncora visível na composição.
* **`source_density` (25% a 40%):** Tempo dedicado a prints e páginas reais dos veículos de imprensa.
* **`graphic_density` (20% a 35%):** Tempo dedicado a cartelas especiais (Quotes, Documentos, Timelines, Dados e Comparações).
* **`min_beat_duration_s` (8.0s):** Nenhuma tela fica menos de 8 segundos no ar (exceto transições rápidas de b-roll de 1.2s), garantindo tempo hábil de leitura.
* **`max_beat_duration_s` (22.0s):** Nenhuma cena estática permanece mais de 22 segundos sem variação visual ou scroll suave.

---

## 6. Memória Anti-Fadiga (`last_videos.json`)

Para evitar que três vídeos consecutivos do canal usem exatamente a mesma fórmula visual, o pipeline consulta o histórico recente antes de fechar o Scene Plan:

```json
{
  "history": [
    {
      "video_id": "yt_bm_20260904_01",
      "date": "2026-09-04",
      "dominant_style": "standard_source",
      "components_used": ["source", "x-post", "source"]
    },
    {
      "video_id": "yt_bm_20260905_01",
      "date": "2026-09-05",
      "dominant_style": "standard_source",
      "components_used": ["source", "source"]
    }
  ]
}
```

**Regra:** Se os últimos 2 vídeos tiveram como componente dominante `source`, a pontuação de candidatos a cartelas (`quote`, `document`, `chart`, `timeline`) recebe um bônus de **+0.25 no score** se a pauta oferecer oportunidade viável.

---

## 7. Escolha Tecnológica: Por que SVG Procedural + GSAP no Browser?

1. **Aceleração VA-API da Intel HD 630:** O Chromium no Playwright renderiza vetores SVG e estilos CSS acelerados por GPU local. Elementos procedurais têm custo computacional mínimo se comparados a vídeos 3D.
2. **Resolução 1080p Cristalina:** Vetores SVG não perdem nitidez em qualquer escala e mantêm a tipografia perfeitamente legível no YouTube em TVs, desktops e celulares.
3. **Parametrização por Dados:** Um gráfico ou timeline em SVG é alterado via atributos (`width`, `points`, `stroke-dashoffset`) sem exigir renderização de imagens externas ou download de b-rolls pesados.
