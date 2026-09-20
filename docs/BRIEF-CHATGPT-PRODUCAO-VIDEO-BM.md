# Brief para ChatGPT — Produção de vídeo do Vale da Liberdade (Brasil e Mundo)

Documento de contexto para sugerir **melhorias na produção visual do vídeo YouTube**. Não é spec de implementação. Não inventar arquivos, constantes ou fluxos que não estejam aqui. Se algo estiver em conflito, preferir os números da seção “Constantes vivas no código”.

**Data do snapshot:** 2026-09-20  
**Repo:** `/home/osmar/web-jornal-vale-da-liberdade`  
**Branch de trabalho visual:** `feat/evolucao-visual-broadcast`  
**Produto:** Web Jornal Vale da Liberdade — PWA `https://news.mob.tec.br`  
**Quadro de vídeo:** especial **Brasil e Mundo** (~5 min), apresentador único **Peter Albuquerque**  
**Pedido ao ChatGPT:** sugerir melhorias concretas de direção de arte, pacing visual, composição, motion, lower third, mockup de browser, card do X, avatar, captura de matérias, encode e retenção YouTube. Priorizar o que cabe neste pipeline (Playwright + HTML 1080p + ffmpeg). Não religar HyperFrames. Não propor karaoke palavra-a-palavra.

---

## 1. O que é o projeto

O Vale da Liberdade é um webjornal libertário em português do Brasil. Tem:

1. **Diário em áudio** (dois apresentadores no site: Peter + Ricardo) — fora do foco deste brief.
2. **Especial Brasil e Mundo (BM)** — um comentário solo do Peter sobre um tema, publicado no **site e no YouTube** como vídeo 1920×1080.

O vídeo BM **não** é um talking-head filmado. É um **telejornal sintético**:

- Áudio TTS do Peter por cima.
- Canvas HTML 1080p gravado no Chromium (Playwright) com “estúdio + navegador + cards”.
- Loop de avatar do Peter com chromakey, colado no canto inferior esquerdo.
- Lower third (manchete + linha fina + ticker) **na frente** do avatar.
- Intro musical com ducking e outro de encerramento obrigatório.
- Upload público no YouTube com marca de mídia sintética.

Tom editorial do Peter: irônico, cético, analogias de empresa privada, sem saudação nos primeiros segundos, bordão de fechamento obrigatório. Primeiros 3 minutos sem palavrão (monetização). Não creditar o canal-fonte ANCAPSU. Link canônico do app: `https://news.mob.tec.br`.

---

## 2. Esteira de produção (do tema ao MP4)

Fase 1 (atual): cron hourly monitora um canal YouTube de origem → transcrição → condensador LLM → JSON do episódio → TTS → captura de prints/vídeos das fontes → timeline de beats → gravação Playwright do mockup → composição ffmpeg (avatar + L3) → intro/outro → thumbnail → upload.

```
bm_pipeline.py process-queue
        ↓  (áudio do site continua mesmo se o vídeo falhar)
bm_mockup_video.py --pending --upload --privacy public --max 1 --days 2
```

- Cron: `web-jornal-brasil-mundo-hourly` (`30 * * * *`) → `scripts/bm-hourly-pipeline.sh`
- Orçamento do job ~3300 s; mockup só se restarem ≥900 s
- **1 vídeo por hora**, janela 2 dias
- Python do vídeo: `.venv` do **projeto** (Playwright)
- Python da fila TTS: venv do Hermes
- HyperFrames / `bm_video_autopilot.py`: **morto**. Não reativar.

Fase 2 (sob demanda): `python scripts/bm_pipeline.py full --youtube-url URL`  
Fase 3 (não é o default): episódio a partir de prompt, só quando pedido.

---

## 3. Stack relevante para o vídeo

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3 (venv do projeto) |
| Canvas | HTML/CSS/JS 1920×1080, GSAP |
| Gravação | Playwright + Chromium headless, `wait_until=domcontentloaded` (**nunca** `networkidle`) |
| Composição | ffmpeg; encode **Intel VA-API** (`h264_vaapi`, qp 20) no HD 630; fallback `libx264` |
| Avatar scale | `flags=bilinear` (lanczos foi medido e descartado: custo no decode 1080p, não no filtro do avatar) |
| TTS Peter | Gemini TTS, voz **Charon**; áudio −16 LUFS |
| Condensador | Gemini 3.8 Flash (roteiro ~750–920 palavras, alvo ~830 / ~5 min) |
| Tradução de tweets | cascade Gemini lite/flash + cache em disco |
| Captura de portais | `scripts/screenshots/` (handlers por domínio + BaseScraper); cache `handler-v6` |
| B-roll | Pexels/Pixabay via `scripts/bm_broll_fetcher.py` → `references/youtube/broll/_index.json` |
| Lower third | `youtube/Lower-third-engine/` + `scripts/faceless_lower_third.py` (overlay WebM + chromakey `#00FF00`) |
| Upload | YouTube Data API, OAuth `credentials/token.json`; `containsSyntheticMedia=true`; categoria 25 |
| Host | Linux; servidor ligado 05:45–23h por causa do jornal 06h; GPU local (RTX 3060 Ti) **não** é o encode do BM (encode é VA-API no iGPU) |

---

## 4. Camadas do quadro final (de trás para frente)

1. **Wallpaper** de estúdio (jpg/png/webp por `md5(video_id)`, pasta `references/youtube/mockup-browser/wallpaper/`). Sem gif.
2. **Mockup-browser** (portal, cards, X, documento, etc.) gravado em MP4.
3. **Avatar loop** do Peter (chromakey verde Picsart `#007E00`).
4. **Lower third** (sempre na frente do avatar; o HTML do mockup **esconde** o L3 interno na gravação para não duplicar).
5. **Áudio** do episódio (ignorar áudio do loop do avatar).
6. **Intro** musical + **outro** concatenado.

Safe zone: palco `#broadcastStage` vai até Y 890 (`bottom: 190px`). Lower third ocupa ~Y 880–1080. Cards não podem invadir essa faixa.

---

## 5. Canvas HTML (mockup-browser)

- Oficial: `references/youtube/mockup-browser/mockup-browser.html`
- Alias legado (typo histórico, **byte a byte idêntico**): `mockup-brower.html`
- Constante: `MOCKUP_HTML` em `scripts/bm_video/constants.py`
- Studio de preview: `demo-broadcast-studio.html` via `python scripts/abrir_demo_broadcast.py` (porta 8765)
- Estética oficial: **Light Editorial Studio** (`DESIGN.md` §8, `LIGHT_BROADCAST_DESIGN_SYSTEM.md`): cartões papel branco, ouro, texto preto. Dark mode “hacker” é repudiado nos cards.
- Defesa anti-flash recente: fundo do viewport `.portal-viewport` é `#11141c` (estúdio escuro) para **não** estourar branco no YouTube quando o print ainda não chegou. Há tensão consciente entre “light editorial nos cards” e “base escura no portal”.

### 5.1 Modos visuais (`kind` / `visual_component`)

| Modo | kind | Tela |
|---|---|---|
| 1 | `source` | Portal de notícias (chrome de browser + print da matéria + ticker) |
| 2 | `quote` | Card Gold / aspas editorial |
| 3 | `document` | Documento oficial com zoom/grifo |
| 4 | `timeline` | Linha do tempo |
| 5 | `chart` | Big number / impacto econômico |
| 6 | `comparison` | Split A × B |
| 7 | `recorte` | Recorte impresso |
| 8 | `x-post` (`x`, `tweet`) | Card do X — Modelo 3 Cinematic Prime 3D Glass |
| extra | `person-photo` | Foto editorial Ken Burns |
| extra | `broll` | Clipe curto de respiro |
| extra | `transition` | wipe/dissolve/flash de estúdio |

Roteamento: JSON → `_build_mockup_update_payload()` → Playwright `VDL_MOCKUP.update()`.

### 5.2 Modo 1 — Browser / matéria

- Print da URL original (não do HTML recuperado por paywall).
- Variantes ópticas na **mesma** screenshot: `portal_hero` (1.0×), `portal_zoom` (1.18× foco 28%), `portal_scroll` (1.08× foco 65%), `portal_highlight` (marca-texto dourado).
- Ken Burns contínuo no browser: escala 1.0 → 1.025 no beat (a tela nunca congela).
- Dual-buffer: `#pageShot` (ativo) + `#pageShotNext` (entrante, opacity 0). Crossfade GSAP 0.55s `power2.inOut`. Decode **só** em `pageShotNext.decode()` (v3: sem `new Image()` intermediário).
- Omnibox + `tabTitle` só atualizam quando a imagem nova está pronta; micro-fade 0.15s out / 0.25s in.
- `onerror`: **não** troca o `pageShot` por URL quebrada; limpa só o buffer next.
- Pré-carga Playwright: `Promise.all` + `img.decode()` de todos os `/shots/` antes do primeiro frame.
- Transições broadcast: `flash_cut` 0.55s shutter âmbar; `dissolve_brand` 0.65s ouro; `wipe_gold` 0.75s; `gsap.killTweensOf` para não empilhar.
- Vídeo vertical (X/Shorts): `object-fit: contain` + laterais `#11141c`. Horizontal: `cover`.
- GPU CSS: `will-change: opacity, transform` + `image-rendering: -webkit-optimize-contrast`.

### 5.3 Modo 8 — Card do X

Layout Modelo 3: `#xStageRoot` e `#xCard` são **siblings**. Speaker VIP `#xSpeakerBox` no quadrante superior esquerdo (avatar 300px + verified).

- Card: 1250×720, `top 44px` / `right 44px` dentro do stage, perspectiva `rotateY(-1.8deg) rotateX(1deg)`, z-index 32
- Invariante: `36 + 44 + 720 ≤ 890` (não invade L3)
- Mídia: `#xMediaBox` 350px + Ken Burns 1.05× / 10s; arquivo `/shots/x-media-{id}.jpg`
- Sem mídia: classe `.is-text-only` e fonte 56→33px por contagem de caracteres
- Tweet estrangeiro: traduzido para pt-BR; original preservado
- GSAP `transitionToX`: browser desce, card sobe (`y 140→0`, `scale 0.95→1`, elastic) + pop no like `#f91880`
- Captura de post sem vídeo: embed público `platform.twitter.com/embed`, **não** `page.goto` em x.com (403 headless)

### 5.4 Outros cards

Quote / document / timeline / chart / comparison / recorte: Light Editorial, papel branco, friso ouro. Person-photo: Ken Burns em foto local (placeholder e arquivo ausente são pulados).

---

## 6. Avatar (Peter)

Arquivo (fora do git):

`references/youtube/Apresentadores/Peter Albuquerque/Peter-Loop-Picsart-BackgroundRemover.mp4`

- Fonte 964×720, fundo Picsart `#007E00` (não é chroma `#00FF00`)
- Crop `910:720:54:0` (corta ~1/18 à esquerda)
- Scale `546:432` (bilinear)
- Overlay `0:H-h+38` (encostado na esquerda; ~38px para baixo, peito sob o L3)
- Chromakey `0x007E00:0.10:0.03` + lut alfa para o paletó não sumir
- Loop infinito (`-stream_loop -1`); delay 1.0 s no início (`tpad`)
- **Não há lip-sync.** Boca e gesto não acompanham o TTS. É um loop contínuo.
- Áudio do loop é descartado.

Otimização já medida (2026-09-16): bilinear −27% vs lanczos no `compose_presenter`; o gargalo é decode do mockup 1080p + overlay por frame, não o scale do avatar. Pré-processar o avatar em ProRes não valeu (SSIM 0.85 na região, tempo igual).

---

## 7. Lower third

Engine: `youtube/Lower-third-engine/obs-overlay.html` via `scripts/faceless_lower_third.py`. Preset `vdl-brasil-mundo`. Overlay WebM, chromakey `#00FF00`, sempre **acima** do avatar.

JSON obrigatório do episódio:

- `titulo`: manchete 40–65 caracteres (máx 80); na tela até 115
- `subtitulo`: linha fina factual 40–85; na tela até 98 e **sempre mais curta** que o título
- Subtítulo **nunca** é fala de abertura (“Fala pessoal…”) nem o nome da fonte

Ticker: título atual + até 6 especiais BM recentes. Sem URL. Velocidade **55 px/s**. Grava 1 ciclo do marquee e o ffmpeg loopa (evita tranco no meio da frase). Largura útil `--lt-width: 1576px`.

No mockup HTML, `renderTicker` faz `trim` + `filter(Boolean)`. O engine JS (`lower-third-engine.js`) ainda faz `split('|')` **sem** trim — drift conhecido.

Karaoke palavra-a-palavra: **proibido**.

---

## 8. Áudio, intro e outro

- Duração falada alvo ~4–5 min; teto do mockup **480 s**; aviso acima de **330 s**
- Intro v2 `branding/audio/intro/Top-Intro.mp3`: 0–1.5s trilha 1.0; voz entra 1.5s e duck 0.18 até 8s; fade 8→15s. Cache `*-with-intro-v2.mp3`
- Outro v2: take + wallpaper + `final-mix-25s.wav`; duck 0.12 na fala; swell depois da voz; +20s de cauda em frame congelado; fade 4s. **Obrigatório** — sem outro o upload aborta
- Peter **não** lê “deixe o like” por cima do bumper

---

## 9. Timeline, pacing visual e fontes

Constantes vivas em `scripts/bm_scene_timeline.py`:

- `MIN_SCENE_DURATION_S = 5.0`
- `MAX_SCENE_DURATION_S = 12.0` (nenhuma tela `source` estática > 12 s)
- `TARGET_MIN_BEATS_5MIN = 18` (piso de telas em episódios ≥ 180 s)
- `MAX_SCENES = 8` matérias visuais
- `MAX_PER_HOST = 2`

Gancho dos **primeiros 15 s**: pelo menos 3 cortes (0–5, 5–9, 9–15) entre manchete, close e B-roll.

B-roll: 0,8–1,5 s na troca de bloco; se a biblioteca estiver vazia, corte direto (não falha).

Fontes: se a descrição do YouTube de origem já tem ≥2 URLs de matérias, **não** forçar RSS. Complementar só com entidades nomeadas (pessoa, órgão, lei). Termos genéricos (economia, stf, governo, brasil) não ligam temas. RSS > 7 dias rejeitado.

Captura: cache 36 h, versão `handler-v6`; print em branco (`stddev` < 6 ou < 20 KB) descartado; 403/login-wall → skip, sem bypass; **não** usar recuperação de paywall para consertar print (isso é só texto de pauta). Handlers específicos: BBC, G1, Instagram, X embed, Polymarket, Kalshi, Agência Brasil, etc.

Shot longo: às vezes stitch de print topo+rodapé. Highlight box pode ir no payload para o overlay de grifo.

Alinhamento fala↔cena: por proporção de palavras (Whisper existe como modo, default é proporção).

---

## 10. Metadados YouTube (contrato)

- Privacidade: `public`
- Título: `titulo` do `especial-{id}.json` (máx 100)
- Thumbnail: `thumbnails/YYYY-MM-DD/bm_{id}.jpg` (mesma do site); falta de capa **não** aborta upload
- IA: `status.containsSyntheticMedia=true`
- Áudio `pt-BR`; certificação de legendas: nenhuma
- 4 parágrafos na descrição (manchete, contexto, “Neste vídeo analisamos”, pergunta+CTA); 0–3 hashtags sem espaço; **zero URL ANCAPSU**
- Capítulos narrativos 3–6 palavras, sem nome de veículo; loop 25–40 s
- 1 playlist das 5 oficiais (2 só se ganchos iguais)

---

## 11. Testes de regressão visual (o que não pode quebrar)

```
PYTHONPATH=. .venv/bin/pytest tests/test_x_post_mockup_integration.py scripts/test_bm_scene_timeline.py -v
```

49 testes no snapshot recente (paridade dos dois HTML, geometria Modelo 3, `transitionToX`, payload, tradução, timeline). Sem `PYTHONPATH=.` os imports `scripts.*` quebram.

Calibração visual = **um commit** com (a) HTML oficial, (b) cópia do alias, (c) asserts da suíte, (d) `docs/BM-VIDEO-LAYOUT.md`. Mexer geometria sem as 3/4 frentes gera drift silencioso.

---

## 12. Limitações conhecidas (ponto de partida para sugestões)

Use isto como lista de dores, não como “já decidido que está errado”:

1. **Avatar é loop, não performance.** Não articula com o TTS; risco de “boneco vivo” repetitivo em 5 min.
2. **Teto de 8 cenas** e reuso da mesma matéria com outro crop. Pode parecer reciclagem.
3. **Print estático** de portais (anti-bot: 1 página = 1 print). Pouca “vida” de página real.
4. **L3 do engine vs ticker do mockup:** sanitização divergente; dois sistemas de manchete.
5. **Light editorial vs viewport `#11141c`:** anti-flash necessário, mas o portal “vazio” ficou escuro.
6. **Encode VA-API qp 20** no HD 630: rápido, lock global (2 encodes paralelos geram NAL inválido). Qualidade YouTube vs tempo de cron.
7. **Scale bilinear no avatar** (performance). Spec antiga citava lanczos.
8. **Crossfade ainda promove `pageShot.src = src` no `onComplete`** — Blink pode descartar textura no frame final; dual-buffer mitiga, não zera o risco teórico.
9. **B-roll curto (0,8–1,5 s)** e biblioteca opcional.
10. **Sem lip-sync, sem câmera real, sem motion graphics After Effects.** Tudo tem de viver em HTML+GSAP+ffmpeg.
11. **Cron 1/hora** e teto 8 min. Sugestões caras de render (WebGL por frame, 60 fps, 4K) provavelmente inviáveis no host.
12. **Person-photo e document/chart** existem no engine; a densidade de uso real depende do condensador/timeline acertar o `kind`. Se o JSON vier quase só `source`, o vídeo vira “browser + zoom” o episódio inteiro.

---

## 13. Arquivos canônicos para citar

- `docs/BM-VIDEO-LAYOUT.md` — geometria avatar/L3/Modo 8
- `docs/BM-EPISODE-PACING.md` — pacing (alguns números de piso de cena/palavras estão mais antigos que o código; preferir constantes da seção 9)
- `pipelines/brasil_e_mundo/SKILL_BRASIL_E_MUNDO.md` — voz, gancho 15 s, 18 telas
- `DESIGN.md` §8 — Light Editorial
- `scripts/bm_mockup_video.py` + `scripts/bm_video/{capture,render,constants,state}.py`
- `scripts/bm_scene_timeline.py`
- `references/youtube/mockup-browser/mockup-browser.html`
- `RELATORIO_OTIMIZACAO_VISUAL_PIPELINE.md` — dual-buffer / auditoria v3 (anti-tela-branca)
- `youtube/Lower-third-engine/lower-third-engine.js`

---

## 14. Como o ChatGPT deve responder

1. Começar pelas **3–7 alavancas de retenção** (0–15 s, variedade de kind, motion, L3, avatar) com impacto vs custo no pipeline atual.
2. Cada sugestão: o que muda, em qual camada (HTML / timeline / ffmpeg / captura), esforço (baixo/médio/alto), risco de quebrar a suíte de 49 testes.
3. Não propor: HyperFrames, karaoke, dark mode nos cards, `networkidle`, scrape agressivo de paywall, 4K, lip-sync pesado sem dizer de onde sai o compute.
4. Preferir melhorias que o condensador/timeline já consegue sinalizar (`kind`, `visual_variant`, `fonte_url`) em vez de um motor 3D novo.
5. Se sugerir geometria, respeitar safe zone Y 890 e paridade dos dois HTML.

Fim do brief.
