# 01 — Screenshots e Captura (bm_mockup_video.py)

**Impacto**: Crítico no vídeo BM
**Ganho realista neste host**: Fase A (1 browser reutilizado) — dezenas de segundos. Fase B async **adiada**.
**Scripts**: `scripts/bm_mockup_video.py` (**2896** linhas / ~117 KB — não 2663)
**Interpretador**: **PROJECT_PY** (`web-jornal-vale-da-liberdade/.venv`, CPython 3.14). Playwright **não** está no HERMES_PY.
**Cron**: `web-jornal-brasil-mundo-hourly` a cada **20 min**. Não editar o arquivo durante um tick.

---

## Alinhamento 2026-09-10 (não executar nesta leitura)

O código vivo **já** faz várias coisas que o plano original tratava como ausentes:

1. Prefetch de cache **antes** de abrir o browser (`to_fetch` vs cache hit, `CAPTURE_CACHE_DIR`, TTL implícito via hash `handler-v4`).
2. Fallback genérico já reutiliza **um** `sync_playwright()` + um `page` para o lote restante (não N cold starts no fallback).
3. Handlers (`try_handler_screenshot`) ainda abrem Playwright **próprio** por URL, **antes** do contexto genérico — comentário no código (vhm4xPVjxFk): aninhar Sync API dentro de outro `sync_playwright()` quebra.
4. Delay anti-bot **já existe**: 8–15 s mesmo domínio, 3.5–8 s domínio diferente. Paralelizar 3 páginas no mesmo host anula isso e aumenta 403/WAF.
5. Viewport vivo: **1400×900**, UA + stealth, locale `pt-BR`. Não “1920×1080” genérico.
6. Host: i5-7400 **4 cores**, 7,6 GiB RAM, swap já ~1,9 GiB. Um Chromium headless ≈ 300–800 MiB. Três browsers simultâneos neste box **não**.

`uvloop` **não** está no PROJECT_PY. Playwright async **existe** no PROJECT_PY (`async_api` no site-packages). Mesmo assim Fase B fica adiada: o ganho some no delay anti-bot, e o tick `*/20` compete com FFmpeg do mockup.

---

## Problema que ainda vale

Handlers por URL ainda podem relançar Chromium. O lote genérico já compartilha contexto. O custo restante é:

- N cold starts nos **handlers** (não no fallback).
- Delay educado (proposital; não “otimizar embora”).
- FFmpeg / HTML render — fora deste documento (plano 08).

---

## Solução (ordem obrigatória)

### Fase A — única desta onda: 1 browser para handlers + genérico

Manter Sync API. Um `chromium.launch(headless=True)` por execução de captura. **Um `context.new_page()` por URL**, `page.close()` no `finally` — **não** reutilizar a mesma `page` em dezenas de sites (dialog preso, service worker, DOM que vaza RSS).

Não misturar handler Sync dentro de outro `with sync_playwright()`. Padrão:

```python
with _open_sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, user_agent=UA, locale="pt-BR",
                              timezone_id="America/Sao_Paulo", extra_http_headers=...)
    for i, scene, dest in to_fetch:
        # delay anti-bot IGUAL ao atual (8–15s mesmo host)
        page = ctx.new_page()
        try:
            # stealth no page (por página)
            try_handler_screenshot(..., page=page)  # injetar; sem launch interno
            # fallback genérico nesta page
        finally:
            page.close()
    browser.close()
```

**Teto:** 1 browser, 1 page **viva** por vez. Semáforo 3 **proibido**. Não 2 pages em paralelo neste host.

**Ganho esperado:** eliminar cold start dos handlers (~3–5 s × N), não “8 cenas em 15 s”.

### Fase B — ADIADA: async_playwright + gather

Não nesta madrugada. Motivos: delay anti-bot, RAM, tick `*/20`, comentário de bug Sync-dentro-de-async.

Se um dia: `Semaphore(1)` neste host (não 3); never `gather` de 8 gotos.

### Fase C — prefetch de cache

Já implementado. Não reescrever. Só garantir que a Fase A não desfaça o split cache vs `to_fetch`.

---

## `/dev/shm`

Screenshots PNG finais ficam em `output/brasil_e-mundo/` (disco). Não jogar o cache de 36 h em `/dev/shm` (some no reboot). `/dev/shm` só para frames intermediários de FFmpeg **se** `disk_usage` livre > 512 MiB e swap < 2,5 GiB. `finally: rmtree`.

---

## Risco

| Risco | Mitigação |
|-------|-----------|
| Editar o .py no meio do tick `*/20` | Pausar `web-jornal-brasil-mundo-hourly` ou esperar o tick terminar |
| 3 Chromiums OOM + swap | Teto 1 browser |
| Anti-bot / mesmo domínio | Manter delays atuais |
| Testes no Python errado | `PROJECT_PY -m unittest scripts/test_bm_mockup_video.py` |
| Import Playwright no diário | Diário usa HERMES_PY — não importar `bm_mockup_video` no `pipeline.py` |

---

## Checklist

- [ ] `PROJECT_PY -m unittest scripts.test_bm_mockup_video scripts.test_render_broadcast_shots`
- [ ] `pgrep -af 'bm_mockup_video|bm_pipeline.py|bm-hourly-pipeline'` vazio (ou job pausado) **antes** de editar/testar
- [ ] Delay mesmo-domínio ainda ≥ 8 s
- [ ] Cada captura abre e fecha a própria `page` (não uma page para o lote)
- [ ] Cache `CAPTURE_CACHE_DIR` / `handler-v4` intacto
- [ ] RSS Chromium < ~1 GiB durante captura
- [ ] Próximo tick BM `*/20` completa (áudio + mockup se houver fila)
- [ ] Não rodou Fase B
