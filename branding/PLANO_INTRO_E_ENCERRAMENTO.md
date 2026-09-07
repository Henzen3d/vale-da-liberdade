# 🎬 Plano de Integração: Música de Intro e Vídeo de Encerramento (Outro)

Este documento detalha o planejamento técnico, fluxos de áudio e vídeo, e a arquitetura para inclusão automática da **trilha de abertura** e do **vídeo de encerramento com tela final do YouTube**.

---

## 1. Estrutura de Pastas e Localização dos Arquivos

A pasta canônica e mais indicada em todo o projeto é **`branding/`**.

### Por que `branding/` e não `audio/` ou `output/`?
- **`audio/` (raiz):** Contém mais de 360 arquivos de episódios diários dinâmicos e temporários (`2026-xx-xx.mp3`). Misturar vinhetas fixas aqui gera poluição e risco de exclusão por rotinas de limpeza.
- **`branding/`:** Já é o diretório oficial do canal para identidade permanente (logos, vinhetas, lower-thirds). Scripts existentes (`youtube_video_generator.py`, `faceless_compose.py`) já apontam nativamente para cá.

### Estrutura Criada:
```text
branding/
├── audio/
│   ├── intro/                 ← Coloque aqui a música de abertura (ex: intro_tema.wav ou .mp3)
│   └── outro/                 ← Coloque aqui a música de fundo do encerramento (ex: outro_tema.wav ou .mp3)
├── encerramento/
│   ├── gravacoes/             ← Vídeos brutos em tela cheia gravados pelo apresentador (Peter/Osmar)
│   ├── templates/             ← Background 1920x1080 com layout/molduras para cards do YouTube
│   └── outro_final.mp4        ← Vídeo montado final (ou gerado automaticamente pelo pipeline)
├── PLANO_INTRO_E_ENCERRAMENTO.md   ← Este plano de engenharia
├── ROTEIROS_ENCERRAMENTO.md        ← Roteiros de 10s a 30s prontos para gravação
└── GUIA_END_SCREEN_YOUTUBE.md      ← Medidas em pixels e mapa do layout 1/4 para o YouTube
```

---

## 2. Formato: MP3 ou WAV?

| Formato | Avaliação | Recomendação |
|---|---|---|
| **WAV (48 kHz, 16 ou 24 bits)** | ⭐ **Ideal / Preferencial** | Formato padrão da indústria de vídeo/broadcast. Não possui perdas de compressão e garante **precisão milimétrica de amostragem** (sample-accurate), sem os atrasos de cabeçalho (*padding delay*) típicos do MP3. |
| **MP3 (192 a 320 kbps)** | ✔️ **Totalmente Suportado** | Pode usar perfeitamente caso você já tenha o arquivo em MP3. O FFmpeg decodifica o MP3 para PCM bruto na memória antes de aplicar qualquer filtro de ducking ou fade. |

> **Recomendação Prática:** Se você estiver exportando do seu software de edição/DAW (Reaper, Premiere, Audacity, etc.), exporte em **WAV 48.000 Hz, Stereo**. Se já baixou uma trilha pronta em MP3 de boa qualidade, pode usar diretamente sem precisar converter antes.

---

## 3. Dinâmica e Automação da Música de Intro

### O Comportamento Solicitado:
- A música começa **1.5s antes** da fala.
- Quando a fala começa, a música baixa suavemente (**ducking**).
- Continua tocando até **7s**, fazendo fade-out nos segundos **6s a 7s**.

### Linha do Tempo da Abertura:
```text
Tempo:    0.0s        1.5s          2.2s                    6.0s         7.0s
Música:   [ 100% Vol ]  \ (Ducking) \ [ 18% Cama Sonora ]   \ (Fade Out) \ [ Silêncio ]
Voz:      [ Silêncio ]  [ Início da locução: "Bom dia, Vale da Liberdade..." ]
```

### Como o FFmpeg implementa isso:
```bash
# Exemplo do filtro de áudio equivalente:
ffmpeg -i intro_tema.wav -i episodio_voz.wav -filter_complex \
"[0:a]volume=enable='between(t,0,1.5)':volume=1.0, \
 volume=enable='between(t,1.5,6.0)':volume=0.18, \
 afade=t=out:st=6.0:d=1.0[bgm]; \
 [1:a]adelay=1500|1500[voz]; \
 [bgm][voz]amix=inputs=2:duration=longest"
```

---

## 4. Vídeo de Encerramento e Enquadramento 1/4 (End Screen do YouTube)

### O Problema do Enquadramento:
O YouTube permite inserir até 4 elementos na Tela Final (cards de vídeo, playlist e botão de inscrever-se) nos **últimos 20 segundos** do vídeo. Se o apresentador estiver centralizado em tela cheia, os cards cobrem o rosto dele.

### Duas Formas de Resolver:

#### Opção A — Pré-renderizado pelo Editor (Mais simples de operar):
- Você cria no seu editor de vídeo um template 1920×1080 com a arte do canal.
- Posiciona o apresentador em um quadro no canto esquerdo (ocupando aprox. 1/4 da tela) e deixa o lado direito livre para os cards.
- Exporta como `branding/outro.mp4` de 10s a 20s (tempo ideal para manter retenção alta no YouTube). O sistema apenas concatena no fim do vídeo gerado.

#### Opção B — Montagem Automática pelo Sistema (Mais flexível e escalável):
- Você grava vários vídeos do apresentador falando em **tela cheia normal (1920×1080)** e salva em `branding/encerramento/gravacoes/`.
- Mantemos um template de fundo fixo em `branding/encerramento/templates/fundo_cards.png` (ou `.mp4`).
- O script FFmpeg faz:
  1. Redimensiona o vídeo do apresentador para 1/4 da tela (`scale=854:480` ou `640:360`).
  2. Aplica borda suave ou cantos arredondados.
  3. Sobrepõe (`overlay=80:160`) sobre o fundo institucional.
  4. Deixa o quadrante superior e inferior direitos 100% livres para os cards do YouTube.
  5. Pode até **sortear aleatoriamente** uma gravação diferente para cada dia!

---

## 5. Áudio de Encerramento com Auto-Ducking (Voz vs Trilha)

No encerramento, queremos que a música toque enquanto o apresentador fala seu texto de encerramento (10s a 17s), com a música de fundo mais baixa, e assim que ele termina de falar, a música **aumenta de volume** nos últimos 2 a 3 segundos de vídeo (fechando no teto de 20s).

### Como o sistema faz isso automaticamente:
Utiliza-se o filtro nativo **`sidechaincompress`** ou detecção de envelope do FFmpeg:
1. O áudio do apresentador entra como canal de controle (*sidechain*).
2. Enquanto o apresentador fala: o compressor atenua a trilha musical para **-18 dB** (volume sutil, não cobre a voz).
3. Quando o apresentador encerra a fala (*"Até a próxima edição!"*): a atenuação cessa automaticamente e a música sobe para **0 dB** (volume cheio), encerrando o vídeo com energia e impacto antes do fade-out.

---

## 6. Alinhamento Editorial: Evitando Redundância com o Áudio Atual

Hoje, o roteiro do episódio termina com Peter e Ricardo se despedindo editorialmente no áudio do dia. Para não ficar redundante com o vídeo final, dividimos as funções:

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. Áudio do Episódio (Despedida Editorial - 5 a 10s)        │
│    Peter/Ricardo fecham as notícias do dia:                 │
│    "Fechamos aqui o giro de notícias de hoje. Para mais     │
│    detalhes e matérias completas, fique com a gente!"       │
└──────────────────────────────┬──────────────────────────────┘
                               ▼ (Transição fluida)
┌─────────────────────────────────────────────────────────────┐
│ 2. Vídeo de Encerramento / Outro Bumper (10 a 20s)          │
│    Ação de Comunidade & YouTube CTA:                        │
│    Focado exclusivamente em:                                │
│    - Clicar nos vídeos que estão na tela                    │
│    - Inscrever-se no canal e curtir                         │
│    - WhatsApp / Portal news.mob.tec.br                      │
└─────────────────────────────────────────────────────────────┘
```
Dessa forma, o ouvinte não sente repetição — sente que uma coisa é o término das notícias e a outra é o fechamento interativo da plataforma.
