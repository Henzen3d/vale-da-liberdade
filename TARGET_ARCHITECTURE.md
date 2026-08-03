# TARGET_ARCHITECTURE — Arquitetura-Alvo

> Arquitetura futura do **Web Jornal Vale da Liberdade**: multi-agente, com Gemini
> restrito a TTS, e pronta para expansão geográfica (multi-cidade/estado/país).
>
> Estado atual em `REVIEW.md` e `ARCHITECTURE.md`. Caminho de chegada em `ROADMAP.md`.
>
> **Mantém:** Hermes Agent | **Locale:** pt-BR | **Atualização:** 2026-06-20

---

## 1. Princípios de design

1. **Gemini = apenas TTS.** Toda decisão editorial (filtro, ranking, sumarização, roteiro)
   é responsabilidade do **Hermes Agent** ou de camadas **determinísticas** em código.
2. **Contratos explícitos.** Comunicação entre agentes via arquivos JSON com schema Pydantic
   (`NewsItem`, `NewsAnalysis`, `RoteiroCompleto`). Nada de estado implícito.
3. **Configuração sobre código.** Nova região/cidade = novo YAML, zero mudança de código.
4. **Falha alta e observável.** Preferir abortar com log claro a emitir produto degradado
   silenciosamente (lição do episódio 2026-06-20).
5. **Idempotência por data.** Cada etapa é retomável; re-executar não duplica artefatos.

---

## 2. Visão geral multi-agente

```
                        ┌──────────────────────────┐
                        │   ORQUESTRADOR HERMES     │
                        │   (chief editor)          │
                        │  - mescla contribuições    │
                        │  - decide lineup final     │
                        │  - gera roteiro (inline)   │
                        │  - aplica SKILL.md         │
                        └─────────────┬─────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
   ┌────────▼─────────┐    ┌──────────▼──────────┐    ┌─────────▼──────────┐
   │ EDITOR REGIONAL  │    │  EDITOR NACIONAL/   │    │   EDITOR SOCIAL    │
   │  (Blumenau/Vale) │    │     INTERNACIONAL   │    │  (X/Twitter)       │
   │                  │    │   (compartilhado)   │    │                    │
   │ - coleta local   │    │ - feeds BR + mundo  │    │ - x_collector.py   │
   │ - scoring geo    │    │ - ranking de impacto│    │ - engajamento      │
   │ - clustering     │    │ - cotas 1+1         │    │ - detecção viral   │
   └────────┬─────────┘    └──────────┬──────────┘    └─────────┬──────────┘
            │                         │                         │
            └─────────────────────────┼─────────────────────────┘
                                      │ _candidates-{date}.json
                                      ▼
                        ┌──────────────────────────┐
                        │   CAMADA DETERMINÍSTICA   │
                        │  (código, sem LLM)        │
                        │  - dedup semântica        │
                        │  - clustering TF-IDF      │
                        │  - credibility scoring    │
                        │  - breaking-news detect   │
                        │  - cross-validation       │
                        └─────────────┬─────────────┘
                                      │ raw-{date}.md
                                      ▼
                        ┌──────────────────────────┐
                        │   HERMES (roteiro inline) │
                        │  - roteiro-{date}.json    │
                        │  - segue SKILL.md         │
                        └─────────────┬─────────────┘
                                      │ {date}.md
                                      ▼
                        ┌──────────────────────────┐
                        │   TTS WORKER (Gemini)     │
                        │  - ÚNICO uso de Gemini    │
                        │  - chunking + pausas reais│
                        │  - prosódia/normalização  │
                        │  - ffmpeg 2-pass EBU R128 │
                        └─────────────┬─────────────┘
                                      │ {date}-vale-da-liberdade.mp3
                                      ▼
                        ┌──────────────────────────┐
                        │   PUBLICAÇÃO + OBSERV.    │
                        │  - archive/index.md       │
                        │  - reports/daily-{date}.json │
                        └──────────────────────────┘
```

---

## 3. Componentes detalhados

### 3.1 Camada Determinística (código puro, sem LLM)

Responsável por tudo que pode ser computado sem raciocínio editorial:

- **Coleta** — `news_collector.py` (mantém-se) + `x_collector.py` (conectado).
- **Dedup semântica** — SimHash/MinHash sobre título+resumo no `content_hashes`.
- **Clustering** — TF-IDF cosine; mesma notícia em 2+ fontes = 1 cluster.
- **Credibilidade** — `credibility_score = f(tier, success_rate, frescura)` usando `tier`
  (hoje morto) e `source_stats` (já coletado).
- **Breaking-news** — cluster em ≥3 fontes tier-1 em ≤6h ou termos de urgência.
- **Cross-validation anti-fake** — item só entra se ≥1 tier-1 OU ≥2 tier-2.
- **Ranking programático:**
  ```
  relevance = 0.35·geo + 0.25·credibilidade + 0.20·recência
            + 0.10·burst + 0.10·engajamento_x
  ```

Saída: `episodes/_candidates-{date}.json` (lista de `NewsItem` com scores calculados).

### 3.2 Editores (agentes especializados)

| Editor | Escopo | Inputs | Outputs |
|---|---|---|---|
| **Editor Regional** | 1 cidade/região (hoje: Blumenau/Vale) | fontes locais, `config/regions/blumenau-vale-itajai.yaml` | candidatos locais ranqueados |
| **Editor Nacional/Internacional** | compartilhado entre regiões | feeds BR + mundo, ranking de impacto | 1 nacional + 1 internacional (cotas) |
| **Editor Social** | X/Twitter | `x_collector.py` | tweets com engajamento, sinal viral |

Cada editor é **config-driven**: fonte de verdade é `config/regions/{region}.yaml`.

### 3.3 Orquestrador Hermes (chief editor)

O agente que executa a cada run. Responsabilidades que **exigem juízo editorial**:

1. Lê `_candidates-{date}.json` (output da camada determinística + editores).
2. Decide lineup final (aplica cotas, prioriza breaking-news).
3. Escreve sumarização rica + `key_points` (dados específicos: R$, %, datas).
4. Gera `roteiro-{date}.json` seguindo `SKILL.md` (personas, quadros, tom, checklist).
5. `format_script()` renderiza para `{date}.md`.

Usa `SKILL.md` como fonte canônica — já está completo (seções 4-9).

### 3.4 TTS Worker (Gemini, único uso de Gemini)

- Modelo: `gemini-3.1-flash-tts-preview` (mantém-se).
- Vozes: Peter→Charon, Ricardo→Schedar (mantém-se).
- **Melhorias:** chunking real, pausas acústicas, normalização `num2words`, lexicon local,
  loudnorm 2-pass EBU R128, resample 44.1kHz.

---

## 4. Segmentação geográfica de conteúdo

### 4.1 Estrutura `config/regions/`

```
config/regions/
├── blumenau-vale-itajai.yaml   ← região ativa hoje
├── florianopolis.yaml           ← exemplo futuro
└── joinville.yaml               ← exemplo futuro
```

### 4.2 Schema do YAML de região

```yaml
region:
  id: blumenau-vale-itajai
  name: "Blumenau e Vale do Itajaí"
  state: "Santa Catarina"
  country: "Brasil"

geo_weights:          # dicionário de relevância geográfica
  Blumenau: 1.0
  Rio do Sul: 0.8
  Indaial: 0.8
  Pomerode: 0.8
  Gaspar: 0.8
  "Santa Catarina": 0.5

sources:
  - {id: ndmais_blumenau, scope: local, tier: 1}
  - {id: g1, scope: nacional, tier: 1}
  - {id: reuters_world, scope: internacional, tier: 1}
  # ...

x_config:
  search_terms: ["Blumenau", "BR-470", "IPTU Blumenau", ...]
  profiles: ["PrefBlumenau", "PMaboresc", "NSCTotal", ...]

pronunciation_lexicon: sources/pronunciation_lexicon.json

presenters:
  peter: presenters/peter.md
  ricardo: presenters/ricardo.md
```

### 4.3 Nova região = zero código

Adicionar Florianópolis = criar `config/regions/florianopolis.yaml` com suas fontes/termos/lexicon.
O Orquestrador Hermes detecta regiões ativas e gera um boletim por região. Os editores
Nacional/Internacional e Social são compartilhados.

---

## 5. Estratégias de agregação de feeds regionais

- **Pool compartilhado:** feeds nacionais/internacionais são coletados **uma vez** e
  distribuídos a todos os editores regionais (evita coleta redundante).
- **Cache centralizado:** `cache.json` único com `url_cache` e `content_hashes` globais;
  cada item marca quais regiões o consumiram.
- **Agendamento:** coleta regional em paralelo (ThreadPoolExecutor já existe);
  coleta nacional/internacional em slot separado.

---

## 6. Observabilidade e métricas

### 6.1 `reports/daily-{date}.json` (gerado a cada run)

```json
{
  "edicao": "2026-06-20",
  "regiao": "blumenau-vale-itajai",
  "tecnico": {
    "fontes_sucesso": 13,
    "fontes_falha": 1,
    "itens_coletados": 115,
    "clusters_formados": 28,
    "duplicatas_removidas": 7,
    "latencia_coleta_s": 17,
    "latencia_tts_s": 54,
    "tentativas_retry_tts": 0,
    "custo_tts_usd_estimado": 0.12
  },
  "editorial": {
    "diversidade_fontes": 9,
    "relevancia_media": 4.1,
    "breaking_news_detectados": 1,
    "continuidade_editorial": 2,
    "nacional_incluido": true,
    "internacional_incluido": true,
    "cross_validation_passou": true
  },
  "audio": {
    "duracao_min": 14.8,
    "lufs_integrado": -16.0,
    "true_peak_dbtp": -1.5,
    "palavras_total": 2350
  }
}
```

### 6.2 Métricas-chave monitoradas

| Categoria | Métrica | Alerta se |
|---|---|---|
| Técnico | taxa de sucesso por fonte | < 70% em 7d → dead-letter |
| Técnico | latência total run | > 5 min |
| Técnico | custo TTS/episódio | > US$ 0,50 |
| Editorial | relevância média | < 3.5 |
| Editorial | % episódios com breaking-news | métrica de cobertura |
| Editorial | cross-validation falhou | qualquer → revisar |
| Áudio | LUFS integrado | fora de [-17, -15] |
| Áudio | duração | fora de [12, 16] min |

---

## 7. Confiabilidade e fault-tolerance

| Mecanismo | Descrição |
|---|---|
| **Dead-letter de fontes** | Fonte com N falhas consecutivas é auto-desabilitada + alerta; reabilitação manual |
| **Checkpointing por etapa** | `collect` → `process` → `audio` → `publish` cada um grava `checkpoint-{date}-{step}.done`; re-executar retoma de onde parou |
| **Idempotência por data** | Re-executar mesma data sobrescreve artefatos, não duplica |
| **Retry com backoff** | Já existe no TTS (3 tentativas); estender para coleta |
| **Fallback gracioso do X** | Se rate-limitado, pular tweets sem abortar o run (já implementado no `x_collector.py`) |
| **Validação bloqueante** | `cmd_full` deve **abortar** se `validate_episode` reprovar critérios críticos (não apenas avisar) |

---

## 8. Personalização e Distribuição (futuro, pós-Fase 6)

- **`listeners/`** — perfis de ouvinte com interesses por quadro (segurança, política, esportes).
- **Feed personalizado** — reordena/destaca quadros por perfil.
- **Recomendação por similaridade** — sugere episódios anteriores por similaridade temática
  (TF-IDF sobre roteiros transcritos).
- **Multi-formato** — a partir do mesmo `roteiro-{date}.json`: áudio longo (15min), versão
  curta (5min highlights), newsletter texto, threads para redes.
- **Portal web dinâmico** — gerador estático automático com player, transcrição e dashboard (Fase 7).
- **Feed RSS de podcast** — distribuição automatizada em Spotify/Apple Podcasts (Fase 8).
- **TTS híbrida local** — engine Kokoro/Piper como fallback zero-custo (Fase 9).
- **Chat interativo** — widget de debate sob demanda com personas no portal (Fase 10).
- **Sonoplastia e Vinhetas** — inserção de música de fundo, transições e blocos de anúncios (Fase 11).

> Escopo futuro — não bloqueia as Fases 0-6. O contrato JSON já prepara o terreno.
> Planos detalhados de execução estão em `ROADMAP.md` Fases 7-11.

---

## 9. Migração do estado atual → alvo

| Componente atual | Componente alvo | Mudança | Fase |
|---|---|---|---|
| `ai_news_filter.py` (Gemini) | Camada determinística + Hermes editorial | Remove Gemini; adiciona scoring programático | 1 |
| `generate_script.py` (Gemini) | Renderer JSON→MD + Hermes inline | Remove Gemini; Hermes gera JSON | 1 |
| `news_collector.py` | + dedup semântica + clustering | Adiciona | 2 |
| `x_collector.py` (desconectado) | Editor Social conectado | Adiciona caller em `cmd_collect` | 2 |
| `sources.json` (só local) | + nacional/internacional por região | Adiciona feeds + campo `scope` | 3 |
| `tts_preprocessor.py` (dict estático) | + `num2words` + lexicon | Substitui normalização | 5 |
| `generate_gemini_tts_multi.py` | + chunking + pausas + 2-pass | Aprimora | 5 |
| `pipeline.py` (sem checkpoint) | + checkpointing + dead-letter | Adiciona | 6 |
| — (sem config regional) | `config/regions/*.yaml` | Novo | 6 |
| `public/index.html` (estático manual) | Gerador estático automático (`build_site.py`) | Substitui; player + transcrição + dashboard | 7 |
| — (sem feed podcast) | `generate_podcast_rss.py` → `public/podcast.xml` | Novo; distribuição Spotify/Apple | 8 |
| `generate_gemini_tts_multi.py` (só Gemini) | + `generate_kokoro_tts.py` (híbrido) | Adiciona fallback local zero-custo | 9 |
| — (sem interação web) | `chat_api.py` + widget frontend | Novo; debate sob demanda | 10 |
| `concat_files` em `generate_gemini...` | `generate_audio_mix.py` (mixagem) | Adiciona intros, transições e ducking | 11 |

A maior parte do código existente é **aproveitada** — a migração é de responsabilidade
(filtro/roteiro saem do Gemini) e de acréscimo (clustering, nacional/intl, observabilidade,
portal web, distribuição, TTS local, interação, sonoplastia), não de reescrita.

---

## 10. Portal Web Dinâmico (Fase 7)

```
                          ┌──────────────────────────┐
                          │    build_site.py           │
                          │    (gerador estático)       │
                          └─────────────┬────────────┘
                                        │
              ┌─────────────┬─────────┼──────────┬───────────┐
              │             │         │          │           │
     archive/index.md  *-metadata  roteiro.md  audio/*.mp3  stats
              │             │         │          │       (calculadas)
              └─────────────┴─────────┼──────────┴───────────┘
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │  public/index.html         │
                          │  ─ Player customizado       │
                          │  ─ Transcrição estilizada   │
                          │  ─ Fontes do dia            │
                          │  ─ Dashboard estatísticas   │
                          │  ─ Arquivo de episódios     │
                          └──────────────────────────┘
```

O portal é regenerado a cada run do pipeline (`cmd_full`). Não há servidor dinâmico — é puro HTML/CSS/JS estático servido pelo Nginx/Cloudflare.

---

## 11. Feed RSS de Podcast (Fase 8)

Arquivo `public/podcast.xml` compatível com RSS 2.0 + namespaces iTunes/Podcast.
Gerado automaticamente pelo `generate_podcast_rss.py` a cada publicação.
Configuração centralizada em `sources/podcast_config.json`.

Permite distribuição em:
- Spotify for Podcasters
- Apple Podcasts Connect
- Google Podcasts
- Deezer
- Qualquer agregador RSS

---

## 12. Engine TTS Híbrida (Fase 9)

```
                    ┌───────────────────────────┐
                    │  pipeline.py cmd_audio      │
                    │  --tts-engine=hybrid         │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │  Tenta Gemini TTS            │
                    │  (multi-locutor nativo)       │
                    └────────┬─────────┬────────┘
                             │ OK      │ Falha/RPD
                             ▼         ▼
                       ┌───────┐  ┌────────────────┐
                       │  .mp3  │  │ Kokoro/Piper     │
                       └───────┘  │ (local, ONNX)    │
                                  │ + ffmpeg pitch   │
                                  │ + diferenciação   │
                                  └────────┬───────┘
                                           │
                                     ┌───────┐
                                     │  .mp3  │
                                     └───────┘
```

Três modos: `gemini` (padrão), `kokoro` (local, custo zero), `hybrid` (fallback automático).

---

## 13. Chat Interativo com Personas (Fase 10)

```
    ┌────────────────────┐
    │  Ouvinte no portal  │
    │  (browser)          │
    └─────────┬──────────┘
              │ POST /api/chat
              ▼
    ┌────────────────────┐
    │  chat_api.py         │
    │  (FastAPI)           │
    │  - Rate limit/IP     │
    │  - Scraping de URL   │
    │  - Prompt personas   │
    └─────────┬──────────┘
              │
              ▼
    ┌────────────────────┐
    │  GeminiClient        │
    │  (gemini-3.5-flash)  │
    └─────────┬──────────┘
              │ JSON debate
              ▼
    ┌────────────────────┐
    │  Widget frontend     │
    │  (bolhas Peter/      │
    │   Ricardo estilizadas)│
    │  + botão "Ouvir"     │
    └────────────────────┘
```

Segue exatamente as personas de `SKILL.md` seções 5-6 e as regras de tom e anti-racionalização.
Toda comunicação com a API é server-side (chave nunca exposta).

---

## 14. Sonoplastia e Monetização (Fase 11)

```
                       ┌────────────────┐
                       │ Roteiro (JSON) │
                       │ com [AD_SLOT]  │
                       └────────┬───────┘
                                ▼
                       ┌────────────────┐
                       │  TTS Pipeline  │
                       │ (falas brutas) │
                       └────────┬───────┘
                                │
    ┌────────────────┐          ▼
    │ assets/audio/  │    ┌───────────────────────────┐
    │ - intro.mp3    ├───►│ generate_audio_mix.py     │
    │ - ads/*.mp3    │    │ (ffmpeg/pydub assembly)   │
    │ - bed.mp3      │    └─────────────┬─────────────┘
    └────────────────┘                  │
                                        ▼
                                ┌────────────────┐
                                │ Final Mix.mp3  │
                                │ (com ducking   │
                                │  e EBU R128)   │
                                └────────────────┘
```

O roteiro prevê pontos de transição. O script de mixagem inteligente costura a voz sintetizada com as vinhetas estáticas, aplica a trilha de fundo e normaliza o volume final. Permite inserção rotativa de anúncios para monetização.

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-24*
