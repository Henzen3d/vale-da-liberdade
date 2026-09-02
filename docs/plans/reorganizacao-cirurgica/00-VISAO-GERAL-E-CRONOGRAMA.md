# Plano Mestre de Execução Cirúrgica — Web Jornal Vale da Liberdade

> **Origem:** Auditoria de Sistemas e Inventário de Produção (Setembro/2026)  
> **Status:** PLANEJADO (Pronto para execução faseada — **NÃO EXECUTAR EM LOTE**)  
> **Diretriz:** 1 mudança cirúrgica por dia, teste atômico antes de commit, zero refactor massivo.  
> **Ambiente real (servidor, 2026-09-02):** path `/home/osmar/web-jornal-vale-da-liberdade`. Crontab do host **não** roda o diário (só o coletor de trânsito). Diário = job Hermes `74472bd658a5`. BM = job Hermes `aefe99598bbe` → `bm-hourly-pipeline.sh` a cada 20 min. Screenshots vivos = `scripts/screenshots/` (base.py + runner.py + sites/), não `screenshots/core/`.

---

## 1. O Que o Projeto Realmente É

O repositório abriga **dois produtos em produção**, operando em relógios e esteiras independentes:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      WEB JORNAL VALE DA LIBERDADE                       │
├────────────────────────────────────┬────────────────────────────────────┤
│ 🎙️ PRODUTO 1: DIÁRIO (06:00)       │ 🎬 PRODUTO 2: BRASIL E MUNDO       │
│ - Peter & Ricardo (Áudio + Portal) │ - Vídeos Mockup YouTube (20 min)   │
│ - Script: pipeline.py full         │ - Script: bm-hourly-pipeline.sh    │
│ - Saída: Site, Feed RSS, R2 MP3    │ - Saída: YouTube, Fila BM, Site    │
└────────────────────────────────────┴────────────────────────────────────┘
```

Ambos os produtos estão funcionais. O risco crítico diagnosticado **não é falta de funcionalidade**, mas sim **complexidade acumulada ("vibe-coding empilhado")**:
- 103+ scripts `.py` no diretório `scripts/`.
- Múltiplas gerações coexistindo de renderizadores de vídeo, geradores de thumbnail e captura de screenshots.
- Working tree sujo com alterações não commitadas sobre a branch `main` de produção.
- Documentação histórica descrevendo crontabs e fluxos desatualizados.
- Job do diário disparado por prompt de agente LLM em vez de gatilho determinístico.

---

## 2. As Regras de Ouro da Execução

1. **Nunca executar múltiplos planos no mesmo dia:** Cada plano deve ser executado, validado no ciclo de produção correspondente e commitado individualmente.
2. **Nenhuma alteração de código sem teste de regressão:** Não alterar scripts Python de produção (`pipeline.py`, `bm_mockup_video.py`, `generate_gemini_tts_multi.py`) durante a organização de infraestrutura.
3. **Não apagar arquivos mortos no primeiro momento:** Primeiro documentar e isolar no papel (marcar como legado); a remoção física só ocorre após 14 dias de estabilidade.
4. **Respeitar os ambientes virtuais (venvs):** Não unificar os venvs do Hermes e do Projeto sem bateria completa de testes de Playwright e TTS.

---

## 3. Matriz e Ordem dos Planos Cirúrgicos

| Ordem | Documento | Foco Principal | Risco Mitigado |
|---|---|---|---|
| **Dia 1** | [`01-CONGELAR-GATILHO-DIARIO.md`](./01-CONGELAR-GATILHO-DIARIO.md) | Migrar job Hermes de agente LLM para `no_agent` + `cron-wrapper.sh` | Quebra silenciosa do diário por falha de prompt/modelo |
| **Dia 2** | [`02-WORKING-TREE-E-COMMITS-ATOMICOS.md`](./02-WORKING-TREE-E-COMMITS-ATOMICOS.md) | Testar, agrupar e commitar arquivos modificados/untracked | Produção divergindo do git e perda de correções |
|| **Dia 3** | [`03-MAPA-CANONICO-VIVO-MORTO.md`](./03-MAPA-CANONICO-VIVO-MORTO.md) | Criar inventário canônico VIVO / MORTO / NÃO TOCAR | Confusão sobre quais scripts manter e o que descartar/isolar |
| **Dia 4** | [`04-SANEAMENTO-CRONS-E-JOBS-HERMES.md`](./04-SANEAMENTO-CRONS-E-JOBS-HERMES.md) | Pausar/desativar jobs zumbis (`scout-weekly`, lembretes) | Poluição de logs e alertas falsos |
| **Dia 5** | [`05-BLINDAGEM-VENVS-BRASIL-MUNDO.md`](./05-BLINDAGEM-VENVS-BRASIL-MUNDO.md) | Documentar e blindar runtimes no `bm-hourly-pipeline.sh` | Conflito de pacotes (Playwright vs APIs) |

---

## 4. O Que NÃO Fazer Durante as Fases

- ❌ **NÃO** unificar o pipeline Diário com o Brasil e Mundo.
- ❌ **NÃO** reescrever `bm_mockup_video.py` (68KB) nem `pipeline.py` (44KB).
- ❌ **NÃO** fazer `rm scripts/*.py` em massa.
- ❌ **NÃO** cadastrar novos domínios ou fazer scrapers novos antes da estabilização.
- ❌ **NÃO** ativar a esteira `faceless_*.py` no pipeline horário.
- ❌ **NÃO** misturar commits de infraestrutura com alterações de lógica de IA/prompts.
- ❌ **NÃO** adicionar `0 6 * * * cron-wrapper.sh` no crontab do host **enquanto** o job Hermes do diário existir — hoje o host não dispara o jornal; duplicar quebra o dia.
- ❌ **NÃO** commitar `moss-tts-nano/`, `.env`, `credentials/`, `sources/cache.json`.
