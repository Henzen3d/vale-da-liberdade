<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# TEST_REPORT — Sistema de Thumbnails Automáticas

Gerado em 2026-08-05T08:43:14.024346-03:00

| # | Teste | Resultado | Evidência |
|---|---|---|---|
| 1 | 9. Lint/tipo (py_compile) | ✅ PASS | ok |
| 2 | 5. Imagem corrompida | ✅ PASS | ModelFailed: imagem corrompida: cannot identify image file <_io.BytesIO object at 0x7229d2cb86d0> |
| 3 | 5b. Imagem monotônica | ✅ PASS | ModelFailed: imagem quase monotônica (std=0.0) |
| 4 | 7. Controle de cota diária | ✅ PASS | after_2_inc remaining=3; after_day_reset remaining=5 |
| 5 | 2. Fallback de modelo | ✅ PASS | used=qwen-image-2.0-pro level=1 calls=['qwen-image-3.0', 'qwen-image-2.0-pro'] |
| 6 | 3. Falha total de API → placeholder | ✅ PASS | model=local-placeholder path=thumbnails/2099-01-01/ep_test_total_fail.webp exists=True |
| 7 | 4. Safety rejection (HTTP 400) | ✅ PASS | sanitized=True calls=2 model=qwen-image-3.0 |
| 8 | 8. Integração não-bloqueante | ✅ PASS | safe_wrapper returned failed=True keys=['path', 'image_model_used', 'is_placeholder', 'error', 'failed'] |
| 9 | 8b. Wiring no cron/pipeline | ✅ PASS | pipeline.py wired=True bm_pipeline.py wired=True cron=cron-wrapper.sh→pipeline.py full |
| 10 | 6. Idempotência | ✅ PASS | skipped=True mtime_same=True model=cached |
| 11 | 1. Happy path (episódio real) | ✅ PASS | path=thumbnails/2026-08-05/ep_2026-08-05.webp model=qwen-image-3.0 placeholder=False meta=thumbnails/2026-08-05/ep_2026-08-05.webp |
| 12 | 6. Idempotência | ✅ PASS | skipped=True mtime_same=True model=cached |

**Total: 12/12 passaram.**
