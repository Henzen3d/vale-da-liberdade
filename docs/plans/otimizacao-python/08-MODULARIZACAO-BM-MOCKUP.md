# 08 — Modularização do bm_mockup_video.py

**Impacto**: Médio, **risco alto no cron BM**
**Ganho**: import time / testes. **Zero** no áudio do diário (diário não importa este arquivo).
**Script**: `bm_mockup_video.py` (**2896** linhas / 117 KB — não 2663)
**Interpretador**: PROJECT_PY apenas
**Cron**: `bm-hourly-pipeline.sh` etapa 3: `PROJECT_PY scripts/bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2`

---

## Alinhamento

- **Não** na mesma noite que o plano 01 (mesmo arquivo, mesmo tick `*/20`).
- Karaoke rejeitado — não criar `bm_video/karaoke.py`.
- Upload YT / `videos_published.json` / handlers X-Instagram são produção. Split grande sem o tick passar = episódio BM sem vídeo até o próximo dia.
- `scripts/scripts/` aninhado já foi removido; o pacote novo é `scripts/bm_video/` (irmão, não nested).
- CLI e flags atuais (`--pending`, `--upload`, `--privacy`, `--max`, `--days`) **não mudam**.
- Testes: `PROJECT_PY -m unittest scripts.test_bm_mockup_video` — aliases no monolito se funções mudarem de módulo.

---

## Solução (quando for a noite certa)

Ordem: `constants.py` + `state.py` primeiro (sem Playwright). Depois `capture.py` (plano 01 já deve ter 1 browser). `render.py` / `youtube.py` por último.

Não importar `bm_video.capture` no `bm_pipeline.py` (HERMES_PY sem Playwright).

---

## Checklist

- [ ] `pgrep -af 'bm_mockup_video|bm_pipeline.py|bm-hourly-pipeline'` vazio, **ou** job `web-jornal-brasil-mundo-hourly` pausado. Teto do tick = 55 min (`BUDGET_S=3300`). Não `pgrep -f bm_`.
- [ ] `PROJECT_PY scripts/bm_mockup_video.py --pending --max 1 --days 2` (sem `--upload` no ensaio)
- [ ] unittest mockup + render_broadcast_shots
- [ ] `bm-hourly-pipeline.sh` intacto (ainda chama o entry point)
- [ ] Tick `*/20` seguinte ok
