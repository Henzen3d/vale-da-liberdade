# Analytics de escuta (geo, mapa, sessão)

**Goal:** No admin, ver de onde vêm os plays e um pouco de comportamento — sem gravar IP nem virar Google Analytics.

**Arquitetura:** o play já chama `fn_increment_view`. Cada play grava uma linha agregável (país/cidade/fuso) derivada de headers + timezone do browser. IP e User-Agent nunca persistem. O mapa e as tabelas leem RPCs admin em cima dessa tabela.

**Tech:** Postgres/Supabase (já no ar), `interaction_bar.js`, aba nova no `public/admin/`.

## Privacidade (não negociável)

- Sem IP, sem UA em claro, sem lat/lon de GPS.
- Geo: header Cloudflare (`cf-ipcountry`, `cf-ipcity` se existir) + `Intl` timezone do cliente.
- Coordenadas no mapa: centroide de cidade (depois), arredondado; nunca ponto do aparelho.
- Retenção: eventos crus 90 dias; agregados diários ficam.

## Fatias (uma por vez)

| # | Entrega | Pronto quando |
|---|---------|----------------|
| **1** | Tabela `listen_events` + gravação no play existente | Play incrementa view **e** insere evento; SQL aplicado no Supabase |
| **2** | RPC admin: plays/dia, top cidades/países, top episódios (7/30d) | `get_admin_listen_stats(days)` devolve JSON |
| **3** | Aba Admin “Audiência”: tabelas + gráfico de plays | Dá para ver números reais (mesmo com cidade vazia) |
| **4** | Mapa (Leaflet, sem API key) por país → cidade | Pins a partir de agregados, não de eventos crus — **feita** |
| **5** | Duração de sessão (heartbeat a cada 60s no player logado **ou** fingerprint) | Tempo médio / conclusão no admin |
| **6** | (opcional) Referrer / origem (home, /noticias, direto) | Coluna `source` no evento |

Não nesta leva: funil GA, heatmap de clique, export de PII, GeoIP MaxMind (só se os headers CF não derem cidade).

## Fatia 1 — o que muda

- Create: `scripts/14_listen_events.sql`
- Modify: `fn_increment_view` (mesmo nome; `p_timezone` opcional)
- Modify: `public/assets/js/interaction_bar.js` — manda timezone

Próxima fatia só depois desta estar no banco e um play de teste gravar linha.
