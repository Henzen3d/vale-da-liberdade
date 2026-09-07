# 🧭 Suíte de Planos — Refatoração e Modernização com Gemini 3.8 Flash

> **Projeto:** Web Jornal Vale da Liberdade  
> **Data de Elaboração:** Setembro / 2026  
> **Adaptação ao servidor:** 2026-09-02 (pós validação 9/9 da reorganização cirúrgica)  
> **Diretriz Geral:** **Zero quebra em produção**. Não executar mudanças em lote. Preservar 100% dos fluxos diários do Jornal (06:00 BRT) e da esteira de vídeos do Brasil & Mundo (a cada 20 min).

---

## Ambiente canônico deste servidor (não inventar)

Estes planos foram escritos genéricos. No host de produção vale **somente** isto:

| Item | Valor real em disco (2026-09-02) |
|---|---|
| Repo | `/home/osmar/web-jornal-vale-da-liberdade` |
| `HERMES_PY` (feed, LLM, TTS, diário, `bm_monitor`/`bm_pipeline`) | `/home/osmar/.hermes/hermes-agent/venv/bin/python3` |
| `PROJECT_PY` (Playwright, `bm_mockup_video`, upload YT, pytest) | `/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3` |
| `python` no PATH | **não existe** — nunca usar `python`; usar o venv do braço |
| Job diário 06:00 | Hermes `74472bd658a5`, `no_agent=true`, shim `~/.hermes/scripts/vale-daily-cron-wrapper.sh` → `scripts/cron-wrapper.sh` |
| Job BM */20 | Hermes `aefe99598bbe`, `no_agent=true`, `scripts/bm-hourly-pipeline.sh` |
| TTS (fora do escopo 3.8 Flash) | Diário: `gemini-2.5-flash-preview-tts` PACKED; BM: `gemini-3.1-flash-tts-preview`. 3.8 Flash é modelo de **texto**, não substitui TTS. |
| Chaves Gemini | Só `$PROJ/.env` (`GEMINI_API_KEY` … `_7`). **Não** misturar `~/.hermes/.env`. |
| pytest | Instalado **só** no `.venv` do projeto (9.1.1). Ausente no venv Hermes. |
| pydantic | Presente nos dois venvs (2.13.4). |

Qualquer comando `python …` nestes planos deve ser lido como `HERMES_PY` (texto/áudio) ou `PROJECT_PY` (vídeo/teste). Nunca republicar episódio com `--force` / `--date` de dia já no ar.

---

## 📂 Índice dos Documentos da Suíte

Esta pasta contém o plano completo, faseado e documentado para elevar o projeto do patamar de "vibe coding orgânico" para um padrão de engenharia de software profissional e manutenível:

| Arquivo | Título | Objetivo Resumido |
|---|---|---|
| [`00-DIAGNOSTICO-E-ARQUITETURA-ALVO.md`](./00-DIAGNOSTICO-E-ARQUITETURA-ALVO.md) | **Diagnóstico Geral e Arquitetura Alvo** | Raio-X completo das dívidas técnicas, duplicidades, riscos de segurança e visão da nova arquitetura. |
| [`01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md`](./01-MODERNIZACAO-COM-GEMINI-3-8-FLASH.md) | **Modernização com Gemini 3.8 Flash** | Especificação da adoção do modelo 3.8 Flash nos roteiros do Diário, síntese do BM, Structured Outputs JSON e rate limiter. |
| [`02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md`](./02-SANEAMENTO-DA-RAIZ-E-SEGURANCA.md) | **Saneamento da Raiz e Segurança** | Isolamento do OAuth em `credentials/`, expurgo de binários ONNX de 63MB, scripts duplicados da raiz e pastas zumbis. |
| [`03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md`](./03-ORGANIZACAO-MODULAR-DE-SCRIPTS.md) | **Organização Modular de Scripts e Core** | Descongestionamento de `scripts/` (139 arquivos), migração dos 21 SQLs para `database/` e criação da camada `core/`. |
| [`04-REFATORACAO-SEGURA-DOS-MONOLITOS.md`](./04-REFATORACAO-SEGURA-DOS-MONOLITOS.md) | **Refatoração Segura dos Monólitos** | Decomposição em camadas de `bm_mockup_video.py` (67 KB) e `pipeline.py` (43 KB) usando o Padrão Fachada (zero quebra de CLI). |
| [`05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md`](./05-PADRONIZACAO-DE-DADOS-SCHEMAS-E-LOGGING.md) | **Schemas Pydantic, Logging e Cache** | Contratos de dados tipados, logging estruturado com timezone `America/Sao_Paulo` e saneamento do `sources/cache.json`. |
| [`06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md`](./06-SUITE-DE-TESTES-E-GARANTIA-DE-QUALIDADE.md) | **Suíte de Testes e Qualidade** | Consolidação de testes unitários e de integração com `pytest`, mocks de API e validação estática de wrappers shell. |
| [`07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md`](./07-CRONOGRAMA-SEMANAL-E-PASSOS-DE-EXECUCAO.md) | **Cronograma Semanal e Checklist** | Roteiro passo a passo dia a dia (Segunda a Domingo) com comandos de teste, gates de produção e protocolo de rollback. |

---

## ⚡ Princípios de Execução

1. **Atômico por dia:** Execute apenas um documento por dia.
2. **Validação antes do commit:** Sempre execute `$HERMES_PY -m py_compile` (scripts de áudio/LLM) e `$PROJECT_PY -m py_compile` / `$PROJECT_PY -m pytest` (vídeo/testes) da respectiva fase antes de qualquer commit na branch principal. Não usar `python` solto.
3. **Produção soberana:** O teste real de sucesso é o jornal das 06:00 rodar liso e os vídeos do Brasil e Mundo continuarem sendo publicados no YouTube no horário previsto.
