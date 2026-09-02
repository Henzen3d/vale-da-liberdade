# Índice de documentação

Root do repo: `/home/osmar/web-jornal-vale-da-liberdade`  
Path canônico: ver `../CANONICAL.md`.

Leia `CANONICAL.md` e `../AGENT_GUIDE.md` antes de qualquer outro doc.

## Vigente

| Arquivo | Uso |
|---|---|
| `CANONICAL.md` | Path único do projeto. Leia primeiro. |
| `README.md` | Visão atual do produto (ago/2026) |
| `PRD.md` | Missão e escopo do produto (não é spec técnica) |
| `AGENT_GUIDE.md` | Ordem de leitura para agentes |
| `SKILL.md` | Regras de **voz e roteiro do diário** (Peter/Ricardo, quadros, checklist). **Não** é cópia nem espelho de `~/.hermes/skills/content/web-jornal-production/`. Essa skill Hermes descreve o pipeline operacional de produção; `SKILL.md` na raiz é só editorial do episódio diário. |
| `pipelines/brasil_e_mundo/SKILL_BRASIL_E_MUNDO.md` | Regras do especial (um narrador, isolado do diário) |
| `LESSONS_LEARNED.md` | Incidentes e decisões (inclui ago/2026) |
| `DESIGN.md` | Decisões de design de UI/UX do site (menus, abas, hero, player, tokens, regras anti-regressão) — editável manualmente |
| `presenters/peter.md` / `presenters/ricardo.md` | Fichas dos apresentadores |
| `docs/ROTEIRO-NATURALIDADE-MULTILOCUTOR.md` | Relatório + diagramas do pipeline de roteiro/TTS para análise externa (naturalidade + multi-locutor) |
| `docs/BM-VIDEO-LAYOUT.md` | Layout oficial do vídeo BM (avatar v6, wallpaper, thumbnail, descrição). Restaurar daqui se o compositor sumir. JSON: `docs/bm-video-layout.json` |
| `docs/BM-EPISODE-PACING.md` | Ritmo, duração (4–5 min / 680–900 palavras), fontes extras, sync de cenas, captura educada e b-roll |

Skills Hermes (fora deste repo; não duplicar aqui):

- `web-jornal-production` — produção diária / B&M. Canônica: `~/.hermes/skills/content/web-jornal-production` (não a cópia em `~/.hermes/skills/web-jornal-production`).
- `web-jornal-frontend` — player e UX em `public/`

## Mapa canônico — VIVO (produção)

Não mexer nestes fluxos sem teste. Paths relativos à raiz do repo.

| Subsistema | Fluxo canônico | Arquivos principais |
|---|---|---|
| Diário (06:00 America/Sao_Paulo) | Coleta → Roteiro → TTS Multi → Publicação | `scripts/pipeline.py`, `scripts/news_collector.py`, `scripts/generate_roteiro_llm.py`, `scripts/generate_script.py`, `scripts/tts_preprocessor.py`, `scripts/generate_gemini_tts_multi.py`, `scripts/publish_site.py`, `scripts/upload_r2.py` |
| Brasil & Mundo | Monitor RSS → Fila → Mockup vídeo → Upload YT | `scripts/bm_monitor.py`, `scripts/bm_pipeline.py`, `scripts/bm_condensador.py`, `scripts/bm_enrich_sources.py`, `scripts/bm_mockup_video.py`, `scripts/youtube_uploader.py` |
| Screenshots jornalísticos | Motor modular + handlers por domínio. Cache `CAPTURE_CACHE_VERSION=handler-v2`. Agência Brasil/EBC: `scripts/screenshots/sites/agenciabrasil.py`. Prints = Chromium headless nas URLs originais via `bm_mockup_video.try_handler_screenshot` — **não** via `blocked-page-recovery` (`recover_page.py` é só texto de pauta/roteiro). | `scripts/screenshots/base.py`, `scripts/screenshots/runner.py`, `scripts/screenshots/sites/`. Não existe `scripts/screenshots/core/`. |
| Thumbnails | Papéis distintos, ambos vivos | Diário: `scripts/thumbnail_generator.py`. Produção BM: `scripts/youtube_thumbnail.py` (importado por `bm_mockup_video.find_episode_thumbnail` → `generate_youtube_thumbnail`). CLI manual/auxiliar: `scripts/hermes_youtube_thumbnail.py` (não é o import do mockup). |
| Gatilhos oficiais | Wrappers de execução | `scripts/cron-wrapper.sh` (diário, job Hermes `no_agent`). `scripts/bm-hourly-pipeline.sh` (BM). |

## Mapa canônico — MORTO / LEGADO (no papel)

Arquivos **não apagados**. Não ligar, não otimizar, não tratar como spec.

| Componente | Motivo | Ação |
|---|---|---|
| `scripts/bm_video_autopilot.py` | Substituído por `bm-hourly-pipeline.sh` + `bm_mockup_video.py` | Job Hermes pausado; legado |
| `scripts/faceless_*.py` | Prova de conceito 22/08 (autopilot não ativado) | Legado |
| `scripts/youtube_video_generator.py` | Renderizador de geração anterior | Legado |
| `references/youtube/prototype/` | Protótipo HyperFrames bancada-render | Só referência de design |
| `scripts/clean_screenshot.py` | Órfão monolítico; canônico = `scripts/screenshots/` | Isolado no papel |
| `thumbnail-generetor/` | Pasta aninhada com typo e código legado | Isolado no papel |
| `scripts/cron-wrapper-v2.sh`, `scripts/cron-daily.sh`, `scripts/daily-collect.sh` | Wrappers antigos; diário oficial = `cron-wrapper.sh` via Hermes | Obsoletos |

Hierarquia de docs: `CANONICAL.md` + este `docs/INDEX.md` + `docs/BM-VIDEO-LAYOUT.md` (só layout visual) + skill `content/web-jornal-production`. `SYSTEM_MAP.md` espelha as tabelas acima.

## Histórico — não tratar como estado vigente

Estes documentos descrevem o pipeline de junho/2026 (`episodes/` → `archive/index.md`) ou planos daquela época. Conservar; não usar como spec do site atual.

| Arquivo (arquivado) | Uso original |
|---|---|
| `docs/archive/2026-06-pipeline/README.md` | README de 22/06 (quick start `pipeline.py`) |
| `docs/archive/2026-06-pipeline/ARCHITECTURE.md` | Fluxo junho: raw → roteiro → TTS → `archive/index.md` |
| `docs/archive/2026-06-pipeline/PRD.md` | PRD completo de 20/06 (requisitos, métricas, roadmap) |
| `docs/archive/2026-06-pipeline/ROADMAP.md` | Fases 0–6 de junho |
| `docs/archive/2026-06-pipeline/TARGET_ARCHITECTURE.md` | Arquitetura-alvo de junho |
| `docs/archive/2026-06-pipeline/REVIEW.md` | Auditoria de 20/06 |
| `docs/archive/2026-06-pipeline/plan.md` / `plan02.md` | Planos pontuais de junho |
| `docs/archive/2026-06-pipeline/IMPLEMENTATION_EXAMPLES.md` | Exemplos daquele roadmap |
| `docs/archive/2026-06-pipeline/prompt.md` | Prompt paralelo ao `SKILL.md` (redundante) |
| `docs/archive/2026-06-pipeline/*_TEST_REPORT.md` | Relatórios de teste de modelo (não são spec) |
| `docs/archive/2026-06-pipeline/site/` | Player proto de junho (`site/index.html`) |
| `docs/archive/2026-06-pipeline/handoffs/2026-06-16-x-collector.md` | Handoff do coletor X |

Outros:

| Path | Uso |
|---|---|
| `ARCHITECTURE.md` (raiz) | Conceitual junho/2026 — **histórico / arquivo** |
| `ROADMAP.md` (raiz) | Fases 0–6 de junho — **histórico / arquivo** |
| `docs/PIPELINE_SCRIPTS_INVENTORY.md` | Inventário 15/08 com crontab antigo — **histórico / arquivo** |
| `news_urls.md` | Lista antiga de URLs; fontes vigentes em `sources/sources.json` |
| `references/youtube/` | Prototype HyperFrames / quadros |
| `YOUTUBE_PIPELINE_MAP.md` | Rascunho untracked; não é spec |
| `~/.hermes/skills/content/web-jornal-production/references/` | Referências operacionais da skill de produção |

## Arquivos que o site precisa em `public/`

Sem isto o anônimo mostra “Sem conexão” e some o login:

- `public/js/supabase_client.js` — botão Entrar / Google
- `public/data/episodes.json` — catálogo do feed
- `public/assets/js/{theme,wakeLock,listen_progress,ad_manager,interaction_bar,orientation_lock}.js`

CSS referenciado por `public/index.html` (restaurado em 14/08 a partir de `new-ux.backup-20260806/`):

- `public/assets/css/{tokens,base,components,audio-wave}.css`

SW (`public/sw.js`) precacheia `./offline.html`.

Regra: **não criar outro README ou outro CANONICAL fora desta árvore.** Não apagar `public/js/` nem `public/data/`.
