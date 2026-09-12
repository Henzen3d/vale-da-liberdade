# 🎚️ Regras de Mixagem — Studio Humanizer

> **Referência para calibração de volumes, EQ, reverb e comportamento geral da mixagem**

---

## 1. Hierarquia de Volumes (Fader Levels)

O áudio final tem 3 camadas. A **voz é sempre a referência (0 dB relativo)**:

```
  0 dB ─────────── VOZ (referência)
 -5 dB ─┐
-10 dB  │
-15 dB  │
-20 dB  │
-25 dB  │
-28 dB ─┤───────── ROOM TONE (máximo)
-30 dB ─┤───────── ROOM TONE (default recomendado)
-32 dB ─┤───────── FOLEY (máximo)
-35 dB ─┤───────── FOLEY (default recomendado)
-38 dB ─┤───────── ROOM TONE (mínimo)
-40 dB ─┤───────── FOLEY (mínimo)
-45 dB ─┘
```

### Regra de Ouro
> **Teste de mute**: Reproduza o áudio completo. Mute a faixa de ambiência subitamente. Se você NÃO perceber uma diferença imediata, o volume está correto. Se perceber um "buraco" sutil, está perfeito. Se perceber claramente, está alto demais.

---

## 2. Equalização (EQ)

### 2.1 EQ da Voz (já existe no pipeline)
O pipeline atual (`run_ffmpeg_chain_2pass`) já aplica:
- High-Pass: 80 Hz
- Compressor: -22 dB threshold, ratio 2.2
- Presence EQ: +2.5 dB @ 3500 Hz

**Não alterar**. O Studio Humanizer trabalha nas camadas de ambiência, não na voz.

### 2.2 EQ do Room Tone

```
Objetivo: Ambiência que NÃO compete com a voz

┌─────────────────────────────────────────────┐
│                                             │
│  HPF @ 100 Hz (12 dB/oct)                   │
│  ├── Remove rumble e graves que embolariam  │
│  │   com o highpass da voz                  │
│                                             │
│  LPF @ 6000 Hz (12 dB/oct)                  │
│  ├── Remove frequências brilhantes          │
│  │   (sibilância, detalhes que distraem)    │
│                                             │
│  Notch @ 2500-4000 Hz: -3 dB (Q=1.5)       │
│  ├── Abre espaço na faixa de presença       │
│  │   vocal (evita mascaramento)             │
│                                             │
└─────────────────────────────────────────────┘
```

### 2.3 EQ do Foley

```
Objetivo: Eventos audíveis mas NÃO intrusivos

┌─────────────────────────────────────────────┐
│                                             │
│  HPF @ 100 Hz (12 dB/oct)                   │
│  ├── Mesma base do room tone               │
│                                             │
│  LPF @ 8000 Hz (12 dB/oct)                  │
│  ├── Mais aberto que room tone (eventos     │
│  │   precisam de alguma definição)           │
│                                             │
│  Sem notch adicional                        │
│  ├── Eventos são tão esparsos que não       │
│  │   competem por frequência sustentada     │
│                                             │
└─────────────────────────────────────────────┘
```

### 2.4 EQ do Reverb (Cola Acústica)

```
Objetivo: Apenas "colar" a voz ao espaço, sem enlamejar

┌─────────────────────────────────────────────┐
│                                             │
│  HPF @ 200 Hz (12 dB/oct)                   │
│  ├── Mais agressivo que os outros layers    │
│  │   (graves reverberados = lama sonora)    │
│                                             │
│  LPF @ 8000 Hz (12 dB/oct)                  │
│  ├── Remove "shhh" metálico do reverb       │
│                                             │
│  Pre-delay: 8-12 ms                         │
│  ├── Mantém a inteligibilidade da voz       │
│  │   (ouvinte percebe a voz direta antes)   │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 3. Parâmetros do Reverb de Convolução

| Parâmetro | Valor Default | Range | Nota |
|---|---|---|---|
| `wet_mix` | 0.04 (4%) | 0.03 – 0.06 | Proporção sinal wet vs. dry |
| `pre_delay_ms` | 10 | 5 – 15 | Delay antes do reverb |
| `ir_hpf_hz` | 200 | 150 – 250 | HPF aplicado ao IR antes da convolução |
| `ir_lpf_hz` | 8000 | 6000 – 10000 | LPF aplicado ao IR antes da convolução |
| `decay_trim_db` | -60 | -40 – -80 | Cortar o IR quando cair abaixo deste nível |

### Como funciona a convolução FFT

```python
# Pseudocódigo simplificado
from scipy.signal import fftconvolve

# 1. Carregar IR e aplicar EQ
ir = load_wav("small_studio_01.wav")
ir = apply_hpf(ir, 200)
ir = apply_lpf(ir, 8000)
ir = trim_silence(ir, threshold=-60)

# 2. Convoluir voz com IR
reverb_signal = fftconvolve(voice_signal, ir, mode='full')
reverb_signal = reverb_signal[:len(voice_signal)]  # truncar

# 3. Mixar
output = voice_signal * (1 - wet_mix) + reverb_signal * wet_mix
```

---

## 4. Estratégia de Anti-Loop

O maior risco é o room tone revelar o ponto de loop. Estratégias:

### 4.1 Crossfade suave
```
Room Tone original:  [======A======][======A======]
                                ╲  ╱
Crossfaded:          [======A=====╲╱=====A======]
                           3-5s de crossfade
```

### 4.2 Variação de ganho (breathing)
Aplicar uma modulação sinusoidal muito lenta no volume:
```
gain(t) = base_gain + 1.5 * sin(2π * t / T)

onde T = 20-40 segundos (período de ondulação)
```

Isso simula variações naturais do ambiente (vento, pressão acústica).

### 4.3 Múltiplos takes
Ter ≥5 room tones e alternar entre episódios. Nunca repetir o mesmo tone em episódios consecutivos. O `studio_humanizer.yaml` mantém um `last_used` para rotação.

---

## 5. Regras de Coerência com o Nicho

### Canal Educativo / Tutorial de Tela
✅ Sons de escritório (mouse, teclado, cadeira)  
✅ Room tone de ambiente interno com computador  
❌ Sons urbanos/externos  
❌ Pássaros, carros, sirenes  

### Narrativa Pessoal / Bate-papo
✅ Sons urbanos sutis (filtrados por "janela fechada")  
✅ Room tone residencial  
✅ Pássaros e carros distantes  
❌ Sons de teclado (a menos que "trabalhando enquanto fala")  

### **Vale da Liberdade (nosso caso): Estúdio de Podcast Jornalístico**
✅ Room tone de estúdio/escritório  
✅ Teclado, mouse (jornalista trabalhando entre falas)  
✅ Cadeira, papel, caneta (micro-ações de mesa)  
✅ Ocasionalmente: respiração/gole de água (transições entre quadros)  
❌ Sons externos (mantém coerência de estúdio fechado)  
❌ Pássaros, trânsito (quebraria a ilusão de estúdio profissional)  

---

## 6. Tabela de Referência Rápida

| Layer | Volume | HPF | LPF | Duração | Posição |
|---|---|---|---|---|---|
| Room Tone | -30 dB | 100 Hz | 6 kHz | 100% contínuo | Toda a timeline |
| Foley | -35 dB | 100 Hz | 8 kHz | 0.1–6s por evento | Esparso, 2-5/min |
| Reverb | 4% wet | 200 Hz | 8 kHz | Cauda do IR | Sobre a voz apenas |
| Voz | 0 dB (ref) | 80 Hz | — | — | — |
