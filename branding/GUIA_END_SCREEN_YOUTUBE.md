# 📐 Guia Técnico: Layout 1/4 e Tela Final do YouTube (End Screen)

Este documento contém as dimensões exatas em pixels, diagramação visual e regras do YouTube para criar o layout de encerramento aproveitando o enquadramento de **1/4 de tela**.

---

## 1. Regras Oficiais da Tela Final do YouTube (End Screen)
- **Janela de Exibição:** Só pode ser inserida nos **últimos 20 segundos** do vídeo (duração mínima permitida pelo YouTube: 5 segundos; recomendada: 10 a 20 segundos).
- **Proporção:** 16:9 obrigatória (Canvas padrão: 1920×1080 ou 1280×720).
- **Elementos Permitidos:**
  - Até 2 Cards de Vídeo/Playlist (retângulos 16:9).
  - 1 Botão de Inscrição no Canal (círculo com a foto do canal).
  - 1 Link externo ou canal parceiro (opcional).

---

## 2. Mapa do Canvas 1920×1080 (Full HD)

```text
0,0 ───────────────────────────────────────────────────────────── 1920,0
│                                                                │
│   ┌──────────────────────────┐    ┌────────────────────────┐   │
│   │                          │    │  CARD DO YOUTUBE 1     │   │
│   │   VÍDEO DO APRESENTADOR  │    │  (Melhor p/ Espectador)│   │
│   │   (Enquadramento 1/4)    │    │  Dimensões: 608 x 342  │   │
│   │   Dimensões: 854 x 480   │    │  X: 1200 | Y: 100      │   │
│   │   ou 640 x 360           │    └────────────────────────┘   │
│   │   Posição: X:80, Y:100   │                                 │
│   └──────────────────────────┘    ┌────────────────────────┐   │
│                                   │  CARD DO YOUTUBE 2     │   │
│   ┌──────────────────────────┐    │  (Vídeo Mais Recente)  │   │
│   │   🔘 INSCREVA-SE         │    │  Dimensões: 608 x 342  │   │
│   │   Botão Circular         │    │  X: 1200 | Y: 520      │   │
│   │   Diâmetro: ~180px       │    └────────────────────────┘   │
│   │   X: 420 | Y: 680        │                                 │
│   └──────────────────────────┘                                 │
│                                                                │
│   [BARRA INFERIOR / IDENTIDADE: Logo Vale da Liberdade | Web]  │
0,1080 ────────────────────────────────────────────────────────── 1920,1080
```

---

## 3. Coordenadas Exatas para Produção / FFmpeg

### A. Para Canvas 1920×1080 (Full HD):
- **Vídeo do Apresentador (Janela 1/4):**
  - Largura: `854 px` | Altura: `480 px` (ou `640 x 360 px`)
  - Margem Esquerda (`X`): `80 px`
  - Margem Superior (`Y`): `100 px`
- **Card YouTube 1 (Superior Direito):**
  - Largura: `608 px` | Altura: `342 px`
  - Posição no YouTube Studio: Alinhado no topo direito (`X: 1200, Y: 100`).
- **Card YouTube 2 (Inferior Direito):**
  - Largura: `608 px` | Altura: `342 px`
  - Posição no YouTube Studio: Alinhado abaixo do Card 1 (`X: 1200, Y: 520`).
- **Botão Inscrever-se:**
  - Tamanho: `180 x 180 px` (área circular)
  - Posição: Alinhado abaixo da janela do apresentador.

---

## 4. Como Gravar os Vídeos de Encerramento

Você **NÃO** precisa se preocupar em recortar ou ficar espremido no canto durante a gravação!

1. **Grave normalmente em tela cheia:**
   - Celular ou câmera na horizontal (1920×1080).
   - Enquadramento em plano médio (cabeça e tronco visíveis).
   - Grave seus takes falando os roteiros de encerramento (10s a 20s).
2. **Salve o arquivo bruto:**
   - Coloque o vídeo em: `branding/encerramento/gravacoes/outro_take01.mp4`.
3. **O Sistema / FFmpeg faz o trabalho pesado:**
   - Redimensiona o vídeo para a janela (`scale=854:480`).
   - Aplica os cantos arredondados ou borda fina elegante.
   - Posiciona sobre o fundo institucional com os espaços já reservados para os cards do YouTube.
