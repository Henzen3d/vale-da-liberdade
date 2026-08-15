<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# MODEL_TEST_REPORT — DashScope (8 modelos)

Gerado em 2026-08-05 por probe real com `DASHSCOPE_API_KEY` (intl Singapore).

Prompt de teste (idêntico para todos):

> Editorial news cover illustration, minimalist black and white composition with a single burnt-amber gold accent color, a fragmented map symbolizing political tension, no human faces, no text, 16:9 aspect ratio, clean vector-editorial style

## Endpoint confirmado

- Base: `https://dashscope-intl.aliyuncs.com/api/v1`
- Path: `/services/aigc/multimodal-generation/generation`
- Auth: `Authorization: Bearer $DASHS...KEY`
- Size nativo 16:9: `1664*928` (aceito por todos os 8)
- Reset de cota local: meia-noite America/Sao_Paulo (tracker em `sources/image_quota_tracker.json`)

## Resultados

| Ordem final | Modelo | Sucesso | Latência | 16:9 nativo | Dimensões | Nota | Imagem |
|---|---|---|---|---|---|---|---|
| 1 | `qwen-image-3.0` | ✅ | 13706 ms | sim | 1664x928 | 5 | `test_output/models/qwen-image-3.0.png` |
| 2 | `qwen-image-2.0-pro` | ✅ | 10810 ms | sim | 1664x928 | 5 | `test_output/models/qwen-image-2.0-pro.png` |
| 3 | `qwen-image-max` | ✅ | 15868 ms | sim | 1664x928 | 5 | `test_output/models/qwen-image-max.png` |
| 4 | `qwen-image-2.0` | ✅ | 4073 ms | sim | 1664x928 | 5 | `test_output/models/qwen-image-2.0.png` |
| 5 | `qwen-image-plus` | ✅ | 4494 ms | sim | 1664x928 | 5 | `test_output/models/qwen-image-plus.png` |
| 6 | `wan2.7-image-pro` | ✅ | 23427 ms | sim | 1664x928 | 5 | `test_output/models/wan2.7-image-pro.png` |
| 7 | `wan2.7-image` | ✅ | 16238 ms | sim | 1664x928 | 5 | `test_output/models/wan2.7-image.png` |
| 8 | `z-image-turbo` | ✅ | 7209 ms | sim | 1664x928 | 5 | `test_output/models/z-image-turbo.png` |

## Ranking final de cascata (produção)

```
1. qwen-image-3.0
2. qwen-image-2.0-pro
3. qwen-image-max
4. qwen-image-2.0
5. qwen-image-plus
6. wan2.7-image-pro
7. wan2.7-image
8. z-image-turbo
9. local-placeholder
```

Justificativa: flagship Qwen 3.0 primeiro; pro/max em seguida; 2.0 e plus como meio-rápidos; Wan como família alternativa; turbo por último (velocidade). Ranking reordenável em `sources/thumbnail_cascade_rank.json`.

## Comportamento de erro observado

- Auth inválida: HTTP 401
- Modelo inexistente: HTTP 400/404
- Cota/rate-limit: HTTP 429 — tratado como fallback
- Safety: HTTP 400 `DataInspectionFailed` — regenera prompt 1× e recomeça cascata
- Todos os 8 modelos retornaram imagem válida (Pillow OK, dims 1664×928)

## Decisão

Nenhum modelo foi removido. Cascata inclui os 8. Ver `DECISIONS.md`.
