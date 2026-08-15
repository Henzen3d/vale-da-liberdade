<!-- [ARQUIVADO em 14/08/2026 — documento histórico, não reflete o estado atual do projeto. Ver CANONICAL.md e README.md para estado vigente.] -->
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

## 8. Personalização (futuro, pós-Fase 6)

- **`listeners/`** — perfis de ouvinte com interesses por quadro (segurança, política, esportes).
- **Feed personalizado** — reordena/destaca quadros por perfil.
- **Recomendação por similaridade** — sugere episódios anteriores por similaridade temática
  (TF-IDF sobre roteiros transcritos).
- **Multi-formato** — a partir do mesmo `roteiro-{date}.json`: áudio longo (15min), versão
  curta (5min highlights), newsletter texto, threads para redes.

> Escopo futuro — não bloqueia as Fases 0-6. O contrato JSON já prepara o terreno.

---

## 9. Migração do estado atual → alvo

| Componente atual | Componente alvo | Mudança |
|---|---|---|
| `ai_news_filter.py` (Gemini) | Camada determinística + Hermes editorial | Remove Gemini; adiciona scoring programático |
| `generate_script.py` (Gemini) | Renderer JSON→MD + Hermes inline | Remove Gemini; Hermes gera JSON |
| `news_collector.py` | + dedup semântica + clustering | Adiciona |
| `x_collector.py` (desconectado) | Editor Social conectado | Adiciona caller em `cmd_collect` |
| `sources.json` (só local) | + nacional/internacional por região | Adiciona feeds + campo `scope` |
| `tts_preprocessor.py` (dict estático) | + `num2words` + lexicon | Substitui normalização |
| `generate_gemini_tts_multi.py` | + chunking + pausas + 2-pass | Aprimora |
| `pipeline.py` (sem checkpoint) | + checkpointing + dead-letter | Adiciona |
| — (sem config regional) | `config/regions/*.yaml` | Novo |

A maior parte do código existente é **aproveitada** — a migração é de responsabilidade
(filtro/roteiro saem do Gemini) e de acréscimo (clustering, nacional/intl, observabilidade),
não de reescrita.

---
*Mantido por: Hermes Agent | Última atualização: 2026-06-20*
