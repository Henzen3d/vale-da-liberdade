# ROADMAP — Plano de Melhorias Priorizado

> Roadmap de execução faseado do **Web Jornal Vale da Liberdade**, classificado por
> **Impacto × Esforço**. Cada fase é independentemente shippável e verificável.
>
> **Princípio:** Fase 0 + Fase 1 entregam ~70% do valor (eliminam a violação de constraint
> e a regressão de qualidade). Fases 2-5 são incrementos de qualidade. Fase 6 é preparação futura.
>
> **Mantém:** Hermes Agent | **Locale:** pt-BR | **Atualização:** 2026-06-20

---

## Matriz Impacto × Esforço (visão geral)

```
  ALTO IMPACTO
       │
       │  ┌─────────────────┐  ┌─────────────────────┐
       │  │ Fase 1 (núcleo) │  │      Fase 2         │
       │  │ Gemini → Hermes │  │  Pipeline robusto   │
       │  │                 │  │                     │
       │  │  Fase 0         │  │      Fase 6         │
       │  │  (quick wins)   │  │  Escalabilidade     │
       │  └─────────────────┘  └─────────────────────┘
       │  ┌─────────────────┐  ┌─────────────────────┐
       │  │  Fase 3         │  │                     │
       │  │  Nacional/Intl  │  │   (sem itens aqui   │
       │  │  Fase 4         │  │    — tudo filtrado  │
       │  │  Roteiro ideal  │  │    para fases acima)│
       │  │  Fase 5 (áudio) │  │                     │
       │  └─────────────────┘  └─────────────────────┘
       │
  BAIXO IMPACTO ───────────────────────────────────────────
       BAIXO ESFORÇO                    ALTO ESFORÇO
```

| Quadrante | Fases | Recomendação |
|---|---|---|
| **Alto Impacto / Baixo Esforço** | Fase 0, Fase 3, Fase 4, Fase 5 | **Fazer primeiro** — retorno máximo |
| **Alto Impacto / Alto Esforço** | Fase 1, Fase 2, Fase 6 | **Planejar** — essenciais mas demandam tempo |
| **Baixo Impacto / Baixo Esforço** | (incluído em Fase 0.5) | Fazer quando conveniente |
| **Baixo Impacto / Alto Esforço** | — | Evitar |

---

## FASE 0 — Quick Wins (Alto Impacto / Baixo Esforço)

> Correções que eliminam defeitos já ativos em produção. Sem arquitetura nova.
> **Estimativa:** 1-2 sessões.

| ID | Item | Arquivo | Por quê |
|---|---|---|---|
| **0.1** | Desativar `_fill_roteiro_from_raw` de caminhos ativos; `cmd_process` deve **falhar alto** (exit non-zero) se `generate_script` falhar, em vez de silenciosamente manter boilerplate | `scripts/pipeline.py:342-422, 442-452` | Elimina a regressão do episódio 2026-06-20 (430 palavras, 3 quadros) |
| **0.2** | Corrigir regra `\bBR\b → "B-R"` para **preservar** `BR-\d+` (rodovias) | `scripts/tts_preprocessor.py:64, 137-140` | `BR-470` hoje vira `B-R-470` no áudio final |
| **0.3** | Implementar dedup semântica no `content_hashes` (hoje vazio) usando hash de conteúdo (SimHash/MinHash sobre título+resumo) | `scripts/news_collector.py:442-454`, `sources/cache.json` | Mesma notícia em 2 portais com URLs diferentes deixa de duplicar |
| **0.4** | Tornar `[PAUSA]`/`[PAUSA_CURTA]` acousticamente reais: dividir texto nos marcadores, gerar áudio por segmento, inserir silêncio (1,5s/0,5s) via ffmpeg | `scripts/generate_gemini_tts_multi.py:92` | Hoje as pausas são removidas do prompt e ignoradas — zero efeito |
| **0.5** | Remover `.continue-here.md` (existe mas AGENT_GUIDE diz removido); consolidar handoffs em `archive/handoffs/YYYY-MM-DD.md` | raiz do projeto, `AGENT_GUIDE.md` | Resolve divergência doc↔código |

**Verificação:** episódio de teste atinge 2.000+ palavras, 6 quadros; `BR-470` pronunciado corretamente; `grep -i pausa` no áudio não encontra texto lido.

---

## FASE 1 — Migrar IA não-TTS para Hermes Agent (Alto Impacto / Alto Esforço)

> **O coração do constraint "Gemini = apenas TTS".** Remove todos os usos não-TTS do Gemini.
> **Estimativa:** 3-4 sessões.

### 1.1 — Converter `ai_news_filter.py`

- **Manter** schemas Pydantic (`NewsItem`, `NewsAnalysis`) como **contrato de dados**.
- **Remover** bloco Gemini: imports `google.genai` (L19-20), `client = genai.Client()` (L84),
  chamada `generate_content` (L131-141).
- **Split em duas camadas:**
  - **Determinística (código):** scoring programático — relevância geográfica (keywords ponderadas),
    credibilidade via `tier`, recência, burst. Produz `NewsAnalysis` parcial com `quality_score` calculado.
  - **Editorial (Hermes Agent inline):** seleção final + sumarização + `key_points` ricos.
    Fluxo: `pipeline.py cmd_collect` escreve `episodes/_candidates-{date}.json` →
    Hermes lê, decide, escreve `raw-{date}.md` seguindo o contrato.
- `fallback_heuristic_filter` (L175) torna-se o fallback **offline** (sem agente, sem Gemini).

### 1.2 — Converter `generate_script.py`

- **Remover** bloco Gemini: imports (L17-18), `client` (L209), chamada (L211-219).
- **Manter** `parse_raw()`, `format_script()`, schema `RoteiroCompleto` — viram **renderer** puro
  de `roteiro-{date}.json` → `{date}.md`.
- Hermes Agent gera o `roteiro-{date}.json` seguindo `SKILL.md` seções 4-9 (já completo).
- Expor `generate_script.render_from_json(path)`.
- `cmd_process`: se `roteiro-{date}.json` não existir → **falha alto** com instrução clara.

### 1.3 — Atualizar documentação

- `ARCHITECTURE.md`: fluxo ponta-a-ponta reflete Hermes como motor não-TTS.
- `PRD.md`: requisitos funcionais 2-3 reescritos.
- `SKILL.md`: nota de execução pelo Hermes Agent.

### 1.4 — Auto-incremento de `episodio`

- Implementar numeração sequencial lendo `archive/index.md` (hoje sempre `null`).

**Verificação de aceitação:** `grep -rn "gemini-2.5-flash" scripts/` retorna **vazio**.

---

## FASE 2 — Pipeline de Aquisição Robusto (Alto Impacto / Alto Esforço)

> Endereça cada lacuna do briefing de aquisição. **Estimativa:** 4-5 sessões.

| ID | Item | Por quê é valioso | Como implementar | Impacto esperado |
|---|---|---|---|---|
| **2.1** | Scoring de credibilidade usando `tier` + `source_stats` | Hoje `tier` é ignorado; fontes confiáveis e não-confiáveis pesam igual | `credibility_score = f(tier, success_rate, frescura)` no scoring da Fase 1.1 | Seleção mais confiável; penaliza fontes instáveis |
| **2.2** | Clustering de eventos (TF-IDF cosine ou MinHash) | Mesma notícia em 2+ fontes hoje vira itens separados | Agrupar por similaridade título+resumo; cluster = versão mais completa + lista de fontes | Reduz duplicação percebida; base da correlação multi-fonte |
| **2.3** | Detecção de breaking-news + trend | Hoje recência é janela binária 48h, sem noção de urgência | Breaking: cluster em ≥3 fontes tier-1 em ≤6h OU termos de urgência. Trend: burst vs. média móvel 7d | Episódio reage a notícias em desenvolvimento |
| **2.4** | Conectar `x_collector.py` (hoje desconectado) | 1.273 linhas funcionais com métricas de engajamento não consumidas | Chamar `consume_x_tweets_for_pipeline()` em `cmd_collect`; likes/RT/views = sinal viral | Captura viral, complementa portais |
| **2.5** | Ranking de relevância local programático | Hoje `quality_score` é puramente LLM-judgado | `relevance = w1·geo + w2·credibilidade + w3·recência + w4·burst + w5·engajamento_x` com geo por dicionário ponderado | Seleção transparente, auditável, ajustável |
| **2.6** | Redução de risco de fake-news | Hoje não há validação cruzada | Cross-validation: item só entra se ≥1 fonte tier-1 OU ≥2 tier-2; flag single-source; regex anti-clickbait | Reduz desinformação; aumenta credibilidade editorial |

**Dicionário geo (proposta):** Blumenau=1.0 · Rio do Sul/Indaial/Pomerode/Gaspar=0.8 ·
Demais Alto Vale=0.7 · SC genérico=0.5 · Nacional-com-impacto-local=0.3 · Sem conexão=0.0.

---

## FASE 3 — Estratégia Nacional/Internacional (Alto Impacto / Baixo Esforço)

> ≥1 notícia nacional + ≥1 internacional por edição, sem ofuscar o local.
> **Decisão:** feeds RSS curados. **Estimativa:** 1-2 sessões.

### 3.1 — Adicionar feeds

- **Nacional (tier-1):** G1, Folha de S.Paulo, Estadão, Valor Econômico, CNN Brasil,
  BBC Brasil, Agência Brasil.
- **Internacional:** Reuters (World), AP News, BBC World.
- Novo campo `scope: "local" | "nacional" | "internacional"` em `sources.json`.

### 3.2 — Metodologia de ranking de impacto

```
impacto = w1·reach + w2·relevância_econômica_SC + w3·recência + w4·alinhamento_libertário
```

- **Cotas fixas:** exatamente 1 nacional + 1 internacional por edição (não mais, para não ofuscar).
- **Filtro de impacto local:** nacional só entra se tiver implicações para SC/Vale do Itajaí
  (ICMS, infraestrutura, política tributária federal) **ou** altíssimo alcance (presidencial, crise).
  Internacional só se altíssimo alcance (geopolítica, economia global, desastre).

### 3.3 — Novos quadros

Adicionar à sequência fixa (após quadros locais, antes de Rapidinhas):
- `### QUADRO: BRASIL` (≥1 nacional)
- `### QUADRO: MUNDO` (≥1 internacional)

Atualizar: `categories_map` (`pipeline.py:59-66`), `QUADROS` (`generate_script.py:58-65`),
`validate_episode` (`tts_preprocessor.py`), `episodes/TEMPLATE.md`, `SKILL.md` seção 4.

---

## FASE 4 — Roteiro Ideal para Audiência Brasileira (Médio Impacto / Baixo Esforço)

> Otimização de retenção e fluidez. **Estimativa:** 1 sessão.

### 4.1 — Estrutura-alvo do bulletin

1. **Cold open** — gancho de impacto (não "bem-vindo"), 1 fala Peter + 1 Ricardo, ≤30s.
2. **Manchetes** — 5-6 bullets, ritmo rápido.
3. **Breaking-news** (condicional) — se detectado na Fase 2.3, vem **antes** dos quadros fixos.
4. **Quadros locais** — Segurança → Saúde → Educação → Política → Esportes.
5. **Brasil** (1 notícia, concisa).
6. **Mundo** (1 notícia, concisa).
7. **Rapidinhas da Loucura Estatal** (opcional, alívio cômico).
8. **Fechamento** — provocação Peter + reflexão/CTA Ricardo.

### 4.2 — Regras de retenção

- **Anti-repetição de transições:** manter histórico em `archive/transitions-used.json`;
  nenhuma transição repetida em episódios consecutivos.
- **Adaptação de duração:** loop de self-check — se >2.500 palavras, enxugar quadros menos
  relevantes; se <2.000, expandir o quadro de maior impacto.
- **Priorização:** quadros com breaking-news ou score mais alto vêm primeiro nos locais.

---

## FASE 5 — Qualidade de Áudio/TTS Avançada (Alto Impacto / Médio Esforço)

> Naturalidade, pronúncia correta, prosódia. **Estimativa:** 2-3 sessões.

| ID | Item | Detalhe |
|---|---|---|
| **5.1** | Normalização robusta via `num2words` pt-BR | Números, datas, anos, horas, moeda (`R$ 70 milhões`→"setenta milhões de reais"), %. Substitui o dict estático de ~40 entradas. |
| **5.2** | Lexicon de pronúncia local | `sources/pronunciation_lexicon.json`: Blumenau, Rua XV de Novembro, BR-470, Vale do Itajaí, Pomerode, Indaial, Rio do Sul, Gaspar, Alesc, Furb, Celesc, Casan. Rewriting fonético onde o TTS errar. |
| **5.3** | Prosódia e ênfase | Investigar SSML/`<prosody>`/`<emphasis>` no `gemini-3.1-flash-tts-preview`. Se suportado, marcar números-chave e nomes próprios. Senão, reforçar `SPEAKER_PERSONAS`. |
| **5.4** | Loudnorm 2-pass EBU R128 | Primeiro pass mede (`print_format=json`), segundo aplica linear. Resample 24kHz→44.1kHz. |
| **5.5** | Chunking real | Implementar `CHUNK_TARGET_WORDS=300` (hoje morto): gerar por chunk, concatenar com crossfades, retomar só chunks falhados. |

---

## FASE 6 — Escalabilidade Multi-Cidade/Estado/País (Alto Impacto / Alto Esforço)

> Preparação para expansão geográfica. **Estimativa:** 5+ sessões. Ver `TARGET_ARCHITECTURE.md`.

| ID | Item |
|---|---|
| **6.1** | Multi-agente: Editor Regional (por cidade) + Editor Nacional/Intl (compartilhado) + Orquestrador Hermes + TTS Worker isolado |
| **6.2** | Segmentação geo: `config/regions/{region}.yaml` (fontes, termos X, lexicon, pesos). Hoje: `blumenau-vale-itajai.yaml` |
| **6.3** | Agregação replicável: nova cidade = novo YAML, zero código |
| **6.4** | Esboço de personalização futura (`listeners/`, recomendação por similaridade) |
| **6.5** | Observabilidade: `reports/daily-{date}.json` (técnicas, editoriais, áudio) |
| **6.6** | Fault-tolerance: dead-letter de fontes crônicas, checkpointing por etapa, idempotência por data |

---

## Ordem de Execução (dependências)

```
Fase 0 (quick wins)        ← independente, fazer primeiro
   ↓
Fase 1 (Gemini→Hermes)     ← pré-requisito para tudo
   ↓
Fase 2 (pipeline robusto)  ← usa contrato da Fase 1
   ↓ (paralelo)
Fase 3 (nacional/intl)     ←  Fase 4 (roteiro ideal)
   ↓
Fase 5 (áudio avançado)
   ↓
Fase 6 (escalabilidade)
```

- **Fase 0** pode iniciar imediatamente e é independente.
- **Fases 3 e 4** podem rodar em paralelo após a Fase 1.
- **Fase 5** beneficia-se da Fase 4 (estrutura de bulletin definida).
- **Fase 6** é incremental e pode ser parcialmente entregue (ex.: só observabilidade 6.5 primeiro).

---

## Confirmações `⚠️ A confirmar com Osmar` endereçadas

| Pendência | Decisão no roadmap |
|---|---|
| `episodio` sempre `null` | Auto-incremento na **Fase 1.4** |
| Custo por episódio em USD | Telemetria na **Fase 6.5** |
| Analytics de plays/retenção | Painel na **Fase 6.5** |
| Deploy do `public/` (auto ou manual) | Documentar em `ARCHITECTURE.md` |
| `x_collector.py` recriar ou legado | **Conectar** na **Fase 2.4** (é código vivo pronto) |
| `.continue-here.md` divergente | Remover na **Fase 0.5** |

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-20*
