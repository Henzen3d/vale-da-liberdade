# 04 — Refatoração Segura dos Monólitos (`bm_mockup_video.py` e `pipeline.py`)

> **Foco:** Decomposição em camadas dos dois maiores monólitos do sistema sem alterar interfaces de linha de comando.  
> **Status:** PLANEJADO (Absorve e cumpre integralmente o [Plano 08 de Otimização Python](../otimizacao-python/08-MODULARIZACAO-BM-MOCKUP.md))  
> **Alinhamento do Servidor:** 2026-09-11 — `bm_mockup_video.py` com ~3.050 linhas / 118 KB (`PROJECT_PY`); `pipeline.py` com 1.150 linhas / 44 KB (`HERMES_PY`).  
> **Risco:** Médio (mitigado pelo Padrão Facade / Fachada de Retrocompatibilidade).  
> **Diretriz de Segurança:** Os comandos do cron `pipeline.py full` e `bm_mockup_video.py` devem manter exatamente as mesmas flags, saídas no stdout e códigos de saída (`exit codes`).

---

## 1. O Problema dos Monólitos

O "vibe coding" acumulativo concentrou dezenas de regras dentro do mesmo script até torná-lo gigantesco e frágil para alterações:

1. **`scripts/bm_mockup_video.py` (3.049 linhas / 118 KB, PROJECT_PY):**
   - Responsabilidades misturadas:
     1. Constantes globais, caminhos e detecção de layout/resoluções.
     2. Servidor HTTP local em thread (`ThreadingHTTPServer`) com rotas de preview.
     3. Automação Playwright Chromium (gestão de browser e contextos).
     4. Orquestração de handlers de notícias e fallback de screenshots (Multi-Shot, X, Instagram, UOL Flash).
     5. Cálculo de timeline de cenas (b-roll, notícias, avatar de Peter) sincronizadas com o áudio MP3.
     6. Linha de comando FFmpeg complexa com aceleração VA-API e lock em `/tmp/vale-bm-vaapi.lock`.
     7. Upload e publicação no YouTube via API v3 com gestão de cotas.
   - *Nota de Governança:* Karaoke BM (`bm_karaoke.py`) foi rejeitado — **não** criar módulo de karaoke.

2. **`scripts/pipeline.py` (1.147 linhas / 44 KB, HERMES_PY):**
   - CLI real: `init`, `collect`, `roteiro`, `process`, `validate`, `audio`, `full`, `update-archive`/`archive`, `publish`. Flags: `--date`, `--hours`, `--no-collect`, `--skip-audio`, `--force-roteiro`, `--allow-short-audio`. **Não existe `--dry-run`.**
   - A otimização Python já introduziu `_run_subprocess_step` e o paralelismo `ads ∥ thumb` via `ThreadPoolExecutor`.

---

## 2. A Solução: Arquitetura em Fachada (Facade Pattern)

Para garantir **zero impacto operacional**, o arquivo na raiz de `scripts/` é preservado, mas seu interior se torna um orquestrador limpo de menos de 100 linhas que delega cada etapa para submódulos especializados e testáveis isoladamente.

O pacote oficial do BM é **`scripts/bm_video/`** (conforme alinhado no Plano 08):

```
scripts/
├── bm_mockup_video.py                  # Fachada canônica (mantém o CLI original)
├── bm_video/                           # [NOVO PACOTE - Absorve Plano 08 de Otimização]
│   ├── __init__.py
│   ├── constants.py                    # Constantes de layout, resolução e caminhos
│   ├── state.py                        # Estrutura de cenas, beat payload e estado
│   ├── server.py                       # Servidor HTTP local isolado
│   ├── capture.py                      # Playwright Chromium, stealth e handlers
│   ├── render.py                       # Compositor FFmpeg, VA-API lock e muxing
│   └── youtube.py                      # Upload YouTube v3 e registro em videos_published.json
│
├── pipeline.py                         # Fachada canônica do Diário
└── pipeline_steps/                     # [NOVO PACOTE]
    ├── __init__.py
    ├── step_init.py                    # Coleta e template inicial
    ├── step_roteiro.py                 # Roteirização via Gemini 3.8 Flash
    ├── step_process.py                 # Markdown final e pré-processamento TTS
    ├── step_audio.py                   # Orquestração TTS multi-voz e fallbacks
    └── step_publish.py                 # R2 upload e catálogo PWA
```

---

## 3. Plano de Decomposição de `bm_mockup_video.py`

### Módulo 1: `scripts/video/server.py`
- Extrai a classe `ThreadingHTTPServer` e `SimpleHTTPRequestHandler`.
- Função simples:
  ```python
  def start_mockup_server(root_dir: Path, port: int = 0) -> tuple[ThreadingHTTPServer, int]:
      """Inicia servidor local em thread separada e retorna instância e porta alocada."""
  ```
- **Vantagem:** Pode ser testado com um simples `requests.get("http://127.0.0.1:port")`.

### Módulo 2: `scripts/video/timeline.py`
- Extrai o cálculo de tempos de cena a partir do MP3 e dos links em `fonte_referencias`.
- Função pura sem efeitos colaterais de I/O de rede:
  ```python
  def calculate_scene_schedule(audio_duration: float, sources: list[dict], max_scenes: int = 8) -> list[SceneTiming]:
      """Retorna lista de cenas com início, fim e recurso associado."""
  ```

### Módulo 3: `scripts/video/compositor_ffmpeg.py`
- Isola a montagem da linha de comando do FFmpeg, preservando os parâmetros aprovados em `docs/BM-VIDEO-LAYOUT.md`:
  - Avatar Crop: `910:720:54:0`
  - Avatar Scale: `546:432`
  - Avatar Overlay: `0:H-h+38`
- Execução segura com captura de logs detalhados em caso de falha de codec.

### Fachada Resultante (`scripts/bm_mockup_video.py`):
O arquivo original passa a ser apenas o integrador:
```python
#!/usr/bin/env python3
"""bm_mockup_video.py — Ponto de entrada canônico em Fachada."""
import sys
from pathlib import Path
from video.timeline import calculate_scene_schedule
from video.server import start_mockup_server
from video.capture import resolve_scenes_screenshots
from video.compositor_ffmpeg import render_mockup_video
from video.publisher_youtube import maybe_upload_youtube

def main():
    # Mantém os mesmos argparse arguments
    # Executa os 5 passos desacoplados
    ...

if __name__ == "__main__":
    main()
```

---

## 4. Plano de Decomposição de `pipeline.py`

A decomposição de `pipeline.py` segue o mesmo princípio:
1. **`pipeline_steps/step_audio.py`**:
   - Isola a cascata de TTS **atual** (não usar 3.8 Flash aqui):
     1. Diário: `gemini-2.5-flash-preview-tts` PACKED (chunks).
     2. BM: `gemini-3.1-flash-tts-preview`.
     3. Fallback Edge-TTS por fala (não ElevenLabs como primário).
   - Centraliza o gate de segurança: conferir se o arquivo MP3 tem no mínimo 1 MB antes de aprovar a entrega.
2. **`pipeline_steps/step_publish.py`**:
   - Isola o upload para Cloudflare R2 e a chamada de reconstrução do catálogo em `public/`.
3. **`pipeline.py` (Fachada)**:
   - Gerencia apenas a CLI e o roteamento das etapas solicitadas (`init`, `full`, `audio`, etc.).

---

## 5. Estratégia de Transição Sem Regressão

1. **Fase Paralela (Shadow Verification):**
   - Criar os módulos internos em `scripts/video/` e `scripts/pipeline_steps/`.
   - Executar testes unitários em cada módulo isolado com dados de teste.
2. **Troca da Fachada:**
   - Fazer backup do script monolítico em `archive/legacy_monoliths/`.
   - Conectar a fachada aos novos módulos.
3. **Validação:**
   ```bash
   HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
   PROJECT_PY=/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3
   $HERMES_PY scripts/pipeline.py --help
   $PROJECT_PY scripts/bm_mockup_video.py --help
   ```
   **Proibido:** `$HERMES_PY scripts/pipeline.py full --date 2026-09-01` e qualquer `--dry-run` no diário (flag inexistente). `bm_mockup_video.py --dry-run` existe e é o smoke de vídeo (sem upload se não passar `--upload`).
