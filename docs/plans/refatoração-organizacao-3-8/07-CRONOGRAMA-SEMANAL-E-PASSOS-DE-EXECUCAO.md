# 07 — Cronograma Semanal de Execução e Checklist de Segurança

> **Foco:** Roteiro executivo dia a dia para implementar a refatoração ao longo da semana com **zero downtime**.  
> **Status:** PLANEJADO (Pronto para execução)  
> **Adaptação servidor:** 2026-09-02 — venvs explícitos; sem `--force` em data publicada; `python` não existe no PATH.  
> **Regra Fundamental:** Cada dia representa uma mudança atômica, validada e commitada separadamente. Se o ciclo do jornal das 06:00 oscilar, o dia atual sofre rollback em minutos.

---

## 1. Visão Geral do Cronograma Semanal

```
┌──────────┬──────────────────────────────────────┬───────────────────────────────┐
│ DIA      │ ESCOPO PRINCIPAL                     │ ARTEFATOS / COMANDO CRÍTICO   │
├──────────┼──────────────────────────────────────┼───────────────────────────────┤
│ Dia 1    │ Gemini 3.8 Flash no Diário e BM      │ 01-MODERNIZACAO...3-8-FLASH   │
│ Dia 2    │ Saneamento da Raiz e Segredos OAuth  │ 02-SANEAMENTO-DA-RAIZ...      │
│ Dia 3    │ Organização de Scripts & Migração SQL│ 03-ORGANIZACAO-MODULAR...     │
│ Dia 4    │ Camada Core & Fim das Duplicações    │ core/gemini/ e core/utils/    │
│ Dia 5    │ Decomposição dos Monólitos (Fachadas)│ 04-REFATORACAO-MONOLITOS...   │
│ Dia 6    │ Schemas Pydantic, Logging e Cache    │ 05-PADRONIZACAO-DADOS...      │
│ Dia 7    │ Bateria de Testes Pytest & Baseline  │ 06-SUITE-DE-TESTES...         │
└──────────┴──────────────────────────────────────┴───────────────────────────────┘
```

---

## 2. Passo a Passo Detalhado Dia a Dia

### 📅 Dia 1 — Adoção do Gemini 3.8 Flash
- **Objetivo:** Elevar a qualidade dos roteiros e síntese com Gemini 3.8 Flash sem mexer na estrutura de arquivos.
- **Passos:**
  1. Atualizar `sources/gemini_limits.json` adicionando `gemini-3.8-flash`.
  2. Atualizar `scripts/gemini_client.py` para mapear os limites da família 3.8.
  3. Atualizar `scripts/generate_roteiro_llm.py` colocando `gemini-3.8-flash` no topo de `GEMINI_MODELS`.
  4. Atualizar `scripts/bm_condensador.py` e `scripts/youtube_thumbnail.py`.
- **Validação Antes do Commit:**
  ```bash
  HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
  $HERMES_PY -m py_compile scripts/generate_roteiro_llm.py scripts/bm_condensador.py scripts/gemini_client.py scripts/youtube_thumbnail.py
  ```
  **Proibido:** `python scripts/generate_roteiro_llm.py --date 2026-09-01 --force` (republica episódio, gasta RPD). `--dry-run` não existe nesse CLI.
- **Gate de Produção:** Após 06:05 BRT, `logs/daily-$(date +%F).log` com `Daily build started` / `finished`. Job `74472bd658a5`.

---

### 📅 Dia 2 — Higiene da Raiz, Segredos e Binários
- **Objetivo:** Proteger credenciais e eliminar arquivos pesados da raiz.
- **Passos:**
  1. Confirmar `credentials/client_secret.json` (já no lugar — não `mv` ID inventado).
  2. Blindar `.gitignore` contra `client_secret*.json` na raiz se ainda faltar a linha.
  3. Mover ONNX da raiz para `archive/legacy_models/` **se existirem**.
  4. Remover `edge.mp3` / `piper.wav` se existirem.
  5. Quarentena só de pastas **presentes** (`new-ux.backup-20260806/`, `site/`, `thumbnail-generetor/`, …). Pular `new-ux/` e `BACKUP-…` (ausentes).
  6. Organizar `.md` antigos com `test -f` antes do `mv`. Preservar `SYSTEM_MAP.md`, `SKILL.md`, `AGENT_GUIDE.md`, `PRD.md`.
- **Validação Antes do Commit:**
  ```bash
  git status -s
  # Verificar se scripts e public/ continuam intactos
  ```

---

### 📅 Dia 3 — Organização da Pasta `scripts/`
- **Objetivo:** Reduzir o congestionamento de **139** arquivos em `scripts/`.
- **Passos:**
  1. Mover os **21** `*.sql` para `database/migrations/`.
  2. Mover `test_*.py` / `teste_*.py` dispersos para `tests/` (atualizar imports/`sys.path`).
  3. Mover protótipos mortos (`faceless_*.py`, `clean_screenshot.py`, wrappers antigos) para `scripts/archive_legacy/`.
- **Validação Antes do Commit:**
  ```bash
  HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
  PROJECT_PY=/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3
  $HERMES_PY -m py_compile scripts/pipeline.py scripts/bm_pipeline.py
  $PROJECT_PY -m py_compile scripts/bm_mockup_video.py
  bash -n scripts/cron-wrapper.sh
  bash -n scripts/bm-hourly-pipeline.sh
  ```

---

### 📅 Dia 4 — Extração da Camada `core/` e Fim do Código Copiado
- **Objetivo:** Centralizar leituras de env, rate-limits e parsing JSON eliminando funções duplicadas.
- **Passos:**
  1. Criar `core/config.py`, `core/utils/env_loader.py` e `core/utils/json_parser.py`.
  2. Mover o motor do cliente Gemini para `core/gemini/client.py` e deixar shim de retrocompatibilidade em `scripts/gemini_client.py`.
  3. Refatorar os scripts vivos (`generate_roteiro_llm.py`, `bm_condensador.py`, `title_optimizer.py`) para importar do `core`.
- **Validação Antes do Commit:**
  ```bash
  HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
  cd /home/osmar/web-jornal-vale-da-liberdade
  PYTHONPATH=. $HERMES_PY -c "from core.gemini.client import GeminiClient; print(GeminiClient)"
  PYTHONPATH=. $HERMES_PY -c "from core.utils.env_loader import get_gemini_api_keys; from pathlib import Path; print(len(get_gemini_api_keys(Path('.'))))"
  ```
  Não imprimir as chaves. `get_gemini_api_keys` lê **só** `$PROJ/.env`.

---

### 📅 Dia 5 — Modularização dos Monólitos em Fachadas
- **Objetivo:** Quebrar `bm_mockup_video.py` (67 KB) e `pipeline.py` (43 KB) em módulos gerenciáveis.
- **Passos:**
  1. Criar o pacote `scripts/video/` isolando servidor HTTP, captura e FFmpeg.
  2. Criar a fachada `scripts/bm_mockup_video.py` mantendo exatamente a mesma interface CLI.
  3. Criar `scripts/pipeline_steps/` isolando as etapas do Diário.
- **Validação Antes do Commit:**
  ```bash
  HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
  PROJECT_PY=/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3
  $PROJECT_PY scripts/bm_mockup_video.py --help
  $HERMES_PY scripts/pipeline.py --help
  ```

---

### 📅 Dia 6 — Schemas Pydantic, Logging e Purge de Cache
- **Objetivo:** Blindar tipos de dados, centralizar logs com timezone brasileira e limpar cache antigo.
- **Passos:**
  1. Criar `core/models/schemas.py` com as classes `RoteiroDiario` e `BMRoteiroEspecial`.
  2. Criar `core/logger.py` com formatação ISO-8601 e timezone `America/Sao_Paulo`.
  3. Criar script de purga de cache para `sources/cache.json` (descartar itens com mais de 45 dias).
- **Validação Antes do Commit:**
  ```bash
  HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
  PYTHONPATH=. $HERMES_PY -c "from core.models.schemas import RoteiroCompleto; print('Schemas OK')"
  ```

---

### 📅 Dia 7 — Suíte de Testes Automatizada e Congelamento de Baseline
- **Objetivo:** Garantir que o repositório possua testes rápidos de regressão com `pytest`.
- **Passos:**
  1. Configurar `pytest.ini` na raiz.
  2. Estruturar os testes em `tests/unit/` e `tests/integration/`.
  3. Rodar a suíte completa de testes.
  4. Atualizar `CANONICAL.md` e `docs/INDEX.md` refletindo a nova arquitetura limpa.
- **Validação Final:**
  ```bash
  PROJECT_PY=/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3
  $PROJECT_PY -m pytest
  ```

---

## 3. Protocolo de Rollback em Caso de Falha

Se qualquer etapa apresentar comportamento anômalo durante a madrugada (06:00 do Diário) ou nos ciclos de 20 minutos do BM:

1. **Reversão Imediata via Git (local primeiro):**
   ```bash
   git revert HEAD --no-edit
   git fetch origin
   # Só push se origin/main não tiver avançado. Sem --force.
   ```
   Produção lê o disco (`main` local), não o remoto. `main` já esteve ahead de `origin/main` na validação 9/9.
2. **Checagem Rápida de Logs:**
   - Diário: `tail -n 50 logs/daily-$(date +%F).log`
   - BM: `tail -n 50 logs/bm-monitor.log`
3. **Pausa de Segurança:**
   Nenhuma nova alteração deve ser aplicada no mesmo dia antes da análise da causa raiz.
