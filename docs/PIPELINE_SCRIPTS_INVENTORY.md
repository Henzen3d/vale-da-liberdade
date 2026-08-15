# Inventário de scripts — pesquisa e produção

**Gerado:** 2026-08-15  
**Repo:** `/home/osmar/web-jornal-vale-da-liberdade`  
**Público:** para um agente (Agy / Gemini) sugerir melhorias **sem reexplorar o disco**.  
**Método:** leitura do código atual + `crontab -l` + `~/.hermes/cron/jobs.json`. Nada abaixo é inferido de docs de junho sem confirmação no arquivo.

**Não é spec do site/player.** Player/UX = `public/` + skill `web-jornal-frontend`. Este arquivo cobre **pesquisa de notícias + pipelines de áudio/catálogo**.

---

## Como a produção realmente dispara hoje

Há **dois agendadores** (risco de corrida / duplicata):

### A) crontab do host (`crontab -l`, `CRON_TZ=America/Sao_Paulo`)

| Quando | Comando | Status |
|---|---|---|
| `0 6 * * *` | `scripts/cron-wrapper.sh` → `pipeline.py full --date $HOJE` | **ATIVO** — diário oficial |
| `0 5-23 * * *` | `scripts/bm_monitor.py` | **ATIVO** — enfileira lives/vídeos ANCAPSU |
| `10 5-23 * * *` | `scripts/bm_pipeline.py process-queue` | **ATIVO** — processa fila B&M |
| `0 9 * * 1` | `scripts/bm_persona_digest.py` | **ATIVO** — digest semanal de persona |

Python do host: `/home/osmar/.hermes/hermes-agent/venv/bin/python3`. Log diário: `logs/daily-YYYY-MM-DD.log`. B&M: `logs/bm-monitor.log`, `logs/bm-pipeline.log`, `logs/bm-persona.log`.

### B) Hermes cron (`~/.hermes/cron/jobs.json`)

| Job | Agenda | O que faz | Status |
|---|---|---|---|
| `web-jornal-vale-da-liberdade-daily` | `0 6 * * *` | Prompt de agente p/ rotina diária (além do bash cron) | **ATIVO** — **duplica** o 06:00 do host |
| `web-jornal-delivery-precheck` | `30 5 * * *` | `no_agent` → `delivery_health_check.sh` | **QUEBRADO** — wrapper aponta para `scripts/delivery_health_check.sh` **ausente** |
| `webjornal-scout-weekly` | `0 6 * * 1` | Prompt p/ “Agente Scout” | **QUEBRADO** — `scripts/scout.py` **não existe** |
| `web-jornal-brasil-mundo-hourly` | `30 * * * *` | `bm-hourly-pipeline.sh` → `bm_pipeline.py process-queue` | **ATIVO** — **segunda** passagem na fila (host já roda `:10`) |
| `web-jornal-bm-video-autopilot` | `45 * * * *` | `scripts/bm_video_autopilot.py --days 1 --max 1` | **DESLIGADO** (`enabled: false`) e script **ausente** |
| `web-jornal-perf-monitor-semanal` | `0 12 * * 0` | Lighthouse/UX (não é pipeline editorial) | ATIVO, fora de escopo editorial |
| `auditoria-noturna-vale` | `30 23 * * *` | Auditoria do site `public/` | ATIVO, fora de escopo editorial |
| `youtube-pipeline-lembrete` | `0 9 * * 1` | Só lembrete; spec de vídeo **não implementada** | ATIVO como lembrete |

### Incidente ainda relevante (2026-08-15)

Em 14/08 o working tree foi para `main`. Isso **substituiu** `pipeline.py` (7 etapas → 4), **removeu** `ads_insert.py` e tirou o bit `+x` do `cron-wrapper.sh`. O cron das 06:00 falhou em silêncio (`Permission denied`). Restaurado e rodado à mão. Ver `archive/handoffs/2026-08-15.md`.

**Atenção:** o working tree **continua em `main`**, não em `feature/gemini-rate-limiting` (branch que o handoff chama de “produção”). Qualquer merge/checkout descuidado pode repetir o incidente.

Avisos recorrentes do run de hoje (não bloqueiam):

- Cota RPD do TTS `gemini-3.1-flash-tts-preview` estoura nas chaves (failover OK, 4º dia seguido).
- RSS `altovalenoticias` 404 → fallback WordPress API.
- `nsctotal` sem Playwright → fallback HTTP.
- R2 lifecycle API `AccessDenied` (upload em si funciona).
- `build_site.py` ausente — `publish_site.py` é quem publica de fato.

---

## Mapa rápido do fluxo

```
FONTES (sources/sources.json)
        │
        ▼
news_collector.py  (+ cache X se houver)
        │
        ▼
ai_news_filter.py  →  episodes/raw-YYYY-MM-DD.md
        │
        ▼
generate_roteiro_llm.py  →  roteiro-YYYY-MM-DD.json
        │                     (+ naturalize_roteiro)
        ▼
generate_script.render_from_json  →  YYYY-MM-DD.md
        │
        ▼
tts_preprocessor  →  YYYY-MM-DD-tts.txt
        │
        ▼
generate_gemini_tts_multi.py  →  audio/YYYY-MM-DD.mp3
        │
        ▼
ads_insert.py  →  splice de patrocínio no MP3
        │
        ▼
thumbnail_generator.py
        │
        ▼
upload_r2.py  +  publish_site.py  →  public/ + news.mob.tec.br
                 └── gen_noticias.py → public/noticias/

B&M (paralelo, isolado do diário):
bm_monitor.py → queue.json
      → bm_pipeline.py process-queue
           transcript → condensador → TTS Peter solo → R2 → publish_site
           (+ persona_watch; digest semanal)
```

---

## 1. Descoberta e coleta de fontes

### Dados (não são scripts, mas o collector lê daqui)

| Path | Papel | Status |
|---|---|---|
| `/home/osmar/web-jornal-vale-da-liberdade/sources/sources.json` | **Operacional.** `news_collector` lê daqui. 39 fontes: 35 `rss`, 3 `scraping`, 1 `browser`. Versionado. | ATIVO |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/sources_registry.json` | Governança (`status`: 38 ativa / 6 probatória / 2 banida). Gitignored. | DADO VIVO, **sem script de governança no disco** |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/sources_candidates.json` | 28 candidatas (20 `candidata` / 8 `banida`). Gitignored. | DADO ÓRFÃO (scout sumiu) |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/sources_weekly_report.json` | Relatório semanal human-in-loop. | DADO ÓRFÃO |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/cache.json` | Cache/dedup + `source_stats` + `last_run`. | ATIVO |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/feeds_candidates.json` (+ `*_retry*.json`) | Lista p/ `validate_feeds.py`. | MANUAL / QA |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/x_config.json` | Config do coletor X. | SÓ SE `x_collector` rodar |
| `/home/osmar/web-jornal-vale-da-liberdade/sources/sources.md`, `sources.txt` | Listas humanas. | LEGADO / referência |
| `/home/osmar/web-jornal-vale-da-liberdade/news_urls.md` | URLs antigas. Docs dizem: não é vigente. | HISTÓRICO |

A skill Hermes `web-jornal-source-governance` ainda descreve `scout.py` / `source_judge.py` / `source_governance.py`. **Esses três arquivos não existem no disco** (busca em `/home/osmar` sem hit). O job Hermes `webjornal-scout-weekly` chama um Scout que não tem implementação.

### Scripts

#### `scripts/news_collector.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/news_collector.py` (661 linhas)
- **Propósito:** Coleta paralela (`ThreadPoolExecutor`) das fontes de `sources.json`; dedup via `cache.json` + MinHash; devolve artigos candidatos.
- **Pipeline:** Etapa 1 do diário (`pipeline.py` `cmd_init` / `cmd_collect` → `_run_news_collection`).
- **Deps:** `feedparser`, `bs4`, `requests`, `urllib3`, `minhash_dedup`; `playwright` só no método `browser`.
- **Métodos:** `fetch_rss_source`, `fetch_scraping_source`, `fetch_browser_source` (Playwright). CLI: `--test-sources`, `--hours`.
- **Limitações:** 1 fonte `browser` (NSC) cai p/ HTTP se Playwright faltar. RSS 404 em algumas fontes (ex. altovalenoticias) precisa de fallback interno — o handoff de hoje confirma que o fallback WP API existe e foi usado.

#### `scripts/minhash_dedup.py` — ATIVO (lib)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/minhash_dedup.py` (85 linhas)
- **Propósito:** Dedup semântica leve (3-grams + MD5 truncado) em Python puro.
- **Pipeline:** usado só por `news_collector`.
- **Deps:** stdlib.

#### `scripts/ai_news_filter.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/ai_news_filter.py` (787 linhas)
- **Propósito:** Scoring **determinístico** (geo, credibilidade, recência, burst) + categorias por keyword. Não chama LLM apesar do nome.
- **Pipeline:** logo após a coleta; produz a lista que vira `raw-YYYY-MM-DD.md`. Menciona `candidates-{date}.json` p/ Hermes no docstring — **necessita validação** se esse JSON ainda é escrito no fluxo `full` atual.
- **Deps:** `pydantic`.

#### `scripts/x_collector.py` — PARCIALMENTE ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/x_collector.py` (1748 linhas)
- **Propósito:** Playwright + stealth no X/Twitter; perfis/termos; cache JSON; `consume_x_tweets_for_pipeline()`.
- **Pipeline:** o diário **só consome o cache** (try/except, não aborta). **Não há cron** que rode o scrape (`--mode` etc.). Sem cache fresco, o log típico é “nenhum tweet”.
- **Deps:** `playwright`, `dotenv`.
- **Limitações:** cookies de sessão voláteis; rate-limit. `scripts/run_x_collector.bat` = leftover Windows.

#### `scripts/validate_feeds.py` — MANUAL / QA

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/validate_feeds.py` (334 linhas)
- **Propósito:** Testa `sources/feeds_candidates.json` sem gravar cache/`sources.json`. Relatório em `logs/feeds_validation_YYYY-MM-DD.md`.
- **Deps:** reusa `fetch_rss_source` / `clean_html` de `news_collector`.
- **Não está no cron.**

#### Scout / Judge / Governance — AUSENTES

| Path esperado | Papel (skill/memória 2026-07-25) | Status |
|---|---|---|
| `scripts/scout.py` | Tavily/Exa + citações nos raw + hook X → candidatas | **NÃO EXISTE** |
| `scripts/source_judge.py` | LLM Judge 6 eixos (OpenRouter) + fallback heurístico | **NÃO EXISTE** |
| `scripts/source_governance.py` | Relatório semanal; `--apply` sincroniza `sources.json` | **NÃO EXISTE** |
| `scripts/source_discovery_search.py` | Tavily → Exa → DDG | **NÃO EXISTE** |

Os JSONs de registry/candidates/weekly_report **continuam no disco**. A governança human-in-loop está congelada: dados sem código.

---

## 2. Pipeline diário (Peter + Ricardo)

Orquestrador: `pipeline.py full` (o docstring fala 6 etapas; o código de `cmd_full` é **8 fatias**).

| # | Etapa | Função / script |
|---|---|---|
| 1 | Init / coleta | `cmd_init` → `news_collector` + `ai_news_filter` (+ X cache) → `raw-{date}.md` |
| 2 | Roteiro JSON | `ensure_roteiro_json` → `generate_roteiro_llm.py` → `roteiro-{date}.json` |
| 2.5 | Título | `title_optimizer.py` (não bloqueia) |
| 3 | Process | `cmd_process` → `render_from_json` + `tts_preprocessor` + manchetes/metadata |
| 4 | Validate | `tts_preprocessor.validate_episode` — erros críticos dão `sys.exit(4)` |
| 5 | Áudio | `cmd_audio` → `generate_gemini_tts_multi.py` (gate: roteiro ≥ 1500 palavras, MP3 ≥ 1 MB) |
| 5.5 | Anúncio | `ads_insert.py --no-republish` (não bloqueia) |
| 5.6 | Thumbnail | `thumbnail_generator.generate_thumbnail_safe` (não bloqueia) |
| 6 | Archive | `cmd_update_archive` → `archive/index.md` |
| 7 | Publish | `cmd_publish_site` → `upload_r2.py` + (`build_site.py` se existir) + `publish_site.py` |

CLI: `init | collect | process | validate | audio | full | update-archive | roteiro | deliver-check | publish`. Flags: `--date`, `--hours`, `--no-collect`, `--skip-audio`, `--force-roteiro`, `--allow-short-audio`.

### `scripts/pipeline.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/pipeline.py` (1092 linhas)
- **Deps:** `dotenv`, `news_collector`, `ai_news_filter`, `generate_script`, `generate_roteiro_llm`, `naturalize_roteiro`, `tts_preprocessor`, `thumbnail_generator`, `x_collector` (opcional).
- **Subprocessos:** `title_optimizer.py`, `ads_insert.py`, `generate_gemini_tts_multi.py`, `upload_r2.py`, `publish_site.py`, e (se existirem) `build_site.py`, `tts_fallback_elevenlabs.py`, `tts_fallback_edge.sh`.
- **Limitações:**
  - Docstring de `cmd_publish_site` ainda fala em rebuild via `build_site.py` — arquivo **não existe**; o aviso é esperado.
  - Fallbacks ElevenLabs/Edge/MOSS referenciados **não estão no disco** (só Gemini de fato).
  - `deliver-check` no argparse: **necessita validação** do que implementa (o precheck Hermes aponta para um `.sh` ausente).
  - Troca de branch pode reverter este arquivo para a versão de 4 etapas (incidente 15/08).

### `scripts/cron-wrapper.sh` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh`
- **Propósito:** `source .env`, chama `pipeline.py full`, log `logs/daily-$DATA.log`.
- **Limitações:** precisa `chmod +x`. Sem MTA, falha de permissão some no vazio.

### `scripts/cron-daily.sh` — LEGADO / QUEBRADO

- Chama `scripts/daily-pipeline.sh` **que não existe**. Não está no crontab atual.

### `scripts/daily-collect.sh` — LEGADO / PERIGOSO

- Gera `raw-$HOJE.md` **vazio** (“Extração automática indisponível”) + roteiro template. O `pipeline.py` detecta esses marcadores e **recoleta** se o `full` rodar depois. Se alguém chamar só este shell, o episódio nasce oco.
- Não está no crontab. Continua com `+x` após o incidente de hoje.

### `scripts/generate_roteiro_llm.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/generate_roteiro_llm.py` (475 linhas)
- **Propósito:** `raw-{date}.md` → `roteiro-{date}.json` via prompt de `generate_script.build_script_prompt()`.
- **Pipeline:** etapa 2 do `full` / comando `roteiro`.
- **Deps:** `gemini_client`, `generate_script`, `naturalize_roteiro`, `requests`, `dotenv`.
- **Backends:** Gemini (`gemini-3.6-flash` → `3.5-flash` → `3.5-flash-lite` → `3.1-flash-lite` → `gemma-4-31b-it`) depois OpenRouter free (`nvidia/nemotron-3-super-120b-a12b:free`, `google/gemma-4-31b-it:free`, etc.). Lê keys do `.env` do projeto e `~/.hermes/.env`; pula key 401.
- **Limitações:** memória antiga (25/07) dizia GEMINI_API_KEY inválida e queda no OpenRouter — **necessita validação** do estado atual das keys. Cota RPD baixa no 3.6/3.5-lite.

### `scripts/generate_script.py` — ATIVO (renderer + contratos)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/generate_script.py` (393 linhas)
- **Propósito:** Pydantic `RoteiroItem`/`RoteiroCompleto`; `parse_raw`; `render_from_json` (JSON Hermes/LLM → `{date}.md`); `build_script_prompt`; `format_script`.
- **Pipeline:** etapa 3. **Não** gera o JSON sozinho no `full` atual — só renderiza.
- **Deps:** `pydantic`.
- **Limitações históricas:** `_fill_roteiro_from_raw` em `pipeline.py` já causou notícia duplicada (LESSONS 2026-06-20). `cmd_process` deve falhar/manter template, não voltar a preencher do raw.

### `scripts/naturalize_roteiro.py` — ATIVO (pós-JSON)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/naturalize_roteiro.py` (327 linhas)
- **Propósito:** Tira abertura de telejornal, muletas (“Vai daí…”), corta falas 4+ frases. Não injeta transições mecânicas.
- **Chamado por:** `generate_roteiro_llm` (e CLI `--date`).
- **Deps:** `generate_script`, `validate_naturalidade`.

### `scripts/validate_naturalidade.py` — ATIVO (lib + CLI)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/validate_naturalidade.py` (302 linhas)
- **Propósito:** Checklist SKILL §7.1 (dinâmica Peter/Ricardo). Usado por `tts_preprocessor.validate_episode`.
- **Deps:** stdlib.

### `scripts/gen_noticias.py` — ATIVO (via publish)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/gen_noticias.py` (373 linhas)
- **Propósito:** Gera `public/noticias/` (home + artigos) a partir dos roteiros `.md`. Sem prefixos de locutor. Fonte citada no rodapé.
- **Pipeline:** chamado por `publish_site.py` depois das páginas `/ep/`. Falha **não** deve abortar o publish (contrato da skill frontend).
- **Deps:** `noticias_templates`, `dotenv`.

### `scripts/noticias_templates.py` — ATIVO (lib)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/noticias_templates.py` (306 linhas)
- **Propósito:** HTML/CSS das páginas de notícia (preto / Inter / âmbar `#e8a23d`). Precisa de `[hidden]{display:none!important}` no CSS gerado (bug real: filtro de editoria não escondia).

### `scripts/ads_insert.py` — ATIVO (não bloqueia)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/ads_insert.py` (392 linhas)
- **Propósito:** Lê `ads/schedule.json`, escolhe anúncio por rotação, acha silêncio perto do meio (40–60%), splice ffmpeg (MP3 192k mono 44.1k).
- **Pipeline:** etapa 5.5 do `full`. `--no-republish` no cron. CLI: `--date`, `--dry-run`, `--force-ad`.
- **Deps:** `ffmpeg` CLI; chama `upload_r2` / `publish_site` se não `--no-republish`.
- **Limitações:** some se o arquivo for apagado no switch de branch (aconteceu 14–15/08). Dashboard admin ainda não substitui `schedule.json`.

### `scripts/test_green_build.py` — TESTE

- Roda `pipeline.py process+validate` contra `episodes/roteiro-template.json`. Não é cron.

---

## 3. Pipeline Brasil e Mundo (especial / Peter solo)

Isolado do diário. Regras em `pipelines/brasil_e_mundo/SKILL_BRASIL_E_MUNDO.md` (um narrador, 750–900 palavras, sem Ricardo, sem quadros). Estado: `pipelines/brasil_e_mundo/{config,queue,seen_videos}.json`. Canal: ANCAPSU `UCLTWPE7XrHEe8m_xAmNbQ-Q`. Filtro duração: 180–3600 s.

`bm_pipeline.py full` (também usado por `process-queue`):

| # | Etapa | Script |
|---|---|---|
| 1/5 | Transcrição | `bm_transcript.py` |
| 2/5 | Condensação LLM | `bm_condensador.py` |
| 3/5 | Pré-TTS | `tts_preprocessor.preprocess_for_tts` |
| 4/5 | Áudio Peter | `generate_gemini_tts_multi.py --single-speaker Peter --model gemini-2.5-flash-preview-tts` |
| 4.5 | Thumbnail | `thumbnail_generator` id `bm_{video_id}` — data **do nome do MP3**, não `now()` |
| 5 | Feed RSS B&M + persona | `step_publish_feed` + `bm_persona_watch.py` |
| 6 | R2 + catálogo | `upload_r2.py --date especial-{id}` depois `publish_site.py`. Se R2 falha, **não** publica (evita URL local no catálogo) |

CLI: `full | process-queue | transcript | roteiro | audio`.

### `scripts/bm_monitor.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_monitor.py` (264 linhas)
- **Propósito:** Poll do Atom do YouTube; compara `seen_videos.json`; filtra duração/tipo; append em `queue.json`.
- **Pipeline:** cron host `0 5-23`. CLI: `--dry-run`, `--backfill N`.
- **Deps:** stdlib (`urllib`, `xml.etree`).
- **Limitações:** só o canal do `config.json`. Não puxa descrição completa (isso é `bm_transcript` / yt-dlp).

### `scripts/bm_pipeline.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_pipeline.py` (639 linhas)
- **Propósito:** Orquestra B&M. `process-queue` marca `pending → processing → done|error` e limpa `done`.
- **Deps:** `dotenv`, `tts_preprocessor`, `thumbnail_generator`; subprocesso nos `bm_*.py` + TTS + R2 + publish.
- **Limitações:**
  - Fila processada **duas vezes por hora** (host `:10` + Hermes `:30`).
  - `seen_videos` só atualiza se o MP3 existir (evita “visto” fantasma).
  - TTS B&M usa modelo **2.5** de propósito (isola cota do diário 3.1) — se 2.5 cair, o passo aborta o item.

### `scripts/bm_transcript.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_transcript.py` (541 linhas)
- **Propósito:** yt-dlp legendas; fallback download áudio + `faster_whisper`. Grava `output/brasil_e_mundo/raw/{video_id}.json`.
- **Deps:** `yt-dlp` (CLI), `faster_whisper`.
- **Limitações:** Whisper local é pesado; precisa GPU/CPU ok no host. IDs que começam com `-` são passados via env no condensador.

### `scripts/bm_condensador.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_condensador.py` (644 linhas)
- **Propósito:** Transcrição → roteiro ~5 min só Peter. Escreve `episodes/especial-{id}.md` + `.json`. Extrai “Referências:” da descrição YT. Otimiza título via `title_optimizer`.
- **Deps:** `gemini_client`, `dotenv`, `bm_transcript`, `title_optimizer`.
- **CLI:** `--video-id` / `--video-id-env` / `--force`.

### `scripts/bm_add_video.py` — MANUAL

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_add_video.py` (124 linhas)
- **Propósito:** Empilha qualquer URL YT na mesma `queue.json` do monitor. `--url`, `--title`, `--force`.
- **Deps:** reusa load/save de `bm_monitor`. Sem cron.

### `scripts/bm_persona_watch.py` — ATIVO (não bloqueia)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_persona_watch.py` (218 linhas)
- **Propósito:** Depois de cada vídeo, analisa a transcrição **original** (não o condensado) em 4 camadas; grava `persona_suggestions/raw/{video_id}.json`. Não mexe no diário nem em `SOUL.md`.
- **Deps:** `gemini_client`, `dotenv`.

### `scripts/bm_persona_digest.py` — ATIVO (semanal)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_persona_digest.py` (352 linhas)
- **Propósito:** Segunda 09h BRT. Consolida raw da semana; descarta o que já está em `peter_style_evolution.json`; sinaliza conflitos. Aprovação **manual**.
- **Deps:** `gemini_client`, `dotenv`, `bm_persona_watch`.

### `scripts/bm_feed_rebuild.py` — MANUAL

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_feed_rebuild.py` (91 linhas)
- **Propósito:** Reescreve `<description>` do RSS B&M com referências (itens antigos). Chama `publish_site` no final.
- **Não está no cron.**

### `scripts/bm_backfill_referencias.py` — MANUAL (one-shot / manutenção)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_backfill_referencias.py` (107 linhas)
- **Propósito:** Preenche `fonte_referencias` em especiais gerados antes da extração da seção “Referências:”.
- **Deps:** `bm_condensador`. `--force`. Não é cron.

### `scripts/bm_karaoke.py` — PROTÓTIPO / FORA DO CRON DE ÁUDIO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/bm_karaoke.py` (148 linhas)
- **Propósito:** Corta o MP3 por quadros e gera `*_words.json` via faster-whisper (vídeo/HyperFrames).
- **Deps:** importa `bm_quadros_mapper.py` — **AUSENTE**. Sem o mapper, este script quebra.
- **Não** faz parte do `process-queue` de áudio.

---

## 4. Geração de mídia

### TTS

#### `scripts/gemini_client.py` — ATIVO (lib)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/gemini_client.py` (406 linhas)
- **Propósito:** Wrapper Google GenAI com backoff 429, RPM/RPD/TPM persistidos (`sources/gemini_usage.json`, `gemini_limits.json`).
- **Usado por:** roteiro LLM, condensador B&M, persona, title optimizer, thumbnail (prompt), TTS (via generate_*).
- **Deps:** `google` (genai).
- **Irmão:** `scripts/gemini_client.ts` — **não referenciado** por nenhum pipeline Python. Trata como legado/espelho.

#### `scripts/generate_gemini_tts_multi.py` — ATIVO (TTS real)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/generate_gemini_tts_multi.py` (1382 linhas)
- **Propósito:** Multi-locutor. Peter=`Charon`, Ricardo=`Schedar`. Default `gemini-3.1-flash-tts-preview`. Chunks em `[PAUSA]` / `[PAUSA_CURTA]`. B&M: `--single-speaker Peter --mode halves --model gemini-2.5-flash-preview-tts`.
- **Pós ffmpeg:** loudnorm EBU R128 2 passos (−16 LUFS), highpass 80 Hz, compressor, EQ, 44.1 kHz, MP3 192k.
- **Deps:** `gemini_client`, `google`, `tts_preprocessor`, `dotenv`, `edge_tts` (fallback **interno** `pt-BR-AntonioNeural`), `ffmpeg`.
- **Limitações:** RPD 10 do 3.1 estoura com frequência (handoff 15/08). Edge interno existe neste arquivo; o `tts_fallback_edge.sh` **externo** não.

#### `scripts/generate_gemini_tts.py` — LEGADO / SINGLE-SPEAKER

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/generate_gemini_tts.py` (138 linhas)
- **Propósito:** TTS uma voz. Não é o caminho do `cmd_audio` nem do B&M atuais.
- **Deps:** `gemini_client`, `tts_preprocessor`, `google`, `dotenv`.

#### `scripts/tts_preprocessor.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/tts_preprocessor.py` (999 linhas)
- **Propósito:** SKILL 8.2/8.3 — siglas soletradas, símbolos, tira markdown, pausas, labels PETER/RICARDO; `extract_manchetes`, `generate_metadata`, `validate_episode`.
- **Deps:** `num2words`, `validate_naturalidade`.
- **CLI:** `--input`, `--output`, `--manchetes`, `--validate`, `--test`.

#### Fallbacks TTS referenciados e **ausentes**

| Path | Quem chama | Status |
|---|---|---|
| `scripts/tts_fallback_elevenlabs.py` | `pipeline.cmd_audio` passo 2 | **AUSENTE** |
| `scripts/tts_fallback_edge.sh` | `pipeline.cmd_audio` passo 3 | **AUSENTE** (há Edge *dentro* do multi) |
| `scripts/tts_fallback_moss.py` | Comentado em `pipeline.py` | **AUSENTE**; MOSS desabilitado “aguarda fine-tune pt-BR” |
| `moss-tts-nano/` | Vendor no repo | NÃO ligado ao cron |

### Thumbnail / título

#### `scripts/thumbnail_generator.py` — ATIVO (não bloqueia)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/thumbnail_generator.py` (1214 linhas)
- **Propósito:** Pauta → prompt Gemini Flash → cascata DashScope (qwen-image-3.0, 2.0-pro, 2.0, max, plus, z-image-turbo, + Wan no docstring) → 16:9 webp+jpg em `thumbnails/{date}/{ep_id}.*`. Placeholder se tudo falhar.
- **Pipeline:** diário 5.6 e B&M 4.5.
- **Deps:** `PIL`, `requests`, `gemini_client`, `generate_roteiro_llm` (keys), `dotenv`. Env: `DASHSCOPE_API_KEY`.
- **Bug já corrigido no B&M:** data da pasta vinha de `datetime.now()` (dia do processamento ≠ dia do MP3). Agora deriva de `{video_id}_YYYY-MM-DD.mp3`.

#### `scripts/title_optimizer.py` — ATIVO (não bloqueia)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/title_optimizer.py` (534 linhas)
- **Propósito:** Título 40–60 chars (teto 70) no estilo skill `youtube-journalistic-title-optimizer`. Grava sidecar lido por `publish_site.read_optimized_title`.
- **Deps:** `gemini_client`, `requests`, `dotenv`. Usado no diário e no condensador B&M.

---

## 5. Publicação

### `scripts/publish_site.py` — ATIVO (fonte do catálogo)

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/publish_site.py` (1160 linhas)
- **Propósito:** Única publicação do site estático:
  - `public/data/episodes.json` (+ paginação)
  - `public/feed.xml` / `public/feed.json`
  - Copia áudios → `public/audio/`
  - Copia roteiros → `public/episodes/`
  - `write_share_pages` → `public/ep/<id>.html` (OG p/ WhatsApp/Telegram)
  - `gen_noticias.main()` → `/noticias/`
  - `deploy_noticias_pages()` Cloudflare Pages (falha não aborta)
  - minify CSS/JS, bump SW, sync thumbnails, inject env
- **CLI:** `--date`, `--limit` (default **200** — se baixar, especiais recentes expulsam diários antigos do catálogo).
- **Deps:** `PIL`, `csscompressor`, `rjsmin`, `dotenv`, `gen_noticias`; `wrangler` opcional p/ Pages.
- **Limitações:**
  - **Não** sincroniza `new-ux/` (pasta removida 2026-08-06). Editar `public/` é o correto.
  - Cache-buster `?v=` no `index.html` **não atualiza** se já existir valor — JS novo pode ficar preso (skill frontend).
  - `sync_ux_assets()` no código: **necessita validação** se ainda copia alguma coisa ou é no-op.
- **Chamado por:** `pipeline.cmd_publish_site`, `bm_pipeline.step_publish_site_catalog`, `ads_insert` (se republicar), `bm_feed_rebuild`, `bm_backfill_referencias`.

### `scripts/upload_r2.py` — ATIVO

- **Path:** `/home/osmar/web-jornal-vale-da-liberdade/scripts/upload_r2.py` (247 linhas)
- **Propósito:** Sobe MP3 no R2 (boto3/S3) + espelho `public/audio/{date}.mp3`. URL pública: `R2_PUBLIC_DOMAIN` (ex. `https://audio.mob.tec.br`) ou path local.
- **CLI:** `--date` (diário `YYYY-MM-DD` ou `especial-{id}`), `--file`.
- **Deps:** `boto3`, `botocore`, `dotenv`.
- **Limitações:** lifecycle 90d best-effort; `AccessDenied` na API de lifecycle é esperado e não aborta.

### `scripts/title_optimizer.py`

Já na §4; entra no catálogo via sidecar + `publish_site.read_optimized_title`.

### `scripts/build_site.py` — AUSENTE

- Chamado por `pipeline.cmd_publish_site` se existir. Não existe. Publish real = só `publish_site.py`. Skill/vale-repo: um shim antigo que só delegava ao publish — **não recriar** a versão de junho que gerava HTML próprio (sobrescrevia a PWA).

---

## 6. Órfãos / quebrados / protótipos

### Referenciados por cron ou pipeline e **ausentes**

| Referência | Quem aponta | Efeito |
|---|---|---|
| `scripts/scout.py` | Hermes `webjornal-scout-weekly` + skill governança | Job semanal não tem o que executar |
| `scripts/source_judge.py` | skill governança | Scoring LLM morto |
| `scripts/source_governance.py` | skill governança | `--apply` impossível |
| `scripts/source_discovery_search.py` | memória 2026-07-25 | Busca de fontes morta |
| `scripts/bm_video_autopilot.py` | Hermes job (disabled) | Autopilot de vídeo B&M não pode ligar |
| `scripts/bm_quadros_mapper.py` | `bm_karaoke.py` | Karaoke quebrado |
| `scripts/build_site.py` | `pipeline.cmd_publish_site` | Warning inofensivo |
| `scripts/daily-pipeline.sh` | `cron-daily.sh` | Shell legado quebrado |
| `scripts/tts_fallback_elevenlabs.py` | `cmd_audio` | Passo 2 nunca roda |
| `scripts/tts_fallback_edge.sh` | `cmd_audio` | Passo 3 nunca roda |
| `scripts/tts_fallback_moss.py` | comentado em `pipeline.py` | OK (desligado de propósito) |
| `scripts/delivery_health_check.sh` | Hermes `web-jornal-delivery-precheck` → `~/.hermes/scripts/delivery_health_check.sh` | Precheck 05:30 **quebra** |
| `scripts/youtube_upload.py` | spec/lembrete YouTube | Não implementado |

### Duplicatas / riscos de agendamento

1. Diário 06:00: **host bash + Hermes agent** no mesmo horário.
2. B&M `process-queue`: host `:10` (05–23) **e** Hermes toda hora `:30` (24h, inclusive madrugada).
3. Working tree em `main` vs branch de produção documentada `feature/gemini-rate-limiting`.

### Protótipos (existem, sem cron de produção)

| Path | Nota |
|---|---|
| `references/youtube/prototype/bancada-render/build_episode_composition.py` | HyperFrames 720p — spec de vídeo por quadros **não** está no cron |
| `references/youtube/prototype/bancada-render/build_q02_composition.py` | Idem |
| `moss-tts-nano/**` | Vendor; pipeline declara MOSS off |
| `scripts/gemini_client.ts` | Sem caller |
| `scripts/qa_background_autoplay.mjs` | QA do player (UX-016), não editorial |
| `scripts/test_rpc_proxy.py` | QA nginx→Kong RPCs |
| `metrics/*.py`, `metrics/run_cycle.sh` | Auditoria UX/perf, não produção de episódio |

### Dados de governança sem dono de código

`sources_registry.json` / `sources_candidates.json` / `sources_weekly_report.json` estão no disco e a skill ainda ensina o fluxo `--apply`. Sem os `.py`, qualquer “melhoria de descoberta de fontes” precisa **reimplementar** Scout/Judge/Governance ou editar `sources.json` na mão.

---

## Convenções para quem for sugerir mudanças

1. **Não** tratar `docs/archive/2026-06-pipeline/` como spec. Site atual = `public/` + `publish_site.py`.
2. **Não** recriar `new-ux/`. **Não** recriar `build_site.py` gerador de HTML.
3. Diário e B&M são isolados editorialmente (dois apresentadores vs Peter solo). Compartilham só TTS/R2/publish/thumbnail.
4. Qualquer `await`/pausa/`new Audio()` no player é outro domínio (`web-jornal-frontend`); não misturar com este inventário.
5. Preferir evidência: `crontab -l`, `logs/daily-*.log`, `logs/bm-*.log`, `archive/handoffs/`.
6. `sources.json` é o que o collector usa. Registry/candidates sem script = não automatizar `--apply` até o código voltar.
7. Cota Gemini TTS é o gargalo diário mais repetido (15/08 e 4 dias antes).

---

## Checklist de arquivos em `scripts/` (produção editorial)

| Arquivo | Categoria | Cron / caller | Estado |
|---|---|---|---|
| `pipeline.py` | Diário orquestrador | `cron-wrapper.sh` 06:00 | ATIVO |
| `cron-wrapper.sh` | Diário | crontab host | ATIVO |
| `cron-daily.sh` | Diário | ninguém | LEGADO quebrado |
| `daily-collect.sh` | Diário | ninguém | LEGADO perigoso |
| `news_collector.py` | Coleta | pipeline init | ATIVO |
| `minhash_dedup.py` | Coleta | news_collector | ATIVO |
| `ai_news_filter.py` | Coleta | pipeline init | ATIVO |
| `x_collector.py` | Coleta X | só consume no init | PARCIAL |
| `validate_feeds.py` | Coleta QA | manual | MANUAL |
| `generate_roteiro_llm.py` | Diário roteiro | pipeline etapa 2 | ATIVO |
| `generate_script.py` | Diário renderer | pipeline etapa 3 | ATIVO |
| `naturalize_roteiro.py` | Diário roteiro | generate_roteiro_llm | ATIVO |
| `validate_naturalidade.py` | Diário QA | tts_preprocessor | ATIVO |
| `ads_insert.py` | Diário áudio | pipeline 5.5 | ATIVO |
| `bm_monitor.py` | B&M | crontab 05–23h | ATIVO |
| `bm_pipeline.py` | B&M | crontab + Hermes hourly | ATIVO |
| `bm_transcript.py` | B&M | bm_pipeline | ATIVO |
| `bm_condensador.py` | B&M | bm_pipeline | ATIVO |
| `bm_add_video.py` | B&M | manual | MANUAL |
| `bm_persona_watch.py` | B&M | bm_pipeline | ATIVO |
| `bm_persona_digest.py` | B&M | crontab segunda 09h | ATIVO |
| `bm_feed_rebuild.py` | B&M | manual | MANUAL |
| `bm_backfill_referencias.py` | B&M | manual | MANUAL |
| `bm_karaoke.py` | Vídeo proto | ninguém (e mapper some) | QUEBRADO |
| `gemini_client.py` | Mídia lib | vários | ATIVO |
| `gemini_client.ts` | — | ninguém | LEGADO |
| `generate_gemini_tts_multi.py` | TTS | diário + B&M | ATIVO |
| `generate_gemini_tts.py` | TTS | ninguém no full | LEGADO |
| `tts_preprocessor.py` | TTS | diário + B&M | ATIVO |
| `thumbnail_generator.py` | Mídia | diário + B&M | ATIVO |
| `title_optimizer.py` | Pub | diário + condensador | ATIVO |
| `publish_site.py` | Pub | diário + B&M | ATIVO |
| `upload_r2.py` | Pub | diário + B&M | ATIVO |
| `gen_noticias.py` | Pub | publish_site | ATIVO |
| `noticias_templates.py` | Pub lib | gen_noticias | ATIVO |
| `test_green_build.py` | Teste | manual | TESTE |
| `test_rpc_proxy.py` | Teste site | manual | TESTE |
| `qa_background_autoplay.mjs` | Teste player | manual | FORA DE ESCOPO |

Fim do inventário.
