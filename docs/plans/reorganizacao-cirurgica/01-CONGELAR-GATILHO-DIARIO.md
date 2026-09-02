# Plano 01 — Congelar o Gatilho do Diário (06:00)

> **Fase:** Dia 1  
> **Prioridade:** MÁXIMA (Maior risco de quebra silenciosa do produto diário)  
> **Escopo:** Infraestrutura / Agendamento Hermes / Bash wrapper  
> **Refactor de Python:** ZERO (Nenhum arquivo `.py` deve ser modificado)

---

## 1. Contexto e Diagnóstico

### O Problema Atual
O job agendado no Hermes Agent (`web-jornal-vale-da-liberdade-daily`, às 06:00) está configurado como um **Agente Autônomo com Prompt de uma linha** utilizando um modelo gratuito (`inclusionai/ling-3.0-flash:free`).

```
[06:00 Gatilho Hermes] 
       │
       ▼ (Risco de Alucinação / Quota / Timeout)
[LLM: "Execute pipeline.py full..."] 
       │
       ▼ (Sem garantia de log determinístico diário)
[Execução em Shell Improvisada]
```

### O Risco
1. **Quebra silenciosa:** Se o modelo free estiver instável, sem cota ou alucinar parâmetros de chamada, o diário simplesmente não é gerado.
2. **Perda de Rastreabilidade:** A execução via agente LLM não garante o redirecionamento padronizado para `logs/daily-YYYY-MM-DD.log`.
3. **Divergência de Documentação:** `docs/PIPELINE_SCRIPTS_INVENTORY.md` afirma que o diário oficial roda via bash determinístico, mas a realidade estava dependendo do agente.

---

## 2. A Solução Cirúrgica

Mudar o job do Hermes para o modo **`no_agent`**, apontando exclusivamente para o script canônico `scripts/cron-wrapper.sh` (path absoluto no servidor).

O wrapper **já está** `775` e o conteúdo abaixo **já é o arquivo em disco**. Não reescrever o `.sh` no Dia 1 se o diff for zero.

```
[06:00 Gatilho Hermes (no_agent)]
       │
       ▼
[scripts/cron-wrapper.sh]
       │
       ├── Exporta PATH e variáveis (.env)
       ├── Executa: /home/osmar/.hermes/hermes-agent/venv/bin/python3 scripts/pipeline.py full --date $(date +%F)
       └── Redireciona tudo para: logs/daily-YYYY-MM-DD.log
```

---

## 3. Passo a Passo de Execução

### Passo 1: Verificar e Garantir Permissões do Wrapper
No servidor de produção:
```bash
cd /home/osmar/web-jornal-vale-da-liberdade
chmod +x scripts/cron-wrapper.sh
ls -la scripts/cron-wrapper.sh
```

### Passo 2: Validar o Conteúdo do `cron-wrapper.sh`
Conferir (não reescrever) que `scripts/cron-wrapper.sh` no servidor tem estes caminhos e gravação em log:
```bash
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

export PATH="/home/osmar/.local/bin:/home/osmar/.hermes/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin${PATH:+:$PATH}"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

LOG_FILE="$LOG_DIR/daily-$(date +%F).log"
EXEC_DATE="${1:-$(date +%F)}"

{
  echo "=== Daily build started: $(date '+%a %d %b %Y %H:%M:%S %Z') ==="
  /home/osmar/.hermes/hermes-agent/venv/bin/python3 "$PROJECT_DIR/scripts/pipeline.py" full --date "$EXEC_DATE"
  echo "=== Daily build finished: $(date '+%a %d %b %Y %H:%M:%S %Z') ==="
} > "$LOG_FILE" 2>&1

echo "EXIT:$?"
```

### Passo 3: Atualizar o job Hermes (não o crontab do host)
Não existe `hermes job …` neste ambiente. Usar a ferramenta `cronjob` do agente, **job_id real**:

- **id:** `74472bd658a5`
- **nome:** `web-jornal-vale-da-liberdade-daily`
- **schedule:** `0 6 * * *` (já está; fuso America/Sao_Paulo)
- **no_agent:** `true`
- **script:** path **absoluto** `/home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh`  
  (script relativo resolve em `~/.hermes/scripts/` — **não** usar `scripts/cron-wrapper.sh` relativo)
- **workdir:** `/home/osmar/web-jornal-vale-da-liberdade` (já está)
- **deliver:** pode ficar `telegram:8122386267`; o wrapper só imprime `EXIT:$?` no stdout (o log útil vai para `logs/daily-*.log`)

**Não** criar linha `0 6 * * *` no `crontab` do host. Hoje o crontab do `osmar` só tem o coletor de trânsito (`*/5`). Host + Hermes no mesmo horário = dois `pipeline.py full`.

---

## 4. Teste de Validação / Prova de Sucesso

1. **NÃO passar data de episódio já publicado.** `cron-wrapper.sh 2026-09-01` roda `pipeline.py full` de verdade (TTS, R2, catálogo). Validação segura no Dia 1:
   ```bash
   bash -n /home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh
   test -x /home/osmar/web-jornal-vale-da-liberdade/scripts/cron-wrapper.sh && echo WRAPPER_OK
   ```
2. **Prova da manhã seguinte (única prova real):**
   - Após 06:05, existir `/home/osmar/web-jornal-vale-da-liberdade/logs/daily-$(date +%F).log`
   - Conter `=== Daily build started ===` e `=== Daily build finished ===`
3. Se precisar de smoke **manual**, só com data de hoje e dono ciente de que vai republicar o diário.

---

## 5. Critérios de Rollback
Se o disparo falhar:
- O log em `logs/daily-*.log` conterá a causa exata (ex: variável de ambiente ausente no wrapper).
- Em caso de emergência, rodar manualmente:
  `/home/osmar/.hermes/hermes-agent/venv/bin/python3 /home/osmar/web-jornal-vale-da-liberdade/scripts/pipeline.py full --date $(date +%F)`  
  (`python3` do brew/sistema não é o runtime do diário.)
