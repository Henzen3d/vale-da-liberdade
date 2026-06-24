# AGENT_GUIDE — Web Jornal Vale da Liberdade

Guia para qualquer IA (ou você mesmo, daqui a 6 meses) retomar este projeto sem reconstruir
o contexto do zero.

## Ordem de leitura recomendada

1. `README.md` — visão geral, quick start, comandos principais, problemas comuns
2. `ARCHITECTURE.md` — fluxo ponta-a-ponta, módulos, schemas, variáveis de ambiente, pontos de falha
3. `PRD.md` — produto, personas, escopo, requisitos, roadmap
4. `SKILL.md` — ⭐ fonte canônica do roteiro: regras de formatação, quadros obrigatórios, fichas de Peter/Ricardo, checklist de qualidade, pré-processamento TTS
5. `LESSONS_LEARNED.md` — incidentes reais, decisões tomadas, armadilhas conhecidas
6. `prompt.md` — documento paralelo ao SKILL.md (redundante, manter como referência histórica)
7. Último handoff: `archive/handoffs/YYYY-MM-DD.md` (o mais recente)

## Convenção de handoff

Não sobrescreva `.continue-here.md` (não existe mais no repositório). Ao final de cada sessão
de trabalho relevante, salve um handoff como:

```
archive/handoffs/YYYY-MM-DD.md
```

Formato mínimo do handoff:
- O que foi feito na sessão
- Estado atual dos artefatos (qual raw, qual roteiro, qual áudio)
- Próximos passos planejados
- Decisões tomadas

## Quando atualizar cada documento

| Mudou... | Atualizar... |
|---|---|
| Código, módulos, fluxo, schemas | `ARCHITECTURE.md` |
| Escopo, objetivos, roadmap, público | `PRD.md` |
| Regras de roteiro, personagens, checklist | `SKILL.md` |
| Bug, incidente, decisão técnica, lição aprendida | `LESSONS_LEARNED.md` |
| Erro comum, dica de setup, comando novo | `README.md` (seção Problemas comuns) |
| Nenhuma categoria acima, apenas progresso de sessão | handoff em `archive/handoffs/` |

## Estado atual do pipeline (2026-06-22)

- `generate_script.py` foi migrado para **renderer JSON → MD** (Fase 1.2). O cabeçalho do arquivo marca a restrição: Gemini removido de geração de roteiro.
- `pipeline.py cmd_process()` agora:
  - Se o roteiro for template → chama `generate_script(date)` e falha alto se o JSON não existir (sem mais fallback enxuto).
  - Depois → gera TTS, manchetes e metadados a partir do roteiro renderizado.
- `ai_news_filter.py` também já não usa Gemini (Fase 1.1): scoring determinístico (geo + credibilidade + recência + urgência). Cabeçalho do arquivo documenta a restrição.

## Estado atual da Fase 2 (2026-06-23)

- Fase 2.1 concluída: scoring de credibilidade mais sensível a histórico da fonte em `ai_news_filter.py`.
- Fase 2.4 concluída: `x_collector.py` já está conectado a `cmd_init`/`cmd_collect` com bloco `try/except` resiliente.
- Fase 2.5 incorporada: `x_engagement_score()` adicionado para tweets do X e ranking de relevância com pesos explícitos (`RELEVANCE_WEIGHTS`).
- Nota: a integração do X já está ativa, mas os dados de engajamento são usados apenas quando o cache contém tweets válidos. A calibração do ranking foi feita com dados simulados para não bloquear o pipeline real.

## Dicas para testes ponta-a-ponta

- Use `episodes/roteiro-template.json` como base.
- Para simular um episódio: copie `roteiro-template.json` para `roteiro-YYYY-MM-DD.json` e depois rode `python scripts/pipeline.py process --date YYYY-MM-DD`.

## Regras de ouro

- Não invente comportamento de código — se não confirmou lendo o fonte, marque `⚠️ A confirmar com Osmar`
- Não duplique conteúdo entre arquivos — use links cruzados (`Ver SKILL.md, seção X`)
- Não delete scripts sem confirmação — apenas marque como deprecated
- Cada documento tem um propósito — não concentre tudo no README

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-22*