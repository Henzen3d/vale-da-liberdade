# 05 — Padronização de Dados, Schemas Pydantic e Logging Estruturado

> **Foco:** Tipagem estrita de contratos de dados, unificação de logging e saneamento de caches.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — reutilizar `RoteiroCompleto`; cache 2,6 MB.  
> **Risco:** Baixo (operações aditivas e compatíveis).  
> **Diretriz:** Substituir dicionários sem tipo por classes Pydantic; unificar `print` soltos em logger padrão com timezone de São Paulo.

---

## 1. O Problema da Ausência de Schemas e Logs Dispersos

No desenvolvimento por vibe coding, estruturas de dados são quase sempre representadas como dicionários anônimos (`dict[str, Any]`):
- Notícias coletadas via RSS: às vezes a chave é `"url"`, às vezes `"link"`, às vezes `"source"`, às vezes `"veiculo"`.
- Roteiros do Brasil e Mundo: `especial-<id>.json` gerado por prompts LLM com variações pontuais que quebram o renderizador de vídeo (`bm_mockup_video.py`).
- Caches de arquivos: `sources/cache.json` está com **2,6 MB** (2026-08-31; gitignored) contendo milhares de notícias de meses passados.
- Logging: scripts usam `print()` misturados com `log.info()`, dificultando o monitoramento via cron ou agentes externos.

---

## 2. Modelos de Dados Canônicos (`core/models/`)

Centralizar todos os contratos de dados em `core/models/schemas.py`:

```python
"""core/models/schemas.py — Contratos Pydantic Canônicos do Sistema."""
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime

# ── Notícias e Curadoria ──────────────────────────────────────────────────
class CuratedNewsItem(BaseModel):
    title: str = Field(..., description="Título jornalístico limpo")
    url: str = Field(..., description="URL canônica da notícia")
    source: str = Field(..., description="Nome do veículo de imprensa")
    category: str = Field(..., description="seguranca, saude, educacao, politica, etc.")
    summary: str = Field(..., description="Resumo factual da notícia")
    quality_score: int = Field(default=3, ge=1, le=5)
    is_breaking: bool = Field(default=False)
    published_at: Optional[datetime] = None

# ── Roteiro Diário (Peter e Ricardo) ───────────────────────────────────────
# REUTILIZAR scripts/generate_script.py::RoteiroCompleto + RoteiroItem.
# Não criar RoteiroDiario com campo `date` — os JSON em episodes/roteiro-YYYY-MM-DD.json
# não têm essa chave (há ~40 arquivos roteiro-*.json). Alias:
#   RoteiroDiario = RoteiroCompleto

# ── Roteiro Brasil e Mundo (Peter Solo) ────────────────────────────────────
class BMReference(BaseModel):
    veiculo: str
    url: str
    titulo: Optional[str] = None

class BMRoteiroEspecial(BaseModel):
    video_id: str
    titulo: str
    texto_peter: str = Field(..., min_length=500, description="Comentário corrido de ~800 palavras")
    tags: List[str]
    fonte_referencias: List[BMReference]
    target_word_count: int = 820
```

### Benefícios:
1. **Validação Automática com Gemini 3.8 Flash:** Ao passar o modelo no `response_schema` da API, a resposta da IA é garantidamente compatível com a classe.
2. **Autocompletação e Detecção de Erros no IDE/Pyright:** Erros de digitação de chaves (`item["link"]` vs `item["url"]`) são acusados antes de rodar o código.

---

## 3. Logger Centralizado e Estruturado (`core/logger.py`)

Substituir os múltiplos loggers e prints dispersos por um utilitário centralizado com timezone `America/Sao_Paulo`:

```python
"""core/logger.py — Logging estruturado com suporte a timezone brasileiro."""
import logging
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")

class BrazilTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=BRT)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")

def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = BrazilTimeFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # Handler stdout
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

        # Handler em arquivo diário (se informado)
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            today_str = datetime.now(BRT).strftime("%Y-%m-%d")
            fh = logging.FileHandler(log_dir / f"{name}-{today_str}.log", encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)

    return logger
```

---

## 4. Política de Retenção e Rotação de Logs

Para evitar que a pasta `logs/` ocupe espaço indefinido no servidor:
1. Criar rotina semanal de limpeza: expurgar logs com mais de 14 dias de idade.
2. Script utilitário em `scripts/maintenance/cleanup_logs.py`:
   ```python
   def purge_old_logs(logs_dir: Path, max_age_days: int = 14):
       now = datetime.now().timestamp()
       for f in logs_dir.glob("*.log"):
           if (now - f.stat().st_mtime) > (max_age_days * 86400):
               f.unlink()
   ```

---

## 5. Saneamento do Cache de Notícias (`sources/cache.json`)

O arquivo `sources/cache.json` guarda o histórico de URLs já coletadas para evitar notícias repetidas:
- Atualmente com **2,6 MB**.
- **Ação de saneamento:**
  - Manter apenas entradas dos últimos 45 dias.
  - Backup local do JSON antes do purge (`cp sources/cache.json sources/cache.json.bak` — o `.bak` já é gitignored).
  - Redução estimada: de 2,6 MB para ~300 KB.
