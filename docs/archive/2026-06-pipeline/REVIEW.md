<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# REVIEW — Avaliação Técnica e de Produto

> Avaliação da arquitetura atual do **Web Jornal Vale da Liberdade** com base em
> auditoria de código (leitura linha-a-linha de `scripts/`, `sources/`, `episodes/`,
> `presenters/` e documentos de produto). Foco: aderência ao constraint
> "Gemini = apenas TTS" e qualidade da pipeline ponta-a-ponta.
>
> **Locale:** pt-BR | **Data da auditoria:** 2026-06-20 | **Mantém:** Hermes Agent

---

## Sumário executivo

O projeto tem uma base funcional sólida (coleta de 14 fontes, filtro, roteiro, TTS
multi-locutor, validação, publicação) e entrega episódios diários. No entanto, há
**três problemas estruturais** que comprometem o alinhamento com a estratégia declarada:

1. **Violação do constraint de arquitetura** — Gemini (`gemini-2.5-flash`) é usado para
   filtragem, ranking, sumarização e geração de roteiro, quando deveria ser usado
   **exclusivamente** para TTS.
2. **Regressão silenciosa de qualidade** — o episódio `2026-06-20` saiu por um caminho
   boilerplate (`_fill_roteiro_from_raw`) que produz um roteiro de 430 palavras (alvo:
   2.000-2.500) com apenas 3 quadros, **reprovando o próprio checklist de validação**.
3. **Lacunas de pipeline** que reduzem a densidade editorial — sem dedup semântica real,
   sem clustering de eventos, sem detecção de breaking-news, sem cobertura
   nacional/internacional, e o `x_collector.py` (1.273 linhas, funcional) está
   completamente desconectado.

O roteiro de correção completo está em `ROADMAP.md` e a arquitetura-alvo em
`TARGET_ARCHITECTURE.md`.

---

## 1. Forças (Strengths)

| Força | Evidência |
|---|---|
| **Coleta automatizada e resiliente** | `news_collector.py` cobre 14 fontes locais via RSS + fallback WordPress API + scraping + Playwright, com dedup por URL e cache TTL de 7 dias. `cache.json` registra `success_count` e `avg_items_per_fetch` por fonte. |
| **Fallbacks em camadas** | Cada estágio tem degradação graciosa: RSS→scraping→Playwright; Gemini→heurística por keyword; ffmpeg ausente→mantém WAV; Playwright ausente→HTTP scraping. |
| **Schema estruturado Pydantic** | `NewsItem`/`NewsAnalysis` (`ai_news_filter.py:42-62`) e `RoteiroCompleto` (`generate_script.py:72-76`) garantem contrato de dados estável entre etapas — base excelente para a migração. |
| **TTS multi-locutor funcional** | `generate_gemini_tts_multi.py` mapeia corretamente Peter→Charon / Ricardo→Schedar via `gemini-3.1-flash-tts-preview` com `multi_speaker_voice_config`, retry com backoff exponencial (3 tentativas) e cadeia ffmpeg (highpass→compressor→EQ→loudnorm). |
| **Preprocessor determinístico maduro** | `tts_preprocessor.py` normaliza ~40 siglas/símbolos, insere marcadores de pausa, extrai manchetes, valida checklist e gera metadados — toda a lógica não-AI está bem isolada e testável. |
| **Documentação viva** | `ARCHITECTURE.md`, `PRD.md`, `SKILL.md`, `AGENT_GUIDE.md`, `LESSONS_LEARNED.md` formam um conjunto coerente com convenção clara de quando atualizar cada um. |
| **Persona editorial rica** | `SKILL.md` seções 5-6 + `presenters/peter.md` / `ricardo.md` definem Peter/Ricardo com crenças, frases características, referências intelectuais — material pronto para qualquer motor de geração. |
| **Observabilidade básica** | `cache.json` rastreia estatísticas por fonte; `metadata.json` por episódio; logs diários em `logs/`. |

---

## 2. Fraquezas (Weaknesses)

### 2.1 Constraint "Gemini = apenas TTS" violado (crítico)

Dois usos não-TTS ativos em `gemini-2.5-flash`:

| Arquivo | Linha | Função | Responsabilidade indevidamente delegada ao Gemini |
|---|---|---|---|
| `scripts/ai_news_filter.py` | `133-141` | `filter_and_categorize_news` | **Filtro**, **categorização** em 6 quadros, **ranking** (quality_score 1-5), **sumarização** (resumo + key_points) |
| `scripts/generate_script.py` | `211-219` | `generate_script` | **Geração de roteiro editorial** com personas Peter/Ricardo, decisão de lineup, tom dialético |

Ambos usam `generate_content` com `response_schema` Pydantic e temperature baixa (0.2 / 0.4).
O TTS (`generate_gemini_tts_multi.py`, modelo `gemini-3.1-flash-tts-preview`,
`response_modalities=["AUDIO"]`) está **correto** e dentro do constraint.

**Impacto:** concentra dependência externa e custo num único provedor para funções que o
Hermes Agent deveria executar; impede auditoria/controle do raciocínio editorial.

### 2.2 Regressão de qualidade em produção (crítico)

O episódio `2026-06-20` foi gerado pelo caminho boilerplate `_fill_roteiro_from_raw`
(`pipeline.py:342-422`) — **não** pelo `generate_script`:

- `episodes/2026-06-20.md`: 430 palavras, apenas 3 quadros (SEGURANÇA, SAÚDE, POLÍTICA).
- `episodes/2026-06-20-metadata.json`: `duracao_estimada_min: 2.9`, `palavras_total: 430`
  (alvo: 2.000-2.500 palavras / ~15 min).
- Intro genérica hardcoded (`pipeline.py:379-380`): *"Olá, ouvinte. Bem-vindo..."*
- Falta EDUCAÇÃO, ESPORTES, RAPIDINHAS, e **zero** viés libertário (o diferencial do produto).
- `validate_episode` sinaliza: *"Quadro obrigatório ausente: Educação"*, *"Esportes"*,
  *"Roteiro curto"*, *"Poucas referências ao viés libertário"*.

**Causa-raiz:** `cmd_process` (`pipeline.py:442-452`) tenta `generate_script`, mas em falha
apenas *"mantém o roteiro existente/template"* — e o template já havia sido preenchido pelo
`_fill_roteiro_from_raw` num fluxo anterior, mascarando a falha. O pipeline **não falha alto**.

### 2.3 Dedup semântica é scaffolding morto

`cache.json` tem `content_hashes: {}` — **sempre vazio**. A dedup é puramente por URL exata
(`news_collector.py:442-454`). Consequências:

- A mesma notícia em 2 portais com URLs diferentes entra duas vezes.
- URLs coletadas-mas-descartadas pelo filtro **não** são cacheadas (o cache só grava itens
  selecionados em `add_selected_to_cache`, `pipeline.py:115-123`), então re-aparecem no run seguinte.

### 2.4 Sem clustering / correlação multi-fonte

`grep -i "cluster|correla|similar|cosine|embedding|tfidf|minhash"` em `scripts/` → **zero matches**.
Cada notícia é pontuada independentemente. O incêndio na BR-470 coberto por 3 portais vira
3 itens separados, nunca mesclados.

### 2.5 Sem breaking-news / trend / viral

- `grep -i "breaking|urgente|trend|burst"` → **zero**.
- Recência é janela binária de 48h (`is_recent`, `news_collector.py:111`), sem score de velocidade.
- `x_collector.py` (1.273 linhas, coleta tweets com métricas de engajamento likes/RT/views
  via `_parse_metric` L751) está **desconectado** — `consume_x_tweets_for_pipeline()` (L1004)
  não tem nenhum caller. Sinais virais disponíveis mas não consumidos.

### 2.6 Credibilidade de fonte não ponderada

O campo `tier` em `sources.json` é definido no schema mas **nunca lido** por código algum
(`news_collector.py` e `ai_news_filter.py` ignoram-no). `source_stats` coleta confiabilidade
mas não alimenta seleção.

### 2.7 Zero cobertura nacional/internacional

Todos os 14 feeds são Blumenau/Alto Vale/SC. O prompt do filtro (`ai_news_filter.py:102`)
**instrui o Gemini a rejeitar** notícias puramente nacionais/internacionais. A estratégia
editorial (≥1 nacional + ≥1 internacional por edição) é **impossível** com a configuração atual.

### 2.8 Defeitos de áudio/TTS

| Defeito | Local | Impacto |
|---|---|---|
| `[PAUSA]`/`[PAUSA_CURTA]` removidos do prompt e explicitamente ignorados | `generate_gemini_tts_multi.py:92` (`re.sub`) + prompt "IGNORE completamente" | **Zero efeito acústico** — as pausas são documentação only |
| Regra `\bBR\b → "B-R"` corrompe rodovias | `tts_preprocessor.py:64,139` | `BR-470`→`B-R-470` (confirmado em `2026-06-20-tts.txt:6-7,16-17`) |
| Sem normalização numérica | `tts_preprocessor.py` | `104`, `2025`, `21h40` passam crus para o TTS |
| Gramática quebrada em moeda | `tts_preprocessor.py:117` | `R$ 70 milhões`→"reais 70 milhões" |
| Sem SSML/prosódia/ênfase | `generate_gemini_tts_multi.py` | Apenas hints textuais de persona no prompt |
| Loudnorm de passo único | `generate_gemini_tts_multi.py:117-138` | Sem EBU R128 de 2 passos (medido→linear) |
| Chunking morto | `generate_gemini_tts_multi.py:62` `CHUNK_TARGET_WORDS=300` | Episódio inteiro numa chamada; sem proteção a timeout |
| Resampling baixo | `-ar 24000` | 24kHz é abaixo do padrão de podcast (44.1/48kHz) |

### 2.9 Metadados hard-coded

`generate_metadata` (`tts_preprocessor.py:328-377`) fixa `noticias_com_continuidade: 0`,
`fontes_utilizadas: ["manus","grok","busca_web"]` e `arquivos_gerados` — independentemente
do input real. `episodio` é sempre `null`.

---

## 3. Gargalos (Bottlenecks)

| Gargalo | Onde | Consequência |
|---|---|---|
| **Chamada Gemini monolítica para roteiro** | `generate_script.py:211` | Episódio inteiro numa única chamada — se falhar após 3 retries, não há recuperação parcial; latência alta |
| **Coleta serial dentro de `cmd_collect`** | `pipeline.py:239-262` | Apesar de `ThreadPoolExecutor` no `collect_all_news`, a sequência coleta→filtro→formatação é bloqueante |
| **Pipeline sem checkpointing** | `cmd_full` (`pipeline.py:577-601`) | Se `audio` falha, refaz `process` inteiro; sem idempotência por data |
| **`TierDeduplicator` O(n)** | `x_collector.py:954-970` usa `list` membership | Lento em volume; deveria ser `set` |
| **Conteúdo truncado a 300 chars no filtro** | `ai_news_filter.py:93` | Perde contexto para sumarização rica |

---

## 4. Riscos (Risks)

| Risco | Severidade | Probabilidade | Mitigação |
|---|---|---|---|
| **Dependência crítica de Gemini para não-TTS** | Alto | Alta | Fase 1 do roadmap: migrar para Hermes Agent |
| **Episódios publicados que reproduzem validação** | Alto | Alta (já ocorreu em 2026-06-20) | Fase 0.1: falhar alto; `cmd_full` deve abortar se validação reprovar |
| **Custo de API não monitorado** | Médio | Alta | Telemetria por chamada (Fase 6.5) |
| **Fake-news de fonte única** | Médio | Média | Cross-validation ≥1 tier-1 OU ≥2 tier-2 (Fase 2.6) |
| **Rate-limit/bloqueio do X** | Médio | Já ocorreu (`.continue-here.md`) | Stealth + max_sessions_per_day já implementados; conectar com fallback gracioso |
| **Mudanças de layout dos portais quebram scraping** | Médio | Média-alta | Dead-letter de fontes crônicas (Fase 6.6) |
| **Divergência entre doc e código** | Baixo | Alta | `.continue-here.md` existe mas AGENT_GUIDE diz removido (Fase 0.5) |

---

## 5. Aderência por área (scorecard)

| Área | Estado | Lacuna principal |
|---|---|---|
| **Coleta regional** | 🟡 Bom | Sem clustering/dedup semântica |
| **Filtro & ranking** | 🔴 Não-conforme | Gemini não-TTS; sem score programático |
| **Geração de roteiro** | 🔴 Não-conforme + regressão | Gemini não-TTS; boilerplate bypassa |
| **TTS** | 🟢 Conforme (constraint) | Pausas inefetivas; pronúncia local; prosódia |
| **Validação** | 🟡 Existe mas não bloqueia | `cmd_full` avisa e segue |
| **Estratégia editorial nacional/intl** | 🔴 Ausente | 0 feeds; filtro ativamente rejeita |
| **Observabilidade** | 🟡 Básica | Sem custo/latência/qualidade consolidada |
| **Escalabilidade geo** | 🔴 Não-arquitetada | Hardcoded Blumenau |
| **Confiabilidade** | 🟡 Fallbacks parciais | Sem checkpointing/dead-letter |

Legenda: 🟢 adequado | 🟡 parcial | 🔴 crítico/não-conforme

---

## 6. Próximos passos

A correção destes achados está detalhada em:

- **`ROADMAP.md`** — priorização Impacto×Esforço das Fases 0-6
- **`TARGET_ARCHITECTURE.md`** — arquitetura-alvo multi-agente
- **`IMPLEMENTATION_EXAMPLES.md`** — exemplos práticos e recomendações estratégicas

A **Fase 0** (quick wins) e a **Fase 1** (migração Gemini→Hermes) entregam ~70% do valor
e devem ser executadas primeiro.

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-20 | Auditoria baseada em leitura de código*
