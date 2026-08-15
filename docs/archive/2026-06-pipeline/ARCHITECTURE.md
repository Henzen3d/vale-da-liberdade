<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
# ARCHITECTURE — Web Jornal Vale da Liberdade

> Documento de arquitetura real do projeto, refletindo o estado atual do código
> após a migração Fase 1.1/1.2 (Gemini removido de filtro e geração de roteiro).
> Mantido por: Hermes Agent | Última atualização: 2026-06-22

---

## Fluxo ponta-a-ponta (estado atual)

```
Fontes (RSS/scraping/browser)
    │ news_collector.py
    ▼
Artigos brutos (lista dict)
    │ ai_news_filter.py (scoring determinístico)
    ▼
Notícias curadas (raw-YYYY-MM-DD.md)
    │ Hermes Agent (opcional) + generate_script.render_from_json()
    ▼
Roteiro final (YYYY-MM-DD.md)
    │ tts_preprocessor.py
    ▼
roteiro_tts.txt + manchetes.txt + YYYY-MM-DD-metadata.json
    │ generate_gemini_tts_multi.py (Gemini TTS multi-locutor)
    ▼
audio/YYYY-MM-DD-completo.wav
    │ ffmpeg (chain embutida no script)
    ▼
audio/YYYY-MM-DD-vale-da-liberdade.mp3
    │ pipeline.py cmd_update_archive
    ▼
archive/index.md
```

---

## Status de automação por etapa

| Etapa | Status | Observação |
|---|---|---|
- Coleta (RSS/scraping/browser) | 100% automatizada | 14 fontes + `x_collector.py` opcional (Playwright/stealth), injetado em `cmd_init`/`cmd_collect` com try/except
- Dedup | Híbrida (URL + fingerprint SHA-256 + MinHash leve + keyword overlap) | `news_collector.py`: URL, fingerprint SHA-256 sobre title+lead, MinHash 3-grams sobre título (janela 50, threshold 0.80) e camada lexical Jaccard (threshold 0.70, stopwords PT, janela 50)
| Filtro + categorização + scoring | 100% automatizada | `ai_news_filter.py` determinístico (geo, credibilidade, recência, urgência) |
| Geração do roteiro | **Assistida pelo Hermes** | `pipeline.py` requer `roteiro-{date}.json`; Hermes lê `raw-{date}.md` e gera o JSON seguindo `build_script_prompt()` |
| TTS multi-locutor | 100% automatizada | Único uso de Gemini no projeto (tarefa de TTS apenas) |
| Validação | 100% automatizada | Checklist em `tts_preprocessor.validate_episode()` |
| Publicação | 100% automatizada | Atualiza `archive/index.md`; `episodio` agora é auto-incrementado |

**Constraint atendido:** Gemini é usado EXCLUSIVAMENTE para TTS. Nenhuma outra etapa
chama LLM externo. `grep -ri "gemini-2.5-flash\|google.genai\|genai.Client" scripts/*.py`
retorna vazio (apenas `generate_gemini_tts*.py` e `__pycache__`).

---

## Schemas dos arquivos de dados

### `sources/sources.json`

```json
{
  "version": "1.0",
  "sources": [
    {
      "id": "string",
      "name": "string",
      "url": "string",
      "method": "rss | scraping | browser",
      "tier": 1 | 2,
      "scope": "local | nacional | internacional",
      "enabled": true | false
    }
  ]
}
```

`method`: `rss` (feedparser + fallback WordPress API), `scraping` (BeautifulSoup em home),
`browser` (Playwright headless). `scope` controla em qual categoria o filtro colocará a notícia.

### `sources/cache.json`

```json
{
  "schema_version": "1.0",
  "last_run": {
    "date": "YYYY-MM-DD",
    "duration_seconds": int,
    "items_collected": int,
    "sources_used": ["id", ...]
  },
  "source_stats": {
    "<source_id>": {
      "total_fetches": int,
      "success_count": int,
      "avg_items_per_fetch": float,
      "last_fetch": "ISO8601"
    }
  },
  "url_cache": { "<url>": "ISO8601 timestamp" },
  "content_hashes": {}
}
```

TTL do `url_cache`: 7 dias.

### `episodes/roteiro-{date}.json` (contrato Hermes → pipeline)

Gerado pelo Hermes Agent, consumido por `generate_script.render_from_json()`.

```json
{
  "manchetes": ["manchete 1", "manchete 2", ...],
  "introducao": [
    {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter|Ricardo", "texto": "..."}
  ],
  "quadros": [
    {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "texto": "..."},
    {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "texto": "..."},
    {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "texto": "..."}
  ],
  "fechamento": [
    {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Peter", "texto": "..."},
    {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Ricardo", "texto": "..."}
  ]
}
```

- No campo `texto`: escrever APENAS o que o locutor fala, sem prefixo `Peter:`/`Ricardo:`.
- Prompt canônico para o Hermes: `python scripts/generate_script.py --print-prompt --date YYYY-MM-DD`
- Template de referência: `episodes/roteiro-template.json`

### `episodes/{date}-metadata.json`

```json
{
  "edicao": "YYYY-MM-DD",
  "episodio": int,
  "duracao_estimada_min": float,
  "palavras_total": int,
  "quadros_gerados": ["seguranca", "saude", ...],
  "noticias_total": int,
  "noticias_com_continuidade": int,
  "fontes_utilizadas": ["id", ...],
  "arquivos_gerados": ["roteiro.md", "roteiro_tts.txt", "manchetes.txt"],
  "pipeline_stats": { ... },
  "validacao": { ... }
}
```

`episodio` agora é calculado automaticamente por `get_episode_number()` lendo `archive/index.md`.

### `episodes/raw-YYYY-MM-DD.md`

Formato gerado por `pipeline.format_raw_markdown()`:
- Cabeçalho com data, fontes usadas, total de notícias
- Bloco `## 📋 NOTÍCIAS CURADAS POR QUADRO`
- Quadros no formato `### QUADRO: <NOME>` com itens `#### • <título>`, URL, Score, Resumo, Pontos Chave

---

## Variáveis de ambiente

| Variável | Obrigatória | Uso |
|---|---|---|
| `GEMINI_API_KEY` | Sim | TTS multi-locutor em `generate_gemini_tts_multi.py` |
| `X_USERNAME` | Não | Login no X (somente se `x_collector.py` for usado) |
| `X_PASSWORD` | Não | Login no X (somente se `x_collector.py` for usado) |

`⚠️ A confirmar com Osmar`: há chaves de APIs externas adicionais ou config de distribuição
que não estão em `.env.example`?

---

## Módulos — responsabilidades (estado atual)

| Módulo | Responsabilidade |
|---|---|
| `scripts/pipeline.py` | CLI orquestrador: init, collect, process, validate, audio, full, update-archive |
| `scripts/news_collector.py` | Coleta de notícias: RSS → scraping → Playwright fallback; dedup + cache |
| `scripts/ai_news_filter.py` | Filtro e categorização determinística (geo + credibilidade + recência + urgência) |
| `scripts/generate_script.py` | Renderer JSON → MD (roteiro-{date}.json → {date}.md); prompt canônico para Hermes |
| `scripts/tts_preprocessor.py` | Limpeza markdown, substituições de siglas, inserção de pausas, extração de manchetes, validação, metadados |
| `scripts/generate_gemini_tts_multi.py` | TTS multi-locutor com Gemini (Charon + Schedar), pós-processamento ffmpeg |
| `scripts/generate_gemini_tts.py` | TTS single-speaker (legado, não usado pelo pipeline) |
| `scripts/x_collector.py` | Coleta do X (Twitter) via Playwright + stealth; integrado opcionalmente no `cmd_collect` / `cmd_init` |
| `scripts/validate_feeds.py` | Validação e otimização de feeds RSS (pré-busca HTTP, retry, jitter) |
| `scripts/daily-collect.sh` | DEPRECATED — template raw manual, sem coleta automatizada |
| `scripts/cron-wrapper.sh` | Wrapper chamado pelo cron; executa `pipeline.py full` |
| `scripts/cron-daily.sh` | DEPRECATED — referencia `daily-pipeline.sh` que não existe |

---

## Contrato Hermes Agent (Fase 1.2)

1. `pipeline.py init --date YYYY-MM-DD` cria `raw-YYYY-MM-DD.md` (coleta automática opcional) + template de roteiro.
2. Hermes Agent lê `raw-YYYY-MM-DD.md` e gera `episodes/roteiro-YYYY-MM-DD.json` usando o prompt canônico de `generate_script.build_script_prompt()`.
3. `pipeline.py process --date YYYY-MM-DD` chama `render_from_json()` → valida → gera TTS/manchetes/metadados.
4. Se `roteiro-YYYY-MM-DD.json` não existir: `process` falha alto (exit 3) sem produzir roteiro degradado.

Template de JSON para testes: `episodes/roteiro-template.json`.

---

## Pontos de falha conhecidos e reação do sistema

| Ponto de falha | Reação |
|---|---|
| `roteiro-{date}.json` ausente | `process` aborta com exit 3 e instrução para gerar o JSON via Hermes |
| RSS vazio / WordPress API indisponível | Tenta scraping → Playwright → retorna `success=False`, source_report sem itens |
| Rate limit / erro Gemini (TTS) | 3 retries com backoff exponencial; falha crítica se esgotar (não há fallback de voz) |
| Playwright não instalado | Cai automaticamente para scraping HTTP |
| `x_collector.py` indisponível | `_X_COLLECTOR_AVAILABLE=False`; pipeline ignora X silenciosamente |
| ffmpeg ausente | Gera WAV, mas avisa que MP3 não foi criado |

---

*Mantido por: Hermes Agent | Última atualização: 2026-06-22*
