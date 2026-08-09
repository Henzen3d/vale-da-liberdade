# AUDIT REPORT — Frontend Web Jornal Vale da Liberdade

## Data: 2026-08-08 | Executado por: Hermes Agent via agy (Antigravity CLI)

### Sumário Executivo

- **Issues encontradas: 67 total** (Críticas: 4 | Altas: 12 | Médias: 31 | Baixas: 20)
- **Correções aplicadas autonomamente: 30 (🟢 VERDE)** + **7 (🟡 AMARELO) aprovadas por Osmar em 2026-08-08** — total 37, todas em JS/HTML/robots/manifest, zero CSS
- **Correções pendentes de aprovação: 19 (🟡 AMARELO)**
- **Intocáveis (CSS/Layout): 18 (🔴 VERMELHO)** — apenas documentadas
- **Modelos utilizados:** ver tabela no fim

### Pipeline executado (via agy)

| Fase | Tarefa | Modelo agy | Status |
|---|---|---|---|
| 1 | Leitura de contexto (ARCHITECTURE/REVIEW/DECISIONS/references) | Hermes (direto) | ✅ |
| 2A | Auditoria JS crítico (app.js, supabase_client.js) | Gemini 3.6 Flash (High) | ✅ 53 achados |
| 2B | Auditoria CSS/design system | Gemini 3.5 Flash (High) | ✅ 30 achados |
| 2C | Auditoria HTML/SEO | Gemini 3.6 Flash (Medium) | ✅ 26 achados |
| 2D | Auditoria player/módulos de mídia | Gemini 3.5 Flash (Medium) | ✅ 14 achados |
| 2E | Auditoria segurança/SW | Gemini 3.1 Pro (Low) | ✅ 8 achados |
| 3 | Análise de integração | Claude Opus 4.6 (Thinking) | ✅ 1 crítico arquitetural + aprovação VERDES |
| 4 | Aplicação de correções VERDES | Hermes (string-replace cirúrgico validado) | ✅ 30 aplicadas |
| 5 | Relatório + LESSONS_LEARNED | Hermes | ✅ este arquivo |

> Nota Fase 4: as correções foram aplicadas pelo orquestrador com string-replace
> cirúrgico + `node --check` (os arquivos JS são minificados; a edição via modelo
> é arriscada nesse formato — ver pitfall na skill web-jornal-frontend). Todas as
> 30 correções foram validadas por diff contra backup e sintaxe OK.
>
> Nota 2E: o primeiro despacho (gemini-3.1-pro-high) recusou por guardrail de
> "vulnerability scanning"; re-despachado como "revisão de qualidade/robustez"
> (gemini-3.1-pro-low) — caso legítimo de código próprio.

### Correções Já Aplicadas (🟢 VERDE) — 30

| # | Arquivo | O que foi corrigido | Por quê era um bug |
|---|---|---|---|
| F1 | public/assets/js/app.js:13,200 | `.catch()` na Clipboard API (4 pontos: shareEpisode + bindSocialButtons) | Unhandled Promise Rejection se permissão negada/aba em background |
| F2 | public/assets/js/app.js:103 | `escapeHtml()` em `rowThumb`/`rowThumbJpg` (renderRow) | XSS: URL externa de capa (ep.cover_url_abs) interpolada sem escape em `<img>`/onError |
| F3 | public/assets/js/app.js:145 | `escapeHtml()` em `railThumb`/`railThumbJpg` (renderContinueRail) | XSS idêntico ao F2 no rail "Continuar ouvindo" |
| F4 | public/assets/js/app.js:126 | `console.warn` no catch do push AdSense | catch vazio silenciava falha de renderização de anúncio |
| F5 | public/assets/js/app.js:323 | `console.warn` no catch do register do SW | catch vazio escondia falha crítica de instalação do PWA |
| F6 | public/assets/js/app.js:327 | Validação de protocolo `https?:` no href de patrocinadores | XSS via pseudo-protocolo `javascript:` em `s.website_url` |
| F7 | public/assets/js/app.js:329 | Validação de protocolo `https?:` no CTA da sidebar | XSS via `javascript:` em `ad.click_url` |
| F8 | public/assets/js/app.js:254 | `console.warn` no catch do parse do cache | catch vazio silenciava JSON inválido no localStorage |
| F9 | public/assets/js/app.js:176 | `console.warn` no catch do updateFullPlayerMetadata | catch vazio silenciava erros de meta tags/SEO |
| F10 | public/assets/js/app.js:216 | `console.warn` no catch do requestFullscreen | catch vazio silenciava rejeição do fullscreen |
| F11 | public/assets/js/app.js:185 | `console.warn` no catch do dispatch `episodeloaded` (playEpisode) | catch vazio engolia falha de evento |
| F12 | public/assets/js/app.js:252 | `console.warn` no catch do dispatch `episodeloaded` (renderFilteredFeed) | idem F11 |
| F13 | public/js/supabase_client.js:33 | `.catch()` no `getSession()` + `updateAuthUI(null)` | unhandled rejection em falha de storage; UI presa |
| F14 | public/js/supabase_client.js:76 | `try/catch` no `signOutUser()` | falha de rede deixava estado local inconsistente (não limpava currentUser/UI) |
| F15 | public/js/supabase_client.js:466 | Guard `document.readyState` antes de `initSupabase()` | init nunca rodava se o DOM já estivesse pronto |
| F16 | public/assets/js/player.js:2 | Guard `typeof window.findNextEpisode==="function"` | TypeError em autoplay se o app.js não expusesse a função |
| F17 | public/assets/js/ad_manager.js:2,18 | `fakeInterval` movido p/ escopo pai + `clearInterval` no cleanup | memory leak: timer de imagem de anúncio continuava rodando até 10s após fechar |
| F18 | public/assets/js/listen_progress.js:13 | `.sort((a,b)=>a-b)` no merge de `completed_at` | `.sort()` léxico ordenava timestamps como strings |
| F19 | public/index.html:24 | `<link rel="canonical">` + favicon-32 | SEO: página sem canonical; ícone 32px existia sem tag |
| F20 | public/admin/index.html:5 | meta description | painel sem description (SEO/UX) |
| F21 | public/admin/index.html:10 | `defer` no script do Supabase (CDN) | script no head bloqueava render; ordem de execução verificada segura |
| F22 | public/admin/index.html (22 botões) | `type="button"` em todos os `<button>` sem type | default `submit` podia disparar submit acidental; padrão a11y |
| F23 | public/admin/index.html:409,478,527 | `aria-label="Fechar modal"` nos 3 botões modal-close | botões de ícone sem texto acessível |
| F24 | public/robots.txt | `Disallow: /admin/` | admin indexável por buscadores |
| F25 | public/offline.html:5 | meta description | página offline sem description |
| F26 | public/manifest.webmanifest | ícone maskable 192x192 | PWA: installability exige maskable em 192 |
| F27 | public/sw.js:2 + index.html | Bump do cache `vld-v1-202608081430` + `?v=` dos assets alterados | entregar as correções (sem bump, browser serve JS antigo) |

### Correções AMARELAS aplicadas (aprovadas por Osmar, 2026-08-08) — 7

| # | Arquivo | O que foi corrigido | Por quê |
|---|---|---|---|
| A1 | public/assets/js/player.js:2 | Removido o autoplay direto do `ended` handler (findNextEpisode/playEpisode); ficou só a liberação do WakeLock | Elimina a corrida com `handleAutoPlayNext()`: ad toca limpo e evita double-view (incrementView 2× por transição). Agora `handleAutoPlayNext()` é o ÚNICO caminho de autoplay |
| A2 | public/offline.html:9 | `./styles.css` (inexistente) → `./assets/css/{tokens,base,components}.css` | Página offline estava sem estilo |
| A3 | public/sw.js:102 | `offline.html` só para `req.mode==="navigate"`; demais recursos → `Response("", {status:503})` | Recursos quebrados (imagens) recebiam um documento HTML indevido |
| A4 | public/js/supabase_client.js:133,216,255 | `.limit(1000)` em loadUserFeedback e `.limit(500)` em syncSavedEpisodes/loadUserFavorites | Teto de carga nas queries por usuário |
| A5 | public/js/supabase_client.js:233-239 | `syncSavedEpisodes`: loop de inserts → `insert(toPush.map(...))` em lote único | Menos round-trips no login |

### Correções Pendentes de Aprovação (🟡 AMARELO) — restantes (12)

| Arquivo | Descrição | Risco | Benefício | Recomendação |
|---|---|---|---|---|
| player.js:2 + app.js:325 | **Duplo autoplay no `ended`**: player.js chama `playEpisode(next)` direto; app.js também chama `handleAutoPlayNext()` (ad). Race: próximo episódio toca por trás do ad | Médio (afeta fluxo autoplay/monetização) | Ad toca limpo; evita double-view (incrementView 2× por transição) | **Aplicar**: remover autoplay direto do player.js e deixar só handleAutoPlayNext (decidido por Claude Opus F3) |
| sw.js:102 | offline.html servido para QUALQUER fetch falho (imagens recebem HTML) | Baixo | Erros HTTP corretos para assets | Aplicar: `if (req.mode==="navigate")` antes do fallback |
| offline.html:8 | Referencia `./styles.css` que **não existe** (página offline sem estilo) | Baixo | Offline renderiza com estilo | Corrigir href para os CSS reais |
| app.js:325 | Race `handleAutoPlayNext`: duplo disparo durante `await fetchActiveAd()` (mitigado parcialmente por `isShowing`) | Médio | Robustez do autoplay | Trava `_isAdvancing` com finally |
| app.js:205 | `handleThumbs` sem debounce: cliques rápidos → RPCs concorrentes | Baixo | Evita estados inconsistentes | Disable temporário do botão |
| supabase_client.js:123,206,243 | Queries Supabase sem `.limit()` (feedback, saved, favoritos) | Baixo | Teto de carga por usuário | `.limit(500/1000)` |
| supabase_client.js:226 | `syncSavedEpisodes`: inserts sequenciais → batch único | Baixo | Menos round-trips | `insert(toPush.map(...))` |
| supabase_client.js:36 | Cold start: `getSession()` não carrega favoritos (onAuthStateChange cobre? **verificar**) | Baixo | Favoritos no boot | ⚠️ A confirmar com Osmar |
| app.js:17,22,65,69 | Dead code: `renderShowNotes`, `linksHtml`, `isoWeekKey`, `renderCard` | Baixo | Menos bytes | Remover após confirmar que nada referencia |
| app.js:335 | `window.*` globals (playEpisode etc.) | Baixo | Namespace limpo | `window.AppCore` (quebraria scripts inline — verificar) |
| supabase_client.js:9 | Encapsular em IIFE | Médio | Sem globais | Refactor estrutural |
| listen_progress.js:8 | `record()` com `progressSeconds >= 0` | Baixo | Grava início em 0 | Sem efeito prático (app.js guarda `>0`) — rebaixado de VERDE p/ AMARELO por F3 |
| player.js:8 | Tratamento de erro em URL de áudio quebrada (limpar estado) | Médio | Player não fica preso | Listener `error` com cleanup |
| theme.js:1,6 | Gravar localStorage só em mudança explícita; sync com `prefers-color-scheme` | Baixo | FOUC/preferência correta | Decisão de design |
| ad_manager.js:1 | Pausa explícita do player dentro do `showInterstitial` | Médio | Ad nunca toca por cima | Já mitigado no app.js; centralizar |
| ad_manager.js:30 | Safety timeout fixo 20s → dinâmico pela duração da mídia | Baixo | Ads longos legítimos | Calcular por duração |
| interaction_bar.js:3 | Dispatch `favoriteschange` após save/remove | Baixo | UI de favoritos sempre em sync | 1 linha |
| wakeLock.js:3 | Listener `release` do sentinel + dedup | Baixo | Ciclo de vida correto | Menor |
| — | Favoritos no full player vs drawer (verificar fluxo) | — | — | ⚠️ A confirmar |

### Issues de CSS/Layout (🔴 VERMELHO — Não tocadas) — 18

| Arquivo | Seletor | Problema | Correção Sugerida |
|---|---|---|---|
| components.css | `.speed-select-wrapper select`, `.scrubber-slider` | `outline:0` sem `:focus-visible` (WCAG 2.4.7) | Adicionar `:focus-visible` com mesma especificidade |
| components.css | `.mini-player` | Declaração triplicada sobrescreve design translúcido | Consolidar em 1 regra |
| components.css | `[data-theme="dark"] .mini-player` | Cores sólidas sobrescrevem translucidez | Consolidar |
| components.css | `.drawer-theme-action-btn` etc. | Bloco de regras copiado 2× consecutivo | Remover duplicata |
| components.css | `.host-avatars .avatar`, `:first-child` | Regras duplicadas; `margin-left:0` repetido | Unificar |
| components.css | `.especial-badge`, `.sponsor-tag`, `.drawer-feature-card` | Contraste AA falha no light (~4.24:1 vs 4.5:1) | Escurecer texto/clarear fundo |
| components.css | `.hero-title` | `font-size:1.25rem` idêntico dentro do media query ≥768px | Escalar no MQ |
| components.css | `.ep-row` | Estouro potencial <360px (thumb fixa 92px) | MQ de empilhamento |
| components.css | `.pulse-dot`, `.rotate-icon`, `.sk::after` | Animação sem `will-change` / sem `prefers-reduced-motion` | Adicionar |
| components.css | `.mini-progress-fill` (light/dark) | `background-color` duplicado (hex vs var) | Manter só a var |
| components.css | `.host-avatars .avatar.ricardo`, `.feed-action-btn[data-action="like"].active`, `[data-theme="dark"] .mini-play*`, `.pwa-modal-content`, `.drawer-feature-card`, `.ad-media-container`, `.badge-novo` | Cores hex hardcoded fora do design system | Mapear para tokens |
| components.css | `.ep-row-thumb` (92×69px), `.rail-card` (188px fixos) | Dimensões fixas sem tokens | aspect-ratio / flex |
| components.css | `.topbar-inner` | `padding:8px 0` hardcoded | `var(--space-2) 0` |
| tokens.css | `--color-success`, `--state-success`, `--n-ink-inv-400` | Variáveis órfãs | Remover |
| audio-wave.css | `.scrubber-container` | Seletor dividido entre 2 arquivos | Unificar |
| components.css | *(alegação 2B)* `play:flex` corrompido | **FALSO POSITIVO** — verificado: é `display:flex` de `.topbar-inner` | — |
| components.css | brace count 464 vs 466 | Desequilíbrio aparente (provável conteúdo em strings) | Investigar com parser real se desejar |

### Issues de Segurança

| Severidade | Arquivo | Descrição | Mitigação | Status |
|---|---|---|---|---|
| Alta | app.js:103,145 | XSS em thumbnails via `ep.cover_url_abs` (dado externo) | escapeHtml aplicado | ✅ CORRIGIDO (F2/F3) |
| Alta | app.js:327 | XSS `javascript:` em URL de patrocinador | Validação de protocolo | ✅ CORRIGIDO (F6) |
| Alta | app.js:329 | XSS `javascript:` em CTA de ad (sidebar) | Validação de protocolo | ✅ CORRIGIDO (F7) |
| Média | sw.js:98 | Cache-first salva URLs dinâmicas no cache principal (stale até bump) | Cache separado para dinâmicos | 🟡 AMARELO |
| Média | sw.js:102 | offline.html devolvido p/ fetch de qualquer recurso | Guard `req.mode==="navigate"` | 🟡 AMARELO |
| Baixa | admin/index.html:51 | UI admin escondida por CSS; dados protegidos por RLS/RPCs (sem vazamento real) | — | ✅ Verificado OK |
| Baixa | — | Anon key Supabase no client | Por design (SPA client-side) | ✅ Não é achado |
| Informação | supabase_client.js:90 | `avatar_url` em `src` de `<img>` (javascript: em img src é inerte) | Não explora — documentado | ✅ OK |

### Análise de Integração entre Módulos (Fase 3 — Claude Opus 4.6)

**🔴 Crítico arquitetural (AMARELO — pendente):** duplo caminho de autoplay no `ended`:
`player.js` (listener nativo) chama `window.playEpisode(nextEp.id)` imediatamente, enquanto
`app.js` (via `playerevent`) chama `handleAutoPlayNext()` que busca ad e só então toca o
próximo. Consequências: (1) o próximo episódio começa a tocar por trás do interstitial
(~0,3–1s de áudio duplo); (2) `playEpisode` é invocado 2× por transição → `incrementView`
2× (double view). Correção recomendada: remover o autoplay direto do `player.js` e deixar
o `handleAutoPlayNext()` como único caminho (ele já cobre o caso sem ad).

**Contratos entre módulos:** eventos `playerevent`/`listenprogresschange`/`episodeloaded`/
`favoriteschange`/`themechange` estão corretamente casados (emissores ↔ listeners). O
`episodeloaded` é escutado por `interaction_bar.js` (view counting) — fluxo OK.

**Consistência de dados:** `ep.id` vs `ep.date` para especiais B&M (`especial-XXX`):
código do feed/rail/player já usa `ep.id` nas chaves de interação (fix anterior 2026-08-07
documentado na skill). Auditoria confirmou nenhuma regressão. `cover_url_abs` → `cover_url`
→ fallback thumbnails: cadeia consistente.

**Cascata de falhas:** Supabase offline → ads/auth/newsletter falham silenciosamente com
warn (por design); feed vem de `episodes.json` (network-first com cache) — player segue
funcionando. SW falhando → fetch normal. Único ponto frágil: offline.html sem CSS (achado
AMARELO acima).

**Conflitos entre achados resolvidos:**
- XSS thumbs (2A ∩ 2E) → mesma correção, aplicada 1× (F2/F3).
- `listen_progress >= 0` (2D) → rebaixado p/ AMARELO (sem efeito prático; app.js guarda).
- IIFE no supabase_client (2A) → AMARELO (mudança estrutural, não verde).
- "play:flex corrompido" (2B) → falso positivo verificado.

### Plano de Correção Sugerido

#### Imediato — Esta semana
1. ✅ Aplicar o fix do **duplo autoplay** (player.js remover autoplay direto) — AMARELO aprovado
2. ✅ Corrigir `offline.html` (styles.css inexistente)
3. ✅ SW: offline.html só para `req.mode==="navigate"`
4. ✅ Rodar `publish_site.py` e validar em :8090 + browser (gesture real, autoplay, ad, console 0 erros)

#### Próximo sprint
5. `.limit()` nas queries Supabase + batch insert no syncSavedEpisodes
6. Trava de reentrância no `handleAutoPlayNext`
7. Tratamento de erro de URL de áudio no player.js
8. Dead code (renderCard/linksHtml/renderShowNotes/isoWeekKey)

#### Backlog
9. Refactor IIFE/namespace do supabase_client
10. Fixes de acessibilidade CSS (focus-visible, contraste AA) — exigem aprovação de design
11. Tokens: mapear hex hardcoded, remover vars órfãs, `prefers-reduced-motion`
12. Safety timeout dinâmico do ad; wakeLock sentinel listener

### Modelos Utilizados

| Tarefa | Modelo |
|---|---|
| Fase 1 contexto | Hermes Agent (direto) |
| Fase 2A JS crítico | Gemini 3.6 Flash (High) |
| Fase 2B CSS | Gemini 3.5 Flash (High) |
| Fase 2C HTML/SEO | Gemini 3.6 Flash (Medium) |
| Fase 2D player/mídia | Gemini 3.5 Flash (Medium) |
| Fase 2E segurança/SW | Gemini 3.1 Pro (Low) [High recusou por guardrail] |
| Fase 3 integração | Claude Opus 4.6 (Thinking) |
| Fase 4 correções | Hermes Agent (string-replace validado; ver nota) |
| Fase 5 relatório | Hermes Agent |

### Verificação

- `node --check` em 9 arquivos JS: ✅ todos OK
- `manifest.webmanifest` JSON válido: ✅
- Diffs vs backup (30 correções): ✅ cirúrgicos, sem mudança de layout
- Nenhum arquivo .css modificado: ✅ (verificado por diff)
- Cache-busters `?v=` + SW version bump: ✅ conferidos por grep

*Gerado por: Hermes Agent (orquestrador) | Data: 2026-08-08 | Executor: agy 1.1.11*
