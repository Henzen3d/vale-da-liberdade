# SYSTEM_MAP — Web Jornal Vale da Liberdade

> **Documentação Viva do Sistema & Grafo de Dependências**  
> Gerado após Auditoria dos Sistemas Vitais (31/08/2026)  
> Mantido por: Antigravity / Hermes Agent  

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
   │ (Diário - 06:00 UTC)      │               │ (Horário - Fila BM)       │
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

## 2. Mapa Completo de Scripts e Gatilhos

| Script Principal | Gatilho / Chamador | Entrada | Saída | Dependências |
|---|---|---|---|---|
| `scripts/pipeline.py` | `cron-wrapper-v2.sh` (06:00 UTC) ou manual | `--date YYYY-MM-DD` | `raw-{date}.md`, `{date}.md`, `{date}-tts.txt`, MP3 | Gemini TTS API, ffmpeg |
| `scripts/news_collector.py` | `pipeline.py init` / `cmd_collect` | `sources/sources.json`, `sources/cache.json` | Lista de notícias filtradas por hash | feedparser, requests, playwright (fallback) |
| `scripts/ai_news_filter.py` | `pipeline.py init` | Artigos coletados | Notícias agrupadas por quadro (determinístico) | MinHash, TF-IDF |
| `scripts/generate_roteiro_llm.py` | `pipeline.py process` / `full` | `episodes/raw-{date}.md` | `episodes/roteiro-{date}.json` | Gemini API / OpenRouter |
| `scripts/tts_preprocessor.py` | `pipeline.py process` | `episodes/roteiro-{date}.json` | `episodes/{date}-tts.txt`, `manchetes.txt`, `{date}-metadata.json` | Python nativo (regex) |
| `scripts/generate_gemini_tts_multi.py` | `pipeline.py audio` | `episodes/{date}-tts.txt` | `audio/{date}-vale-da-liberdade.mp3` | Gemini Audio Modality, ffmpeg |
| `scripts/publish_site.py` | `pipeline.py full` / manual | `episodes/`, `audio/` | `public/data/episodes.json`, `feed.xml`, R2 upload | boto3, Cloudflare R2 |
| `scripts/upload_r2.py` | `publish_site.py` / `batch_upload_r2.py` | Arquivos MP3/JPG | R2 Bucket + `episodes/{date}-r2.json` | boto3 |
| `scripts/bm_monitor.py` | `bm-hourly-pipeline.sh` (horário) | RSS do canal YouTube | `pipelines/brasil_e_mundo/queue.json` | feedparser |
| `scripts/bm_pipeline.py` | `bm-hourly-pipeline.sh` ou `--youtube-url` | Fila BM ou URL manual | Roteiro BM + Áudio MP3 + `public/data/episodes-bm.json` | Gemini Flash, TTS |
| `scripts/bm_enrich_sources.py` | `bm_pipeline.py` / `bm_condensador.py` | Fontes YouTube / RSS / Tavily | Fontes estritamente relevantes com deduplicação | feedparser, Tavily API, Gemini |
| `scripts/bm_scene_timeline.py` | `bm_mockup_video.py` | Cues de áudio / fontes | Timeline com gancho 15s e >=10 cenas/5min | Python nativo |
| `scripts/bm_broll_fetcher.py` | `bm_mockup_video.py` / manual | Palavras-chave / tema | Clipes 1080p MP4 em `references/youtube/broll/` | Pexels API, Pixabay API, ffmpeg |
| `scripts/bm_mockup_video.py` | `bm-hourly-pipeline.sh` | Especial BM (`especial-*.json`) + MP3 | MP4 1080p + Upload YouTube | Playwright, ffmpeg, YouTube API |
| `scripts/youtube_uploader.py` | `bm_mockup_video.py` | Arquivo MP4 + Metadados | Vídeo publicado no YouTube | `google-api-python-client` |
| `scripts/thumbnail_generator.py` | `publish_site.py` / manual | Notícia principal / Episódio | `thumbnails/{date}/{id}.webp` | Pillow, DashScope / Imagen 4 |
| `scripts/hermes_youtube_thumbnail.py` | `bm_mockup_video.py` / manual | Vídeo ID + Título + Highlight | Capa 1280x720 (Peter Presenter) | Playwright / HTML template |


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
| `PEXELS_API_KEY` | Recomendada | Download de B-rolls gratuitos em 1080p para o pipeline de vídeo |
| `PIXABAY_API_KEY` | Recomendada | Download de stock footage gratuito para apoio visual |
| `TAVILY_API_KEY` | Opcional | Busca web precisa e factual de fontes de notícias complementares |

---

## 5. Regras de Continuidade para Novos Agentes e IAs

1. **Nunca editar episódios históricos:** Arquivos em `episodes/` anteriores à data de hoje nunca devem ser renomeados ou deletados.
2. **Nunca alterar o corpo de insert do YouTube sem checar cotas:** A cota padrão é 10.000 unidades (máx 6 vídeos/dia).
3. **Respeitar o isolamento de TTS:** O Gemini TTS é o motor de áudio canônico. Não alterar o mapeamento de vozes (`Charon` = Peter, `Schedar` = Ricardo) sem aprovação.
4. **Usar sempre o wrapper canônico:** No cron do sistema operacional, utilizar apenas `scripts/cron-wrapper-v2.sh` para o jornal diário e `scripts/bm-hourly-pipeline.sh` para Brasil & Mundo.
