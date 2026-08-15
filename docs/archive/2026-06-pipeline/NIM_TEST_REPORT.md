<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# NIM_TEST_REPORT — Validação das chaves/modelos NVIDIA NIM

Gerado em 2026-08-05 03:31 UTC por `scripts/test_nim_models.py` (passada adaptativa).
Prompt de teste (idêntico para todos): 'Editorial news cover illustration, minimalist black and white composition with a single burnt-amber gold accent color, a fragmented map symbolizing political tension, no human faces, no text, 16:9 aspect ratio, clean vector-editorial style'

| Modelo | Sucesso | Endpoint | Latência | 16:9 nativo | Dimensões | Imagem |
|---|---|---|---|---|---|---|
| qwen-image | ❌ | — | — ms | — | — | — |
| stable-diffusion-3.5-large | ❌ | — | — ms | — | — | — |
| flux.2-klein-4b | ✅ | genai black-forest-labs/flux.2-klein-4b | 2235 ms | sim | 1344x768 | test_output/nim_models/flux.2-klein-4b.png |
| flux.1-schnell | ❌ | — | — ms | — | — | — |
| flux.1-dev | ✅ | genai black-forest-labs/flux.1-dev | 6354 ms | sim | 1344x768 | test_output/nim_models/flux.1-dev.png |
| flux.1-kontext-dev | ❌ | — | — ms | — | — | — |

## Observações por modelo

### qwen-image
- genai qwen/qwen-image: HTTP 404 — '404 page not found\n'
- genai qwen/qwen-image-2512: HTTP 404 — '404 page not found\n'
- genai qwen/qwen_image: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=qwen/qwen-image: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=qwen/qwen-image-2512: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=qwen/qwen_image: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=qwen/qwen-image: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=qwen/qwen-image-2512: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=qwen/qwen_image: HTTP 404 — '404 page not found\n'

### stable-diffusion-3.5-large
- genai stabilityai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- genai stabilityai/sdxl-turbo: HTTP 404 — '{"status":404,"title":"Not Found","detail":"Function \'f886140c-424e-4c82-a841-99e23f9ae35d\': Not found for account \'EZEwSvnQKcJsJrDbXQI6Xgk_CwLNe5B-0K'
- genai stability-ai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- genai stabilityai/stable-diffusion-3-5-large: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=stabilityai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=stabilityai/sdxl-turbo: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=stability-ai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- ai.api.nvidia.com/v1/images/generations model=stabilityai/stable-diffusion-3-5-large: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=stabilityai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=stabilityai/sdxl-turbo: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=stability-ai/stable-diffusion-3.5-large: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=stabilityai/stable-diffusion-3-5-large: HTTP 404 — '404 page not found\n'

### flux.2-klein-4b
- genai black-forest-labs/flux.2-klein-4b: 422 → ajustando ['cfg_scale', 'steps'] (tentativa 2)
- genai black-forest-labs/flux.2-klein-4b: ✅ 1344x768 em 2235ms

### flux.1-schnell
- genai black-forest-labs/flux.1-schnell: erro de rede ReadTimeout
- ai.api.nvidia.com/v1/images/generations model=black-forest-labs/flux.1-schnell: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=black-forest-labs/flux.1-schnell: HTTP 404 — '404 page not found\n'

### flux.1-dev
- genai black-forest-labs/flux.1-dev: ✅ 1344x768 em 6354ms

### flux.1-kontext-dev
- genai black-forest-labs/flux.1-kontext-dev: 422 → ajustando ['height', 'image', 'width'] (tentativa 2)
- genai black-forest-labs/flux.1-kontext-dev: 422 → ajustando ['height', 'image', 'width'] (tentativa 3)
- genai black-forest-labs/flux.1-kontext-dev: 422 → ajustando ['height', 'image', 'width'] (tentativa 4)
- ai.api.nvidia.com/v1/images/generations model=black-forest-labs/flux.1-kontext-dev: HTTP 404 — '404 page not found\n'
- integrate.api.nvidia.com/v1/images/generations model=black-forest-labs/flux.1-kontext-dev: HTTP 404 — '404 page not found\n'
