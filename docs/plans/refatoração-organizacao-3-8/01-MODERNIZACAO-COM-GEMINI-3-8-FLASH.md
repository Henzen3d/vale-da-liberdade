# 01 — Modernização dos Subsistemas com Gemini 3.8 Flash

> **Foco:** Atualização da camada de Inteligência Artificial para o modelo **Gemini 3.8 Flash** (texto). TTS **não muda**.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Adaptação servidor:** 2026-09-02 — CLI real, venv Hermes, cotas 3.8 TBD.  
> **Arquivos Impactados:** `scripts/gemini_client.py`, `sources/gemini_limits.json`, `scripts/generate_roteiro_llm.py`, `scripts/bm_condensador.py`, `scripts/youtube_thumbnail.py`, `scripts/title_optimizer.py`.  
> **Diretriz de Segurança:** Nenhuma chave em código; fallback automático para os modelos anteriores caso haja esgotamento temporário de cota. Não gastar RPD de produção em `--force` de episódio já publicado.

---

## 1. Por Que o Gemini 3.8 Flash Muda o Jogo

O **Gemini 3.8 Flash** traz ganhos imediatos nos dois gargalos principais de IA do Web Jornal:

1. **Roteiro do Diário (Peter & Ricardo):**
   - No modelo anterior, havia tendência a respostas burocráticas quando o texto da fonte vinha de assessorias de imprensa, exigindo scripts de "desburocratização" e naturalização.
   - O Gemini 3.8 Flash possui compreensão de estilo conversacional muito mais apurada, captando a malícia jornalística, o sarcasmo do Peter Albuquerque e a vibração popular de rádio do Ricardo Souto de primeira.
2. **Condensação do Brasil e Mundo (YouTube):**
   - Transcrições de 30 a 50 minutos agora podem ser passadas inteiras no prompt, permitindo ao modelo identificar a tese central, os argumentos fracos e os furos do debate original sem truncamento.
3. **Structured Outputs com Schema Nativo:**
   - Elimina de vez o risco de `json.JSONDecodeError` por causa de markdown fences (` ```json `), comentários ou aspas desbalanceadas.

---

## 2. Especificação Técnica das Mudanças

### A. Atualização do Registro Central de Modelos (`sources/gemini_limits.json`)

Adicionar o modelo `gemini-3.8-flash` **somente depois de copiar RPM/TPM/RPD do AI Studio**. `sources/gemini_limits.json` (2026-09-02) **não contém 3.8**. Os números abaixo são **placeholder** — não commitar 15/1500 inventados.

Cascata **atual em disco** (antes da troca):
- `generate_roteiro_llm.py`: `3.6-flash` → `3-flash-preview` → `3.5-flash-lite` → `3.1-flash-lite` → `gemma-4-31b-it`
- `bm_condensador.py`: `3.5-flash-lite` → `3.1-flash-lite` → `3.6-flash` → `3-flash-preview` → `gemma-4-31b-it`
- `youtube_thumbnail.py` L239: `gemini-flash-latest`, `gemini-flash-lite-latest` (aliases)

```json
{
  "modelos": {
    "gemini-3.8-flash": {
      "rpm": "TBD_AI_STUDIO",
      "tpm": "TBD_AI_STUDIO",
      "rpd": "TBD_AI_STUDIO",
      "categoria": "flash_nextgen",
      "descricao": "Modelo primário para roteiro diário, condensação BM, curadoria e manchetes — preencher cotas reais no Dia 1"
    }
  }
}
```

`aceitos_pela_chave` hoje: `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemma-4-31b-it`. Incluir `gemini-3.8-flash` só se a chave AI Studio aceitar (senão 404 como `gemini-2.5-flash`).

---

### B. Ajuste do Cliente Unificado (`scripts/gemini_client.py`)

No método `_get_model_category` e `DEFAULT_LIMITS`, **não sobrescrever** os limites reais da chave (já em disco):

```python
DEFAULT_LIMITS = {
    "flash": {"rpm": 5, "rpd": 20, "tpm": 250000},   # 3.6 / 3.5-flash
    "lite":  {"rpm": 15, "rpd": 500, "tpm": 250000},
    "tts":   {"rpm": 3, "rpd": 10, "tpm": 10000},    # 2.5 / 3.1 TTS — intocado
}
```

Se 3.8 Flash tiver cotas diferentes no AI Studio, criar categoria `flash_nextgen` **aditiva**. Não inventar `flash rpm=10 rpd=200`.

Adicionar sanitização de apelidos: se o script pedir `"gemini-flash"`, o cliente resolve para `"gemini-3.8-flash"` **só depois** de o modelo estar em `aceitos_pela_chave`.

---

### C. Roteirização do Jornal Diário (`scripts/generate_roteiro_llm.py`)

#### 1. Reordenação da Cascata Canônica de Modelos:
```python
GEMINI_MODELS = [
    "gemini-3.8-flash",        # Primário: velocidade máxima, structured outputs perfeitos e nuance editorial
    "gemini-3.6-flash",        # Fallback 1: alta estabilidade histórica
    "gemini-3.5-flash-lite",   # Fallback 2: alta cota (500 RPD) para dias com muitas notícias
    "gemini-3.1-flash-lite",   # Fallback 3: backup leve
    "gemma-4-31b-it",          # Fallback 4: contingência aberta
]
```

#### 2. Implementação de Structured Outputs Nativos do SDK Google GenAI:
Em vez de confiar em prompts pedindo "retorne apenas json", passar o contrato Pydantic `RoteiroCompleto` diretamente no `response_schema`.

**Schema já existente:** `scripts/generate_script.py` tem `RoteiroCompleto` (`manchetes`, `introducao`, `quadros`, `fechamento`) + `RoteiroItem`. Reutilizar esse contrato — **não** criar `RoteiroDiario` paralelo com campo `date` que os JSON históricos não têm.

```python
from google.genai import types
from generate_script import RoteiroCompleto

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=RoteiroCompleto,
        max_output_tokens=16384,
    ),
)
```

**Benefício imediato:** Impossibilidade de o modelo devolver texto quebrado, eliminando dezenas de linhas de regex de extração de JSON.

---

### D. Condensador Brasil e Mundo (`scripts/bm_condensador.py`)

No pipeline do Brasil e Mundo, a transcrição bruta do YouTube (`RAW_DIR / f"{video_id}.json"`) contém fala informal, repetições e gaguejos do vídeo fonte.

#### Atualização de Modelos:
```python
GEMINI_MODELS = [
    "gemini-3.8-flash",        # Primário absoluto
    "gemini-3.5-flash-lite",   # Fallback rápido
    "gemini-3.6-flash",
]
```

#### Refinamento do Prompt com Gemini 3.8 Flash:
Aproveitar a capacidade de raciocínio do 3.8 Flash para instruir a postura editorial de Peter Albuquerque com mais clareza:
- Extração de fatos brutos ignorando a narrativa do vídeo original.
- Aplicação imediata dos 10 mandamentos editoriais do Peter (anti-estatismo lúcido, impacto econômico real, ceticismo com discursos oficiais).
- Saída diretamente no schema `EspecialPeterRoteiro` com validação de contagem de palavras (~800 palavras = ~5 minutos).

---

### E. Otimizador de Manchetes e Thumbnails (`youtube_thumbnail.py` & `title_optimizer.py`)

Atualmente, `youtube_thumbnail.py` linha 239 tenta `("gemini-flash-latest", "gemini-flash-lite-latest")`, que são nomes genéricos ou que caem em modelos legados.

#### Atualização:
```python
THUMBNAIL_HEADLINE_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
)
```

Com o Gemini 3.8 Flash, a manchete curta da thumbnail ganha regras mais apuradas:
- Máximo 4 a 6 palavras.
- Destaque em amarelo (highlight de 1 a 2 palavras com alto impacto visual).
- Linguagem assertiva, sem termos pomposos ou burocráticos.

---

## 3. Protocolo de Validação Sem Quebrar Produção

Interpretador: `HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3`.

`generate_roteiro_llm.py` **não tem `--dry-run`**. Flags reais: `--date` (obrigatório), `--force`, `--attempts`. `bm_condensador.py` flags reais: `--video-id`, `--video-id-env`, `--force`. **Não há `--dry-run`.**

1. **Não regenerar episódio publicado.** `--force` em `2026-09-01` (ou qualquer data já no ar) dispara LLM + reescreve `episodes/roteiro-*.json`. Validação segura:
   ```bash
   HERMES_PY=/home/osmar/.hermes/hermes-agent/venv/bin/python3
   $HERMES_PY -m py_compile scripts/generate_roteiro_llm.py scripts/bm_condensador.py scripts/gemini_client.py
   $HERMES_PY -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/generate_roteiro_llm.py').read_text())"
   ```
2. Smoke **só** com data de hoje e dono ciente, ou com `--date` de um rascunho que ainda não entrou no catálogo.
3. **Inspeção do JSON** (se houver smoke autorizado): chaves `manchetes`, `introducao`, `quadros`, `fechamento`; speakers Peter/Ricardo.
4. **Cota:** inspecionar `sources/gemini_usage.json` (já gitignored) após qualquer chamada real. TTS 3.1/2.5 permanece intocado.
