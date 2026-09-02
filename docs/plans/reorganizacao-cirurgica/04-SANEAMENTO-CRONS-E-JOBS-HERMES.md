# Plano 04 — Saneamento de Crons e Jobs Hermes

> **Fase:** Dia 4  
> **Prioridade:** MÉDIA (Elimina ruído operacional, jobs zumbis e falhas intermitentes no painel)  
> **Escopo:** Configuração de Jobs no Hermes Agent / Crontab do Host  
> **Diretriz:** **Não consertar ferramentas não vitais** (como `scout.py`). Pausar ou remover jobs quebrados.

---

## 1. Contexto e Diagnóstico

### Jobs com Erro Recorrente
No painel e inventário do Hermes Agent, há tarefas agendadas que falham periodicamente e poluem o histórico:
1. `webjornal-scout-weekly`: Apresenta status de erro constante. O script [scripts/scout.py](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/scout.py) é experimental e não faz parte do fluxo vital de produção.
2. `youtube-pipeline-lembrete`: Apresenta status de erro constante (lembrete redundante).
3. `web-jornal-bm-video-autopilot`: Está com status `paused` (decisão correta, deve ser mantido pausado ou desativado formalmente).

---

## 2. Ações Cirúrgicas por Job

| Job Hermes / Crontab | job_id | Estado Atual | Ação Cirúrgica |
|---|---|---|---|
| `web-jornal-vale-da-liberdade-daily` | `74472bd658a5` | Agente LLM | Plano 01: `no_agent` + wrapper absoluto |
| `webjornal-scout-weekly` | `253558aea1e6` | last_status error | **PAUSAR**. `scripts/scout.py` existe, mas o job não é vital |
| `youtube-pipeline-lembrete` | `02e26ba9a2e9` | last_status error | **PAUSAR** |
| `web-jornal-bm-video-autopilot` | `e5d6df754c19` | paused | **MANTER PAUSADO** |
| `web-jornal-brasil-mundo-hourly` | `aefe99598bbe` | no_agent + `bm-hourly-pipeline.sh` | **MANTER** |
| Coletor de trânsito | crontab host `*/5` | ativo | **MANTER** (não é Vale) |
| `persona-digest-sexta`, Firecrawl, perf-monitor, server-digest | outros ids | ativos | **NÃO MEXER** neste plano |

---

## 3. Passo a Passo de Execução

### Passo 1: Pausar jobs zumbis
Não existe `hermes job pause`. Usar a ferramenta `cronjob` do agente:

- `action=pause`, `job_id=253558aea1e6` (scout)
- `action=pause`, `job_id=02e26ba9a2e9` (lembrete YouTube)

Preferir pause a delete. `scripts/scout.py` **existe** no disco; o job que falha é o agendamento, não a ausência do arquivo.

### Passo 2: Auditar o Crontab do Host
Verificar o crontab do usuário `osmar` no servidor:
```bash
crontab -l
```
Garantir que apenas as entradas intencionais estejam ativas, sem duplicidades com os agendamentos do Hermes.

---

## 4. Teste de Validação / Prova de Sucesso

1. Executar listagem de status de jobs do Hermes:
   - Nenhum job com `last_status: error` ativo no painel.
2. Monitorar os logs por 24 horas:
   - Nenhum log de tentativa de execução de `scout.py` ou `youtube-pipeline-lembrete`.
