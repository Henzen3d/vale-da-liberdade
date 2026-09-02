# Plano 05 — Blindagem e Documentação de Ambientes Virtuais (Venvs BM)

> **Fase:** Dia 5  
> **Prioridade:** MÉDIA-ALTA (Previne quebras silenciosas por instalação de dependências no venv errado)  
> **Escopo:** [scripts/bm-hourly-pipeline.sh](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm-hourly-pipeline.sh) / Documentação de Runtimes  
> **Regra Crítica:** **NÃO UNIFICAR OS VENVS AGORA**. O isolamento atual é intencional. Apenas documentar e blindar as chamadas no script.

---

## 1. Contexto e Diagnóstico

### A Separação Atual de Ambientes
O pipeline horário do Brasil e Mundo (`scripts/bm-hourly-pipeline.sh`) utiliza **dois interpretadores Python distintos de forma consciente**:

1. **`HERMES_PY` (`/home/osmar/.hermes/hermes-agent/venv/bin/python3`):**
   - Roda `bm_monitor.py` e `bm_pipeline.py`.
   - Possui as dependências de feedparser, Gemini API, TTS e utilitários de IA.
2. **`PROJECT_PY` (`/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3`):**
   - Roda `bm_mockup_video.py`.
   - Possui o **Playwright**, navegadores Chromium compilados, dependências de captura gráfica e cliente YouTube.

### O Risco
Qualquer instalação acidental de pacotes via `pip install` no ambiente errado (por exemplo, instalar Playwright no venv do Hermes ou atualizar o SDK do Google no `.venv` do projeto com versões conflitantes) quebra um dos braços da esteira.

---

## 2. A Solução Cirúrgica

1. **Blindar o cabeçalho** de `scripts/bm-hourly-pipeline.sh` com comentários e checagem de executáveis (diff mínimo no `.sh`).
2. **Registrar só em `CANONICAL.md`** qual venv recebe pacote novo. **Não** editar `docs/BM-VIDEO-LAYOUT.md` (é spec visual v6 do mockup).
3. Não unificar venvs.

---

## 3. Modelo do Script Blindado (`scripts/bm-hourly-pipeline.sh`)

```bash
#!/bin/bash
# ==============================================================================
# BM HOURLY PIPELINE RUNNER (Brasil e Mundo)
# ==============================================================================
# SEPARAÇÃO DE AMBIENTES VIRTUAIS (CANÔNICO - NÃO ALTERAR SEM TESTE):
# 1) HERMES_PY  -> bm_monitor.py + bm_pipeline.py (Feed RSS, LLM, TTS, Áudio)
# 2) PROJECT_PY -> bm_mockup_video.py (Playwright, Renderizador de Vídeo, Upload YT)
# ==============================================================================

set -u

WORK_DIR="/home/osmar/web-jornal-vale-da-liberdade"
HERMES_PY="/home/osmar/.hermes/hermes-agent/venv/bin/python3"
PROJECT_PY="$WORK_DIR/.venv/bin/python3"
LOG_DIR="$WORK_DIR/logs"

cd "$WORK_DIR"
mkdir -p "$LOG_DIR"

# ------------------------------------------------------------------------------
# ETAPA 1: Monitor RSS ANCAPSU -> Fila de episódios (Ambiente Hermes)
# ------------------------------------------------------------------------------
set +e
"$HERMES_PY" scripts/bm_monitor.py >> "$LOG_DIR/bm-monitor.log" 2>&1
MONITOR_RC=$?
set -e
if [[ "$MONITOR_RC" -ne 0 ]]; then
  echo "WARN: bm_monitor exit $MONITOR_RC" >&2
fi

# ------------------------------------------------------------------------------
# ETAPA 2: Processamento da Fila (Áudio / Metadados / Site) (Ambiente Hermes)
# ------------------------------------------------------------------------------
set +e
"$HERMES_PY" scripts/bm_pipeline.py process-queue
QUEUE_RC=$?
set -e

# ------------------------------------------------------------------------------
# ETAPA 3: Renderização de Vídeo Mockup & Upload YouTube (Ambiente Projeto/Playwright)
# ------------------------------------------------------------------------------
if [[ -x "$PROJECT_PY" ]]; then
  set +e
  "$PROJECT_PY" scripts/bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2
  VIDEO_RC=$?
  set -e
  if [[ "$VIDEO_RC" -ne 0 ]]; then
    echo "WARN: bm_mockup_video exit $VIDEO_RC (fila audio rc=$QUEUE_RC)" >&2
  fi
else
  echo "WARN: venv do projeto sem python ($PROJECT_PY nao encontrado) — pulando video mockup" >&2
fi

exit "$QUEUE_RC"
```

---

## 4. Teste de Validação / Prova de Sucesso

1. **Verificação de binários e pacotes:**
   ```bash
   # Valida Hermes venv (feedparser, requests, google-genai)
   /home/osmar/.hermes/hermes-agent/venv/bin/python3 -c "import feedparser, requests; print('HERMES VENV OK')"

   # Valida Project .venv (playwright, PIL)
   /home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3 -c "import playwright, PIL; print('PROJECT VENV OK')"
   ```
2. **Não rodar `bash scripts/bm-hourly-pipeline.sh` como “teste”.** Isso processa a fila e pode **upload público**. Validação do Dia 5 = só os `import` acima + `bash -n scripts/bm-hourly-pipeline.sh`.
