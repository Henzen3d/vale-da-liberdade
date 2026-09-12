# 07 — Cronograma Semanal de Execução e Checklist de Segurança

> **Foco:** Roteiro executivo dia a dia para implementar a refatoração ao longo da semana com **zero downtime**.  
> **Status:** FASE 2 — Executar imediatamente após a consolidação do [Plano de Otimização Python](../otimizacao-python/00-VISAO-GERAL.md).  
> **Alinhamento do Servidor:** 2026-09-11 (aproveitando flock Gemini, Edge-TTS Python, CRLF/LF já entregues).  
> **Regra Fundamental:** Cada dia representa uma mudança atômica, validada e commitada separadamente. Se o ciclo do jornal das 06:00 oscilar, o dia atual sofre rollback em minutos.

---

## 1. Visão Geral do Cronograma Semanal (Fase 2)

```
┌──────────┬──────────────────────────────────────┬───────────────────────────────┐
│ DIA      │ ESCOPO PRINCIPAL                     │ ARTEFATOS / COMANDO CRÍTICO   │
├──────────┼──────────────────────────────────────┼───────────────────────────────┤
│ Dia 1    │ Gemini 3.8 Flash no Diário e BM      │ 01-MODERNIZACAO...3-8-FLASH   │
│ Dia 2    │ Saneamento da Raiz e Segredos OAuth  │ 02-SANEAMENTO-DA-RAIZ...      │
│ Dia 3    │ Organização de Scripts & Migração SQL│ 03-ORGANIZACAO-MODULAR...     │
│ Dia 4    │ Camada Core & Fim das Duplicações    │ core/gemini/ e core/utils/    │
│ Dia 5    │ Decomposição dos Monólitos (Fachadas)│ 04-REFATORACAO-MONOLITOS (P08)│
│ Dia 6    │ Schemas Pydantic, Logging e Cache    │ 05-PADRONIZACAO-DADOS...      │
│ Dia 7    │ Bateria de Testes Pytest & Baseline  │ 06-SUITE-DE-TESTES...         │
└──────────┴──────────────────────────────────────┴───────────────────────────────┘
```

---

## 2. Passo a Passo Detalhado Dia a Dia

### 📅 Dia 1 — Adoção do Gemini 3.8 Flash
- **Objetivo:** Elevar a qualidade dos roteiros e síntese com Gemini 3.8 Flash sem mexer na estrutura de arquivos.
- **Passos:**
  1. **Consultar cotas reais no Google AI Studio:** Acessar o painel da conta, checar a tabela de Rate Limits da chave para o `gemini-3.8-flash` e atualizar `sources/gemini_limits.json` com os valores oficiais de RPM, RPD e TPM (**sem inventar 15/1500**; caso não haja tabela explícita, adotar baseline conservador de 5 RPM / 20 RPD / 250K TPM).
  2. Atualizar `scripts/gemini_client.py` garantindo que o modelo `gemini-3.8-flash` caia na categoria `"flash"`.
  3. Atualizar `scripts/generate_roteiro_llm.py` colocando `gemini-3.8-flash` no topo de `GEMINI_MODELS` e ajustando timeout HTTP para 30s-45s (devido ao thinking nativo).
  4. Atualizar `scripts/bm_condensador.py` e `scripts/youtube_thumbnail.py`.
- **Validação Antes do Commit:**
  ```bash
  python scripts/generate_roteiro_llm.py --date 2026-09-01 --force
  ```
  Inspecionar se o JSON foi gerado com sucesso e contém Peter e Ricardo.
- **Gate de Produção:** Monitorar a execução do Diário às 06:00 do dia seguinte em `logs/daily-*.log`.

---

### 📅 Dia 2 — Higiene da Raiz, Segredos e Binários
- **Objetivo:** Proteger credenciais e eliminar arquivos pesados da raiz.
- **Passos:**
  1. Mover `client_secret_*.json` para `credentials/client_secret.json`.
  2. Blindar `.gitignore` contra qualquer `credentials/` ou `client_secret*.json`.
  3. Mover `pt_BR-faber-medium.onnx` e `kokoro-v1.0.onnx` para `archive/legacy_models/`.
  4. Remover arquivos de áudio temporários (`edge.mp3`, `piper.wav`).
  5. Mover pastas zumbis (`thumbnail-generetor/`, `new-ux/`, `site/`) para `archive/quarantine_2026/`.
  6. Organizar arquivos `.md` antigos da raiz para `docs/archive/` e `docs/reports/`.
- **Validação Antes do Commit:**
  ```bash
  git status -s
  # Verificar se scripts e public/ continuam intactos
  ```

---

### 📅 Dia 3 — Organização da Pasta `scripts/`
- **Objetivo:** Reduzir o congestionamento de 150 arquivos em `scripts/`.
- **Passos:**
  1. Mover todos os arquivos `*.sql` para `database/migrations/`.
  2. Mover os arquivos `test_*.py` e `teste_*.py` dispersos para a pasta `tests/`.
  3. Mover scripts de protótipos mortos (`faceless_*.py`, `clean_screenshot.py`, wrappers antigos) para `scripts/archive_legacy/`.
- **Validação Antes do Commit:**
  ```bash
  python -m py_compile scripts/pipeline.py scripts/bm_pipeline.py scripts/bm_mockup_video.py
  bash -n scripts/cron-wrapper.sh
  bash -n scripts/bm-hourly-pipeline.sh
  ```

---

### 📅 Dia 4 — Extração da Camada `core/` e Fim do Código Copiado
- **Objetivo:** Centralizar leituras de env, rate-limits e parsing JSON eliminando funções duplicadas.
- **Passos:**
  1. Criar `core/config.py` (integrando e padronizando a infraestrutura iniciada em `scripts/_bootstrap.py`), `core/utils/env_loader.py` e `core/utils/json_parser.py`.
  2. Mover o motor do cliente Gemini para `core/gemini/client.py` (preservando o flock POSIX e o rollback criados na otimização) e deixar shim de retrocompatibilidade em `scripts/gemini_client.py`.
  3. Refatorar os scripts vivos (`generate_roteiro_llm.py`, `bm_condensador.py`, `title_optimizer.py`) para importar do `core`.
- **Validação Antes do Commit:**
  ```bash
  python -c "from core.gemini.client import GeminiClient; print(GeminiClient)"
  python -c "from core.utils.env_loader import get_gemini_api_keys; print(len(get_gemini_api_keys()))"
  ```

---

### 📅 Dia 5 — Modularização dos Monólitos em Fachadas (Cumprimento do Plano 08)
- **Objetivo:** Quebrar `bm_mockup_video.py` (~3.050 linhas) e `pipeline.py` (1.147 linhas) em submódulos especializados.
- **Passos:**
  1. Criar o pacote `scripts/bm_video/` (isolando `constants.py`, `state.py`, `server.py`, `capture.py`, `render.py`, `youtube.py`) conforme o Plano 08 de Otimização.
  2. Transformar `scripts/bm_mockup_video.py` em fachada fina (~80 linhas), mantendo 100% da interface CLI (`--pending`, `--upload`, `--privacy`, `--max`, `--days`).
  3. Criar `scripts/pipeline_steps/` isolando as etapas do Diário e simplificando `scripts/pipeline.py`.
- **Validação Antes do Commit:**
  ```bash
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
  python -c "from core.models.schemas import RoteiroDiario; print('Schemas OK')"
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
  pytest
  ```

---

## 3. Protocolo de Rollback em Caso de Falha

Se qualquer etapa apresentar comportamento anômalo durante a madrugada (06:00 do Diário) ou nos ciclos de 20 minutos do BM:

1. **Reversão Imediata via Git:**
   ```bash
   git revert HEAD --no-edit
   git push origin main
   ```
2. **Checagem Rápida de Logs:**
   - Diário: `cat logs/daily-$(date +%F).log | tail -n 50`
   - BM: `cat logs/bm-monitor.log | tail -n 50`
3. **Pausa de Segurança:**
   Nenhuma nova alteração deve ser aplicada no mesmo dia antes da análise da causa raiz.
