# ⚜️ VALE DA LIBERDADE — DIRETRIZ OFICIAL DE IDENTIDADE VISUAL BROADCAST
## Padrão Oficial: Light Editorial Studio (Design Claro)

**Data de Ratificação:** Setembro de 2026  
**Status:** Obrigatório (Mandatório para todas as gerações de vídeo BM e Diário)  
**Arquivos de Referência:**
- Template Principal: `references/youtube/mockup-browser/mockup-brower.html`
- Studio Interativo: `references/youtube/mockup-browser/demo-broadcast-studio.html`
- Pipeline de Gravação: `scripts/bm_mockup_video.py`

---

## 1. Princípio & Decisão Estratégica: Por que o Design Claro (Light Mode)?

Historicamente, muitos canais digitais recorrem a fundos pretos chapados ("dark mode de programador/hacker"), o que empobrece a percepção de valor do jornalismo e prejudica a experiência do espectador em TVs e monitores de alta definição.

Para os vídeos e transmissões do **Web Jornal Vale da Liberdade**, a diretriz permanente e obrigatória é o **Light Editorial Studio**:

1. **Autoridade de Telejornalismo Prime (TV Padrão Broadcast)**:
   - Inspirado no padrão visual de grandes referências de jornalismo diurno e vespertino (CNN Newsroom, Bloomberg Studio, BBC World News, GloboNews e Jornal Nacional).
   - Telões e gráficos claros, limpos e solenes transmitem credibilidade institucional, transparência e profissionalismo de ponta.

2. **Legibilidade Superior & Anti-Compressão H.264**:
   - Em telas de TV (a 3 ou 4 metros de distância) e telas de smartphones (sob luz ambiente intensa), o contraste de tipografia preta/grafite profundo sobre fundo branco/marfim oferece taxa de legibilidade 300% superior ao texto branco sobre fundo escuro.
   - A compressão de vídeo do YouTube (codec AVC/VP9/AV1) gera menos artefatos de "banding" em fundos claros iluminados do que em gradientes de preto puro.

3. **Harmonia Total com o Lower Third e o Portal**:
   - O Lower Third consagrado do Vale da Liberdade já utiliza o cartão principal em papel branco (`--lt-paper: #ffffff`) com manchetes em preto carvão (`#0a0a0a`) e frisos em ouro nobre (`#d4a017`).
   - O portal web (`valedaliberdade.com.br`) opera com tipografia editorial limpa e clara. A transição entre o browser do portal e os gráficos broadcast agora é visualmente contínua e sem quebras abruptas de contraste.

4. **Recorte Natural do Apresentador**:
   - Peter Albuquerque (o apresentador virtual do canal) fica posicionado no quadrante inferior esquerdo. O estúdio claro e iluminado cria uma separação óptica perfeita da silhueta do apresentador, dispensando luzes de recorte artificiais excessivas.

---

## 2. Paleta de Cores e Tokens Oficiais (Light Studio)

| Token | Cor Hex | Uso / Aplicação |
|---|---|---|
| `--scene-bg-start` | `#f8fafc` | Ponto mais iluminado do estúdio superior |
| `--scene-bg-mid` | `#edf2f7` | Transição do estúdio diurno |
| `--scene-bg-end` | `#e2e8f0` | Base do cenário de estúdio |
| `--studio-mesh` | `rgba(15, 23, 42, 0.04)` | Malha sutil de vetor/perspectiva de estúdio |
| `--orb-gold` | `rgba(212, 160, 23, 0.18)` | Luz difusa de estúdio dourada (suave) |
| `--orb-blue` | `rgba(59, 130, 246, 0.14)` | Luz difusa de estúdio azul-safira (suave) |
| `--card-paper` | `#ffffff` | Fundo principal de todos os broadcast cards |
| `--card-border` | `rgba(212, 160, 23, 0.45)` | Friso metálico dourado de contorno |
| `--card-shadow` | `0 35px 85px rgba(15, 23, 42, 0.18)` | Sombra física flutuante de profundidade |
| `--text-headline` | `#0a0e17` | Manchetes e declarações principais (preto editorial) |
| `--text-lead` | `#334155` | Subtítulos e parágrafos de contexto |
| `--text-muted` | `#64748b` | Metadados, datas e fontes |
| `--accent-gold` | `#d4a017` / `#b8860b` | Destaques da marca Vale da Liberdade |
| `--accent-red` | `#ef2633` / `#b91c1c` | Alertas, LIVE e carimbo forense digital |

---

### 3. Especificações dos Componentes no Padrão Claro

### 3.0. Barra Superior Institucional Universal (`.bcard-brand-header`)
- **Fundo**: Branco translúcido com leve transição off-white (`linear-gradient(90deg, #ffffff 0%, #f8fafc 50%, #ffffff 100%)`).
- **Friso de Topo**: Ouro nobre luminoso (`#d4a017` a `#f59e0b`).
- **Identidade do Canal**: Brasão dourado ⚜️ + `VALE DA LIBERDADE` em preto editorial (`#0a0e17`) e ouro (`#b8860b`).
- **Sub-Programa & Badges**: Grafite suave (`#475569`), com badges de status de alto contraste (ex.: selo carmim com fundo suave translúcido).

### 3.1. QuoteCard (`#quoteCard`) — Aspas Editoriais
- **Estrutura 100% Light Mode**:
  - **Coluna do Speaker (Esquerda, 380px)**: Fundo claro off-white (`linear-gradient(180deg, #f8fafc 0%, #edf2f7 100%)`) com borda direita dourada, avatar em anel metálico de ouro e nome do autor em preto profundo (`#0a0e17`, 28px, font-weight: 900) com cargo em âmbar nobre (`#8c6504`).
  - **Coluna da Citação (Direita, Flex)**: Fundo branco puro (`#ffffff`) com aspas esculturais douradas translúcidas (opacidade 8%), texto da declaração em preto editorial (`#0a0e17`, 46px), e rodapé limpo com a fonte auditada.

### 3.2. DocumentCard (`#documentCard`) — Decisão Judicial / Diário Oficial
- **Barra Superior Judicial (`.doc-top-bar`)**: Fundo claro (`#ffffff` a `#f8fafc`) com friso em ouro, badge de processo com fundo suave `#f1f5f9` e texto em preto carvão (`#0a0e17`), e tag do tribunal em preto solene.
- **Canvas Notarial**: Textura de pergaminho/papel solene claro (`#faf8f2`), com marca d'água da República em filigrana ultra sutil.
- **Grifo Fluorescente**: Sweep animado de marca-texto amarelo neon (`rgba(255, 234, 0, 0.52)`), guiando o olhar do público para o dispositivo da decisão.
- **Carimbo Forense Oficial**: Carimbo circular em vermelho carmim (`#b91c1c`) rotacionado a -7°, atestando autenticidade digital (PJe / STF / TJSC).

### 3.3. TimelineCard (`#timelineCard`) — Linha do Tempo / Cronologia
- **Barra Superior Clara**: Cabeçalho institucional claro com selo dourado `LINHA DO TEMPO`.
- **Dimensões Ampliadas para TV/Monitores**:
  - Área de trilho aumentada para 520px de altura.
  - Largura de cada nó expandida de 290px para **370px**.
  - Nós de data (`.timeline-card-date`) com fundo claro `#f8fafc`, borda ouro e fonte ampliada para **22px** (font-weight: 900).
  - Texto de descrição dos passos (`.timeline-card-desc`) com fonte ampliada para **21px** (preto grafite profundo `#0f172a`), garantindo leitura imediata e sem esforço em telas de TV.
  - Nós do eixo com anel dourado espesso de 32px e centro branco.

### 3.4. DataChartCard (`#dataChartCard`) — Impacto Econômico & Métricas
- **Padrão Bloomberg/FT**: Fundo do card em branco puro (`#ffffff`).
- **Hero Number Box**: Fundo off-white (`#f8fafc`) com número gigante de 88px em preto carvão (`#0a0c10`), prefixo/sufixo em ouro e tag de tendência com contraste perfeito (verde esmeralda ou vermelho carmim).
- **Barras Procedurais**: Trilhos em cinza claro (`#e2e8f0`) com barras em gradiente ouro/âmbar e números em ouro nobre.

### 3.5. ComparisonCard (`#comparisonCard`) — Antes x Depois / Fato x Versão
- **Fundo**: Branco puro (`#ffffff`).
- **Coluna A (Proposta/Antes)**: Azul cerúleo suave (`#f0f7ff`) com borda `#bae6fd` e número em azul profundo (`#0369a1`).
- **Coluna B (Realidade/Depois)**: Dourado solar suave (`#fefce8`) com borda `#fde047` e número em âmbar escuro (`#854d0e`).
- **Divisor Central "VS"**: Medalha circular metálica em azul-marinho com anel de ouro polido.

### 3.6. RecorteCard (`#recorteCard`) — Imprensa Histórica
- **Papel Jornal Tradicional**: Off-white linho (`#fdfcf9`) com bordas serrilhadas realistas e manchete serifada preta de jornal impresso de grande circulação.

---

## 4. Regras de Ouro para Novos Componentes

Qualquer novo componente ou layout inserido na suíte broadcast do Vale da Liberdade deve:
1. **Priorizar Sempre Fundo Claro/Branco**: Nunca utilizar caixas escuras inteiriças como corpo de texto corrido.
2. **Utilizar Azul-Marinho Apenas para Âncora/Contraste**: Fundo escuro (`#090e17` / `#131c2d`) deve ser restrito a barras de marca superiores, painéis laterais de orador ou divisores VS.
3. **Respeitar as Safe Zones**:
   - Margem Superior: Y: 0 a 36px livre.
   - Margem Inferior: Y: 890 a 1080px reservado estritamente para o Lower Third oficial.
   - Margem Esquerda: O apresentador Peter Albuquerque ocupa o quadrante inferior esquerdo até X: 480px / Y: 540 a 1080px; o card de broadcast flutua no plano intermediário sem colidir com o enquadramento principal.
