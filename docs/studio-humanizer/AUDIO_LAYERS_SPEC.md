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

Os eventos Foley são divididos em **duas categorias de contexto**:

#### A) Speech-Concurrent (Ações de Mesa durante a Fala)
*Eventos que ocorrem preferencialmente durante ou colados na fala do locutor (simulando que ele consulta notas ou usa o computador enquanto fala).*

| Evento | Volume (rel. voz) | Frequência | Duração | Contexto |
|---|---|---|---|---|
| Clique de mouse (distante) | -35 a -40 dB | 1-3x por minuto | 0.1-0.3s | Durante fala |
| Teclas de teclado mecânico | -33 a -38 dB | 0.5-2x por minuto | 0.2-0.8s | Durante fala |
| Cadeira rangendo levemente | -36 a -42 dB | 0.2-0.5x por minuto | 0.5-1.5s | Fala ou transição |
| Papel sendo movido | -38 a -44 dB | 0.1-0.3x por minuto | 0.3-1.0s | Durante fala |
| Caneta/objeto na mesa | -37 a -43 dB | 0.1-0.2x por minuto | 0.1-0.3s | Durante fala |

#### B) Pause-Transition (Micro-Ações Humanas em Silêncios)
*Eventos que ocorrem **exclusivamente em pausas** entre blocos ou falas (nunca enquanto o apresentador pronuncia uma palavra).*

| Evento | Volume (rel. voz) | Frequência | Duração | Contexto |
|---|---|---|---|---|
| Gole de água | -36 a -42 dB | 0.1-0.2x por minuto | 0.4-0.8s | Pausa entre blocos |
| Limpar garganta / pigarro sutil | -38 a -44 dB | 0.05-0.1x por minuto | 0.2-0.5s | Pausa entre blocos |
| Respiração/suspiro sutil | -35 a -40 dB | 0.2-0.5x por minuto | 0.3-0.8s | Pausa entre frases |

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

1. **Contexto obrigatório**: `speech_concurrent` só toca onde há voz detectada; `pause_transition` só toca em silêncios/pausas RMS (nunca em cima de palavras).
2. **Zona de exclusão em troca de locutor**: Nenhum evento Foley dentro de 500ms de uma transição de locutor (se informada via `turn_boundaries`).
3. **Espaçamento mínimo**: 3 segundos entre eventos consecutivos de qualquer tipo.
4. **Variação de volume**: ±3 dB entre instâncias do mesmo tipo para evitar assinatura estática.
5. **Sem repetição consecutiva**: O mesmo arquivo de áudio não pode ser tocado 2x seguidas.
6. **Limite por minuto**: Máximo 5 eventos/minuto no total.

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
│   ├── respiracao_sutil_01.wav
│   ├── gole_agua_01.wav
│   └── limpar_garganta_01.wav
└── residencial/
    ├── passaro_01.wav
    ├── passaro_02.wav
    ├── passaro_03.wav
    ├── carro_distante_01.wav
    ├── carro_distante_02.wav
    ├── cachorro_distante_01.wav
    ├── porta_vizinho_01.wav
    ├── vento_janela_01.wav
    └── sirene_distante_01.wav
```

---

## Camada 3 — Cola Acústica (Reverb de Convolução)

### O que é
A voz TTS é 100% "seca" — sem nenhuma reflexão acústica. O reverb de convolução usa uma **Impulse Response (IR)** de estúdio com absorção acústica alta para integrar a voz ao espaço físico.

### Especificações Técnicas

| Parâmetro | Valor | Nota |
|---|---|---|
| Tipo | **Overlap-Add Convolução** (`scipy.signal.oaconvolve`) | Eficiência máxima de memória e CPU |
| IR recomendada | **Small Room / Studio** | Salas pequenas (RT60 < 0.35s) |
| Wet mix | **4%** (default) | Range: 3% a 6% |
| Pre-delay | **8-12 ms** | Separa a voz direta do reverb |
| HPF no reverb | **200 Hz** | Evita graves reverberados (enlameiam) |
| LPF no reverb | **8000 Hz** | Evita "shhh" metálico |
| Aplicação | **Apenas na voz** | Room tone e foley NUNCA recebem reverb |

---

## Diagrama de Fluxo de Sinal (Sem Noise Pumping)

```
                     VOZ TTS (44.1kHz)
                             │
                     ┌───────┴───────┐
                     │               ▼
                     │         [Reverb Conv.]
                     │         (oaconvolve 4% wet)
                     │         HPF 200Hz / LPF 8kHz
                     │               │
                     └───────┬───────┘
                             │ soma (wet mix)
                             ▼
                    [Voz com Cola Acústica]
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
       [Room Tone]    [Voz + Reverb]     [Foley]
       -30 dB rel.    (Voz Principal)    -35 dB rel.
       HPF 100Hz                         (Speech ou Pause)
       LPF 6kHz / Notch                  HPF 100Hz / LPF 8kHz
       Contínuo + Breathing              Esparso (2-5/min)
              │              │              │
              └──────────────┼──────────────┘
                             │ mixagem balanceada (headroom check)
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
