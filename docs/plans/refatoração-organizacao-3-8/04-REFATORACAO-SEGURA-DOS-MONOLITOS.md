# 04 — Refatoração Segura dos Monólitos (`bm_mockup_video.py` e `pipeline.py`)

> **Foco:** Decomposição em camadas dos dois maiores monólitos do sistema sem alterar interfaces de linha de comando.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — 1749/67KB e 1111/43KB; sem `--dry-run` no `pipeline.py`; TTS ≠ 3.8.  
> **Risco:** Médio (mitigado pelo Padrão Facade / Fachada de Retrocompatibilidade).  
> **Diretriz de Segurança:** Os comandos do cron `pipeline.py full` e `bm_mockup_video.py` devem manter exatamente as mesmas flags, saídas no stdout e códigos de saída (`exit codes`).

---

## 1. O Problema dos Monólitos

O "vibe coding" acumulativo tende a concentrar novas regras dentro do mesmo script funcional até torná-lo um arquivo gigantesco e difícil de testar:

1. **`scripts/bm_mockup_video.py` (1.749 linhas / 67 KB, PROJECT_PY):**
   - Responsabilidades misturadas:
     1. Levantar servidor HTTP local em thread com rotas para assets e wallpapers.
     2. Automação Playwright Chromium para navegar e esperar fontes.
     3. Orquestração de handlers de notícias e fallback de screenshots.
     4. Cálculo de timeline de cenas (b-roll, notícias, avatar de Peter Albuquerque) sincronizadas com o áudio MP3.
     5. Linha de comando FFmpeg complexa com múltiplos inputs e filtros complexos (`[0:v]scale...`).
     6. Geração de thumbnails.
     7. Upload e publicação no YouTube via API v3.
   - *Consequência:* Qualquer ajuste no layout do vídeo corre o risco de quebrar o servidor HTTP ou o upload do YouTube.

2. **`scripts/pipeline.py` (1.111 linhas / 43 KB, HERMES_PY):**
   - CLI real: `init`, `collect`, `roteiro`, `process`, `validate`, `audio`, `full`, `update-archive`/`archive`, `publish`. Flags: `--date`, `--hours`, `--no-collect`, `--skip-audio`, `--force-roteiro`, `--allow-short-audio`. **Não existe `--dry-run`.**

---

## 2. A Solução: Arquitetura em Fachada (Facade Pattern)

Para garantir **zero impacto operacional**, o arquivo na raiz de `scripts/` é preservado, mas seu interior se torna um orquestrador limpo de menos de 100 linhas que delega cada etapa para submódulos especializados e testáveis isoladamente.

```
scripts/
├── bm_mockup_video.py                  # Fachada canônica (mantém o CLI original)
├── video/                              # [NOVO PACOTE]
│   ├── __init__.py
│   ├── server.py                       # Servidor HTTP local isolado
│   ├── capture.py                      # Gerenciador de screenshots e handlers
│   ├── timeline.py                     # Cálculo de cenas, durações e b-roll
│   ├── compositor_ffmpeg.py            # Geração de comandos FFmpeg e muxing
│   └── publisher_youtube.py            # Integração com YouTube API
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
