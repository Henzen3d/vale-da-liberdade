# 03 — Organização Modular de Scripts e Eliminação de Código Duplicado

> **Foco:** Descongestionamento do diretório `scripts/` (de **139** arquivos no maxdepth 1 para ~25) e criação da camada compartilhada `core/`.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — censo real; `core/` ainda não existe; env só do `.env` do projeto.  
> **Risco:** Baixo (preservando shims e retrocompatibilidade com scripts chamadores).  
> **Diretriz Suprema:** Manter os pontos de entrada oficiais (`scripts/pipeline.py`, `scripts/bm_pipeline.py`, `scripts/cron-wrapper.sh`, etc.) intactos no CLI.

---

## 1. Diagnóstico do Caos em `scripts/`

O diretório `scripts/` sofre do efeito "gaveta de bagunça": qualquer nova funcionalidade criada por agentes LLM foi gravada diretamente na raiz de `scripts/`.

### 📊 Censo Atual de `scripts/` (139 arquivos maxdepth 1; 103 `.py`):
1. **21 Arquivos SQL:** `01`–`18` (sem `13_`) + `fix_admin_rpc.sql`, `fix_campaigns_rpc.sql`, `fix_interactions_rpc.sql`, `seed_test_data.sql`.
2. **28 Arquivos de Teste Soltos:** `21 test_*.py`, `2 teste_*.py`, `1 check_*.py`, `4 qa_*`. `tests/` na raiz tem 11 arquivos.
3. **8 Scripts de Protótipos Aposentados:** `faceless_*.py` (5 arquivos), `clean_screenshot.py` (untracked), `youtube_video_generator.py`, `bm_video_autopilot.py`.
4. **Wrappers Shell Obsoletos (existem):** `cron-daily.sh`, `cron-wrapper-v2.sh`, `daily-collect.sh`, `qa_delivery_chain.sh`, `tts_fallback_edge.sh`.
5. **Funções Idênticas Duplicadas** em `generate_roteiro_llm.py`, `bm_condensador.py`, `title_optimizer.py` (`_candidate_keys`, `_call_gemini`, `_call_openrouter`, `extract_json` / `extract_json_object`). `thumbnail_generator.py` importa `_candidate_keys` de `generate_roteiro_llm` — atualizar esse import junto.

---

## 2. Nova Estrutura Arquitetural

A reorganização separa responsabilidades em 4 áreas claras:

```
web-jornal-vale-da-liberdade/
├── core/                               # NOVO: Camada pura de regras e utilitários
│   ├── __init__.py
│   ├── config.py                       # Caminhos globais, detecção de OS e venvs
│   ├── logger.py                       # Logger estruturado padrão
│   ├── gemini/
│   │   ├── __init__.py
│   │   ├── client.py                   # GeminiClient e GeminiMultiClient unificados
│   │   ├── rate_limiter.py             # Lógica de quotas, backoff e persistência
│   │   └── schemas.py                  # Schemas Pydantic canônicos
│   └── utils/
│       ├── __init__.py
│       ├── env_loader.py               # Leitura segura de chaves sem duplicação
│       ├── json_parser.py              # Parser JSON resiliente centralizado
│       └── url_cleaner.py              # Limpeza de UTMs e normalização
│
├── database/migrations/                # NOVO: Todos os 21 arquivos .sql
│
├── tests/                              # Consolidação de todos os testes
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── scripts/                            # Apenas pontos de entrada executáveis (~25 arquivos)
    ├── cron-wrapper.sh                 # Gatilho canônico Diário
    ├── bm-hourly-pipeline.sh           # Gatilho canônico BM
    ├── pipeline.py                     # CLI do Diário
    ├── bm_pipeline.py                  # CLI do BM
    ├── bm_mockup_video.py              # Renderizador Mockup YouTube
    ├── generate_gemini_tts_multi.py    # Motor TTS multi-voz
    ├── publish_site.py                 # Publicador de catálogo e PWA
    ├── news_collector.py               # Coletor RSS
    ├── tts_preprocessor.py             # Pré-processador de fala
    ├── youtube_uploader.py             # Uploader YouTube
    ├── screenshots/                    # Motor de screenshots jornalísticos
    └── archive_legacy/                 # Quarentena de scripts aposentados
```

---

## 3. Passo a Passo da Migração

### Passo 1: Mover os Arquivos SQL para `database/migrations/`
```bash
mkdir -p database/migrations/
mv scripts/*.sql database/migrations/
```
*Impacto:* Zero em produção (SQL é setup pontual do Supabase). São **21** arquivos, não 18. `vale-production-safety` aplica SQL via `docker exec -i supabase-db psql` — atualizar qualquer doc/skill que cite `scripts/NN_*.sql` para `database/migrations/`.

---

### Passo 2: Migrar Arquivos de Teste Soltos para `tests/`
Mover os 28 arquivos de teste dispersos em `scripts/` para `tests/`:
```bash
mv scripts/test_*.py tests/
mv scripts/teste_*.py tests/
mv scripts/check_*.py tests/
mv scripts/qa_*.mjs tests/
mv scripts/qa_*.sh tests/
```
*Garantia:* Atualizar o `PYTHONPATH` nos testes para incluir a raiz do projeto (`sys.path.insert(0, str(PROJECT_ROOT))`).

---

### Passo 3: Isolar Scripts Legados e Protótipos Aposentados
Mover scripts que já foram oficialmente desligados (conforme `03-MAPA-CANONICO-VIVO-MORTO.md`):
```bash
mkdir -p scripts/archive_legacy/
mv scripts/faceless_*.py scripts/archive_legacy/
mv scripts/clean_screenshot.py scripts/archive_legacy/
mv scripts/youtube_video_generator.py scripts/archive_legacy/
mv scripts/bm_video_autopilot.py scripts/archive_legacy/
mv scripts/cron-daily.sh scripts/archive_legacy/
mv scripts/cron-wrapper-v2.sh scripts/archive_legacy/
mv scripts/daily-collect.sh scripts/archive_legacy/
mv scripts/tts_fallback_edge.sh scripts/archive_legacy/
```

---

### Passo 4: Construir o Pacote `core/` e Eliminar Duplicações

#### 1. Criar `core/utils/env_loader.py`:
Unificar a função copiada `_candidate_keys` em um único ponto com cache:
```python
"""core/utils/env_loader.py"""
from pathlib import Path
import os
from functools import lru_cache

@lru_cache(maxsize=4)
def get_gemini_api_keys(project_root: Path) -> list[str]:
    """Retorna lista única de chaves GEMINI_API_KEY do ambiente e arquivos .env."""
    seen = set()
    keys = []
    # 1. Variáveis de ambiente
    for k, v in os.environ.items():
        if (k == "GEMINI_API_KEY" or (k.startswith("GEMINI_API_KEY_") and k.split("_")[-1].isdigit())) and v.strip():
            val = v.strip()
            if val not in seen and "***" not in val:
                seen.add(val)
                keys.append(val)
    # 2. Arquivos .env
    for env_path in (project_root / ".env",):
        # SOMENTE o .env do projeto. NÃO ler Path.home() / ".hermes" / ".env"
        # (vale-production-safety: cron faz source só do .env do Vale).
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if (k == "GEMINI_API_KEY" or (k.startswith("GEMINI_API_KEY_") and k.split("_")[-1].isdigit())) and v:
                        if v not in seen and "***" not in v:
                            seen.add(v)
                            keys.append(v)
    return keys
```

#### 2. Criar `core/utils/json_parser.py`:
Extração resiliente de JSON com tratamento de blocos de markdown e chaves balanceadas em um único lugar testado.

#### 3. Substituir nos Scripts Vivos:
Em `scripts/generate_roteiro_llm.py`, `scripts/bm_condensador.py`, `scripts/title_optimizer.py` e `scripts/youtube_captions.py`:
- Remover as 80 linhas duplicadas de `_candidate_keys` e `extract_json`.
- Substituir por:
  ```python
  from core.utils.env_loader import get_gemini_api_keys
  from core.utils.json_parser import extract_json_object
  from core.gemini.client import GeminiMultiClient
  ```

---

## 4. Garantia de Retrocompatibilidade

Para garantir que nada quebre caso algum script legado ou crontab tente importar `gemini_client` diretamente de `scripts/`:
- Deixar um shim em `scripts/gemini_client.py`:
  ```python
  # scripts/gemini_client.py (shim de compatibilidade)
  import sys
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
  from core.gemini.client import GeminiClient, GeminiMultiClient, DEFAULT_LIMITS  # noqa: F401
  ```
- O `cron-wrapper.sh` já exporta `PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"` — imports `from core...` funcionam no diário. `bm-hourly-pipeline.sh` **não** seta PYTHONPATH hoje: na execução do Dia 3/4, ou adicionar `export PYTHONPATH="$WORK_DIR:${PYTHONPATH:-}"` no wrapper BM, ou manter `sys.path` nos scripts.
- Testes: `$PROJECT_PY -m pytest` (pytest **não** está no venv Hermes).
- `core/` deve importar nos **dois** venvs (pydantic 2.13.4 nos dois). Não unificar venvs (Dia 5 da reorganização cirúrgica).
