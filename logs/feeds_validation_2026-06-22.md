# Relatório de Validação de Feeds RSS — 2026-06-22

Gerado em: 2026-06-22 às 12:56:46
Total testado: 4 | Aprovados: 2 | Vazios: 1 | Reprovados: 1

---

## Resumo

⚠️ `brasil247_r3` — **Brasil 247 — /rss/ (com barra)** | 0 itens | 4.73s | via HTTP 200 mas feedparser não encontrou entries
✅ `estadao_r3` — **Estadão — Política (Arc outboundfeeds)** | 20 itens | 1.1s | via feedparser_prefetched
❌ `terra_r3` — **Terra — terra.com.br/noticias/feed/** | 0 itens | 5.31s | via HTTP 404
✅ `cnn_politica_r3` — **CNN Brasil — Política (alternativa)** | 60 itens | 7.08s | via feedparser_prefetched

---

## ✅ Aprovados (2)

| # | ID | Nome | Itens | Método | Tempo | Primeira notícia |
|---|---|---|---|---|---|---|
| 1 | `estadao_r3` | Estadão — Política (Arc outboundfeeds) | 20 | feedparser_prefetched | 1.1s | O passado ainda pesa |
| 2 | `cnn_politica_r3` | CNN Brasil — Política (alternativa) | 60 | feedparser_prefetched | 7.08s | Pavilhão Anhembi recebe festa de música eletrônica na sexta … |

## ⚠️ Vazios (1)

| ID | Nome | HTTP | Erro |
|---|---|---|---|
| `brasil247_r3` | Brasil 247 — /rss/ (com barra) | 200 | HTTP 200 mas feedparser não encontrou entries |

## ❌ Reprovados (1)

| ID | Nome | Erro |
|---|---|---|
| `terra_r3` | Terra — terra.com.br/noticias/feed/ | HTTP 404 |

---

## JSON dos Aprovados (pronto para sources.json)

```json
[
  {
    "id": "estadao_r3",
    "name": "Estadão — Política (Arc outboundfeeds)",
    "url": "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/politica/?outputType=xml",
    "method": "rss",
    "tier": 1,
    "scope": "nacional",
    "enabled": true,
    "_note": "Editoria: politica. Validado 2026-06-22 (feedparser_prefetched)."
  },
  {
    "id": "cnn_politica_r3",
    "name": "CNN Brasil — Política (alternativa)",
    "url": "https://www.cnnbrasil.com.br/feed/?cat=politica",
    "method": "rss",
    "tier": 1,
    "scope": "nacional",
    "enabled": true,
    "_note": "Editoria: politica. Validado 2026-06-22 (feedparser_prefetched)."
  }
]
```
