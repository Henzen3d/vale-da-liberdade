# DECISIONS.md — Thumbnails automáticas (2026-08-05)

Decisões tomadas em modo YOLO durante a implementação do sistema de capas por episódio.

## 1. Provedor de imagem

- **Escolha:** Alibaba Cloud Model Studio via **DashScope API** (não NVIDIA NIM).
- **Motivo:** Os 8 model IDs fornecidos (`qwen-image-*`, `wan2.7-image*`, `z-image-turbo`) são da família Qwen/Wan no Model Studio. NIM (NVIDIA) retornou 404 para qwen-image / SD3.5 nas chaves disponíveis; Imagen 4 está deprecado para “new users”.
- **Chave:** `DASHSCOPE_API_KEY` copiada de `~/.hermes/.env` → `.env` do projeto (prefixo `sk-ws-…` = workspace intl).
- **Base URL:** `https://dashscope-intl.aliyuncs.com/api/v1` (Singapore / international). Beijing (`dashscope.aliyuncs.com`) não foi necessário — a chave intl autentica e gera com sucesso.
- **Endpoint de geração (todos os 8):**  
  `POST /services/aigc/multimodal-generation/generation`  
  Payload: `{ model, input.messages[{role,content:[{text}]}], parameters:{size, n, watermark, prompt_extend} }`  
  Resposta: `output.choices[0].message.content[].image` (URL OSS, expira ~24h → download imediato).

## 2. Size / aspect ratio

- Size nativo 16:9 aceito por **todos** os 8: `1664*928`.
- Pós-processamento: crop 16:9 (se necessário) + downscale para **1280×720** WebP q85 + JPG fallback.
- `prompt_extend=false` e `watermark=false` para latência e branding limpo.

## 3. Cascata final de produção

Ordem editorial (não só std de pixels — turbo tinha std alto por ruído/grain, não fidelidade editorial):

1. `qwen-image-3.0` (flagship)
2. `qwen-image-2.0-pro`
3. `qwen-image-max`
4. `qwen-image-2.0`
5. `qwen-image-plus` (rápido ~4.5s)
6. `wan2.7-image-pro`
7. `wan2.7-image`
8. `z-image-turbo` (último fallback de velocidade)
9. placeholder local SVG/Pillow

Arquivo de ranking reordenável: `sources/thumbnail_cascade_rank.json`.  
Latências medidas (teste 2.3): 4–23 s por modelo.

## 4. Cota diária local

- Tracker: `sources/image_quota_tracker.json` (compartilhado diário + BM).
- Reset: **meia-noite America/Sao_Paulo (UTC−3)**. Conservador vs. janela UTC do DashScope; evita estourar cota real se o reset do provedor for UTC.
- Limites locais default (por modelo/dia): 3.0=30, 2.0-pro=40, max=40, 2.0=50, plus=80, wan-pro=30, wan=40, turbo=100.
- Checagem **antes** da chamada HTTP; HTTP 429 também cai para o próximo.

## 5. Meta-prompt (Etapa B)

- Primário: `gemini-3.6-flash` → fallback `gemini-3.5-flash` (mesmas chaves do pipeline).
- Compliance inegociável: sem rostos reais, sem violência gráfica, **sem texto na imagem**.
- Incorpora “assinatura visual”: film grain + 35mm + no text/letters/typography.
- Em HTTP 400 / DataInspectionFailed: sanitiza prompt 1× e recomeça a cascata inteira uma vez.

## 6. Integração no pipeline / cron

- Diário: `scripts/pipeline.py` `cmd_full` → **Etapa 5.6/8** após ads, antes de archive/publish.  
  Cron: `0 6 * * * scripts/cron-wrapper.sh` → `pipeline.py full` (confirmado lendo o wrapper).
- BM: `scripts/bm_pipeline.py` `cmd_full` → **Etapa 4.5/6** (também cobre `process-queue`, que chama `cmd_full`).
- Ambos usam `generate_thumbnail_safe()` — **nunca bloqueiam** áudio/publicação.

## 7. Nomenclatura e metadata

- Path: `thumbnails/{YYYY-MM-DD}/{episode_id}.webp` (+ `.jpg`).
- Diário: `episode_id = ep_YYYY-MM-DD`.
- BM: `episode_id = bm_{video_id}`.
- Metadata mesclado em `episodes/{date}-metadata.json` (campo `thumbnail`) ou JSON do especial BM.
- Espelho em `public/thumbnails/...` com chmod 0644.

## 8. O que NÃO foi feito (de propósito)

- Não reintroduzir Imagen 4 / NIM como primários (falharam nos probes anteriores).
- Não bloquear publish se thumbnail falhar.
- Não gastar cota em re-runs sem `--force` (idempotência por existência do webp).

## 9. Artefatos de prova

- `MODEL_TEST_REPORT.md` + `test_output/models/*.png` (8/8 OK)
- `TEST_REPORT.md` (12/12 PASS)
- Exemplo real: `thumbnails/2026-08-05/ep_2026-08-05.webp` (1280×720, modelo `qwen-image-3.0`)
