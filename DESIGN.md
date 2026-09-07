# DESIGN.md — Vale da Liberdade (Web Jornal)

Registro de decisões de design de UI/UX do site. **Editável manualmente** — este
arquivo é o ponto único para documentar/atualizar o design de menus, abas,
player e layout sem precisar caçar nas skills.

Fonte de verdade do código: `public/` (única fonte desde 2026-08-06; `new-ux/`
aposentada). Specs operacionais complementares vivem na skill Hermes
`web-jornal-frontend` (`~/.hermes/skills/...`) — este arquivo **não duplica** a
skill, apenas resume o design vigente e as regras anti-regressão.

---

## 1. Arquitetura de CSS e temas

| Arquivo | Papel |
|---------|-------|
| `public/assets/css/tokens.css` | Variáveis dos 2 temas (dark/light via `data-theme`) |
| `public/assets/css/base.css` | Reset + regras base: `overflow-x: clip`, `[hidden]{display:none!important}` |
| `public/assets/css/components.css` | Componentes (topbar, tabs, hero, cards, full player). ~77KB, carregado com `media="print" onload="this.media='all'"`; há um bloco de CSS crítico inline no `<head>` do `index.html` com as regras layout-affecting |
| `public/assets/css/audio-wave.css` | Reduzido a `.scrubber-container{position:relative}` (waveform removido) |
| `public/assets/css/consent.css` | Banner LGPD |

**Cache-busters:** após QUALQUER edição em CSS/JS, bumpar o `?v=` no
`index.html` ANTES do publish (ex.: `components.css?v=202608161000`). O publish
não atualiza query params sozinho — se esquecer, o Cloudflare serve o arquivo
velho por até 1 ano.

---

## 2. Menus e navegação

### 2.1 Topbar (sticky)

- **Sticky top:** `0px`, `z-index` alto; fixa ao rolar nos dois viewports.
- **Vidro:** `rgba(248,249,250,0.85)` (light) / `rgba(11,13,16,0.85)` (dark) +
  `backdrop-filter: blur(16px)`.
- **Botões:** hambúrguer (`#btnMenu` — abre drawer), busca (`#btnSearch`),
  toggle de tema. Ícones com alvo de toque **44×44px** (WCAG 2.5.5).
- Regras vivem no `components.css` **E** no CSS crítico inline do `index.html`
  (editar os dois).

### 2.2 Abas editoriais (tab bar superior)

- **Tabs:** `Diário` (`diario`) e `Brasil e Mundo` (`bm`), com contadores
  `.tab-count`.
- **Sticky top:** `56px` (logo abaixo da topbar), `z-index: 90`.
- **Vidro:** `blur(12px)` — mesmo padrão translúcido da topbar. ⚠️ PITFALL:
  `backdrop-filter` com `background-color` oposta (sólida) anula o vidro; usar
  SEMPRE rgba translúcido nas duas camadas.
- **Tipografia:** Title Case (NUNCA UPPERCASE), botão `13px/600`, contador
  `10px` + `margin-left: 4px`, `white-space: nowrap`.
- **Persistência:** aba ativa sobrevive ao refresh (localStorage
  `vld_active_tab`, UX-011) — restaurar NO BOOT antes do primeiro render, e
  persistir nas DUAS vias (clique na tab E clique no drawer).
- **Regra de navegação:** tabs superiores = `diario` e `bm`. INVESTIMENTOS e
  TECNOLOGIA vivem SÓ no drawer lateral (não na barra superior).
- **Filtro:** prev/next/autoplay/feed SEMPRE passam por `getFilteredEpisodes()`
  — nunca filtrar `state.episodes` inline por tab.

### 2.3 Drawer lateral (menu hambúrguer)

- **Itens** (`data-drawer-tab`): `todos`, `diario`, `bm`, `investimentos`,
  `tecnologia`, `especial`, `favoritos`.
- Item ativo sincronizado com a tab ativa (`.drawer-nav-item.active`).
- **Rodapé do drawer:** toggle de tema + logout (`.sidebar-footer-actions`).
- Mobile: sidebar começa escondida (`translateX(-100%)`); abre via
  `#btnSidebarToggle` no header + overlay `#sidebarOverlay`
  (`setupSidebarToggle()` em `admin_init.js` — padrão do admin; na home o
  handler é o `#btnMenu`).
- **Favoritos no drawer:** filtra por `ep.id` (NUNCA `ep.date` — especiais têm
  `id="especial-XXX"` mas `date="YYYY-MM-DD"`).

---

## 3. Layout responsivo

### 3.1 Hero (card do episódio em destaque)

**Mobile-first vertical (`.hero-card{flex-direction:column}`):**
- Capa 100% largura, `aspect-ratio 16/9`; conteúdo abaixo.
- `border-radius: 12px`; `max-height: 200px` (compacto).

**Variante desktop horizontal (`@media(min-width:768px)`):**
- `flex-direction: row; max-height: 240px`.
- Capa **45%** à esquerda (`aspect-ratio: 992/240`, faixa estilo "Google
  Stitch"), conteúdo **55%** à direita (`padding: 24px 32px`, título `1.5rem`,
  desc `0.9rem` clamp 3, meta com `margin-top:auto`).
- ⚠️ JÁ FOI REMOVIDO UMA VEZ (sync 611eee3, 09/08) e o dono pediu de volta —
  NÃO remover o bloco `@media(min-width:768px)` ao mexer no hero. Validar com
  `scripts/qa_hero_desktop_restore.mjs` (CDP: desktop row/45-55, mobile column,
  0 exceções).
- **Botão de play** = disco sobreposto à imagem (`.hero-play-overlay` >
  `.hero-play-circle`), não no footer.
- **Meta compacto:** `Novo · {duration} · {data}` — sem avatares dos
  apresentadores (ganhar espaço vertical).

### 3.2 Grid geral

- `.app-layout-grid` + `.desktop-sidebar` (sidebar de anúncios no desktop).
- `.timeline` (gap `var(--space-4)`) espaça grupos de feed; o
  `.feed-item-group` (card + action row) fica SEM gap — os 4 botões
  (play/share/copy/save) colados ao card, sem "ícones soltos" (decisão do dono).

---

## 4. Player

- **Mini player** (barra inferior) + **full player** (expande).
- **Full player — título/autor SOBRE a capa**: overlay `.full-cover-caption`
  (gradiente `rgba(0,0,0,0.82) → transparent`, texto branco com text-shadow,
  `pointer-events:none`), capa `aspect-ratio 1` radius 28px.
- **Share no lugar do favorito** no full player (decisão do dono 07/08):
  `#fullShareBtn` no canto da capa.
- **Scrubber:** barra simples **3px** com fill gradiente âmbar + bolinha 14px
  (waveform REMOVIDO por decisão do dono — não reintroduzir).
- **Interstitial de anúncio** = full player de anúncio (estilo Spotify, não
  modal): reusa as classes do full player (`full-player-overlay
  ad-player-overlay`), capa do anúncio, "A seguir:", CTA, "Pular anúncio ⏭️"
  após countdown. Só sai pelo botão Pular, fim do media ou safety timeout de
  20s — **chevron de minimizar oculto durante o ad** (UX-012).
- **Sleep timer** (15/30/45/fim do episódio/off), **velocidade**
  (0.75–2×, persistida), **"A seguir"** via `findNextEpisode` (mesmo do
  autoplay), **manchetes da edição** em accordion, **MediaSession** com artwork
  do episódio.

---

## 5. Tokens de tema e contraste (WCAG AA)

**Dark (`[data-theme="dark"]`):**
- `--color-ink-faint`: `#848D9C` (5.81:1) — era `#4B5563` (2.57:1, falhava)
- `--color-live`: `#D9604F` (5.32:1)
- `--color-success`: `#4CAF78` (7.14:1)
- Ouvido: `--row-done-title: #848D9C` (5.81:1), `--row-done-meta: #7A8291`
  (5.03:1) sobre `#0B0D10` — AA (sem opacity na linha inteira).

**Light:** não é inversão do dark. Âmbar de texto `#965A15` (5.28:1) — `#A9661F`
falha AA; o âmbar cru `#c9a227` = 2.4:1 sobre branco. `--row-done-*` com tinta
cinza dedicada (sem opacity).

**Badges/chips:** `border-radius: 4px` (cantos levemente arredondados) +
padding compacto — NUNCA pill/999px (decisão do dono: "parece literalmente uma
pílula").

---

## 6. Regras anti-regressão (não quebrar)

1. **`overflow-x: clip`** em html/body/.app — `hidden` cria scroll container e
   MATA `position: sticky` da topbar/abas. O rail horizontal usa
   `overflow-x: auto` no FILHO, nunca no ancestral sticky.
2. **Vidro** = rgba translúcido nas duas camadas (topbar E abas) + CSS crítico
   inline. Fundo sólido anula o blur.
3. **Service worker:** navegação **network-first** (cache só fallback offline);
   precache NUNCA com css/js sem `?v=` (Cloudflare cacheia URL sem versão por
   ​1 ano e envenena o cache local). sw.js deve sair com `no-cache` na origem
   (regra `location = /sw.js` no `deploy/nginx.conf`) — senão o Cloudflare
   cacheia o SW por 1 ano e o PWA nunca recebe updates. Se mexer no nginx.conf,
   recriar o container: `docker compose up -d --force-recreate --no-deps web`
   (bind mount fica preso ao inode antigo; `nginx -s reload` NÃO basta).
4. **Cache-buster:** bump `?v=` no index.html antes de TODO publish de CSS/JS.
5. **`[hidden]{display:none!important}`** no base.css — regras `display:grid/
   flex` de autor anulam o atributo hidden.
6. **Autoplay/navegação** passa por UMA função central (`handleAutoPlayNext` +
   `getFilteredEpisodes()`) — nunca dois caminhos paralelos (duplo autoplay).
7. **QA da cadeia de entrega:** `bash scripts/qa_delivery_chain.sh` após
   publish — 6 checks (sw.js no-cache local, cf BYPASS na prod, prod 200, hero
   horizontal, vidro das abas, base.css com clip).
8. **Edições em arquivos minificados:** usar Python string-replace/heredoc com
   âncora validada byte-a-byte (`data.count(anchor)==1`) + `node --check`;
   conferir `grep -rn '\*\*\*'` (redator de segredos corrompe literais).
9. **Fonte dos dados:** `ep.id` para interação (views/likes/share/fav) — nunca
   `ep.date` (especiais B&M).

---

---

## 8. Diretriz de Vídeo e Broadcast (Light Editorial Standard — TV & YouTube)

Decisão oficial ratificada em **Setembro de 2026**: todas as peças em vídeo geradas pelo canal (Brasil e Mundo, Diário, transmissões e simuladores de browser) adotam obrigatoriamente a estética **Light Editorial Studio**:

1. **Repúdio ao Dark Mode em Vídeo**: Fundos escuros e pretos ("dark mode de programador/hacker") empobrecem a estética televisiva, sofrem artefatos severos com compressão H.264 do YouTube e possuem baixa legibilidade em telas de TV a 3-4 metros.
2. **Estúdio Diurno Iluminado**: O cenário de fundo opera com iluminação diurna límpida (`#f8fafc` a `#e2e8f0`), luzes quentes douradas sutis e malha de estúdio suave.
3. **Cartões em Papel Branco (`#ffffff`)**: Todos os componentes de dados (`QuoteCard`, `DocumentCard`, `TimelineCard`, `DataChartCard`, `ComparisonCard`, `RecorteCard`) são construídos em fundo branco puro/marfim notarial com molduras douradas e tipografia em preto editorial (`#0a0e17` / `#0f172a`), garantindo máxima legibilidade.
4. **Barras Superiores Claras**: Barras de topo universais (`.bcard-brand-header` e `.doc-top-bar`) mantêm fundo branco/off-white com friso luminoso ouro e brasão ⚜️.
5. **Integração com Lower Third**: O Lower Third oficial já opera com cartão branco (`--lt-paper: #ffffff`) e texto preto (`#0a0a0a`), garantindo unidade visual absoluta da marca Vale da Liberdade em toda a grade.
6. **Documento de Referência**: [`references/youtube/mockup-browser/LIGHT_BROADCAST_DESIGN_SYSTEM.md`](references/youtube/mockup-browser/LIGHT_BROADCAST_DESIGN_SYSTEM.md).

---

## 9. Changelog de design

| Data | Mudança | Commit | Onde |
|------|---------|--------|------|
| 2026-09-06 | Light Editorial Broadcast Standard oficializado como padrão para todos os vídeos/broadcast | — | `mockup-brower.html`, `LIGHT_BROADCAST_DESIGN_SYSTEM.md`, `bm_mockup_video.py` |
| 2026-08-16 | Hero desktop horizontal restaurado (row 45/55, max-height 240px) | `491f82e` | `public/assets/css/components.css` |
| 2026-08-16 | Vidro (glassmorphism) devolvido à barra de abas Diário/Brasil e Mundo | `deb0015` | `components.css` + CSS crítico inline |
| 2026-08-16 | SW network-first + precache sem URLs sem versão + bump `base.css?v=202608161100` (fix sticky na prod) | `cc8ac70` | `public/sw.js`, `public/index.html` |
| 2026-08-16 | QA da cadeia de entrega automatizado | `747aa07` | `scripts/qa_delivery_chain.sh` |
| 2026-08-09 | Aba ativa sobrevive ao refresh (UX-011) | — | `app.js` (localStorage `vld_active_tab`) |
| 2026-08-07 | Scrubber simples 3px + bolinha (waveform removido, UX-008) | — | `components.css`, `audio-wave.css` |
| 2026-08-07 | Título/autor sobre a capa no full player; share no lugar do favorito | — | `app.js`, `components.css` |

---

*Última atualização: 2026-09-06. Edite livremente; se mudar comportamento
visual, lembre do cache-buster (§1) e do QA da cadeia (§6.7).*
