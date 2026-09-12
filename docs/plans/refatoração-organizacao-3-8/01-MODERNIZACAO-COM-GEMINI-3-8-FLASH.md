# 01 — Modernização dos Subsistemas com Gemini 3.8 Flash

> **Foco:** Atualização da camada de Inteligência Artificial para o modelo **Gemini 3.8 Flash**.  
> **Status:** PLANEJADO (Pronto para execução atômica)  
> **Arquivos Impactados:** `scripts/gemini_client.py`, `sources/gemini_limits.json`, `scripts/generate_roteiro_llm.py`, `scripts/bm_condensador.py`, `scripts/youtube_thumbnail.py`, `scripts/title_optimizer.py`.  
> **Diretriz de Segurança:** Nenhuma chave em código; fallback automático para os modelos anteriores caso haja esgotamento temporário de cota.

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

> [!CAUTION]
> **REGRA DE OURO DAS COTAS:** As cotas de RPM, RPD e TPM do `gemini-3.8-flash` **NÃO devem ser inventadas** (evitar valores hipotéticos como 15 RPM / 1500 RPD).  
> No momento da execução do **Dia 1**, o desenvolvedor/operador deve **consultar o painel real do Google AI Studio** (na aba de Rate Limits / Quotas da chave ativa) e registrar os valores oficiais exatos.  
> Caso o painel não informe limites específicos para o 3.8 Flash no Free Tier, **adotar o baseline conservador comprovado dos modelos Flash da conta** (`rpm: 5`, `rpd: 20`, `tpm: 250000`).

Adicionar o modelo `gemini-3.8-flash` com seus parâmetros de governança obtidos do AI Studio:

```json
{
  "modelos": {
    "gemini-3.8-flash": {
      "rpm": "<PREENCHER_PELO_AI_STUDIO_DEFAULT_5>",
      "tpm": "<PREENCHER_PELO_AI_STUDIO_DEFAULT_250000>",
      "rpd": "<PREENCHER_PELO_AI_STUDIO_DEFAULT_20>",
      "categoria": "flash",
      "descricao": "Modelo primário para roteiro diário, condensação BM, curadoria e manchetes (verificado no AI Studio)"
    }
  },
  "aceitos_pela_chave": [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it"
  ]
}
```

---

### B. Ajuste do Cliente Unificado (`scripts/gemini_client.py`)

> [!NOTE]
> **Base Sólida Pós-Otimização Python:** O `gemini_client.py` já recebeu a blindagem de concorrência com `fcntl.flock` no `gemini_usage.json.lock`, gravação atômica com `os.replace` e `time.sleep` fora do lock (Plano 06 de Otimização). O cliente está 100% preparado para receber o Gemini 3.8 Flash sem risco de colisão de cotas com o BM.

No método `_get_model_category` e `DEFAULT_LIMITS`, a categoria `"flash"` continua regida pelos limites conservadores reais da conta do usuário até confirmação do AI Studio:

```python
DEFAULT_LIMITS = {
    # flash: gemini-3.8/3.6/3.5/2.5-flash = 5 RPM / 250K TPM / 20 RPD (baseline real da conta)
    "flash": {
        "rpm": 5,
        "rpd": 20,
        "tpm": 250000,
    },
    # lite: gemini-3.5/3.1-flash-lite = 15 RPM / 250K TPM / 500 RPD
    "lite": {
        "rpm": 15,
        "rpd": 500,
        "tpm": 250000,
    },
    # tts: gemini-2.5/3.1-flash-tts = 3 RPM / 10K TPM / 10 RPD
    "tts": {
        "rpm": 3,
        "rpd": 10,
        "tpm": 10000,
    },
}
```

Adicionar sanitização automática de apelidos: se o script pedir `"gemini-flash"`, o cliente resolve deterministicamente para `"gemini-3.8-flash"`.

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
Em vez de confiar em prompts pedindo "retorne apenas json", passar o contrato Pydantic `RoteiroCompleto` diretamente no `response_schema`:

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

Antes de colocar o Gemini 3.8 Flash para rodar no diário das 06:00:

1. **Teste Unitário Isolado (sem impactar episódios reais):**
   ```bash
   python scripts/generate_roteiro_llm.py --date 2026-09-01 --dry-run
   ```
2. **Inspeção do JSON Gerado:**
   - Verificar se as chaves `manchetes`, `introducao`, `quadros`, `fechamento` estão presentes.
   - Conferir se o total de palavras está entre 1.500 e 2.200 palavras.
   - Validar alternância de speakers (Peter e Ricardo).
3. **Teste de Condensação BM:**
   ```bash
   python scripts/bm_condensador.py --video-id "<TEST_ID>" --dry-run
   ```
4. **Verificação de Consumo de Cota:**
   - Inspecionar `sources/gemini_usage.json` para certificar que o rate limiter registrou o modelo e calculou os tokens corretamente.
