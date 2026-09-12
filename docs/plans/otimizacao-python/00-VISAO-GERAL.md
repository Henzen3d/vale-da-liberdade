# Plano de Otimização Python — Vale da Liberdade

**Data original**: 2026-09-09
**Alinhado ao host**: 2026-09-10 (leitura do disco + cron + venvs; planos **não** executados)
**Escopo**: Scripts em `scripts/` do repo `/home/osmar/web-jornal-vale-da-liberdade`
**Foco**: Desempenho do pipeline, **sem** quebrar o diário 06:00 nem o BM `*/20`

---

## Objetivo

Reduzir o tempo do pipeline diário e do BM eliminando gargalos reais de I/O, CPU e rede.

O pipeline diário (`pipeline.py full` via `cron-wrapper.sh`) é sequencial e leva de 15 a 40 min conforme API. As melhorias visam 40–60% **somente se** respeitarem cota Gemini, RAM do host e os dois interpretadores. Ganho de paper (asyncio + 8 browsers + 8 Edge + 3 DashScope) **não** cabe neste servidor.

**Esta pasta é plano, não execução.** Aplicar na madrugada só depois de ler «Janela de madrugada» abaixo.

---

## Métricas Antes (Baseline)

Tempos abaixo são **estimativa operacional**, não medição desta sessão.

| Etapa | Tempo médio estimado | Gargalo principal | Python real |
|-------|----------------------|-------------------|-------------|
| Coleta (`news_collector.py`) | 2–4 min | HTTP; já tem ThreadPool 5; ~41 fontes, não 11 | HERMES_PY |
| Filtro IA (`ai_news_filter.py`) | 10–30s | CPU (scoring) | HERMES_PY |
| Roteiro JSON LLM | 2–5 min | API Gemini (RPM/RPD) | HERMES_PY |
| Pré-processamento TTS | 5–15s | regex (ganho pequeno no wall-clock) | HERMES_PY |
| TTS Gemini multi | 5–15 min | 3 RPM/chave, 10 RPD/chave, chunk sequencial | HERMES_PY |
| Fallback Edge (`tts_fallback_edge.sh`) | 5–10 min | loop bash + N spawns; FX Ricardo **sem** librosa neste host | HERMES_PY |
| Thumbnail | segundos–2 min típico | **Não** é cascata DashScope de 8 modelos | HERMES_PY |
| Publicação (`publish_site.py`) | 30–90s | I/O + minify | HERMES_PY |
| Vídeo BM (`bm_mockup_video.py`) | 3–8 min (orçamento até 25–40) | Playwright + FFmpeg; delays anti-bot 3.5–15s | **PROJECT_PY** |

---

## Arquitetura de Dependências (código vivo)

Contagens `wc -l` em 2026-09-10:

```
pipeline.py                     1147
news_collector.py                915
ai_news_filter.py                785
generate_gemini_tts_multi.py    1713
tts_preprocessor.py             1099
thumbnail_generator.py          1576
publish_site.py                 1240
bm_mockup_video.py              2896
bm_pipeline.py                   875
gemini_client.py                 688
http_fetch.py                    322
bm_condensador.py                832
ricardo_voice_fx.py              425
```

Dois interpretadores **não unificar** (canônico em `scripts/bm-hourly-pipeline.sh`):

1. **HERMES_PY** = `/home/osmar/.hermes/hermes-agent/venv/bin/python3` (CPython **3.11.15**)
   - Diário, `bm_monitor.py`, `bm_pipeline.py`, TTS, Gemini, coleta.
   - Tem: `aiohttp`, `uvloop`, `edge_tts`, `google.genai`, `feedparser`, `pydantic_settings`.
   - **Não tem**: `playwright`, `librosa`, `pyworld`, `scipy`.
2. **PROJECT_PY** = `/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3` (CPython **3.14**)
   - Só `bm_mockup_video.py` (Playwright, render, upload YT).
   - Tem: `playwright` (+ chromium em `~/.cache/ms-playwright`), `aiohttp`, `scipy`, `edge_tts`.
   - **Não tem**: `uvloop`, `pydantic_settings`, `librosa`, `pyworld`.

`python3` no PATH do login é **Linuxbrew 3.14.3**. Cron **não** usa esse binário. Scripts novos devem usar `sys.executable` do braço certo, nunca `python3` solto.

Diário: `cron-wrapper.sh` chama HERMES_PY `pipeline.py full`.
BM: `*/20` → `bm-hourly-pipeline.sh` (HERMES_PY áudio, depois PROJECT_PY mockup se restarem ≥900s do orçamento 3300s).

---

## Índice dos Documentos

Ordem de **impacto** (não é ordem de execução na madrugada — ver janela):

| # | Documento | Impacto | Ganho realista neste host | Executar madrugada? |
|---|-----------|---------|---------------------------|---------------------|
| 01 | [Screenshots paralelos](01-SCREENSHOTS-PARALELOS.md) | Crítico no vídeo BM | Fase A (1 browser). Fase B async **adiada** | Só fora do tick `*/20`; PROJECT_PY |
| 02 | [TTS paralelo](02-TTS-CHUNKING-PARALELO.md) | Crítico | Edge: 1 processo + concurrency baixa. Gemini: **não** furar 3 RPM | HERMES_PY; sem overlap com diário 06:00 |
| 03 | [Coleta async](03-COLETA-NOTICIAS-ASYNC.md) | Alto | aiohttp via `http_fetch`; workers ≤5; 41 fontes | HERMES_PY |
| 04 | [Thumbnails](04-THUMBNAILS-PARALELOS.md) | Médio (rebaixado) | Cascata viva = CF flux → Pollinations. **Sem** paralelo DashScope | Não paralelizar modelos |
| 05 | [Regex](05-COMPILACAO-REGEX.md) | Baixo no wall-clock | Seguro, ganho de ms–centenas ms | Sim, isolado |
| 06 | [Gemini client](06-GEMINI-CLIENT-OTIMIZADO.md) | Alto risco | `fcntl.flock` no JSON. **Sem** SQLite nesta onda | Não migrar persistência de madrugada |
| 07 | [Cache](07-CACHE-MEMOIZACAO.md) | Médio | `lru_cache` + lazy import. Sem PipelineContext grande | Sim, isolado |
| 08 | [Modularizar mockup](08-MODULARIZACAO-BM-MOCKUP.md) | Médio / risco alto | Adiar: cron BM chama o monolito a cada 20 min | Não na mesma noite que 01 |
| 09 | [Bootstrap](09-INFRAESTRUTURA-COMPARTILHADA.md) | Baixo | `_bootstrap.py` opt-in. Sem Pydantic Settings | Opcional; não misturar com 02/06 |
| 10 | [Paralelismo full](10-PARALELISMO-PIPELINE-FULL.md) | Médio / contenção | Title∥Desc **não** (Gemini). Ads∥thumb ok com teto RAM | Depois de 06 estável |

Os documentos **não** são independentes: todos competem por RAM, `gemini_usage.json`, `/dev/shm` e o tick BM.

---

## Ambiente real (2026-09-10)

| Item | Valor medido |
|------|----------------|
| Host | Linux 6.8, Ubuntu, TZ `America/Sao_Paulo` |
| CPU | Intel i5-7400, **4 cores / 4 threads** @ 3.00 GHz |
| RAM | 7,6 GiB total; ~4,9 GiB available; **swap 4 GiB com ~1,9 GiB em uso** |
| `/dev/shm` | tmpfs 3,9 GiB, hoje vazio (`rw,nosuid,nodev`) |
| Serviços sempre ligados | Docker Vale + Supabase + Facilita + Hermes (~0,5–1,1 GiB RSS só no Hermes) |
| Consumo idle citado | ~28 W; servidor **não** desliga à noite |
| Chaves Gemini no `.env` do projeto | `GEMINI_API_KEY`, `_3`…`_7` (**6 chaves**; sem `_2` neste arquivo) |
| TTS Gemini | 3 RPM / 10 RPD / chave; intervalo local 20 s; RR em `sources/gemini_usage.json` |
| CHUNK_TARGET_WORDS no código | **300** (não 200) |
| Vozes Gemini no código | Peter=Charon, Ricardo=**Kore** (avaliação; não alterar neste plano) |
| Edge | Fallback novo: Peter=`pt-BR-AntonioNeural`, Ricardo=`pt-BR-FranciscaNeural` (já em `pipeline.py` / `generate_gemini_tts_multi.py`). Shell antigo = Antonio + FX (FX morto sem librosa). **Não** Fabio; Azure Humberto/Brenda é outra stack. |
| FFmpeg TTS | cadeia **v2** (EQ depois medido, loudnorm −16 LUFS). Não promover v3 |
| Thumbnails | `cf-flux-schnell` → `pollinations-flux`. DashScope **Arrearage / disabled** |
| Fontes RSS | **41** em `sources.json`; paywall_aware: `folha_mercado`, `bloomberg_brasil` |
| Cron diário | `0 6 * * *` **local (−03)**, job `web-jornal-vale-da-liberdade-daily` |
| Cron BM | `*/20 * * * *`, job `web-jornal-brasil-mundo-hourly` |
| Outro cron no host | Tráfego `/home/osmar/transito` a cada **5 min** |

### Bloqueio operacional (não é este plano, mas impede o diário)

O job diário em 2026-09-10 06:00 falhou com exit **127**:

`vale-daily-cron-wrapper.sh` → `scripts/cron-wrapper.sh: cannot execute: required file not found`

Causa alinhada ao disco: `cron-wrapper.sh` e `tts_fallback_edge.sh` estão com **CRLF** (`file` reporta `CRLF line terminators`; shebang `#!/bin/bash\r`). O kernel procura `/bin/bash\r`.

**Pré-requisito antes de qualquer execução de madrugada:** converter esses wrappers para LF (`dos2unix` ou equivalente). Sem isso o diário não roda, independentemente das otimizações.

Trava permanente no repo (2026-09-10): `.gitattributes` na raiz com `*.sh text eol=lf`. `dos2unix` nos `.sh` CRLF **e** o attributes — senão um checkout/edição Windows reinsere `\r`.

Karaoke BM (`bm_karaoke.py`) foi rejeitado — não reintroduzir. ElevenLabs nunca teve conta — não restaurar. MOSS desligado até fine-tune pt-BR.

---

## Janela de madrugada (obrigatório)

Objetivo do dono: aplicar na próxima madrugada **sem** brigar com processos pesados nem com os scripts que estamos refatorando.

1. **Não aplicar os 10 planos na mesma noite.** Teto: 1 plano de I/O pesado (01 **ou** 02 **ou** 03) + planos CPU/seguros (05, 07).
2. **Não tocar `bm_mockup_video.py` (01/08) dentro de 5 min de um tick `*/20`.** Ou pausar o job `web-jornal-brasil-mundo-hourly` durante o teste e religar no fim. **Antes** de teste/edição 01 ou 08: `pgrep -af 'bm_mockup_video|bm_pipeline.py|bm-hourly-pipeline'` — se houver PID, esperar o tick (teto 55 min / 3300 s) ou abortar a noite. Não usar `pgrep -f bm_` sozinho (casa `bm_monitor`, `bm_condensador`, esta sessão).
3. **Não refatorar TTS/Gemini (02/06) entre 05:45 e o fim do diário (~07:00).** O diário 06:00 é o consumidor canônico.
4. **Teto de concorrência neste host (4 cores, 7,6 GiB, swap já sujo):**
   - Chromium: **1 `browser.launch()`**, **1 `context.new_page()` por captura** (abre → screenshot → `page.close()`). Nunca reutilizar a mesma `page` em dezenas de sites. Nunca 3 browsers.
   - Edge-TTS: `Semaphore(3)` (não 8).
   - Coleta HTTP: `limit=8`, `limit_per_host=2`, workers ≤5 (já é o teto atual).
   - Paywall recover (Playwright possível): **1** por vez; no HERMES_PY Playwright **não existe**.
   - Gemini TTS: no máximo 1 chamada em voo **por chave**, via `GeminiMultiClient` (reserva + rollback). Nunca `asyncio.gather` crú nas 6 chaves.
5. **`/dev/shm`:** usar só com `disk_usage` + teto **512 MiB** por job + `try/finally` `rmtree`. Não assumir 200 MiB “sempre cabe”: Chromium e FFmpeg também usam tmpfs/RAM. Se swap > 2,5 GiB, cair para `audio/tmp/`.
6. **`uvloop`:** só no HERMES_PY; no PROJECT_PY está ausente — `try/except ImportError`.
7. **Testes:** `python3 -m py_compile` e `unittest` no **mesmo** interpretador do braço (`HERMES_PY` vs `PROJECT_PY`). `test_bm_mockup_video.py` no PROJECT_PY.
8. **Git:** commits atômicos por plano; sem `--force` em `origin/main`; não commitar `.env`, `sources/cache.json`, `gemini_usage.json`.
9. **Prova viva:** depois da madrugada, o diário 06:00 e o próximo tick BM `*/20` precisam completar. Não afirmar “pronto” só com unit test.

---

## Princípios de Execução

1. **Não quebrar o que funciona** — testes `scripts/test_*.py` no interpretador certo.
2. **Mudanças incrementais** — um plano pesado por noite.
3. **CLI estável** — `--date`, `--video-id`, `pipeline.py full`, `bm_mockup_video.py --pending`.
4. **Dois venvs** — pacote novo no braço que o usa. Não unificar.
5. **Sem dependência pesada nova na madrugada** (`librosa`/`pyworld` no HERMES_PY é decisão explícita, não efeito colateral do plano 02).
6. **Cota Gemini** — RPM ≠ RPD; 429 com `Please retry in Xs` ≤180s **não** é fim do dia; `exhausted_until` sem requests reais **não** queima a chave.
7. **FFmpeg TTS v2** — default de produção. `VALE_TTS_FFMPEG_CHAIN=v3` só opt-in.
