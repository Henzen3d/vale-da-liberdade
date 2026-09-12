# 00 — Diagnóstico Geral e Arquitetura Alvo (Gemini 3.8 Flash Edition)

> **Origem:** Auditoria Geral de Sistemas & Código (Setembro/2026)  
> **Status:** PLANEJADO — PRONTO PARA EXECUÇÃO MODULAR AO LONGO DA SEMANA  
> **Adaptação servidor:** 2026-09-02 — números e paths abaixo conferidos no disco. Não executar neste passo.  
> **Diretriz Suprema:** **Zero quebra em produção**. Nenhuma alteração disruptiva em lote. Preservar 100% dos fluxos diários do Jornal (06:00 BRT) e da esteira Brasil & Mundo (a cada 20 min).

---

## 1. Contexto do Projeto e Diagnóstico Geral

O **Web Jornal Vale da Liberdade** é um ecossistema autônomo de jornalismo hiperlocal e nacional com viés libertário, operado por IA. Ele opera dois produtos independentes em produção:

1. **🎙️ Produto 1: Diário do Vale (06:00 BRT)**
   - **Apresentadores:** Peter Albuquerque (anarcocapitalista) & Ricardo Souto (rádio dinâmico/rua).
   - **Pipeline:** Coleta RSS de Santa Catarina/Vale → Seleção IA → Roteiro com Gemini → TTS Multi-Locutor → Normalização Loudnorm → Upload Cloudflare R2 → Geração de Site Estático / Feed PWA.
   - **Disparo:** Job Hermes `74472bd658a5` chamando wrapper canônico em ambiente blindado (`HERMES_PY`).

2. **🎬 Produto 2: Brasil e Mundo (BM — a cada 20 min)**
   - **Apresentador:** Peter Albuquerque (solo).
   - **Pipeline:** Monitor de canais e feeds RSS → Fila de processamento (`queue.json`) → Transcrição de vídeos longos → Condensador em roteiro de 5 min → Áudio Gemini TTS → Renderizador de vídeo mockup-browser com Playwright Chromium + FFmpeg → Upload YouTube + R2.
   - **Disparo:** Job Hermes `aefe99598bbe` executando `bm-hourly-pipeline.sh` (`HERMES_PY` para áudio, `PROJECT_PY` para vídeo Playwright).

---

## 2. A Oportunidade: Gemini 3.8 Flash

O projeto cresceu organicamente usando modelos variados: `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, além de testes com `gemini-2.5-flash-preview-tts` e `gemini-3.1-flash-tts-preview`.

A chegada do **Gemini 3.8 Flash** (modelo de **texto**; TTS permanece 2.5/3.1) representa um salto qualitativo para roteiro/condensação. **Cotas RPM/RPD do 3.8 não estão em `sources/gemini_limits.json` ainda** — preencher na execução Dia 1 a partir do AI Studio, sem inventar 15/1500.

| Dimensão | Estado Atual (Legado) | Com Gemini 3.8 Flash |
|---|---|---|
| **Raciocínio & Síntese** | Roteiros gerados com modelos fragmentados, necessitando pós-processamento pesado (`naturalize_roteiro.py`) para evitar monotonia. | Capacidade analítica superior em português brasileiro, compreensão aprofundada de nuances libertárias e diálogos dinâmicos de rádio. |
| **Janela de Contexto** | Transcrições longas de 40 min precisavam ser fatiadas ou truncadas na entrada do condensador BM. | Contexto massivo nativo: absorve o vídeo/notícia bruto integralmente e gera síntese factual cirúrgica sem alucinações. |
| **Structured Outputs (JSON)** | Parsing frágil baseado em Regex (`re.search(r"```json...")`), sujeito a falhas de aspas e quebras de linha. | Resposta com schema JSON nativo rigoroso (`response_mime_type="application/json"`), garantindo 100% de conformidade com os modelos Pydantic. |
| **Latência & Custo** | Roteirização demorava 25-45s com risco de timeouts e retries desnecessários. | Tempo de resposta ultra-baixo, ideal para a esteira rápida de 20 minutos do Brasil e Mundo. |

---

## 3. Radiografia das Dívidas Técnicas ("Vibe Coding Empilhado")

A análise revelou inconsistências arquiteturais típicas de crescimento rápido sem refatoração periódica:

### ⚠️ A. Proliferação e Desordem em `scripts/` (139 arquivos no maxdepth 1; 103 `.py`)
- **21 arquivos `.sql`** misturados em `scripts/`: `01`–`18` (lacuna do `13_`) + `fix_admin_rpc.sql`, `fix_campaigns_rpc.sql`, `fix_interactions_rpc.sql`, `seed_test_data.sql`.
- **28 arquivos de teste soltos** em `scripts/` (`21 test_*.py` + `2 teste_*.py` + `1 check_*.py` + `4 qa_*`). A pasta raiz `tests/` tem **11** arquivos (não 9).
- **Scripts legados e zumbis mantidos na pasta de produção:** `faceless_*.py` (5), `clean_screenshot.py` (untracked), `youtube_video_generator.py`, wrappers obsoletos (`cron-daily.sh`, `cron-wrapper-v2.sh`, `daily-collect.sh`).

### ⚠️ B. Poluição Crítica e Risco de Segurança na Raiz do Projeto
- **OAuth YouTube:** **já isolado.** Não há `client_secret*.json` na raiz. Canônico: `credentials/client_secret.json` (e slots). `scripts/youtube_uploader.py` já aponta `CRED_DIR = ROOT / "credentials"`. `.gitignore` já tem `credentials/`. **Não republicar IDs de cliente nos planos.**
- **Binários pesados ainda na raiz (já no `.gitignore`):** `pt_BR-faber-medium.onnx`, `kokoro-v1.0.onnx`, `edge.mp3`, `piper.wav`.
- **Diretórios zumbis que AINDA existem:** `new-ux.backup-20260806/`, `thumbnail-generetor/`, `site/`, `kokoro_work/`, `test_output/`, `persona_suggestions/`.
- **Já ausentes (não tentar `mv`):** `new-ux/` (aposentada 2026-08-06), `BACKUP-web-jornal-vale-da-liberdade/`.
- **Scripts espelhados na raiz (existem):** `run_audio.py`, `run_pipeline_today.py`, `run_process.py`, `run_publish.py`, `process_today.py`, `serve.py`.
- **22 arquivos `.md` na raiz** (não 30+): preservar `README.md`, `CANONICAL.md`, `SYSTEM_MAP.md`, `SKILL.md`, `AGENT_GUIDE.md`, `LESSONS_LEARNED.md`, `PRD.md`, `ARCHITECTURE.md`/`ROADMAP.md` (banners históricos).

### ⚠️ C. Duplicação Massiva de Código (Copiar-Colar)
- Funções idênticas como `_candidate_keys`, `_call_gemini`, `_call_openrouter`, `extract_json` estão copiadas e coladas linha por linha em:
  - `scripts/generate_roteiro_llm.py`
  - `scripts/bm_condensador.py`
  - `scripts/title_optimizer.py`
  - `scripts/youtube_captions.py`
  - `scripts/thumbnail_generator.py`
- Qualquer ajuste de cota, timeout ou mudança de modelo obriga a alterar 5 arquivos manualmente, gerando divergências silenciosas.

### ⚠️ D. Monólitos Excessivamente Densos
- `bm_mockup_video.py` (1.749 linhas / 67 KB): mistura no mesmo arquivo um servidor HTTP em thread, automação Playwright Chromium, injeção de CSS em `mockup-brower.html`, cálculos de frame/tempo de áudio, geração de thumbnail e upload para o YouTube. Roda no **PROJECT_PY**.
- `pipeline.py` (1.111 linhas / 43 KB): orquestra desde raspagem de notícias até chamada de subshell, verificação de áudio e publicação de site. Roda no **HERMES_PY**. Sem flag `--dry-run`.

### ⚠️ E. Inconsistência de Observabilidade e Logging
- Parte dos scripts usa `logging.getLogger()`, parte usa `print()`, parte redireciona saídas em wrappers bash.
- Não há rotação ou política de retenção para os logs acumulados em `logs/`.
- Caches de notícias (`sources/cache.json`) com **2,6 MB** (2026-08-31) sem rotina de expurgo de matérias antigas. Já está no `.gitignore`.

### ✅ Dívidas Técnicas Já Quitadas pelo Plano de Otimização Python (10/09 e 11/09)
O [Plano de Otimização Python](../otimizacao-python/00-VISAO-GERAL.md) adiantou e eliminou gargalos operacionais críticos:
1. **Concorrência Gemini & Atomicidade:** `scripts/gemini_client.py` ganhou lock POSIX via `fcntl.flock` no `gemini_usage.json.lock`, `os.replace` atômico e `time.sleep` estritamente fora do lock. Diário e BM rodam simultaneamente sem colidir nem corromper arquivos.
2. **Crash CRLF / Exit 127:** Scripts `.sh` convertidos para LF e `.gitattributes` adicionado com `*.sh text eol=lf`.
3. **Loop Shell do Fallback Edge-TTS:** Substituído por `scripts/tts_fallback_edge.py` em 1 processo Python (`asyncio` + `Semaphore(3)`), vozes distintas (`Antonio` e `Francisca`) e concat FFmpeg v2.
4. **Gargalo de Regex e Lexicon:** `scripts/tts_preprocessor.py` teve todas as expressões e o lexicon regional pré-compilados em nível de módulo.
5. **Vazamento de Contexto no Mockup Playwright:** No fallback de `bm_mockup_video.py`, cada captura agora abre e fecha sua própria página (`ctx.new_page()` / `page.close()`), sem poluição de DOM entre matérias.
6. **Ads ∥ Thumb em Paralelo:** `pipeline.py` paralelizado com `ThreadPoolExecutor(max_workers=2)` na etapa de fechamento.
7. **Bootstrap Opt-in:** Criação de `scripts/_bootstrap.py` para detecção limpa de raiz e `.env`.

---

## 4. A Arquitetura Alvo (Target Architecture)

A meta da refatoração **NÃO É REESCREVER O SISTEMA DO ZERO**, mas sim modularizá-lo e aplicar boas práticas de engenharia de software de forma progressiva e não-destrutiva:

```
web-jornal-vale-da-liberdade/
├── core/                           # [NOVO] Camada compartilhada do sistema
│   ├── __init__.py
│   ├── gemini/                     # Cliente centralizado Gemini 3.8 Flash + rate limiter
│   │   ├── client.py
│   │   ├── rate_limiter.py
│   │   └── schemas.py              # Modelos estruturados de resposta (Pydantic)
│   ├── config.py                   # Carregador de variáveis de ambiente e caminhos canônicos
│   ├── logger.py                   # Logger estruturado padrão com timezone São Paulo
│   └── utils/                      # Utilitários de texto, sanitização de URL, data e áudio
│
├── database/                       # [NOVO] Migrações e governança de dados
│   └── migrations/                 # Os 21 arquivos .sql (01–18 + fix_* + seed)
│
├── scripts/                        # Ponto de entrada operacional (CLI e cron wrappers)
│   ├── cron-wrapper.sh             # Gatilho canônico Diário (Hermes 06:00, HERMES_PY)
│   ├── bm-hourly-pipeline.sh       # Gatilho canônico BM (Hermes */20; HERMES_PY áudio + PROJECT_PY vídeo)
│   ├── pipeline.py                 # Orquestrador Diário (fachada para core)
│   ├── bm_pipeline.py              # Orquestrador BM
│   ├── bm_mockup_video.py          # Renderizador modularizado
│   ├── generate_gemini_tts_multi.py# Motor TTS Gemini
│   ├── publish_site.py             # Publicador de catálogo e feeds RSS
│   └── archive_legacy/             # Scripts aposentados devidamente isolados
│
├── tests/                          # Suíte unificada de testes (Pytest)
│   ├── unit/                       # Testes de unidade sem chamadas reais de API
│   ├── integration/                # Testes de integridade de schemas e JSONs
│   └── regression/                 # Testes de não-regressão dos cron wrappers
│
├── credentials/                    # Armazenamento isolado de OAuth e segredos (.gitignore)
├── public/                         # Fonte única da verdade do portal estático/PWA
├── episodes/                       # Roteiros e metadados diários
├── output/                         # Saídas do pipeline Brasil e Mundo
└── docs/plans/                     # Planos de governança e evolução
```

---

## 5. Matriz dos Planos de Execução Semanal

Para garantir segurança total, a refatoração foi dividida em documentos executáveis individualmente:

| Documento | Tema Principal | Risco | Meta |
|---|---|---|---|
| [`01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md`](./01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md) | Adoção do Gemini 3.8 Flash nos motores de roteiro e BM | Baixo | Elevação drástica de qualidade editorial e velocidade |
| [`02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md`](./02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md) | Limpeza de segredos, binários pesados e backups zumbis | Quase zero | Segurança, higiene e leveza do repositório |
| [`03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md`](./03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md) | Migração de SQLs, isolamento de testes e código legado | Baixo | Descongestionar `scripts/` de **139** para ~25 arquivos vitais |
| [`04-REFATORACAO-SEGURA-DOS-MONOLITOS.md`](./04-REFATORACAO-SEGURA-DOS-MONOLITOS.md) | Decomposição de `bm_mockup_video.py` (absorve Plano 08) e `pipeline.py` | Médio | Fatiar monólitos sem alterar CLI de produção |
| [`05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md`](./05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md) | Schemas Pydantic, logger padronizado e purge de cache | Baixo | Eliminar parsing manual frágil e vazamentos de disco |
| [`06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md`](./06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md) | Bateria de testes Pytest com mocks locais | Zero | Garantir que nenhuma alteração futura quebre o jornal |
| [`07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md`](./07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md) | Guia prático dia a dia com rollback gates | Zero | Roteiro passo a passo para o desenvolvedor executar |

---

## 6. Regras de Ouro da Execução

1. **Testar antes de commitar:** Nenhum arquivo de produção é alterado sem teste de compilação estática (`py_compile`) e teste de importação.
2. **Preservar a linha de comando:** Wrappers e scripts CLI (`pipeline.py full`, `bm_pipeline.py process-queue`) devem manter rigorosamente os mesmos argumentos e códigos de saída (`exit codes`).
3. **Rollback imediato se o diário oscilar:** Se o ciclo das 06:00 BRT apresentar qualquer falha, o rollback da fase anterior é executado em menos de 5 minutos.
