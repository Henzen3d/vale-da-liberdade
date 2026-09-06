# 04 — DETECTOR DE OPORTUNIDADES VISUAIS
> **Módulo de Análise e Scoring Editorial Determinístico + Refinamento**  
> **Arquivo Alvo:** Integrado a [`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py)  
> **Custo de Execução:** Custo zero (Nível 0 determinístico) com chamada opcional ao Gemini (Nível 1)  

---

## 1. Por que um Detector de Oportunidades?

Uma heurística cega do tipo:
> *"Se encontrar `%`, vire um gráfico."*

gera falsos positivos. Exemplo:
> *"O governador afirmou que 'com 51% das obras concluídas, o prazo será cumprido'."*

Neste trecho, há o símbolo `%`, mas o elemento mais relevante para o espectador é a **declaração entre aspas do governador** (`QuoteCard`), acompanhada do print da matéria original, e não um gráfico em tela cheia.

O **Visual Opportunity Detector** avalia múltiplos sinais concorrentes em cada parágrafo, calcula uma **pontuação de relevância (score de 0.0 a 1.0)** e decide o melhor componente com base em pesos editoriais.

---

## 2. Padrões Regex e Heurísticas de Nível 0 (Custo Zero)

O detector roda localmente em Python via expressões regulares e análise léxica rápida:

```python
import re

# 1. Citações e Declarações Fortes
QUOTE_PATTERNS = [
    re.compile(r'["“]([^"”]{20,260})["”]'),
    re.compile(r'(?:afirmou|disse|declarou|ressaltou|garantiu|destacou)\s+(?:que\s+)?["“](.+?)["”]', re.I),
    re.compile(r'em\s+nota(?:,\s+afirmou\s+que)?:\s*["“]?([^.\n]+)', re.I),
]

# 2. Dados Econômicos, Orçamento e Estatísticas
CHART_PATTERNS = [
    re.compile(r'R\$\s*([0-9.,]+)\s*(milhões|milhão|bilhões|bilhão|bi|mi|mil)?', re.I),
    re.compile(r'([0-9]+(?:,[0-9]+)?)\s*%', re.I),
    re.compile(r'(?:alta|queda|recuo|avanço|crescimento|inflação)\s+de\s+([0-9]+(?:,[0-9]+)?)\s*(?:%|pontos|p\.p\.)', re.I),
]

# 3. Documentos Oficiais e Justiça
DOC_PATTERNS = [
    re.compile(r'(?:processo|autos)\s+n[ºo°]?\s*([0-9.-]+)', re.I),
    re.compile(r'(?:decisão|liminar|despacho|sentença|acórdão)\s+(?:do|da|de)\s+([A-ZÇÃÉÍÓÚa-zçãéíóú\s]{3,25})', re.I),
    re.compile(r'(?:publicado|consta)\s+no\s+(?:diário\s+oficial|portal\s+da\s+transparência)', re.I),
    re.compile(r'(?:decreto|portaria|lei\s+complementar)\s+n[ºo°]?\s*([0-9]+)', re.I),
]

# 4. Cronologia e Linha do Tempo
TIMELINE_PATTERNS = [
    re.compile(r'(?:em\s+)?(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(202[0-9])', re.I),
    re.compile(r'(?:em|desde)\s+(201[8-9]|202[0-6])', re.I),
    re.compile(r'(?:meses\s+depois|semanas\s+após|na\s+sequência|posteriormente|anos\s+antes)', re.I),
]

# 5. Comparações e Contradições
COMPARISON_PATTERNS = [
    re.compile(r'(?:prometeu|anunciou|havia\s+dito)\s+.*?\s+(?:mas|porém|contudo|no\s+entanto|todavia)', re.I),
    re.compile(r'(?:antes\s+era|em\s+202[0-4]\s+era)\s+.*?\s+(?:agora|hoje|em\s+202[5-6])', re.I),
    re.compile(r'(?:enquanto\s+o\s+governo\s+diz|de\s+um\s+lado\s+.*?\s+de\s+outro)', re.I),
]
```

---

## 3. Matriz de Pontuação e Cálculo de Relevância

Para cada parágrafo/fala do roteiro, a função `detect_visual_opportunities(text, url, veiculo)` gera um mapa de candidatos com suas respectivas pontuações:

$$\text{Score Final} = \text{Base} + \text{ContextBoost} + \text{AntiFatigueBonus}$$

| Componente | Gatilho Detectado | Peso Base | Bônus de Contexto (+0.15 a +0.25) |
| :--- | :--- | :---: | :--- |
| **`quote`** | Frase entre aspas com verbo de elocução | **0.75** | Menção explícita de nome próprio de autoridade ou cargo. |
| **`document`** | Termos jurídicos, número de processo | **0.80** | Domínio oficial da fonte (`jus.br`, `sc.gov.br`, `stf.jus.br`). |
| **`chart`** | Big Number monetário (`R$ mi`) ou `%` | **0.70** | Pauta com tema econômico ou inflação. |
| **`timeline`** | 2 ou mais referências temporais distintas | **0.65** | Presença de conectivos cronológicos (`depois`, `em seguida`). |
| **`comparison`** | Conjunção adversativa confrontando fatos | **0.70** | Presença de datas em contraste (ex: 2024 vs 2026). |
| **`source`** | Fallback padrão do navegador | **0.50** | Screenshot capturada de alta resolução disponível. |

---

## 4. Algoritmo de Decisão: Quando Acionar o Gemini (Nível 1)?

O acionamento de modelos externos é restrito para economizar cota e tempo de CPU:

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Calcular scores dos candidatos visuais                   │
│    Exemplo: [Quote: 0.85, Chart: 0.50, Source: 0.50]        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
            ┌──────────────────────────────────────┐
            │ O candidato líder tem Score >= 0.75  │
            │ E a diferença para o 2º é >= 0.20?   │
            └──────────────────┬───────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼ SIM                           ▼ NÃO (Empate / Ambiguidade)
┌─────────────────────────────┐  ┌──────────────────────────────────────────┐
│ DECISÃO DETERMINÍSTICA      │  │ NÍVEL 1: REFINAMENTO GEMINI 2.5 FLASH    │
│ Adota o componente líder    │  │ Prompt enxuto (<150 tokens) de desempate │
│ Custo: R$ 0,00 | Latência: 0│  │ Custo: ~US$ 0.0001 | Retorna JSON        │
└─────────────────────────────┘  └──────────────────────────────────────────┘
```

### Prompt Enxuto de Nível 1 (Desempate)
Quando o determinístico encontra empate (ex: texto tem uma citação com `%` e dados numéricos), uma chamada ultra-rápida desempata:

```text
Sistema: Você é o Diretor de Arte do Web Jornal Vale da Liberdade.
Entrada:
Trecho: "{paragrafo}"
Candidatos: ["quote", "chart"]
Objetivo: Escolha o componente visual de maior clareza narrativa para a TV.
Responda exclusivamente em JSON:
{"chosen": "quote" | "chart", "reason": "...", "highlight_data": "..."}
```

---

## 5. Integração com a Timeline de Cenas

No arquivo [`scripts/bm_scene_timeline.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_scene_timeline.py), a nova função `build_scene_timeline_v2()` substitui a fila circular simples de screenshots:

1. Agrupa as falas por bloco temático.
2. Roda o `Visual Opportunity Detector` em cada bloco.
3. Se um bloco é classificado como `QuoteCard`, calcula o tempo do beat baseado nas palavras daquele trecho e monta o payload correspondente.
4. Respeita o piso mínimo de **8.0s** e máximo de **22.0s**.
5. Emite a lista de `SceneBeatV2` pronta para consumo pelo Playwright.
