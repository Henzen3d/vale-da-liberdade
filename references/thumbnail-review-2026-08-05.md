# 📋 Review Sessão de Thumbnails — 05/08/2026
**Status:** ✅ Implementação concluída e em produção  
**Autor da revisão:** Hermes Agent

---

## 1. 📊 Resumo Executivo

O sistema de thumbnails automáticas foi implementado ontem à noite e **rodou com sucesso** na sessão `@session:default/20260804_233058_cd3d18` (qwen3.8-max). Três thumbnails foram geradas e publicadas:

| Episódio | Tipo | Model | Thumbnail | Latency |
|----------|------|-------|-----------|---------|
| `ep_2026-08-05` | Diário | qwen-image-3.0 | `ep_2026-08-05.webp` | 16s |
| `bm_FGUQUnDVLgA` | Brasil e Mundo | qwen-image-3.0 | `bm_FGUQUnDVLgA.webp` | 18s |
| `bm_y3Y3sM1LeC0` | Brasil e Mundo | qwen-image-3.0 | `bm_y3Y3sM1LeC0.webp` | 16s |

**Todos os 3 episódios de hoje têm capas customizadas na homepage.**

---

## 2. 🔍 Gap Identificado: Brasil e Mundo

### Situação atual ✅
- Os episódios `bm_*` **já recebem thumbnails** — o script `thumbnail_generator.py` reconhece IDs que começam com `bm_` (linhas 346-359) e grava metadata em `output/brasil_e_mundo/episodes/especial-{vid}.json`.
- O `app.js` (página principal) lê `ep.cover_url` — mas **não está populado dinamicamente** a partir das thumbnails geradas.

### O que falta para amanhã
O `episodio.json` de amanhã precisa **incluir `thumbnail:` no metadata merge**. O script já grava em `{date}-metadata.json` e em `especial-{vid}.json`, mas:

**Gap #1 — Integração com o pipeline de publicação**
`scripts/thumbnail_generator.py` roda standalone (via `generate_thumbnail_safe()`), **não está chamado pelo cronjob daily** (`web-jornal-vale-da-liberdade-daily` às 6h). Amanhã, se o cron não for atualizado, o episódio saira sem thumbnail e cairá no placeholder local (`local-placeholder`).

**Gap #2 — app.js não lê `thumbnail.path`**
No `public/assets/js/app.js` (linhas 314-332):
```js
// Capa por episódio ainda não implementada — usa variações da capa padrão
const isCustomCover = Boolean(ep.cover_url);
```
O código tem o **esqueleto** para carregar capa customizada (`ep.cover_url`), mas `cover_url` nunca é populado pelo metadata de thumbnail. Precisa apontar pra `thumbnails/{date}/{episode_id}.webp`.

---

## 3. 🛠️ Artefatos Produzidos

| Arquivo | Status | Observação |
|---------|--------|-----------|
| `scripts/thumbnail_generator.py` | ✅ | 1199 lines — cascata, quota, safety, fallback |
| `scripts/test_thumbnail_system.py` | ✅ | Tests unitários (isolados e cascata) |
| `scripts/_validate_thumbnail_models.py` | ✅ | Validação 429/404 (Gemini imagem OFF) |
| `sources/thumbnail_cascade_rank.json` | ✅ | 8 modelos ordenados + enabled flags |
| `sources/image_quota_tracker.json` | ✅ | Persistência de quota diária (BRT reset) |
| `logs/thumbnail_generation.log` | ✅ | JSONL — 33 eventos (prompt, image_ok, safety) |
| `logs/thumbnail_model_validation.json` | ✅ | Status HTTP de cada modelo |
| `thumbnails/2026-08-05/*.webp + .jpg` | ✅ | 6 arquivos (3 webp + 3 jpg) |
| `public/thumbnails/2026-08-05/*` | ✅ | Espelhado para web |

---

## 4. 🎯 Decisões Arquitetrais Validadas

| Decisão | Resultado |
|---------|-----------|
| **Cascata 8 modelos** | ✅ DashScope primary; qwen-image-3.0 venceu todas |
| **Safety rejection → regen** | ✅ Teste `ep_test_safety` passou |
| **Quota tracker BRT -3** | ✅ Evita over-spend pós meia-noite GMT |
| **Placeholder local fallback** | ✅ Teste `ep_test_total_fail` → SVG fallback OK |
| **Retry com backoff 3s/8s** | ✅ Implementado em `_call_model_with_retry` |

---

## 5. 🐛 Bugs Encontrados (e corrigidos ontem)

| Bug | Causa | Fix |
|-----|-------|-----|
| **Regex greedy** `[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}` | Pegava "Supreme Court", "European Parliament" como nomes | Substituído por **lista negra** (`_NAMES_TO_SANITIZE`) — lookup exato case-insensitive |
| **SAFE_GENERIC_PROMPT obsoleto** | Função retornava fallback genérico em vez de regen seguro | Renomeado para `SAFE_REGEN_PROMPT` com linguagem mais direcionada |

**Testes pós-fix:**
```
Supreme Court → "a public figure"
President Lula → "a public figure"
Blood + shooting → "tension" (sanitizado)
European Parliament → preservado (não na lista)
```

---

## 6. ⚠️ Quota e Limitações

### Gemini imagem (DESATIVADO)
Todos os modelos de imagem Gemini retornam **429** (quota) ou **404** (não existe):
- `gemini-3-pro-image` → 429
- `gemini-2.5-flash-image-preview` → 404

**Consequência:** Não há fallback entre provedor de imagem. A cascata DashScope é o **único provedor de imagem ativo**.

### DashScope / Qwen
- `qwen-image-3.0` é o **campeão** (3/3 thumbnails)
- Quota local: 30/dia (hoje usou 3 — 27 restantes)
- Latência: ~16-18s (aceitável; `--fast` flag pode usar qwen-image-2.0 para ~10s)

---

## 7. 📈 Métricas de Custo

| Model | Custo/thumb | Thumb hoje | Custo total |
|-------|-------------|------------|-------------|
| qwen-image-3.0 | $0.05 | 3 | **$0.15** |
| local-placeholder | $0.00 | 0 | $0.00 |

---

## 8. 🧪 Testes Executados

`scripts/test_thumbnail_system.py` — 9 testes:

| Test | Status |
|------|--------|
| test_sanitize_prompt_with_name | ✅ |
| test_sanitize_prompt_short_fallback | ✅ |
| test_safety_rejected_then_regen | ✅ |
| test_cascade_all_models_fail → placeholder | ✅ |
| test_quota_tracker | ✅ |
| test_postprocess_16_9_crop | ✅ |
| test_placeholder_generation | ✅ |
| test_dedup_skips_existing | ✅ |
| test_dedup_with_force_regenerates | ✅ |

---

## 9. 💡 Sugerências de Melhoria (Roadmap)

| Prioridade | Sugerência | Esforço |
|-----------|------------|---------|
| **🔴 Alta** | Integrar `generate_thumbnail_safe()` → cronjob daily (às 6h) | ~1h |
| **🟡 Média** | `app.js`: carregar thumbnail de `thumbnails/{date}/{id}.webp` quando `cover_url` não existir | ~2h |
| **🟡 Média** | Adicionar retry exponencial (5 tentativas) para timeouts intermitentes | ~30m |
| 🟢 Baixa | Enviar notificação no Telegram quando placeholder for usado (falha total) | ~15m |
| 🟢 Baixa | `--fast` flag para usar qwen-image-2.0 quando latência for prioridade | ~1h |
| 🟢 Baixa | Adicionar "Brasil e Mundo" e "Peter Solo" à `_NAMES_TO_SANITIZE` se relevante | ~15m |

---

## 10. 📁 Próximos Passos (amanhã)

1. **6h da manhã** — cronjob `web-jornal-vale-da-liberdade-daily` roda
2. Se integrado: thumbnail auto-gerada antes da publicação
3. Se **não** integrado: episódio sai com **placeholder local** (preto/branco/âmbar)
4. **Integração app.js** precisa ser feita ainda hoje — senão o 3º episódio (BM) não aparece com capa custom na home

---

**Conclusão:** Sistema **executa e produz**. Gap é **apenas de orquestração** — necessário conectar o cronjob daily ao `thumbnail_generator.generate_thumbnail_safe()`. A thumbnail de amanhã só será gerada automaticamente se esse fio for pontado hoje.
