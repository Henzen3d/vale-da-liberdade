# 03 — ESPECIFICAÇÃO DOS COMPONENTES GSAP & SVG
> **Mapeamento Gráfico e Procedural para `mockup-brower.html`**  
> **Tecnologias:** HTML5, CSS3 Glassmorphism, Vetores SVG, GSAP 3.14.2  
> **Canvas Oficial:** 1920 × 1080 (Full HD Broadcast)  

---

## 1. Regras de Composição e Áreas Seguras (Safe Zones)

No [`bm_mockup_video.py`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/scripts/bm_mockup_video.py), o vídeo final recebe duas sobreposições críticas via FFmpeg:
1. **Lower Third Oficial VDL:** Ocupa a faixa inferior da tela (altura de ~140px a partir de `bottom: 28px`).
2. **Apresentador Peter Albuquerque:** Loop com Chroma Key posicionado no canto inferior esquerdo (`AVATAR_SCALE = "546:432"`, `AVATAR_OVERLAY = "0:H-h+38"`).

### Mapa de Áreas Seguras no Canvas 1920×1080
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 0,0                                                               1920,0    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     ZONA PRINCIPAL DE CONTEÚDO                        │  │
│  │                                                                       │  │
│  │   [ÁREA LIVRE]                   ┌──────────────────────────────┐     │  │
│  │                                  │                              │     │  │
│  │                                  │   CARDS EDITORIAIS VDL       │     │  │
│  │                                  │   (Quote, Doc, Chart, etc.)  │     │  │
│  │                                  │   Largura: 980px a 1150px    │     │  │
│  │                                  │   Alinhamento: Centro/Direita│     │  │
│  │                                  │                              │     │  │
│  │  ┌──────────────────┐            └──────────────────────────────┘     │  │
│  │  │   APRESENTADOR   │                                                 │  │
│  │  │   PETER (ÂNCORA) │                                                 │  │
│  └──┴──────────────────┴─────────────────────────────────────────────────┴──┘
│  │  [ LOWER THIRD BROADCAST - DATA + TICKER + PROGRAMA ]                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│ 0,1080                                                            1920,1080 │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Regra Estrita de CSS:** Todo novo card deve seguir a convenção já aprovada no `#xCard`:
* `position: absolute;`
* `top: 50%; left: 50%;`
* `transform: translate(-50%, -50%);`
* `margin-top: -65px;` (compensa a altura do Lower Third na base).
* `z-index: 25;`

---

## 2. Paleta de Cores e Tokens do Estúdio VDL

```css
:root {
  /* Fundos Escuros */
  --vdl-bg-dark-1: #0e1118;
  --vdl-bg-dark-2: #161b26;
  --vdl-bg-card: rgba(22, 27, 38, 0.94);
  
  /* Ouros e Destaques */
  --vdl-gold-main: #d4a017;
  --vdl-gold-amber: #b8860b;
  --vdl-gold-glow: rgba(212, 160, 23, 0.25);
  
  /* Alertas e Tendências */
  --vdl-red-live: #ef2633;
  --vdl-green-pos: #10b981;
  --vdl-red-neg: #f43f5e;
  
  /* Tipografia */
  --font-headline: 'Roboto Condensed', 'Barlow Condensed', sans-serif;
  --font-body: 'Plus Jakarta Sans', 'Inter', sans-serif;
  --font-mono: 'Roboto Mono', monospace;
}
```

---

## 3. Especificação dos 5 Novos Componentes

### 3.1 Componente 1: `QuoteCard` (`#quoteCard`)
* **Objetivo:** Destacar declarações fortes de autoridades ou trechos essenciais.
* **Estrutura HTML/SVG:**
```html
<div id="quoteCard" class="vdl-card quote-card" style="display:none; visibility:hidden;">
  <div class="quote-watermark-icon">
    <svg viewBox="0 0 24 24"><path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z" fill="url(#goldGradient)"/></svg>
  </div>
  
  <div class="quote-body-text" id="quoteText">
    "A meta é liberar o trecho duplicado da BR-470 sem novas interrupções até o fim do semestre."
  </div>

  <div class="quote-footer">
    <div class="quote-author-box">
      <div class="quote-avatar">
        <img id="quoteAvatarImg" src="" alt="" hidden>
        <div id="quoteAvatarFallback" class="avatar-fallback">VDL</div>
      </div>
      <div class="quote-author-info">
        <div class="quote-author-name" id="quoteAuthorName">Nome do Autor</div>
        <div class="quote-author-role" id="quoteAuthorRole">Cargo / Instituição</div>
      </div>
    </div>
    
    <div class="quote-context-tag">
      <span class="dot-gold"></span>
      <span id="quoteSourceTag">Entrevista Exclusiva • 05/09/2026</span>
    </div>
  </div>
</div>
```

* **Linha do Tempo GSAP:**
```javascript
transitionToQuote(data = {}) {
  const browserEl = document.getElementById("browserMockup");
  const cardEl = document.getElementById("quoteCard");
  
  // Popula dados
  document.getElementById("quoteText").textContent = `"${data.quote_text || ''}"`;
  document.getElementById("quoteAuthorName").textContent = data.author_name || "";
  document.getElementById("quoteAuthorRole").textContent = data.author_role || "";
  document.getElementById("quoteSourceTag").textContent = `${data.source_name || 'Declaração'} • ${data.date || ''}`;

  const tl = gsap.timeline();
  // 1. Oculta navegador
  tl.to(browserEl, { y: 70, opacity: 0, scale: 0.96, duration: 0.45, ease: "power2.inOut" });
  // 2. Surge o card de citação com amortecimento elástico
  tl.set(cardEl, { display: "flex", visibility: "visible", y: 120, opacity: 0, scale: 0.95 });
  tl.to(cardEl, { y: 0, opacity: 1, scale: 1, duration: 0.6, ease: "power3.out" }, "-=0.15");
  // 3. Efeito sutil de brilho dourado nas aspas
  tl.fromTo(".quote-watermark-icon", { scale: 0.8, opacity: 0 }, { scale: 1, opacity: 0.15, duration: 0.8, ease: "back.out(1.5)" }, "-=0.4");
}
```

---

### 3.2 Componente 2: `DocumentZoom` (`#documentCard`)
* **Objetivo:** Explorar visualmente documentos oficiais, decisões do TJSC/STF, certidões ou contratos.
* **Estrutura HTML/SVG:**
```html
<div id="documentCard" class="vdl-card doc-card" style="display:none; visibility:hidden;">
  <div class="doc-header-bar">
    <div class="doc-badge" id="docTypeBadge">DECISÃO JUDICIAL</div>
    <div class="doc-process-num" id="docProcessNum">PROCESSO Nº 500214-2026.8.24.0008</div>
    <div class="doc-institution" id="docInstitution">VARA DA FAZENDA PÚBLICA</div>
  </div>

  <div class="doc-sheet-viewport">
    <div class="doc-sheet" id="docSheet">
      <!-- Imagem real do documento ou texto simulado com grifo -->
      <img id="docSheetImg" src="" alt="Documento Oficial" hidden>
      <div id="docTextSimulated" class="doc-simulated-text">
        <p class="doc-p">Vistos etc.</p>
        <p class="doc-p">Considerando a urgência dos pedidos formulados e o risco de dano irreparável ao erário municipal...</p>
        <div class="doc-highlight-target">
          <span class="highlighter-sweep" id="highlighterSweep"></span>
          <p class="doc-highlight-text" id="docHighlightText">
            DEFIRO A LIMINAR pleiteada para determinar a suspensão imediata dos efeitos do reajuste contratual.
          </p>
        </div>
        <p class="doc-p">Intimem-se com urgência as partes envolvidas.</p>
      </div>
    </div>
  </div>
</div>
```

* **Linha do Tempo GSAP (Zoom + Marca-texto Animado):**
```javascript
transitionToDocument(data = {}) {
  const browserEl = document.getElementById("browserMockup");
  const cardEl = document.getElementById("documentCard");
  const sheet = document.getElementById("docSheet");
  const sweep = document.getElementById("highlighterSweep");

  const tl = gsap.timeline();
  tl.to(browserEl, { y: 70, opacity: 0, scale: 0.96, duration: 0.45 });
  tl.set(cardEl, { display: "flex", visibility: "visible", y: 120, opacity: 0 });
  tl.to(cardEl, { y: 0, opacity: 1, duration: 0.55, ease: "power3.out" }, "-=0.15");

  // Animação de câmera: aproximação suave na cláusula relevante
  tl.to(sheet, { scale: 1.28, y: -45, duration: 1.2, ease: "power2.out" });

  // Efeito marca-texto amarelo correndo da esquerda para a direita
  tl.fromTo(sweep, 
    { width: "0%" }, 
    { width: "100%", duration: 0.9, ease: "power1.inOut" }, 
    "-=0.5"
  );
}
```

---

### 3.3 Componente 3: `DataChart / StatCounter` (`#dataChartCard`)
* **Objetivo:** Exibir Big Numbers com impacto cinematográfico (números subindo em tempo real com indicador de tendência).
* **Estrutura HTML/SVG:**
```html
<div id="dataChartCard" class="vdl-card chart-card" style="display:none; visibility:hidden;">
  <div class="chart-header">
    <div class="chart-badge">INDICADOR ECONÔMICO</div>
    <div class="chart-title" id="chartTitle">GASTO PÚBLICO MUNICIPAL COM PUBLICIDADE</div>
  </div>

  <div class="chart-hero-number-box">
    <span class="chart-prefix" id="chartPrefix">R$ </span>
    <span class="chart-big-number" id="chartBigNumber">0,0</span>
    <span class="chart-suffix" id="chartSuffix"> mi</span>
  </div>

  <div class="chart-trend-box" id="chartTrendBox">
    <!-- Seta SVG de tendência -->
    <svg id="trendIconUp" class="trend-icon green" viewBox="0 0 24 24"><path d="M7 14l5-5 5 5z" fill="currentColor"/></svg>
    <svg id="trendIconDown" class="trend-icon red" viewBox="0 0 24 24" hidden><path d="M7 10l5 5 5-5z" fill="currentColor"/></svg>
    <span class="trend-text" id="chartTrendText">+14,2% em comparação ao mesmo período de 2025</span>
  </div>

  <!-- Barra de Comparação Vetorial SVG -->
  <div class="chart-svg-bar-container">
    <svg width="100%" height="24" class="svg-progress-track">
      <rect x="0" y="4" width="100%" height="16" rx="8" fill="rgba(255,255,255,0.08)"/>
      <rect id="svgProgressBar" x="0" y="4" width="0%" height="16" rx="8" fill="url(#goldGradient)"/>
    </svg>
  </div>
</div>
```

* **Linha do Tempo GSAP (Contador Procedural):**
```javascript
transitionToChart(data = {}) {
  const browserEl = document.getElementById("browserMockup");
  const cardEl = document.getElementById("dataChartCard");
  const numEl = document.getElementById("chartBigNumber");
  const barEl = document.getElementById("svgProgressBar");

  const targetValue = parseFloat(data.metric_value || 0);
  const counterObj = { val: 0 };

  const tl = gsap.timeline();
  tl.to(browserEl, { y: 70, opacity: 0, scale: 0.96, duration: 0.45 });
  tl.set(cardEl, { display: "flex", visibility: "visible", y: 120, opacity: 0 });
  tl.to(cardEl, { y: 0, opacity: 1, duration: 0.55, ease: "power3.out" }, "-=0.15");

  // Anima o número de 0 até o valor final com formatação PT-BR
  tl.to(counterObj, {
    val: targetValue,
    duration: 1.4,
    ease: "power2.out",
    onUpdate: () => {
      numEl.textContent = counterObj.val.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    }
  }, "-=0.2");

  // Expande a barra de progresso em sincronia
  tl.to(barEl, { width: "78%", duration: 1.3, ease: "power2.out" }, "<");
}
```

---

### 3.4 Componente 4: `Timeline` (`#timelineCard`)
* **Objetivo:** Exibir cronologia de acontecimentos, desdobramentos de crises ou evolução de processos.
* **Estrutura HTML/SVG:**
```html
<div id="timelineCard" class="vdl-card timeline-card" style="display:none; visibility:hidden;">
  <div class="timeline-title-row">
    <div class="timeline-badge">CRONOLOGIA DOS FATOS</div>
    <div class="timeline-headline" id="timelineHeadline">LINHA DO TEMPO: O CASO DA TARIFA DE ÔNIBUS</div>
  </div>

  <div class="timeline-track-container">
    <!-- Linha SVG conectora -->
    <svg class="timeline-svg-line" width="100%" height="8">
      <line x1="10%" y1="4" x2="90%" y2="4" stroke="rgba(255,255,255,0.15)" stroke-width="3"/>
      <line id="timelineProgressLine" x1="10%" y1="4" x2="10%" y2="4" stroke="#d4a017" stroke-width="4"/>
    </svg>

    <div class="timeline-nodes-wrapper" id="timelineNodes">
      <!-- Gerado via JavaScript: 3 a 4 nós cronológicos -->
    </div>
  </div>
</div>
```

---

### 3.5 Componente 5: `Comparison` (`#comparisonCard`)
* **Objetivo:** Confrontar promessas com realizações, dados antigos versus novos, posições contraditórias.
* **Estrutura HTML/SVG:**
```html
<div id="comparisonCard" class="vdl-card comparison-card" style="display:none; visibility:hidden;">
  <div class="comparison-header">
    <div class="comparison-badge">ANÁLISE COMPARATIVA</div>
    <div class="comparison-title" id="compTitle">PROMESSA EM CAMPANHA × REALIDADE NO DIÁRIO OFICIAL</div>
  </div>

  <div class="comparison-grid">
    <!-- Lado Esquerdo: Promessa / Posição A -->
    <div class="comp-col col-left">
      <div class="comp-col-header" id="compLeftHeader">PROMESSA (2024)</div>
      <div class="comp-highlight-text red-accent" id="compLeftHighlight">NENHUM NOVO IMPOSTO</div>
      <p class="comp-desc" id="compLeftDesc">Compromisso público firmado de não elevar impostos nem criar taxas durante o mandato.</p>
    </div>

    <!-- Divisor Central Dourado -->
    <div class="comp-divider">
      <div class="comp-divider-circle">VS</div>
    </div>

    <!-- Lado Direito: Fato / Posição B -->
    <div class="comp-col col-right">
      <div class="comp-col-header" id="compRightHeader">REALIDADE (2026)</div>
      <div class="comp-highlight-text gold-accent" id="compRightHighlight">+12% NO IPTU</div>
      <p class="comp-desc" id="compRightDesc">Decreto municipal aprovou atualização monetária retroativa com impacto imediato no carnê.</p>
    </div>
  </div>
</div>
```

---

## 4. Orquestração de Estados no `VDL_MOCKUP_ENGINE`

O objeto [`window.VDL_MOCKUP`](file:///j:/Arquivos%20Osmar/Hermes/web-jornal-vale-da-liberdade/references/youtube/mockup-browser/mockup-brower.html) é atualizado para gerenciar de forma limpa as saídas e entradas:

```javascript
// Tabela de métodos de transição por componente
const COMPONENT_TRANSITIONS = {
  "source": "transitionToBrowser",
  "x-post": "transitionToX",
  "quote": "transitionToQuote",
  "document": "transitionToDocument",
  "chart": "transitionToChart",
  "timeline": "transitionToTimeline",
  "comparison": "transitionToComparison"
};

// Reset universal de visibilidade antes de transicionar
hideAllCardsExcept(activeComponent) {
  const allCardIds = ["browserMockup", "xCard", "quoteCard", "documentCard", "dataChartCard", "timelineCard", "comparisonCard"];
  allCardIds.forEach(id => {
    const el = document.getElementById(id);
    if (el && id !== activeComponent) {
      gsap.to(el, { opacity: 0, duration: 0.35, onComplete: () => { el.style.visibility = "hidden"; el.style.display = "none"; } });
    }
  });
}
```
