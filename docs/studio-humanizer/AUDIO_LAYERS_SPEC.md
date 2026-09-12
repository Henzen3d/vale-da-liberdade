# 🔊 Especificação das 3 Camadas de Áudio

> **Referência técnica para implementação do `studio_humanizer.py`**

---

## Camada 1 — Room Tone (Ruído de Sala Contínuo)

### O que é
O Room Tone é o "silêncio" de um ambiente real. Todo cômodo tem um som residual composto por:
- Ventoinha de computador/ar-condicionado
- Vibração de geladeira distante
- Zumbido elétrico de lâmpadas e equipamentos (60 Hz / 120 Hz)
- Sopro de vento leve em janelas

### Por que é o mais importante
É a base que **elimina o silêncio digital absoluto**. Sem room tone, cada pausa entre frases da IA cria um "buraco negro" acústico que o cérebro identifica imediatamente como artificial.

### Especificações Técnicas

| Parâmetro | Valor | Nota |
|---|---|---|
| Nível (relativo à voz) | **-30 dB** (default) | Range: -28 dB a -38 dB |
| Duração | **Contínuo** (loop suave) | Cobre 100% da timeline |
| Crossfade de loop | **3-5 segundos** | Elimina o "click" da repetição |
| EQ — High-Pass | **100 Hz** (12 dB/oct) | Evita embolar com graves da voz |
| EQ — Low-Pass | **6000 Hz** (12 dB/oct) | Evita brilho que compita com a voz |
| Fade-in | **2 segundos** | Entrada suave |
| Fade-out | **3 segundos** | Saída gradual |
| Variação de ganho | **±1.5 dB** (automática) | Ondulação lenta (15-30s) para evitar estática |

### Tipos de Room Tone recomendados

```
audio/ambience/room-tones/
├── escritorio_ventilador_leve.wav     # ar condicionado/ventilador suave
├── escritorio_silencio_eletrico.wav   # apenas hum elétrico sutil
├── sala_residencial_noite.wav         # ambiente noturno calmo
├── sala_residencial_dia.wav           # com leve ruído urbano filtrado
├── estudio_podcast.wav                # tratamento acústico real
└── sala_com_janela_fechada.wav        # urbano bem amortecido
```

---

## Camada 2 — Foley Sutil (Eventos Incidentais)

### O que é
Sons discretos e esporádicos que simulam a presença física do apresentador em um espaço real. São "micro-eventos" que acontecem em segundo plano.

### Perfil: Escritório / Estúdio de Podcast

| Evento | Volume (rel. voz) | Frequência | Duração |
|---|---|---|---|
| Clique de mouse (distante) | -35 a -40 dB | 1-3x por minuto | 0.1-0.3s |
| Teclas de teclado mecânico | -33 a -38 dB | 0.5-2x por minuto | 0.2-0.8s |
| Cadeira rangendo levemente | -36 a -42 dB | 0.2-0.5x por minuto | 0.5-1.5s |
| Papel sendo movido | -38 a -44 dB | 0.1-0.3x por minuto | 0.3-1.0s |
| Caneta/objeto na mesa | -37 a -43 dB | 0.1-0.2x por minuto | 0.1-0.3s |
| Respiração/suspiro sutil | -34 a -40 dB | 0.3-0.8x por minuto | 0.3-0.8s |

### Perfil: Residencial / Janela Aberta

| Evento | Volume (rel. voz) | Frequência | Duração |
|---|---|---|---|
| Pássaro cantando (distante) | -32 a -38 dB | 0.3-1x por minuto | 1.0-3.0s |
| Carro passando (distante) | -35 a -42 dB | 0.2-0.5x por minuto | 2.0-5.0s |
| Cachorro latindo (bem distante) | -40 a -48 dB | 0.05-0.15x por min | 0.5-2.0s |
| Porta batendo (vizinho) | -42 a -50 dB | 0.02-0.08x por min | 0.3-0.8s |
| Vento suave na janela | -36 a -44 dB | 0.1-0.3x por minuto | 2.0-6.0s |
| Ambulância/sirene (distante) | -44 a -52 dB | 0.01-0.03x por min | 3.0-8.0s |

### Regras de Posicionamento

1. **Zona de exclusão**: Nenhum evento Foley dentro de 500ms de uma troca de locutor
2. **Espaçamento mínimo**: 3 segundos entre eventos consecutivos
3. **Variação de volume**: ±3 dB entre instâncias do mesmo tipo
4. **Sem repetição consecutiva**: O mesmo sample não pode ser usado 2x seguidas
5. **Limite por minuto**: Máximo 6 eventos/minuto (evitar "poluição sonora")
6. **Correlação com fala**: Eventos de teclado/mouse devem ocorrer preferencialmente durante falas longas (como se o apresentador estivesse trabalhando enquanto fala)

### Estrutura de arquivos

```
audio/ambience/foley/
├── escritorio/
│   ├── mouse_click_01.wav
│   ├── mouse_click_02.wav
│   ├── mouse_click_03.wav         # 3+ variações evitam repetição
│   ├── teclado_curto_01.wav
│   ├── teclado_curto_02.wav
│   ├── teclado_longo_01.wav
│   ├── cadeira_range_01.wav
│   ├── cadeira_range_02.wav
│   ├── papel_01.wav
│   ├── caneta_mesa_01.wav
│   └── respiracao_sutil_01.wav
├── residencial/
│   ├── passaro_01.wav
│   ├── passaro_02.wav
│   ├── passaro_03.wav
│   ├── carro_distante_01.wav
│   ├── carro_distante_02.wav
│   ├── cachorro_distante_01.wav
│   ├── porta_vizinho_01.wav
│   ├── vento_janela_01.wav
│   └── sirene_distante_01.wav
└── transicoes/
    ├── gole_agua_01.wav            # entre quadros
    └── limpar_garganta_01.wav      # muito raro, muito baixo
```

---

## Camada 3 — Cola Acústica (Reverb de Convolução)

### O que é
A voz TTS é 100% "seca" — sem nenhuma reflexão acústica. Isso faz com que a voz pareça "flutuar" desconectada do ambiente, especialmente quando há room tone embaixo.

O reverb de convolução usa uma **Impulse Response (IR)** gravada em um ambiente real para simular as reflexões sonoras daquele espaço.

### Especificações Técnicas

| Parâmetro | Valor | Nota |
|---|---|---|
| Tipo | **Convolução FFT** | Não usar reverb algorítmico (menos realista) |
| IR recomendada | **Small Room / Studio** | Salas pequenas (RT60 < 0.4s) |
| Wet mix | **4%** (default) | Range: 3% a 6% |
| Pre-delay | **8-12 ms** | Separa a voz direta do reverb |
| HPF no reverb | **200 Hz** | Evita graves reverberados (enlameiam) |
| LPF no reverb | **8000 Hz** | Evita "shhh" nas reflexões |
| Aplicação | **Apenas na voz** | Room tone e foley NÃO recebem reverb |

### Impulse Responses recomendadas

```
audio/impulse-responses/
├── small_studio_01.wav          # estúdio de podcast ~15m²
├── small_studio_02.wav          # quarto/home office ~12m²
├── small_room_carpeted.wav      # sala com carpete (absorção alta)
├── office_medium.wav            # escritório médio ~25m²
└── vocal_booth_subtle.wav       # cabine vocal (reverb mínimo, 0.15s RT60)
```

### Fontes de IRs gratuitas (CC0 / permissive)

1. **OpenAIR** (University of York) — academia, licenças abertas
2. **EchoThief** — IRs de ambientes reais, CC
3. **Voxengo** — "Voxengo Impulse Responses" (free pack)
4. **Fokke van Saane** — Free IR collection
5. **Gravar a própria** — Estourar um balão em um cômodo e gravar o decay (método DIY)

---

## Diagrama de Fluxo de Sinal

```
                     VOZ TTS (24kHz → 44.1kHz)
                              │
                     ┌────────┴────────┐
                     │                 │
                     ▼                 ▼
              [Voz Seca]        [Reverb Conv.]
              (100% dry)         (wet 3-6%)
                     │                 │
                     │    HPF 200Hz    │
                     │    LPF 8kHz     │
                     │                 │
                     └────────┬────────┘
                              │ mix
                              ▼
                     [Voz com Cola]
                              │
                 ┌────────────┼────────────┐
                 │            │            │
                 ▼            ▼            ▼
          [Room Tone]   [Voz + Reverb]  [Foley]
          -30 dB rel.                   -35 dB rel.
          HPF 100Hz                     HPF 100Hz
          LPF 6kHz                      LPF 8kHz
          Contínuo                      Esparso
                 │            │            │
                 └────────────┼────────────┘
                              │ sum
                              ▼
                     [WAV Humanizado]
                              │
                              ▼
                  run_ffmpeg_chain_2pass()
                  (loudnorm + compressor)
                              │
                              ▼
                      [MP3 Final 192k]
```
