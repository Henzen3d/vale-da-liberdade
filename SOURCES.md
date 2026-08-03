# SOURCES.md — Descoberta Contínua de Fontes (Web Jornal Vale da Liberdade)

Sistema de governança de fontes do Web Jornal, inspirado no padrão de
verificação *Fable* do Fusion. O objetivo é evoluir o jornal de uma lista
fixa de feeds RSS para um ecossistema que **descobre, avalia e promove**
novas fontes com supervisão humana.

---

## 1. Arquitetura

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐
│  scout.py    │→  │  candidates   │→  │ source_judge  │→  │ sources_weekly_  │
│ (descoberta) │   │ .json         │   │  .py (LLM)    │   │ report.json      │
└─────────────┘   └──────────────┘   └──────────────┘   └─────────────────┘
       │                                                            │
       └──────────→ sources_registry.json ←────────────────────────┘
                    (base de verdade + métricas)
```

| Arquivo | Papel |
|---|---|
| `sources/sources.json` | Fonte operacional do `news_collector.py` (o que é coletado de fato). |
| `sources/sources_registry.json` | Registro de governança: status, métricas, probatório. **Base de verdade.** |
| `sources/sources_candidates.json` | Candidatas descobertas pelo Scout, já julgadas. |
| `sources/sources_weekly_report.json` | Relatório semanal de propostas **pendentes de aprovação**. |
| `scripts/scout.py` | Agente de descoberta (3 vias). |
| `scripts/source_judge.py` | Scoring por LLM Judge (6 eixos). |
| `scripts/source_governance.py` | Probatório + relatório human-in-loop + aplicação após aprovação. |
| `scripts/source_discovery_search.py` | Busca web (Tavily → Exa → DuckDuckGo). Reutiliza chaves do `.env`. |

---

## 2. Fluxo de estados de uma fonte

```
descoberta (Scout) ──▶ candidata ──▶ probatória (N=15 matérias) ──▶ ativa
                                    │
                                    └─── falha critérios ──▶ banida
```

- **candidata**: descoberta e julgada (score ≥ 7.0). Ainda não é coletada.
- **probatória**: o collector já coleta dela, mas o conteúdo é marcado. Após
  `probation_min_articles` (15) matérias coletadas, mede-se uso/duplicação.
- **ativa**: aprovada após probatório — entra no `sources.json` operacional.
- **banida**: rejeitada pelo Judge (score < 5.0 recorrente) ou no probatório.

---

## 3. Agente Scout (descoberta)

Roda semanalmente. Três vias de descoberta:

1. **Busca direta** — queries geográficas ("notícias Blumenau", "portal Vale
   do Itajaí") via `source_discovery_search.web_search()` (Tavily/Exa).
2. **Mineração de citações** — varre os `raw-{date}.md` dos últimos 7–14 dias
   e extrai links de outros veículos que não estão no registry (sinal de que
   uma fonte ativa citou/linkou outro veículo).
3. **Contas X** — *hook* preparado para quando o `x_collector.py` estiver
   coletando; extrai handles retuitados por fontes confiáveis. (Atualmente
   retorna vazio — não bloqueia o pipeline.)

As descobertas são cruzadas contra o registry (descarta domínios já conhecidos)
e salvas em `sources_candidates.json`.

```bash
python3 scripts/scout.py --weeks 1 --max-candidates 30
python3 scripts/scout.py --dry-run        # só imprime, não salva
```

---

## 4. Source Judge (scoring por LLM)

Cada candidata é avaliada por um LLM Judge (OpenRouter free / Gemini) em 6
eixos (0–10), com pesos:

| Eixo | Peso | Avalia |
|---|---|---|
| relevancia_geo_tematica | 25% | Cobertura de Blumenau/Vale/SC ou pauta nacional útil |
| qualidade_editorial | 25% | Fato vs opinião, evita clickbait, cita fontes |
| frequencia_regularidade | 15% | Cadência previsível (não fica meses muda) |
| confiabilidade_tecnica | 15% | RSS estável > scraping frágil |
| ineditismo | 10% | Pauta que as fontes atuais não cobrem |
| transparencia_vies | 10% | Se opinativo, é explícito sobre isso |

- **score_final ≥ 7.0** → veredicto `promover`
- **score_final < 5.0** (recorrente) → veredicto `banir` (com motivo)
- Entre 5.0 e 7.0 → `observar`

Se a LLM não estiver disponível, aplica-se um **fallback heurístico local**
(nunca bloqueia o pipeline, mas o score é apenas aproximado — revise o
relatório antes de aprovar).

```bash
python3 scripts/source_judge.py --candidates sources/sources_candidates.json
```

---

## 5. Governança (human-in-the-loop)

O `source_governance.py` **não promove nem bane nada sozinho**. Ele:

1. Atualiza métricas de fontes em probatória a partir do `cache.json`.
2. Gera `sources_weekly_report.json` com **propostas** de promoção/banimento.
3. Imprime o relatório legível.

A aprovação é feita pelo operador (Hermes pergunta ao usuário). Só após
`--apply` é que o registry e o `sources.json` operacional são alterados.

```bash
python3 scripts/source_governance.py            # gera relatório (propostas)
python3 scripts/source_governance.py --apply    # efetiva (APÓS aprovação)
```

### Campos-chave de decisão (no registry)
- `usage_rate` = matérias aproveitadas ÷ coletadas
- `scrape_error_rate` = taxa de erro de coleta
- `duplicate_rate` = sobreposição com fontes já ativas (redundante não agrega)
- `avg_editorial_score` = nota média do Judge

---

## 6. Agendamento (cron Hermes)

O Scout roda **semanalmente** (sugerido: toda segunda-feira, 06:00). O
`source_judge.py` roda na sequência do Scout. O `source_governance.py` roda
logo após, gerando o relatório que o Hermes entrega ao usuário para aprovação.

Exemplo de cron (criado via `cronjob` do Hermes):
- `scout + judge` → toda segunda 06:00
- `governance --apply` → **não** automático; só após aprovação manual.

---

## 7. Chaves necessárias (`.env` do web-jornal)
- `TAVILY_API_KEY` — busca web do Scout (reutilizada do Fusion)
- `EXA_API_KEY` — busca semântica do Scout (reutilizada do Fusion)
- `OPENROUTER_API_KEY` — LLM Judge (reutilizada do Fusion; a do web-jornal
  original estava inválida e foi substituída)
- `GEMINI_API_KEY` — reserva para o Judge (presente no `.env`)

---

## 8. Status de implementação
- ✅ `sources_registry.json` (39 fontes migradas do `sources.json`)
- ✅ `scout.py` (3 vias, testado com Tavily real)
- ✅ `source_judge.py` (LLM Judge testado — scores coerentes)
- ✅ `source_governance.py` (probatório + relatório + apply)
- ✅ `source_discovery_search.py` (Tavily→Exa→DDG)
- ✅ Relatório semanal human-in-loop
- ⏳ Integração fina de métricas no `news_collector.py` (o collector já grava
  `source_stats` no `cache.json`; o governance lê daí para o probatório)
- ⏳ Via X do Scout (hook pronto, aguarda `x_collector` funcional)

---

## 9. Exemplo de execução ponta-a-ponta
```bash
cd /home/osmar/web-jornal-vale-da-liberdade
python3 scripts/scout.py --max-candidates 30
python3 scripts/source_judge.py
python3 scripts/source_governance.py        # relatório p/ aprovação
# (usuário aprova) →
python3 scripts/source_governance.py --apply
```
