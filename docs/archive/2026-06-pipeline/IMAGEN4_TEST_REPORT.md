<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# IMAGEN4_TEST_REPORT — Validação geração de imagem (Gemini API)

Gerado em 2026-08-05 03:42 UTC por `scripts/test_imagen4_models_v2.py`.
Prompt: 'Editorial news cover illustration, minimalist black and white composition with a single burnt-amber gold accent color, a fragmented map symbolizing political tension, no human faces, no text, 16:9 aspect ratio, clean vector-editorial style'

## Resultado

| Família | Modelo | Sucesso | Latência | 16:9 | Dimensões | Path |
|---|---|---|---|---|---|---|
| imagen4 | `imagen-4.0-ultra-generate-001` | ❌ | — ms | — | — | — |
| imagen4 | `imagen-4.0-generate-001` | ❌ | — ms | — | — | — |
| imagen4 | `imagen-4.0-fast-generate-001` | ❌ | — ms | — | — | — |
| gemini-image | `gemini-3.1-flash-image` | ❌ | 284 ms | — | — | — |
| gemini-image | `gemini-3-pro-image` | ❌ | 195 ms | — | — | — |
| gemini-image | `gemini-2.5-flash-image` | ❌ | 203 ms | — | — | — |
| gemini-image | `gemini-3.1-flash-image-preview` | ❌ | 208 ms | — | — | — |
| gemini-image | `gemini-3-pro-image-preview` | ❌ | 196 ms | — | — | — |

## Achados críticos

1. **Imagen 4 (`imagen-4.0-*-generate-001`)**: a API retorna `404 NOT_FOUND` com mensagem *'This model ... is no longer available to new users'*. Os model IDs ainda aparecem em `models.list()`, mas **não geram imagem** para as chaves AI Studio deste projeto (contas/projetos considerados 'new users').
2. **Depreciação oficial** (ai.google.dev/gemini-api/docs/deprecations, atualizado 2026-08-03): Imagen 4 shutdown **2026-08-17**. Replacement recomendado: `gemini-3.1-flash-image` (método `generate_content`, não `generate_images`).
3. **Cascata de produção adotada** (conservadora, o que funciona de verdade): modelos Gemini image disponíveis nesta conta, com fallback local placeholder.
4. **Aspect ratio 16:9**: via `ImageConfig(aspect_ratio='16:9')` em `GenerateContentConfig` para Gemini image; crop/resize no pós-processamento se a saída não for exata.
5. **Cota**: free tier Gemini image é por modelo/projeto; contador local usa **data UTC** (reset RPD típico 00:00 UTC). Erro de cota: `429` / `RESOURCE_EXHAUSTED`.
6. **Custo estimado free tier**: $0 nas cotas gratuitas; acima disso pay-as-you-go.

## Erros / notas detalhadas

- `imagen-4.0-ultra-generate-001`: `no attempt`
- `imagen-4.0-generate-001`: `no attempt`
- `imagen-4.0-fast-generate-001`: `no attempt`
- `gemini-3.1-flash-image`: `429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https:/`
- `gemini-3-pro-image`: `429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https:/`
- `gemini-2.5-flash-image`: `429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https:/`
- `gemini-3.1-flash-image-preview`: `429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https:/`
- `gemini-3-pro-image-preview`: `429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https:/`
