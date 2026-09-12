# 🧭 Suíte de Planos — Refatoração e Modernização com Gemini 3.8 Flash

> **Projeto:** Web Jornal Vale da Liberdade  
> **Data de Elaboração:** Setembro / 2026  
> **Status:** FASE 2 — Sequencial e Posterior ao [Plano de Otimização Python](../otimizacao-python/00-VISAO-GERAL.md)  
> **Alinhamento do Host:** 2026-09-11 (validado após execução da noite de 10/09 e sucesso do diário 06:00 de 11/09)  
> **Diretriz Geral:** **Zero quebra em produção**. Não executar mudanças em lote. Preservar 100% dos fluxos diários do Jornal (06:00 BRT) e da esteira de vídeos do Brasil & Mundo (a cada 20 min).

---

## 🔗 Relação com o Plano de Otimização Python (`docs/plans/otimizacao-python`)

Esta suíte de refatoração foi projetada para ser executada **imediatamente após a consolidação do Plano de Otimização Python**.

### ✅ O Que Já Foi Resolvido pela Otimização Python (10/09/2026):
1. **CRLF & .gitattributes (Item 00):** Shebangs `.sh` saneados para LF; `.gitattributes` travando `*.sh text eol=lf`. Erro 127 eliminado do cron.
2. **Gemini Concorrência & Lock POSIX (Item 06):** Implementado `fcntl.flock` com timeout de 5s em `gemini_usage.json.lock`, `os.replace` atômico e `time.sleep` fora do lock. Diário e BM não colidem mais cotas no JSON.
3. **Fallback Edge-TTS em Python (Item 02):** `scripts/tts_fallback_edge.py` implementado em 1 processo Python com `asyncio`, `Semaphore(3)`, vozes distintas (`AntonioNeural` e `FranciscaNeural`) e concat FFmpeg v2. `tts_fallback_edge.sh` virou wrapper LF limpo.
4. **Regex & Lexicon Pré-compilados (Item 05):** `tts_preprocessor.py` com regexes compilados a nível de módulo e lexicon regional carregado uma única vez.
5. **Padronização HTTP & TLS (Item 03):** `http_fetch.py` com `fetch_html_async` (TLS ligado) e `news_collector.py` usando `fetch_html` seguro (sem `verify=False`).
6. **Cache LRU Seguro (Item 07):** `@lru_cache` aplicado em `load_config()` e `get_episode_number()`.
7. **Ads ∥ Thumb em Paralelo (Item 10):** `pipeline.py` rodando anúncio e thumbnail em paralelo via `ThreadPoolExecutor(max_workers=2)`.
8. **Bootstrap Opt-in (Item 09):** Criação de `scripts/_bootstrap.py` (paths e dotenv sem dependências externas).
9. **Isolamento de Páginas no Mockup (Item 01 Fase A):** `bm_mockup_video.py` abrindo e fechando páginas limpas (`ctx.new_page()` + `page.close()`) no lote de fallback.

### 🎯 O Que Foi Repassado para Esta Suíte Executar:
- **Plano 08 de Otimização (Modularização de `bm_mockup_video.py`):** Foi expressamente adiado na madrugada de 10/09 para não concorrer com o cron do BM. Ele é absorvido e executado integralmente no **Documento 04** desta suíte.
- **Adoção do Bootstrap (Plano 09):** Conectar os scripts à infraestrutura `_bootstrap.py` / `core/` unificada.
- **Title ∥ Description Paralelos (Plano 10):** Com o flock testado, colocar as etapas 2.5 e 2.6 em paralelo no Diário.
- **Modernização de Texto com Gemini 3.8 Flash (Documento 01):** Roteiros e condensação com structured outputs nativos sobre o cliente já protegido por flock.
- **Saneamento Estrutural e Arquitetura Limpa (Documentos 02, 03, 05, 06):** Limpeza da raiz, isolamento de SQLs em `database/migrations/`, consolidação de testes em `tests/` e schemas Pydantic.

---

## Ambiente canônico deste servidor (não inventar)

No host de produção vale **somente** isto:

| Item | Valor real em disco (2026-09-11) |
|---|---|
| Repo | `/home/osmar/web-jornal-vale-da-liberdade` |
| `HERMES_PY` (feed, LLM, TTS, diário, `bm_monitor`/`bm_pipeline`) | `/home/osmar/.hermes/hermes-agent/venv/bin/python3` (CPython 3.11) |
| `PROJECT_PY` (Playwright, `bm_mockup_video`, upload YT, pytest) | `/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3` (CPython 3.14) |
| `python` no PATH | **não existe** — nunca usar `python`; usar o venv do braço (`HERMES_PY` ou `PROJECT_PY`) |
| Job diário 06:00 | Hermes `74472bd658a5`, `no_agent=true`, shim `~/.hermes/scripts/vale-daily-cron-wrapper.sh` → `scripts/cron-wrapper.sh` |
| Job BM */20 | Hermes `aefe99598bbe`, `no_agent=true`, `scripts/bm-hourly-pipeline.sh` |
| TTS (fora do escopo 3.8 Flash) | Diário: `gemini-2.5-flash-preview-tts` PACKED; BM: `gemini-3.1-flash-tts-preview`. 3.8 Flash é modelo de **texto**, não substitui TTS. |
| Chaves Gemini | Só `$PROJ/.env` (`GEMINI_API_KEY` … `_7`). **Não** misturar `~/.hermes/.env`. |
| pytest | Instalado **só** no `.venv` do projeto (9.1.1). Ausente no venv Hermes. |
| pydantic | Presente nos dois venvs (2.13.4). |

Qualquer comando `python …` nestes planos deve ser lido como `HERMES_PY` (texto/áudio) ou `PROJECT_PY` (vídeo/teste). Nunca republicar episódio com `--force` / `--date` de dia já no ar.

---

## 📂 Índice dos Documentos da Suíte (Fase 2)

| Arquivo | Título | Objetivo Resumido |
|---|---|---|
| [`00-DIAGNOSTICO-E-ARQUITETURA-ALVO.md`](./00-DIAGNOSTICO-E-ARQUITETURA-ALVO.md) | **Diagnóstico Geral e Arquitetura Alvo** | Raio-X completo das dívidas técnicas, o que a otimização já sanou e visão da nova arquitetura. |
| [`01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md`](./01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md) | **Modernização com Gemini 3.8 Flash** | Especificação da adoção do modelo 3.8 Flash nos roteiros do Diário, síntese do BM e Structured Outputs JSON. |
| [`02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md`](./02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md) | **Saneamento da Raiz e Segurança** | Isolamento do OAuth em `credentials/`, expurgo de binários ONNX de 63MB, scripts duplicados da raiz e pastas zumbis. |
| [`03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md`](./03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md) | **Organização Modular de Scripts e Core** | Descongestionamento de `scripts/` (139 arquivos), migração dos 21 SQLs para `database/` e criação da camada `core/`. |
| [`04-REFATORACAO-SEGURA-DOS-MONOLITOS.md`](./04-REFATORACAO-SEGURA-DOS-MONOLITOS.md) | **Refatoração Segura dos Monólitos** | Decomposição em camadas de `bm_mockup_video.py` (absorvendo Plano 08 de Otimização) e `pipeline.py` via Padrão Fachada. |
| [`05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md`](./05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md) | **Schemas Pydantic, Logging e Cache** | Contratos de dados tipados, logging estruturado com timezone `America/Sao_Paulo` e saneamento do `sources/cache.json`. |
| [`06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md`](./06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md) | **Suíte de Testes e Qualidade** | Consolidação de testes unitários e de integração com `pytest`, mocks de API e validação estática de wrappers shell. |
| [`07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md`](./07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md) | **Cronograma Semanal e Checklist** | Roteiro passo a passo dia a dia (Segunda a Domingo) com comandos de teste, gates de produção e protocolo de rollback. |

---

## ⚡ Princípios de Execução

1. **Atômico por dia:** Execute apenas um documento por dia, sempre fora dos ticks críticos (janela segura).
2. **Validação antes do commit:** Sempre execute `$HERMES_PY -m py_compile` (scripts de áudio/LLM) e `$PROJECT_PY -m py_compile` / `$PROJECT_PY -m pytest` (vídeo/testes) da respectiva fase antes de qualquer commit na branch principal. Não usar `python` solto.
3. **Produção soberana:** O teste real de sucesso é o jornal das 06:00 rodar liso e os vídeos do Brasil e Mundo continuarem sendo publicados no YouTube no horário previsto.
