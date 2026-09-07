# 06 — Suíte de Testes e Garantia de Qualidade

> **Foco:** Consolidação dos testes em `tests/`, testes de regressão automatizados e validação de pipelines sem gastar cotas de API.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — pytest 9.1.1 só no PROJECT_PY; Hermes venv sem pytest; `tests/` tem 11 arquivos.  
> **Risco:** Zero (aditivo, não altera código de execução de produção).  
> **Meta:** Permitir que qualquer refatoração futura seja validada em menos de 10 segundos com `pytest`.

---

## 1. O Cenário Atual de Testes

Atualmente, o projeto possui testes fragmentados:
- Mais de 25 arquivos `test_*.py` soltos em `scripts/` (21 `test_*.py` + 2 `teste_*.py` + check/qa).
- Testes que batem na API real do Gemini ou do YouTube, gastando cotas de produção e falhando se a máquina estiver offline ou com chaves restritas.
- A pasta `tests/` oficial na raiz tem **11** arquivos (não 9).
- `pytest` está **somente** em `/home/osmar/web-jornal-vale-da-liberdade/.venv` (9.1.1). O venv Hermes **não** tem pytest.

---

## 2. A Nova Arquitetura de Testes (`tests/`)

Consolidação completa usando o padrão profissional `pytest`:

```
tests/
├── conftest.py                     # Fixtures compartilhadas (caminhos, envs mockadas, json mocks)
├── pytest.ini                      # Configuração do pytest (paths, markers, warnings)
├── fixtures/                       # Amostras de dados reais para testes offline
│   ├── raw_sample.md               # Exemplo de coleta de notícias real
│   ├── roteiro_diario_sample.json  # Exemplo de roteiro completo válido
│   └── bm_especial_sample.json     # Exemplo de episódio Brasil & Mundo
├── unit/                           # Testes unitários puros (sem rede, < 1 segundo)
│   ├── test_env_loader.py
│   ├── test_json_parser.py
│   ├── test_url_cleaner.py
│   ├── test_gemini_rate_limiter.py
│   ├── test_tts_preprocessor.py
│   └── test_timeline_builder.py
├── integration/                    # Testes de integração de subsistemas
│   ├── test_pydantic_schemas.py
│   ├── test_cron_wrappers.py
│   ├── test_gemini_38_client_mock.py
│   └── test_upload_r2_contract.py
└── regression/                     # Testes de não-regressão dos fluxos de produção
    ├── test_diario_flow_dryrun.py
    └── test_bm_flow_dryrun.py
```

---

## 3. Principais Testes Críticos a Implementar

### A. Teste de Rate Limiter do Gemini com Mock de Relógio
Garante que o cliente respeite os limites de RPM e RPD do Gemini 3.8 Flash sem disparar requisições prematuras:
```python
"""tests/unit/test_gemini_rate_limiter.py"""
def test_rate_limiter_respects_rpm(tmp_path):
    # Simula uso e valida se tempo de espera é calculado com precisão
    ...
```

### B. Teste de Resiliência de Schemas Pydantic
Carrega episódios já publicados do diretório `episodes/` e valida se todos passam na validação dos novos schemas Pydantic:
```python
"""tests/integration/test_pydantic_schemas.py"""
from pathlib import Path
import json
from core.models.schemas import RoteiroCompleto as RoteiroDiario

def test_historical_episodes_match_schema():
    episodes_dir = Path("episodes")
    json_files = list(episodes_dir.glob("roteiro-*.json"))[:10]
    for jf in json_files:
        data = json.loads(jf.read_text(encoding="utf-8"))
        # Garante retrocompatibilidade total com roteiros anteriores
        assert RoteiroDiario(**data)
```

### C. Teste de Integridade dos Shell Wrappers
Validação estática de sintaxe de todos os wrappers de shell (`bash -n`):
```python
"""tests/integration/test_cron_wrappers.py"""
import subprocess
from pathlib import Path

def test_cron_wrappers_syntax():
    wrappers = [
        Path("scripts/cron-wrapper.sh"),
        Path("scripts/bm-hourly-pipeline.sh"),
    ]
    for w in wrappers:
        res = subprocess.run(["bash", "-n", str(w)], capture_output=True, text=True)
        assert res.returncode == 0, f"Erro de sintaxe em {w}: {res.stderr}"
```

### D. Mock Test do Gemini 3.8 Flash (Sem Gasto de Cota)
Testa se a chamada com `response_schema` monta os parâmetros esperados pelo SDK oficial do Google:
```python
"""tests/unit/test_gemini_38_client_mock.py"""
from unittest.mock import MagicMock
from core.gemini.client import GeminiClient

def test_gemini_38_call_structure():
    mock_genai_client = MagicMock()
    client = GeminiClient(api_key="test-key-fake")
    client.client = mock_genai_client

    # Simula geração com Gemini 3.8 Flash
    ...
```

---

## 4. Como Executar a Suíte de Testes

Configuração de `pytest.ini` na raiz:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
```

Comando neste servidor:

```bash
PROJECT_PY=/home/osmar/web-jornal-vale-da-liberdade/.venv/bin/python3
$PROJECT_PY -m pytest tests/unit/
$PROJECT_PY -m pytest
```

Não usar `pytest` nem `python` soltos. *Tempo total esperado:* inferior a 5 segundos (mocks, sem rede).
