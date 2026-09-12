# 03 — Coleta de Notícias (news_collector.py)

**Impacto**: Alto (rebaixado de “crítico 2–3×”)
**Ganho realista**: conexão reuse + um pouco menos de thread; **não** 11 fontes em 40 s. São **~41 fontes** habilitadas; já há `ThreadPoolExecutor(max_workers=5)`.
**Scripts**: `news_collector.py` (915 linhas), `http_fetch.py` (322 — camada central, `fetch_with_recovery`), `recover_page.py`
**Interpretador**: HERMES_PY (`aiohttp` já instalado). Playwright **ausente** no HERMES_PY — recovery Playwright do `recover_page` **não** sobe de nível neste braço.
**Skill de produção**: não quebrar `http_fetch.fetch_with_recovery` / paywall_aware.

---

## Alinhamento

- Coleta **já é paralela** (5 workers). O texto antigo (“HTTP sequencial por fonte”) está errado.
- `max_workers=5` foi escolhido para DNS/Windows; neste Linux 4 cores + BM `*/20` + cron trânsito `*/5`, **não subir** para 8–15.
- Fontes: 41 em `sources.json` v1.3, não 11. paywall_aware vivos: `folha_mercado`, `bloomberg_brasil` (`folha_poder` não está no JSON atual).
- Recovery canônico: `scripts/recover_page.py` (Wayback → Archive.today → Jina → API Pivot → Playwright). Wrappers: `http_fetch.fetch_with_recovery`, `_maybe_recover_paywalled`, `_recover_source_articles`.
- `http_fetch.py` **não** usa aiohttp hoje (requests). Migrar collector sem passar pelo `http_fetch` duplica timeout/UA/recovery.
- `ssl=False` no snippet original é **proibido** (MITM em fontes). Manter TLS.
- `feedparser` síncrono: ok em thread. Não precisa asyncio para XML.
- Encoding Folha latin-1/mojibake é bug conhecido **fora** deste plano.

---

## Solução

### Fase A — aiohttp só no I/O HTTP, via `http_fetch` (não fork)

Preferência: session aiohttp **dentro** de `http_fetch` (ou helper `_get_async`) com:

```
TCPConnector(limit=8, limit_per_host=2, ttl_dns_cache=300)
ClientTimeout(total=12, connect=5)
```

`collect_all_news()` permanece síncrona (`asyncio.run` no entry). `pipeline.py` não muda a assinatura.

Se aiohttp no collector e requests no `http_fetch` ao mesmo tempo: dois pools, pior. Um caminho só.

**Não** `FETCH_SEMAPHORE(8)` + 41 tasks + recover Playwright. Recover continua 1-a-1 síncrono no worker da fonte.

### Fase B — paywall em batch

**Não** `Semaphore(3)` + `run_in_executor(recover_page)` em paralelo. `recover_page` pode abrir Playwright; no HERMES_PY isso falha ou, se um dia existir, explode RAM no diário 06:00.

Manter `_maybe_recover_paywalled` por artigo, serial **dentro** da fonte. O paralelismo já é entre fontes (5).

### Fase C — session global

Processo do collector é curto (cron). Session por `collect_all_news_async()` + `async with` já basta. Global `_SESSION` sem close vaza FD no cron.

---

## Wrapper

```python
def collect_all_news(hours: int = 48, parallel: bool = True) -> list:
    # parallel=True continua sendo o default; internamente asyncio ou ThreadPool
```

Não quebrar `parallel=False` (debug).

---

## Risco

| Risco | Mitigação |
|-------|-----------|
| 41× aiohttp + recover | limit 8 / per_host 2; recover serial |
| `ssl=False` | nunca |
| Playwright no HERMES_PY | recover cai nos 4 primeiros níveis; não instalar Playwright no Hermes nesta onda |
| cache.json | mesma função `save_cache` |
| Folha mojibake | fora de escopo |

---

## Checklist

- [ ] Diff de `raw-{date}.md` / JSON de artigos vs coleta ThreadPool (mesmas URLs ± ordem)
- [ ] `cache.json` atualiza
- [ ] paywall Folha/Bloomberg ainda passa por `recover_page`
- [ ] Tempo: melhorar vs 2–4 min, meta **< 2 min**, não < 90 s a qualquer custo
- [ ] Diário 06:00 seguinte coleta ok
