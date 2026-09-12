# 07 — Cache e Memoização

**Impacto**: Médio / baixo
**Ganho**: startup de subcomandos; não 5–15 s no full se os JSONs já estão quentes no page cache.
**Scripts**: `pipeline.py`, `news_collector.py`, `publish_site.py`
**Nesta onda:** Fase A + C. Sem `PipelineContext` grande.

---

## Alinhamento

- `sources.json`: 41 fontes; `lru_cache(maxsize=1)` ok **dentro do processo**. Cron é processo novo — cache não atravessa execuções (não precisa “limpar entre noites”).
- `cache.json` **muda** durante a coleta. `lru_cache` em `load_cache()` é **bug** se `save_cache()` não der `load_cache.cache_clear()`. Preferir variável local em `collect_all_news` (já carrega uma vez).
- `gemini_usage.json`: 10–50 reads/request — plano **06** (flock), não lru_cache (stale RPM entre processos).
- `get_episode_number(date)`: cache ok; invalidar se o archive for reescrito no mesmo processo.
- Lazy import: `pipeline.py validate` não precisa de `news_collector`. Cuidado: lazy **dentro** de `cmd_full` não pode atrasar o path que o cron usa; o ganho é em CLI manual.
- Não criar dataclass de contexto nesta onda (acopla todas as etapas; conflito com plano 10).

---

## Checklist

- [ ] `save_cache` limpa cache de leitura se houver lru
- [ ] Artefatos do `full` iguais
- [ ] `pipeline.py validate` no HERMES_PY não importa Playwright / BM mockup
