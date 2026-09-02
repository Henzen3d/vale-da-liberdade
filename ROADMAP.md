# ROADMAP — Plano de Melhorias Priorizado

> ⚠️ **DOCUMENTO HISTÓRICO / ARQUIVO**: Este documento reflete o estado em Junho/Agosto de 2026.
> Para especificações ativas e regras de produção, consulte `CANONICAL.md` e `docs/INDEX.md`.

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

## FASE 7 — Portal Web Dinâmico / Gerador Estático Automático (CONCLUÍDA ✅)

> Transformar o `public/index.html` (hoje manual e estático com 2 episódios hardcoded) em
> um portal web gerado automaticamente a cada publicação, com player customizado, transcrição
> estilizada e painel de estatísticas.
> **Estimativa:** 3-4 sessões.

| ID | Item | Detalhe | Arquivos |
|---|---|---|---|
| **7.1** | Script gerador estático (`build_site.py`) | Script Python que lê `archive/index.md`, os metadados dos episódios (`*-metadata.json`), o roteiro finalizado (`{date}.md`) e o áudio (`{date}-vale-da-liberdade.mp3`) para reconstruir `public/index.html` e `public/styles.css` a cada run do pipeline. Integrar como etapa 5/5 em `cmd_full` após `cmd_update_archive`. | `[NEW] scripts/build_site.py`, `scripts/pipeline.py` |
| **7.2** | Player de áudio customizado | Player HTML/JS embutido no portal com: barra de progresso estilizada, botão play/pause com animação, indicador de duração, velocidade de reprodução (1x/1.5x/2x). Design premium dark-mode com gradiente inspirado nas cores do projeto (`--primary: #cc785c`). Carrega automaticamente o MP3 do episódio mais recente. | `public/index.html`, `public/styles.css` |
| **7.3** | Transcrição dinâmica estilizada | Área expansível (accordion) abaixo do player onde o ouvinte pode ler o roteiro. Falas de **Peter** estilizadas com borda lateral laranja/coral e ícone de microfone. Falas de **Ricardo** com borda lateral azul-acinzentado e ícone de gráfico. Citações famosas das personas (`SKILL.md` seção 5) exibidas em destaque com tipografia serif. Parser de markdown para HTML embutido no `build_site.py`. | `scripts/build_site.py`, `public/index.html` |
| **7.4** | Seção "Fontes do Dia" | Bloco visual com ícones/favicons dos portais de onde as notícias daquele episódio foram coletadas (dados do `*-metadata.json` campo `sources_used`). Links diretos para os portais originais. Aumenta transparência editorial e credibilidade. | `scripts/build_site.py`, `public/index.html` |
| **7.5** | Dashboard de estatísticas divertido | Painel acumulativo com métricas extraídas dos metadados históricos: (a) "Impostômetro de Críticas" — contagem de vezes que Peter mencionou termos como "imposto", "roubo", "Estado" nos roteiros; (b) "Taxa de Contrapesos" — média de interrupções pragmáticas de Ricardo por episódio; (c) Gráfico de barras simples (CSS puro) com a distribuição de notícias por quadro ao longo da semana. Dados pré-calculados pelo `build_site.py` e embutidos como JSON inline no HTML. | `scripts/build_site.py`, `public/index.html`, `public/styles.css` |
| **7.6** | Arquivo de episódios anteriores | Página de listagem paginada (10 por página, JS client-side) com todos os episódios publicados. Cada card exibe: data, número do episódio, duração, contagem de quadros, mini-player e link para transcrição. Gerado a partir do `archive/index.md` + metadados. | `scripts/build_site.py`, `public/index.html` |

**Plano de execução detalhado:**

1. Criar `scripts/build_site.py` com funções: `load_all_episodes()` (lê index.md + metadados), `parse_roteiro_to_html()` (converte markdown de falas em HTML estilizado), `build_stats_dashboard()` (calcula métricas acumuladas), `render_html()` (template string com todo o HTML/CSS/JS embutido).
2. Criar template HTML base com design premium (dark hero, gradientes, glassmorphism nos cards, Google Fonts Inter/Cormorant Garamond).
3. Implementar player de áudio customizado em JS vanilla (~80 linhas).
4. Implementar accordion de transcrição com parser de falas `Peter:/Ricardo:` → HTML estilizado.
5. Integrar `build_site.py` em `pipeline.py cmd_full` como etapa final.
6. Testar com episódios existentes do `archive/`.

**Verificação:** `public/index.html` regenerado automaticamente após `pipeline.py full`; player toca o MP3; transcrição exibe falas coloridas; estatísticas calculadas corretamente.

---

## FASE 8 — Feed RSS de Podcast Automatizado (Alto Impacto / Baixo Esforço)

> Gerar automaticamente um arquivo XML compatível com o padrão de podcasts (RSS 2.0 +
> namespace iTunes/Podcast) para distribuição em Spotify, Apple Podcasts, Google Podcasts,
> Deezer e demais agregadores.
> **Estimativa:** 1-2 sessões.

| ID | Item | Detalhe | Arquivos |
|---|---|---|---|
| **8.1** | Script gerador de feed (`generate_podcast_rss.py`) | Lê `archive/index.md` para listar episódios publicados. Para cada data, carrega `episodes/{date}-metadata.json` (título, duração, quadros, contagem de palavras) e verifica existência de `audio/{date}-vale-da-liberdade.mp3`. Gera `public/podcast.xml` no formato RSS 2.0 com extensões `itunes:` e `podcast:`. | `[NEW] scripts/generate_podcast_rss.py` |
| **8.2** | Metadados do canal | Configuração centralizada em `sources/podcast_config.json`: título do podcast, descrição, autor, e-mail, categoria iTunes (News > Daily News), idioma (pt-BR), URL base para assets (configurável para Cloudflare Tunnel), caminho do artwork. | `[NEW] sources/podcast_config.json` |
| **8.3** | Artwork do podcast | Imagem 3000×3000px PNG para o feed iTunes. Design: logotipo "Vale da Liberdade" com silhueta estilizada de Blumenau (casas enxaimel + montanhas), paleta coral/dark do `styles.css`. Gerar via ferramenta de imagem ou contratar designer. | `[NEW] public/artwork.png` |
| **8.4** | Descrição automática por episódio | Para cada `<item>` do feed, gerar `<description>` a partir das manchetes do `*-metadata.json` campo `quadros_gerados` + manchetes do roteiro. Formato: "Nesta edição: [manchete 1]; [manchete 2]; [manchete 3]... Apresentado por Peter Albuquerque e Ricardo Souto." | `scripts/generate_podcast_rss.py` |
| **8.5** | Integração no pipeline | Chamar `generate_podcast_rss.py` como última etapa de `cmd_full` (após `build_site.py` da Fase 7, ou independentemente). O feed deve ser idempotente (re-executar não duplica episódios). | `scripts/pipeline.py` |
| **8.6** | Validação do feed | Testar o XML gerado contra validadores: (a) `feedvalidator.org`, (b) schema RSS 2.0, (c) submissão teste ao Spotify for Podcasters e Apple Podcasts Connect. Documentar o processo em `LESSONS_LEARNED.md`. | Manual + `scripts/validate_feeds.py` (reutilizar lógica) |

**Plano de execução detalhado:**

1. Criar `sources/podcast_config.json` com metadados fixos do canal (título, autor, categoria, URL base).
2. Implementar `scripts/generate_podcast_rss.py`:
   - Função `load_episodes()`: lê `archive/index.md`, para cada data carrega metadados JSON e verifica existência do MP3.
   - Função `build_item_xml(date, metadata, base_url)`: gera bloco `<item>` com `<enclosure>` (URL do MP3, tamanho em bytes, type audio/mpeg), `<itunes:duration>`, `<pubDate>` (RFC 2822), `<description>`.
   - Função `build_feed_xml(config, items)`: monta o XML completo com `<channel>`, namespaces iTunes/Podcast, `<itunes:image>`, `<itunes:category>`.
   - Saída: `public/podcast.xml`.
3. Gerar artwork placeholder (pode usar `generate_image` ou criar SVG estilizado).
4. Integrar em `pipeline.py cmd_full` como etapa final.
5. Validar XML com parser XML e testar submissão em Spotify for Podcasters.

**Verificação:** `public/podcast.xml` gerado com todos os episódios do `archive/index.md`; XML válido contra schema RSS 2.0; cada `<enclosure>` aponta para MP3 existente; Spotify aceita o feed.

---

## FASE 9 — Engine TTS Híbrida Local com Kokoro (Alto Impacto / Médio Esforço)

> Implementar um módulo alternativo de síntese de voz usando os modelos ONNX locais
> já presentes no projeto (`kokoro-v1.0.onnx`, `pt_BR-faber-medium.onnx`) para funcionar
> como fallback de luxo quando o Gemini TTS estiver indisponível ou a cota diária expirar,
> e como engine de custo zero para testes e iterações rápidas.
> **Estimativa:** 3-4 sessões.

| ID | Item | Detalhe | Arquivos |
|---|---|---|---|
| **9.1** | Módulo TTS local (`generate_kokoro_tts.py`) | Script Python que carrega os modelos ONNX via `onnxruntime`, aceita texto pré-processado (mesma entrada do `generate_gemini_tts_multi.py`) e gera áudio WAV mono 44.1kHz. Interface compatível com a do módulo Gemini TTS (mesmos argumentos CLI: `--episode`, `--out`, `--speakers`). | `[NEW] scripts/generate_kokoro_tts.py` |
| **9.2** | Mapeamento de vozes locais | Mapear as vozes disponíveis nos modelos ONNX para as personas: Peter → voz masculina grave (faber-medium, pitch baixo), Ricardo → voz masculina média (faber-medium, pitch padrão). Investigar se o Kokoro suporta parâmetros de pitch/velocidade via ONNX runtime. Se não, aplicar pós-processamento ffmpeg (pitch shift + tempo). | `scripts/generate_kokoro_tts.py` |
| **9.3** | Diferenciação de locutores por processamento | Já que modelos locais geralmente oferecem uma única voz, implementar diferenciação via ffmpeg: (a) Peter: pitch -2 semitons, velocidade 1.05x, leve distorção warm; (b) Ricardo: pitch padrão, velocidade 0.95x, EQ mais limpo. Aplicar por segmento de fala (split no `Peter:/Ricardo:` como o Gemini TTS já faz). | `scripts/generate_kokoro_tts.py` |
| **9.4** | Modo híbrido inteligente no pipeline | Flag `--tts-engine` em `pipeline.py cmd_audio` com valores: `gemini` (padrão), `kokoro` (local), `hybrid` (tenta Gemini, fallback Kokoro). No modo `hybrid`, se o `GeminiClient` levantar `RuntimeError` por RPD exaurido ou se 3 chunks falharem consecutivamente, chavear automaticamente para Kokoro no restante do episódio. | `scripts/pipeline.py`, `scripts/generate_gemini_tts_multi.py` |
| **9.5** | Benchmark comparativo | Script de benchmark que gera o mesmo trecho de 500 palavras com Gemini TTS e Kokoro TTS, comparando: tempo de geração, tamanho do arquivo, e salvando ambos para avaliação auditiva manual. Resultados em `reports/tts-benchmark-{date}.json`. | `[NEW] scripts/benchmark_tts.py` |
| **9.6** | Documentação e dependências | Adicionar `onnxruntime` ao `requirements.txt`. Documentar em `ARCHITECTURE.md` a engine híbrida e o fluxo de fallback. Criar seção em `LESSONS_LEARNED.md` com notas sobre qualidade das vozes locais vs. Gemini. | `requirements.txt`, `ARCHITECTURE.md`, `LESSONS_LEARNED.md` |

**Plano de execução detalhado:**

1. Investigar a estrutura dos modelos ONNX existentes (`kokoro-v1.0.onnx`, `pt_BR-faber-medium.onnx`, `kokoro_work/`):
   - Verificar inputs/outputs do modelo com `onnxruntime`.
   - Identificar se é modelo de vocoder (mel-spectrogram → waveform) ou end-to-end (text → waveform).
   - Se for Piper TTS (provável pelo nome `faber-medium`), usar a biblioteca `piper-tts` para inferência.
2. Implementar `scripts/generate_kokoro_tts.py`:
   - Função `load_model(model_path)`: carrega ONNX e inicializa sessão.
   - Função `synthesize(text, model, rate, pitch)`: gera PCM raw.
   - Função `split_by_speaker(text)`: divide por `Peter:/Ricardo:`, sintetiza cada segmento com parâmetros de voz distintos.
   - Função `apply_voice_character(pcm, speaker)`: pós-processamento ffmpeg para diferenciar vozes.
   - CLI compatível com `generate_gemini_tts_multi.py`.
3. Integrar modo `--tts-engine hybrid` em `pipeline.py`.
4. Criar benchmark e rodar comparação.
5. Documentar resultados e trade-offs.

**Verificação:** `pipeline.py audio --date YYYY-MM-DD --tts-engine kokoro` gera MP3 completo sem chamadas à API; modo `hybrid` chaveia automaticamente quando Gemini falha; benchmark registra tempos e tamanhos.

---

## FASE 10 — Chat Interativo com Personas na Web (Médio Impacto / Alto Esforço)

> Widget de chat inteligente no portal web onde o ouvinte pode digitar um tema ou colar
> um link de notícia e ver Peter e Ricardo debaterem sob demanda em tempo real, seguindo
> exatamente as personas definidas em `SKILL.md` seção 5 e as regras de tom da seção 6.
> **Estimativa:** 4-5 sessões.

| ID | Item | Descrição | Responsável | Status |
|----|------|-----------|-------------|--------|
| **10.0** | **Integração Defuddle** | Usar defuddle como fallback na coleta de notícias quando RSS/BeautifulSoup falharem. Remove menus, ads, footers automaticamente. Ver `TODO-defuddle-integration.md`. | Hermes Agent | `pending` |
| **10.1** | Backend de chat (`chat_api.py`) | Servidor HTTP leve (Flask ou FastAPI) que recebe um tema/URL via POST, constrói prompt com as personas de `SKILL.md` seção 5 e as regras de tom da seção 6, chama o `GeminiClient` (`gemini-3.5-flash`) e retorna o debate formatado como JSON (`[{speaker, texto}, ...]`). Rate limiting por IP (máx. 5 requisições/minuto por visitante) para proteger a cota da API. | `[NEW] scripts/chat_api.py` | `planned` |
| **10.2** | Extração de contexto de URLs | Quando o usuário colar um link, o backend faz scraping leve (requests + BeautifulSoup, já disponíveis no projeto) para extrair título e primeiros 3 parágrafos da notícia. Esse contexto é injetado no prompt para que Peter e Ricardo debatam com dados reais da matéria. Fallback: se scraping falhar, usar apenas o título da URL. | `scripts/chat_api.py` |
| **10.3** | Widget de chat frontend | Componente JS/CSS no rodapé do portal: botão flutuante "💬 Debata com Peter e Ricardo" que expande um painel de chat. Design dark glassmorphism com bolhas de chat estilizadas por persona (Peter: coral, Ricardo: azul-cinza). Animação de digitação ("...") enquanto aguarda resposta. Histórico local (sessionStorage, máx. 10 trocas). | `public/index.html`, `public/styles.css` |
| **10.4** | Prompt engineering para debate sob demanda | Template de prompt específico para o chat (diferente do prompt de roteiro): deve gerar exatamente 4-6 falas curtas (máx. 50 palavras cada), alternando Peter e Ricardo, com tensão dialética genuína. Inclui instruções para conectar o tema à realidade de Blumenau/Vale do Itajaí sempre que possível. Anti-guardrails: proibir respostas genéricas, exigir dados concretos ou analogias locais. | `[NEW] sources/chat_prompt_template.txt` |
| **10.5** | Opção TTS no chat ("Ouvir debate") | Botão opcional no widget que sintetiza as falas do debate via Gemini TTS (reutilizando `generate_with_retry` do `generate_gemini_tts_multi.py`) e toca o áudio inline no browser. Respeita os limites de cota via `GeminiClient`. Se cota exaurida, desabilitar botão com tooltip explicativo. | `scripts/chat_api.py`, `public/index.html` |
| **10.6** | Deploy e segurança | Configurar CORS restrito ao domínio do portal. Implementar rate limiting por IP com janela deslizante. Sanitizar input do usuário (strip HTML, limitar a 500 caracteres). Não expor a `GEMINI_API_KEY` no frontend — todas as chamadas passam pelo backend. Documentar deployment via systemd/PM2 + Cloudflare Tunnel. | `scripts/chat_api.py`, `ARCHITECTURE.md` |

**Plano de execução detalhado:**

1. Criar `scripts/chat_api.py` com FastAPI (ou Flask):
   - Endpoint `POST /api/chat` recebe `{"topic": "..."}` ou `{"url": "..."}`, retorna `{"debate": [{"speaker": "Peter", "texto": "..."}, ...]}`.
   - Carregar personas de `SKILL.md` seções 5-6 em constantes Python.
   - Integrar com `GeminiClient` para chamada de geração.
   - Rate limiter: dict in-memory `{ip: [timestamps]}`, máx 5/min.
2. Criar `sources/chat_prompt_template.txt` com template Jinja2-like:
   - Placeholders: `{topic}`, `{context}` (conteúdo da URL se fornecida).
   - Regras: máx 6 falas, alternância obrigatória, conexão local, sem concordância fácil.
3. Implementar widget frontend:
   - HTML: `<div id="chatWidget">` com botão flutuante, painel expansível, área de mensagens, input.
   - CSS: glassmorphism, bolhas coloridas por persona, animação de typing.
   - JS: `fetch('/api/chat', ...)`, renderização de bolhas, sessionStorage.
4. Implementar extração de contexto de URLs (requests + BS4).
5. Testes manuais com 10 temas variados.
6. Deploy documentation.

**Verificação:** Widget funciona no portal; digitar "IPTU Blumenau" gera debate com dados locais; colar link de notícia extrai contexto e debate o conteúdo; rate limiting bloqueia após 5 requisições rápidas; nenhuma chave de API exposta no frontend.

---

## FASE 12 — Fontes Alternativas e Expansão de Conteúdo (Baixo Impacto / Médio Esforço)

> Quando o serviço crescer, adicionar novas fontes de conteúdo para diversificar e enriquecer os episódios.
> **Estimativa:** 2-3 sessões por feature.

| ID | Item | Descrição | Responsável | Status |
|----|------|-----------|-------------|--------|
| **12.1** | **Integração YouTube** | Usar vídeos do YouTube como fonte de conteúdo. Extrair transcrições, pesquisar vídeos sobre temas locais, gerar episódios a partir de conteúdo audiovisual. Ver `TODO-youtube-integration.md`. | Hermes Agent | `pending` |
| **12.2** | Fontes internacionais | Adicionar cobertura de notícias internacionais com enfoque no impacto para a região (imigração, comércio exterior, turismo). | `scripts/news_collector.py` | `idea` |

> Incorporar elementos de rádio profissional: música de abertura, vinhetas de transição 
> entre quadros ("E agora, os esportes..."), trilha de fundo sutil (bed) e inserção
> dinâmica de anúncios em áudio pré-gravados (slots de monetização).
> **Estimativa:** 2-3 sessões.

| ID | Item | Detalhe | Arquivos |
|---|---|---|---|
| **11.1** | Banco de assets em áudio (`assets/audio/`) | Diretório para armazenar arquivos estáticos (WAV/MP3 a 44.1kHz): `intro.mp3`, `outro.mp3`, `transicao_esportes.mp3`, `transicao_mundo.mp3`, `transicao_policial.mp3`. | `[NEW] assets/audio/` |
| **11.2** | Script de montagem final (`generate_audio_mix.py`) | Script Python usando `ffmpeg-python` ou `pydub` que recebe os arquivos de fala gerados pelo TTS e os costura junto com as vinhetas. Fluxograma: Intro -> Fala Abertura -> Transição -> Falas Quadro 1 -> Ad Slot -> Falas Quadro 2 -> Outro. Substitui a simples concatenação atual. | `[NEW] scripts/generate_audio_mix.py`, `scripts/pipeline.py` |
| **11.3** | Motor de inserção de anúncios (Ad Insertion) | Lógica para gerenciar blocos comerciais: ler `sources/ads_config.json` para definir se haverá anúncio no episódio atual e selecionar o arquivo `ad_campanha_x.mp3`. Inserir o anúncio estrategicamente no meio do episódio (ex: após o quadro "Mundo" ou "Segurança"). | `[NEW] sources/ads_config.json`, `scripts/generate_audio_mix.py` |
| **11.4** | Trilha de fundo (Bed Track) | Opção para colocar uma cama musical ambiente (low volume) atrás das falas do TTS, usando a funcionalidade de mixagem do `ffmpeg` (`amix`). A trilha faz fade-out rápido nas transições e retorna suavemente. Dá ritmo e evita silêncios mortos. | `scripts/generate_audio_mix.py` |
| **11.5** | Configuração do Roteiro | Atualizar o `generate_script.py` para prever tags de marcação que o motor de áudio possa ler. Ex: `[TRANSICAO: ESPORTES]`, `[AD_SLOT]`. O Hermes pode ser instruído a posicionar o ad_slot num momento de cliffhanger. | `scripts/generate_script.py`, `SKILL.md` |
| **11.6** | Normalização Global (Loudness) | Garantir que o áudio final misturado (voz + vinhetas + música) passe pelo filtro EBU R128 para que a música não encubra a voz (-16 LUFS para podcast ou -14 LUFS). | `scripts/generate_audio_mix.py` |

**Plano de execução detalhado:**

1. Definir e obter os assets (baixar músicas/efeitos sem royalties).
2. Criar `scripts/generate_audio_mix.py` usando `pydub` (mais fácil para edição timeline) ou comandos avançados de `ffmpeg`.
   - Função `assemble_episode(tts_files_dict, assets_dir)`: recebe a lista de áudios TTS por quadro.
   - Concatena: `intro.mp3` + TTS(Abertura) + `transicao_1.mp3` + TTS(Quadro1) + ... + `outro.mp3`.
3. Adicionar lógica de Ducking (baixar o volume da trilha quando a voz fala).
4. Substituir a etapa de `concat_files` do atual `generate_gemini_tts_multi.py` pelo novo script.
5. Adicionar configuração de anúncios.
6. Testar audição completa do mix.

**Verificação:** Arquivo MP3 final contém abertura musical, vinhetas nítidas antes dos quadros corretos, trilha de fundo sutil não atrapalhando a fala, e somatório total normalizado.

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
   ↓ (paralelo, independentes entre si)
Fase 7 (portal web)  ←  Fase 8 (podcast RSS)  ←  Fase 9 (TTS local)
                                                       ↓
                                                  Fase 10 (chat)
                                                       ↓
                                                  Fase 11 (sonoplastia e ads)
```

- **Fase 0** pode iniciar imediatamente e é independente.
- **Fases 3 e 4** podem rodar em paralelo após a Fase 1.
- **Fase 5** beneficia-se da Fase 4 (estrutura de bulletin definida).
- **Fase 6** é incremental e pode ser parcialmente entregue (ex.: só observabilidade 6.5 primeiro).
- **Fases 7 e 8** podem rodar em paralelo após Fase 5 (precisam de áudio e metadados estáveis).
- **Fase 9** é independente — pode iniciar a qualquer momento após Fase 5 (precisa do pipeline TTS estável).
- **Fase 10** depende da Fase 7 (portal web precisa existir) e beneficia-se da Fase 9 (TTS local para o botão "Ouvir").
- **Fase 11** pode iniciar após a Fase 5 (TTS), atuando como um refinamento na etapa final da geração do MP3.

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
*Mantido por: Hermes Agent | Última atualização: 2026-06-24*
