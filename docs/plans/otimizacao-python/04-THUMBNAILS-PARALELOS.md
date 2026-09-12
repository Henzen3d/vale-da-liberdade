# 04 — Thumbnails (thumbnail_generator.py)

**Impacto**: Médio (rebaixado — o “pior caso 8 min DashScope” **não existe** em produção)
**Ganho realista**: quase zero em wall-clock se CF flux responde. Não paralelizar.
**Scripts**: `thumbnail_generator.py` (1576 linhas), `youtube_thumbnail.py` (BM)
**Interpretador**: HERMES_PY (diário) e o braço que o BM já usa para capa
**Estado vivo** (`sources/thumbnail_cascade_rank.json`, 2026-08-24):

```
order: cf-flux-schnell → pollinations-flux
DashScope / Qwen / Wan / Z-Image: enabled=false
notas: DashScope Arrearage. Produção = Cloudflare flux-1-schnell
```

Auth CF: `CLOUDFLARE_API_TOKEN` **ou** OAuth wrangler (`cfoat_*` em `~/.config/.wrangler/config/default.toml`). Não exigir token env.

---

## O que o plano antigo errava

- “Cascata de 8 modelos DashScope” — código ainda **lista** Qwen/Wan, mas o rank de produção tem **2** modelos, DashScope desligado.
- Disparar top-3 em paralelo: gastaria cota e, com DashScope morto, só restam 2. `FIRST_COMPLETED` + cancel no REST CF pode deixar a imagem órfã e mesmo assim cobrar.
- `pipeline.py` etapa 5.6 ainda comenta “DashScope cascade” — comentário stale; a função é `generate_thumbnail_safe`.

---

## Solução alinhada (desta onda)

**Não** `asyncio.wait(FIRST_COMPLETED)` em 3 modelos.

1. Manter cascata sequencial curta: CF flux → Pollinations → placeholder local (já é zero-falha).
2. Timeout por modelo: 45 s está ok; 8×60 s é ficção.
3. Prompt Gemini: gerar **depois** do roteiro, **antes** do TTS longo, gravar `episodes/{date}-thumb-prompt.txt` — único paralelismo útil (CPU/API flash, não imagem). Não competir com TTS (RPD TTS ≠ flash, mas o mesmo anel de chaves e `gemini_usage.json`).
4. Atualizar o comentário em `pipeline.py` 5.6: “CF flux → Pollinations”, não DashScope.
5. BM: `youtube_thumbnail.py` já usa CF. Não duplicar cliente.

---

## Risco

| Risco | Mitigação |
|-------|-----------|
| Reativar DashScope | Conta em atraso; não ligar `enabled` |
| 3 gerações paralelas | Proibido nesta onda |
| Wrangler OAuth expirado | Teste `test_thumbnail_cf_auth.py` no HERMES_PY; fallback Pollinations |

---

## Checklist

- [ ] `HERMES_PY -m unittest scripts.test_thumbnail_system scripts.test_thumbnail_cf_auth`
- [ ] Rank continua CF → Pollinations
- [ ] Placeholder se ambos falharem
- [ ] Sem POST DashScope em produção
