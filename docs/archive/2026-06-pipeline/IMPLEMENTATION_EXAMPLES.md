<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# IMPLEMENTATION_EXAMPLES — Exemplos Práticos e Recomendações Estratégicas

> Exemplos de código, workflows e contratos de dados para executar o `ROADMAP.md`.
> Recomendações estratégicas (deliverable 5) na Seção 6.
>
> **Mantém:** Hermes Agent | **Locale:** pt-BR | **Atualização:** 2026-06-20

---

## 1. Contrato de dados: `roteiro-{date}.json` (Fase 1.2)

O `RoteiroCompleto` (hoje em `generate_script.py:72-76`) passa a ser o **contrato entre
o Hermes Agent (que gera o JSON) e o renderer (que produz `{date}.md`)**.

```json
{
  "edicao": "2026-06-20",
  "episodio": 47,
  "manchetes": [
    "Câmara de Blumenau aprova reajuste de 5% no IPTU 2027",
    "Incêndio atinge galpão na BR-470 em Indaial",
    "Suspensão de 350 ampolas de insulina no SUS municipal"
  ],
  "introducao": [
    {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "..."},
    {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Ricardo", "texto": "..."},
    {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "..."}
  ],
  "quadros": [
    {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "texto": "..."},
    {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "texto": "..."}
  ],
  "fechamento": [
    {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Peter", "texto": "..."},
    {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Ricardo", "texto": "..."}
  ],
  "meta": {
    "palavras_total": 2350,
    "duracao_estimada_min": 15.0,
    "breaking_news": ["Incêndio BR-470"],
    "fontes_utilizadas": ["ndmais_blumenau", "mesorregional", "g1"],
    "continuidade_com": "2026-06-19"
  }
}
```

**Renderer Python (substitui o bloco Gemini em `generate_script.py`):**

```python
def render_from_json(date: str) -> str:
    """Renderiza roteiro-{date}.json → {date}.md. Sem chamadas de LLM."""
    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if not json_path.exists():
        raise FileNotFoundError(
            f"Contrato ausente: {json_path}. "
            f"Execute o Hermes Agent para gerar o roteiro (ver SKILL.md)."
        )
    roteiro = RoteiroCompleto(**json.loads(json_path.read_text(encoding="utf-8")))
    return format_script(date, roteiro)  # format_script() já existe, L224-274
```

---

## 2. Ranking de relevância local (Fase 2.5)

Fórmula programática que substitui o `quality_score` puramente-LLM:

```python
# sources/geo_weights.json (config-driven)
GEO_WEIGHTS = {
    "blumenau": 1.0, "rio do sul": 0.8, "indaial": 0.8, "pomerode": 0.8,
    "gaspar": 0.8, "timbó": 0.7, "ascurra": 0.7,
    "santa catarina": 0.5, "sc": 0.5,
    "brasil": 0.3,  # nacional com impacto
}

def geo_score(text: str) -> float:
    """Maior peso geo encontrado no título+resumo."""
    t = text.lower()
    return max((w for k, w in GEO_WEIGHTS.items() if k in t), default=0.0)

def credibility_score(source_id: str, cache: dict) -> float:
    """tier (1=0.9, 2=0.6) × taxa de sucesso histórica."""
    stats = cache.get("source_stats", {}).get(source_id, {})
    success_rate = stats.get("success_count", 0) / max(stats.get("total_fetches", 1), 1)
    return success_rate  # combinar com tier no caller

def recency_decay(published_iso: str, now=None) -> float:
    """Decai exponencialmente: 1.0 há 0h, ~0.5 há 24h, ~0.13 há 48h."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    age_h = (now - datetime.fromisoformat(published_iso)).total_seconds() / 3600
    return 0.5 ** (age_h / 24)

def relevance(item: dict, source_tier: int, cache: dict, burst: float = 0.0,
              engagement: float = 0.0) -> float:
    """Score composto 0-1."""
    g = geo_score(item.get("title", "") + " " + item.get("content", ""))
    c = (0.9 if source_tier == 1 else 0.6) * credibility_score(item.get("source_id",""), cache)
    r = recency_decay(item.get("published", ""))
    return (
        0.35 * g +
        0.25 * c +
        0.20 * r +
        0.10 * burst +
        0.10 * engagement
    )
```

**Por quê:** transparente, auditável, ajustável sem retratar o LLM. O Hermes faz só o
ajuste editorial final por cima (decide lineup, escreve sumário).

---

## 3. Dedup semântica + clustering (Fase 0.3 + 2.2)

Implementação leve com MinHash (sem dependências pesadas):

```python
import re
from collections import defaultdict

def _shingles(text: str, k: int = 3) -> set:
    """Conjunto de k-shingles de palavras (lowercase, sem acento leve)."""
    tokens = re.findall(r"\w+", text.lower())
    return {" ".join(tokens[i:i+k]) for i in range(len(tokens) - k + 1)} if len(tokens) >= k else set(tokens)

def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)

SIMILARITY_THRESHOLD = 0.45  # ajustável

def cluster_articles(articles: list) -> list:
    """Agrupa artigos por similaridade de título+resumo. Retorna clusters."""
    shingled = [(a, _shingles(a.get("title","") + " " + a.get("content","")[:200])) for a in articles]
    clusters = []
    for art, sh in shingled:
        merged = False
        for cluster in clusters:
            rep, _ = cluster["representative"]
            if _jaccard(sh, _shingles(rep.get("title","") + " " + rep.get("content","")[:200])) >= SIMILARITY_THRESHOLD:
                cluster["members"].append(art)
                merged = True
                break
        if not merged:
            clusters.append({"representative": (art, sh), "members": [art]})
    return clusters

def dedup_by_content(articles: list, cache: dict) -> list:
    """Usa content_hashes (hoje vazio) para descartar duplicatas já vistas."""
    seen = set(cache.setdefault("content_hashes", {}).keys())
    unique = []
    for a in articles:
        h = hash(frozenset(_shingles(a.get("title",""))))
        if h in seen:
            continue
        seen.add(h)
        cache["content_hashes"][str(h)] = a.get("link", "")
        unique.append(a)
    return unique
```

---

## 4. Prompt editorial do Hermes (Fase 1.1) — template de handoff

O `pipeline.py cmd_collect --handoff` escreve `episodes/_candidates-{date}.json` e registra
um pointer. O Hermes Agent então lê e decide:

```markdown
# HANDOFF EDITORIAL — {date}

## Contexto
Você é o **editor-chefe** do Webjornal Vale da Liberdade (lente libertária, Blumenau/Vale do Itajaí).
A camada determinística já coletou, deduplicou, clusterizou e pontuou os candidatos abaixo.

## Sua tarefa
1. Leia `episodes/_candidates-{date}.json` (NewsItem[] com quality_score calculado).
2. Aplique as cotas: 1 nacional + 1 internacional (maior impacto).
3. Promova breaking-news (flag `breaking: true`) ao topo.
4. Para cada selecionado, escreva `summary` (2-4 frases, voz ativa, R$/%/datas específicas)
   e `key_points` (3 pontos com dados concretos). Siga `SKILL.md` seção 8.2 (copywriting).
5. Gere `episodes/raw-{date}.md` no formato de quadros (categories_map).
6. Gere `episodes/roteiro-{date}.json` (RoteiroCompleto) seguindo SKILL.md seções 4-6.

## Regras de ferro (SKILL.md 6.6)
- PROIBIDO consenso fácil entre Peter/Ricardo.
- PROIBIDO suavizar o tom ácido de Peter.
- PROIBIDO comentário genérico — conectar sempre à geografia local.

## Output esperado
- `episodes/raw-{date}.md` ✅
- `episodes/roteiro-{date}.json` ✅
Depois rode: `python scripts/pipeline.py process --date {date}`
```

---

## 5. Cadeia ffmpeg 2-pass EBU R128 + chunking (Fase 5.4 + 5.5)

### 5.1 Loudnorm de 2 passos

```python
import json, subprocess

def loudnorm_2pass(input_wav: str, output_mp3: str):
    # PASSO 1: medir
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", input_wav, "-af",
         "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True
    )
    # Extrair JSON do stderr (últimas linhas)
    measure = json.loads(probe.stderr[probe.stderr.rfind("{"):probe.stderr.rfind("}")+1])

    # PASSO 2: aplicar linear com os valores medidos
    af = (
        f"loudnorm=I=-16:TP=-1.5:LRA=11:"
        f"measured_I={measure['input_i']}:"
        f"measured_TP={measure['input_tp']}:"
        f"measured_LRA={measure['input_lra']}:"
        f"measured_thresh={measure['input_thresh']}:"
        f"offset={measure['target_offset']}:linear=true"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", input_wav,
        "-af", f"highpass=f=80,acompressor=threshold=-25dB:ratio=3:attack=50:release=200,"
               f"equalizer=f=3000:width_type=h:width=1000:g=3,{af}",
        "-ar", "44100", "-ac", "1",          # 44.1kHz (era 24kHz)
        "-acodec", "libmp3lame", "-b:a", "192k",
        output_mp3,
    ], check=True)
```

### 5.2 Inserção de pausas reais (silêncio entre segmentos)

```python
def synthesize_with_pauses(segments: list[str], synthesize_fn, output_wav: str):
    """segments: lista de textos separados por [PAUSA]/[PAUSA_CURTA]."""
    PAUSE_DUR = {"[PAUSA]": 1.5, "[PAUSA_CURTA]": 0.5}
    parts = []
    for seg in segments:
        wav = synthesize_fn(seg)              # chamada Gemini TTS por chunk
        parts.append(wav)
    # Concatenar com silêncios via ffmpeg concat filter
    # (implementação detalhada depende do layout de arquivos temporários)
```

Isso resolve **três** problemas de uma vez: chunking (cada segmento é uma chamada separada,
proteção a timeout), pausas acústicas reais, e retomabilidade (só re-sintetiza chunks falhados).

---

## 6. Recomendações estratégicas (deliverable 5)

### 6.1 Qualidade de conteúdo

| # | Recomendação | Impacto |
|---|---|---|
| 1 | **Cross-validation estrutural** (≥1 tier-1 OU ≥2 tier-2) | Reduz fake-news; aumenta credibilidade |
| 2 | **Clustering multi-fonte** | Elimina duplicação; versão mais completa vira a canônica |
| 3 | **Continuidade editorial** automática (`roteiro_anterior`) | Já esboçado em SKILL.md 2.3; implementar detecção de "novos fatos" |
| 4 | **Lexicon de pronúncia local** + normalização `num2words` | Áudio soa profissional; nomes locais corretos |
| 5 | **Revisão anti-repetição** de vocabulário/transições | Mantém frescor entre episódios |

### 6.2 Engajamento do usuário

| # | Recomendação | Impacto |
|---|---|---|
| 1 | **Cold open com gancho** (não "bem-vindo") | Primeiros 30s retêm ouvinte |
| 2 | **Breaking-news no topo** | Relevância percebida aumenta |
| 3 | **Multi-formato** do mesmo JSON: áudio 15min + highlights 5min + newsletter texto + thread | Multiplica alcance sem custo adicional de geração |
| 4 | **CTA no fechamento** (Ricardo) | Conversão para inscrição/compartilhamento |
| 5 | **Cotas nacional/internacional** | Prepara expansão; dá contexto sem diluir local |

### 6.3 Velocidade de produção

| # | Recomendação | Impacto |
|---|---|---|
| 1 | **Checkpointing por etapa** | Re-execução retoma de onde parou; não refaz coleta se só áudio falhou |
| 2 | **Chunking no TTS** | Falha em 1 chunk ≠ re-sintetizar episódio inteiro |
| 3 | **Pool compartilhado de feeds nacional/intl** | Coletados 1 vez para todas as regiões |
| 4 | **Dead-letter de fontes crônicas** | Para de gastar tempo em fontes que sempre falham |
| 5 | **Scoring determinístico** (sem LLM no filtro) | Latência e custo previsíveis |

### 6.4 Escalabilidade

| # | Recomendação | Impacto |
|---|---|---|
| 1 | **`config/regions/*.yaml`** | Nova cidade = novo YAML, zero código |
| 2 | **Editores como agentes especializados** | Cada região escala independentemente |
| 3 | **Contrato JSON estável** | Permite múltiplos consumidores (áudio, texto, highlights) |
| 4 | **Cache centralizado com `content_hashes`** | Evita re-coleta entre regiões |
| 5 | **Observabilidade `reports/daily-{date}.json`** | Base para auto-escalabilidade informada |

### 6.5 Manutenibilidade de longo prazo

| # | Recomendação | Impacto |
|---|---|---|
| 1 | **Remover Gemini não-TTS** | Reduz dependência de fornecedor único; raciocínio editorial auditável |
| 2 | **Deletar código morto** (`_fill_roteiro_from_raw`, `CHUNK_TARGET_WORDS` não-usado, `daily-collect.sh`, `cron-daily.sh`) | Menos superfície de confusão |
| 3 | **Validação bloqueante** em `cmd_full` | Impede publicação de episódios que reprovam checklist |
| 4 | **Documentação viva sincronizada** (lição do `.continue-here.md`) | Qualquer IA/você retoma sem reconstruir contexto |
| 5 | **Métricas de qualidade de áudio** (LUFS, true-peak) | Detecta drift de qualidade antes do ouvinte |
| 6 | **Numeração sequencial de `episodio`** | Identificação estável para arquivamento/referência |

---

## 7. Workflow diário recomendado (pós-migração)

```bash
# 1. Coleta determinística (sem LLM)
python scripts/pipeline.py collect --date 2026-06-21 --handoff
#   → episodes/_candidates-2026-06-21.json
#   → archive/handoffs/2026-06-21.md (pointer para Hermes)

# 2. Hermes Agent (editorial inline) — gera raw + roteiro JSON
#    [executado pelo agente seguindo SKILL.md]
#   → episodes/raw-2026-06-21.md
#   → episodes/roteiro-2026-06-21.json

# 3. Render + TTS + publicação
python scripts/pipeline.py process --date 2026-06-21   # JSON → MD → TTS prep
python scripts/pipeline.py validate --date 2026-06-21   # bloqueia se reprovar
python scripts/pipeline.py audio --date 2026-06-21      # Gemini TTS (único uso)
python scripts/pipeline.py update-archive --date 2026-06-21
#   → audio/2026-06-21-vale-da-liberdade.mp3
#   → reports/daily-2026-06-21.json

# Ou tudo de uma vez (após passo 2):
python scripts/pipeline.py full --date 2026-06-21
```

---

## 8. Próximas decisões a confirmar com Osmar

Estas não bloqueiam as Fases 0-1 mas devem ser resolvidas antes das Fases 5-6:

1. **Deploy do `public/`** — automatizado (CI/CD) ou manual? Documentar em `ARCHITECTURE.md`.
2. **Analytics de plays/retenção** — qual plataforma? (Spotify for Podcasters, Podtrac, próprio).
3. **Orçamento de custo TTS** — teto em USD por episódio/mês para alertas.
4. **Política de retenção** — quantos dias manter `logs/`, `audio/` bruto, `reports/`.
5. **Multi-região** — qual a próxima região planejada (Florianópolis? Joinville?) para validar o YAML.

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-20*
