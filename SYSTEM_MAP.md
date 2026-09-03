# SYSTEM_MAP — Web Jornal Vale da Liberdade

> **Documentação viva** (Dia 3, 2026-09-02). Espelha as tabelas canônicas de `docs/INDEX.md`.  
> Não é spec de layout (`docs/BM-VIDEO-LAYOUT.md`) nem inventário histórico (`docs/PIPELINE_SCRIPTS_INVENTORY.md`).  
> Gerado após Auditoria dos Sistemas Vitais (31/08/2026); matriz VIVO/MORTO atualizada no Plano 03.  
> Mantido por: Hermes Agent  

---

## 1. Visão Geral dos Subsistemas

```
                      ┌─────────────────────────────────┐
                      │    FONTES EXTERNAS / ENTRADA    │
                      │  - 14 Feeds RSS Regionais       │
                      │  - Web Scraping & WordPress API │
                      │  - X/Twitter (x_collector)      │
                      │  - YouTube RSS (Brasil & Mundo) │
                      └────────────────┬────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
                 ▼                                           ▼
   ┌───────────────────────────┐               ┌───────────────────────────┐
   │ 🎙️ CORE AUDIO WEBJORNAL   │               │ 🎬 BRASIL & MUNDO (VÍDEO) │
   │ (Diário - 06:00 BRT)      │               │ (Horário - Fila BM)       │
   │                           │               │                           │
   │ 1. news_collector.py      │               │ 1. bm_monitor.py          │
   │ 2. ai_news_filter.py      │               │ 2. bm_pipeline.py         │
   │ 3. generate_roteiro_llm.py│               │ 3. bm_condensador.py      │
   │ 4. tts_preprocessor.py    │               │ 4. bm_enrich_sources.py   │
   │ 5. generate_gemini_tts    │               │ 5. bm_mockup_video.py     │
   │ 6. publish_site.py        │               │ 6. youtube_uploader.py    │
   └─────────────┬─────────────┘               └─────────────┬─────────────┘
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │   DISTRIBUIÇÃO & INFRAESTRUTURA │
                      │  - Cloudflare R2 (Áudios/Imgs)  │
                      │  - YouTube Data API v3          │
                      │  - Nginx + Static Site (Astro)  │
                      │  - Supabase (Analytics & Ads)   │
                      └─────────────────────────────────┘
```

---

## 1.1 Matriz canônica VIVO / MORTO

### VIVO (produção — não mexer sem teste)

| Subsistema | Fluxo canônico | Arquivos principais |
|---|---|---|
| Diário (06:00 America/Sao_Paulo) | Coleta → Roteiro → TTS Multi → Publicação | `scripts/pipeline.py`, `scripts/news_collector.py`, `scripts/generate_roteiro_llm.py`, `scripts/generate_script.py`, `scripts/tts_preprocessor.py`, `scripts/generate_gemini_tts_multi.py`, `scripts/publish_site.py`, `scripts/upload_r2.py` |
| Brasil & Mundo | Monitor RSS → Fila → Mockup vídeo → Upload YT | `scripts/bm_monitor.py`, `scripts/bm_pipeline.py`, `scripts/bm_condensador.py`, `scripts/bm_enrich_sources.py`, `scripts/bm_mockup_video.py`, `scripts/youtube_uploader.py` |
| Screenshots jornalísticos | Motor modular + handlers por domínio. Cache `CAPTURE_CACHE_VERSION=handler-v3`. Handlers antes do Playwright genérico (não aninhar). Agência Brasil/EBC: `sites/agenciabrasil.py`. Prints nas URLs originais (Chromium); `blocked-page-recovery` não entra no vídeo. | `scripts/screenshots/base.py`, `scripts/screenshots/runner.py`, `scripts/screenshots/sites/`. Chamada: `try_handler_screenshot` em `bm_mockup_video.py`. Não existe `scripts/screenshots/core/`. |
| Thumbnails | Papéis distintos, ambos vivos | Diário: `scripts/thumbnail_generator.py`. Produção BM: `scripts/youtube_thumbnail.py` (importado por `bm_mockup_video.find_episode_thumbnail` → `generate_youtube_thumbnail`). CLI manual/auxiliar: `scripts/hermes_youtube_thumbnail.py` (não é o import do mockup). |
| Gatilhos oficiais | Wrappers de execução | `scripts/cron-wrapper.sh` (diário, job Hermes `no_agent`). `scripts/bm-hourly-pipeline.sh` (BM). |

### MORTO / LEGADO (no papel — arquivos **não** apagados)

| Componente | Motivo | Ação |
|---|---|---|
| `scripts/bm_video_autopilot.py` | Substituído por `bm-hourly-pipeline.sh` + `bm_mockup_video.py` | Job Hermes pausado; legado |
| `scripts/faceless_*.py` | Prova de conceito 22/08 (autopilot não ativado) | Legado |
| `scripts/youtube_video_generator.py` | Renderizador de geração anterior | Legado |
| `references/youtube/prototype/` | Protótipo HyperFrames bancada-render | Só referência de design |
| `scripts/clean_screenshot.py` | Órfão monolítico; canônico = `scripts/screenshots/` | Isolado no papel |
| `thumbnail-generetor/` | Pasta aninhada com typo e código legado | Isolado no papel |
| `scripts/cron-wrapper-v2.sh`, `scripts/cron-daily.sh`, `scripts/daily-collect.sh` | Wrappers antigos; diário oficial = `cron-wrapper.sh` via Hermes | Obsoletos |

Skill Hermes canônica: `~/.hermes/skills/content/web-jornal-production` (não a cópia em `~/.hermes/skills/web-jornal-production`).

---

## 2. Mapa Completo de Scripts e Gatilhos

| Script Principal | Gatilho / Chamador | Entrada | Saída | Dependências |
|---|---|---|---|---|
| `scripts/pipeline.py` | `cron-wrapper.sh` via Hermes `no_agent` (06:00 America/Sao_Paulo) ou manual | `--date YYYY-MM-DD` | `raw-{date}.md`, `{date}.md`, `{date}-tts.txt`, MP3 | Gemini TTS API, ffmpeg |
| `scripts/news_collector.py` | `pipeline.py init` / `cmd_collect` | `sources/sources.json`, `sources/cache.json` | Lista de notícias filtradas por hash | feedparser, requests, playwright (fallback) |
| `scripts/ai_news_filter.py` | `pipeline.py init` | Artigos coletados | Notícias agrupadas por quadro (determinístico) | MinHash, TF-IDF |
| `scripts/generate_roteiro_llm.py` | `pipeline.py process` / `full` | `episodes/raw-{date}.md` | `episodes/roteiro-{date}.json` | Gemini API / OpenRouter |
| `scripts/tts_preprocessor.py` | `pipeline.py process` | `episodes/roteiro-{date}.json` | `episodes/{date}-tts.txt`, `manchetes.txt`, `{date}-metadata.json` | Python nativo (regex) |
| `scripts/generate_gemini_tts_multi.py` | `pipeline.py audio` | `episodes/{date}-tts.txt` | `audio/{date}-vale-da-liberdade.mp3` | Gemini Audio Modality, ffmpeg |
| `scripts/publish_site.py` | `pipeline.py full` / manual | `episodes/`, `audio/` | `public/data/episodes.json`, `feed.xml`, R2 upload | boto3, Cloudflare R2 |
| `scripts/upload_r2.py` | `publish_site.py` / `batch_upload_r2.py` | Arquivos MP3/JPG | R2 Bucket + `episodes/{date}-r2.json` | boto3 |
| `scripts/bm_monitor.py` | `bm-hourly-pipeline.sh` (horário) | RSS do canal YouTube | `pipelines/brasil_e_mundo/queue.json` | feedparser |
| `scripts/bm_pipeline.py` | `bm-hourly-pipeline.sh` | Fila BM | Roteiro BM + Áudio MP3 + `public/data/episodes-bm.json` | Gemini Flash-lite, TTS |
| `scripts/bm_mockup_video.py` | `bm-hourly-pipeline.sh` | Especial BM (`especial-*.json`) + MP3 | MP4 1080p + Upload YouTube | Playwright, ffmpeg, YouTube API |
| `scripts/youtube_uploader.py` | `bm_mockup_video.py` | Arquivo MP4 + Metadados | Vídeo publicado no YouTube | `google-api-python-client` |
| `scripts/thumbnail_generator.py` | `publish_site.py` / manual | Notícia principal / Episódio | `thumbnails/{date}/{id}.webp` | Pillow, DashScope / Imagen 4 |
| `scripts/youtube_thumbnail.py` | `bm_mockup_video.find_episode_thumbnail` → `generate_youtube_thumbnail` | Episódio BM + imagem editorial | Capa 1280x720 de produção | Pillow / HTML card |
| `scripts/hermes_youtube_thumbnail.py` | CLI manual/auxiliar (não é o import do mockup) | Vídeo ID + Título + Highlight | Capa 1280x720 (Peter Presenter) | Playwright / HTML template |

---

## 3. Matriz de Caches, Dados e Storage

| Arquivo / Diretório | Formato | Volume Atual | Política de Retenção |
|---|---|---|---|
| `sources/cache.json` | JSON | ~2.69 MB | URLs e hashes com TTL de 14 dias (sujeito a pruning). |
| `sources/sources.json` | JSON | ~11 KB | Configuração estática de fontes RSS/Scraping ativas. |
| `sources/sources_registry.json` | JSON | ~38 KB | Registro histórico de credibilidade de fontes. |
| `pipelines/brasil_e_mundo/seen_videos.json` | JSON | ~69 KB | IDs de vídeos do YouTube já processados pela esteira BM. |
| `pipelines/brasil_e_mundo/queue.json` | JSON | ~1 KB | Fila ativa de processamento pendente BM. |
| `episodes/` | MD, JSON, TXT | 760+ arquivos | **Imutável.** Histórico de roteiros e metadados diários. |
| `audio/` | MP3, WAV | Dinâmico | Arquivos locais de áudio renderizados. |
| `public/audio/` | MP3 | Dinâmico | Espelho estático servido pelo Nginx. |
| `thumbnails/` | WEBP, JPG | Dinâmico | Capas de episódios locais e espelho de CDN. |

---

## 4. Variáveis de Ambiente Críticas

| Variável | Obrigatoriedade | Propósito |
|---|---|---|
| `GEMINI_API_KEY` | **Obrigatória** | Síntese de voz TTS multi-locutor e geração de roteiros |
| `R2_ACCOUNT_ID` | **Obrigatória** | Identificador da conta Cloudflare R2 |
| `R2_ACCESS_KEY_ID` | **Obrigatória** | Chave de acesso S3 para upload no R2 |
| `R2_SECRET_ACCESS_KEY` | **Obrigatória** | Chave secreta S3 para upload no R2 |
| `R2_BUCKET_NAME` | **Obrigatória** | Nome do bucket (`web-jornal-liberdade`) |
| `R2_PUBLIC_DOMAIN` | Recomendada | Domínio público CDN para servir áudios e imagens |
| `SITE_URL` | Recomendada | URL base do portal (`https://news.mob.tec.br`) |
| `SUPABASE_URL` | Opcional | URL da instância Supabase para analytics/ads |
| `SUPABASE_ANON_KEY` | Opcional | Chave anônima para interações do cliente |
| `X_USERNAME` / `X_PASSWORD` | Opcional | Credenciais para o coletor do X (Twitter) |

---

## 5. Regras de Continuidade para Novos Agentes e IAs

1. **Nunca editar episódios históricos:** Arquivos em `episodes/` anteriores à data de hoje nunca devem ser renomeados ou deletados.
2. **Nunca alterar o corpo de insert do YouTube sem checar cotas:** A cota padrão é 10.000 unidades (máx 6 vídeos/dia).
3. **Respeitar o isolamento de TTS:** O Gemini TTS é o motor de áudio canônico. Não alterar o mapeamento de vozes (`Charon` = Peter, `Schedar` = Ricardo) sem aprovação.
4. **Usar sempre o wrapper canônico:** Diário = `scripts/cron-wrapper.sh` via job Hermes `no_agent` (não o crontab do host; não `cron-wrapper-v2.sh`). BM = `scripts/bm-hourly-pipeline.sh`.
