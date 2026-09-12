# 📋 Plano Mestre — Humanização do Estúdio Virtual

> **Codinome:** Studio Humanizer  
> **Modelo:** Híbrido (pré-processamento único + montagem por episódio)  
> **Pipeline alvo:** `generate_gemini_tts_multi.py` → `run_ffmpeg_chain_2pass()` + `bm_mockup_video.py`  
> **Impacto:** Todos os vídeos BM e episódios do Jornal Diário publicados no YouTube

---

## 1. Visão Geral da Arquitetura — Modelo Híbrido

O sistema opera em **duas fases distintas**: uma de preparo (executada uma vez) e outra de montagem (executada por episódio).

```
╔══════════════════════════════════════════════════════════════════════╗
║  FASE 0: PREPARE (executado UMA VEZ ou quando a biblioteca muda)   ║
║                                                                      ║
║  studio_humanizer.py prepare                                         ║
║                                                                      ║
║  ┌─────────────────┐   ┌───────────────────┐   ┌──────────────────┐ ║
║  │ Room Tones crus  │   │ Foley sounds crus │   │ IRs de reverb    │ ║
║  │ (downloads CC0)  │   │ (downloads CC0)   │   │ (downloads CC0)  │ ║
║  └────────┬────────┘   └────────┬──────────┘   └────────┬─────────┘ ║
║           │                     │                        │           ║
║           ▼                     ▼                        ▼           ║
║  ┌─────────────────┐   ┌───────────────────┐   ┌──────────────────┐ ║
║  │ EQ + Normalize   │   │ Normalize + Trim  │   │ EQ + Trim decay │ ║
║  │ HPF 100 / LPF 6k │   │ Peak -6 dBFS     │   │ HPF 200 / LPF 8k│ ║
║  │ Notch 3kHz -3dB  │   │ DC offset remove  │   │ Truncar a -60dB │ ║
║  └────────┬────────┘   └────────┬──────────┘   └────────┬─────────┘ ║
║           │                     │                        │           ║
║           ▼                     ▼                        ▼           ║
║  ┌─────────────────────────────────────────────────────────────────┐ ║
║  │            audio/ambience/prepared/                              │ ║
║  │  ├── room-tones/   (EQ-ados, normalizados, prontos)            │ ║
║  │  ├── foley/        (normalizados, trimados, prontos)            │ ║
║  │  └── ir/           (EQ-ados, truncados, prontos)                │ ║
║  └─────────────────────────────────────────────────────────────────┘ ║
║                                                                      ║
║  Tempo: ~30-60 segundos (uma vez)                                    ║
╚══════════════════════════════════════════════════════════════════════╝

                                 │
                   Arquivos preparados ficam em disco
                   (reutilizados em TODOS os episódios)
                                 │
                                 ▼

╔══════════════════════════════════════════════════════════════════════╗
║  PIPELINE POR EPISÓDIO (custo: ~2-3 segundos extras)               ║
║                                                                      ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │  PIPELINE ATUAL (sem mudança)                                │   ║
║  │  Gemini TTS → chunks WAV → concatenação → WAV completo      │   ║
║  └──────────────────────────────┬───────────────────────────────┘   ║
║                                 │                                    ║
║                                 ▼                                    ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │  studio_humanizer.humanize() — MONTAGEM RÁPIDA               │   ║
║  │                                                               │   ║
║  │  Usa os arquivos JÁ PREPARADOS de audio/ambience/prepared/:  │   ║
║  │                                                               │   ║
║  │  1. Seleciona room tone (rotação) → loop + crossfade          │   ║
║  │  2. Convolui voz com IR preparado → mix 4% wet               │   ║
║  │  3. Distribui foley (posições ALEATÓRIAS fresh)               │   ║
║  │  4. Soma tudo → WAV humanizado                                │   ║
║  │                                                               │   ║
║  │  ⚡ Sem EQ/normalização pesada (já feito no prepare)          │   ║
║  └──────────────────────────────┬───────────────────────────────┘   ║
║                                 │                                    ║
║                                 ▼                                    ║
║  ┌──────────────────────────────────────────────────────────────┐   ║
║  │  PIPELINE ATUAL (sem mudança)                                │   ║
║  │  WAV humanizado → run_ffmpeg_chain_2pass() → MP3 final       │   ║
║  └──────────────────────────────────────────────────────────────┘   ║
║                                                                      ║
║  Tempo extra por episódio: ~2-3 segundos                             ║
╚══════════════════════════════════════════════════════════════════════╝
```

### O que é pré-processado (uma vez) vs. fresh (por episódio)

| Componente | Prepare (uma vez) | Episódio (fresh) |
|---|---|---|
| **Room Tone EQ** | ✅ HPF, LPF, notch já aplicados | — |
| **Room Tone seleção** | — | ✅ Qual tone usar (rotação) |
| **Room Tone loop** | — | ✅ Corte na duração certa + crossfade |
| **Foley normalização** | ✅ Peak, trim, DC offset | — |
| **Foley posicionamento** | — | ✅ Posições aleatórias únicas |
| **Foley seleção** | — | ✅ Quais sons, com pesos |
| **IR EQ + trim** | ✅ HPF, LPF, decay truncado | — |
| **Reverb convolução** | — | ✅ FFT convolve voz com IR preparado |
| **Mix final** | — | ✅ Soma das 3 camadas |

### Vantagens do modelo híbrido

1. **Custo por episódio mínimo** (~2-3s vs. ~5-8s sem pré-processamento)
2. **Consistência sonora** — mesmos sons preparados = mesmo "caráter" do estúdio
3. **Variação natural** — posicionamento aleatório garante unicidade
4. **Fácil manutenção** — troca de sons = rodar `prepare` novamente

---

## 2. Componentes do Sistema

### 2.1 Prepare Command (`studio_humanizer.py prepare`)

Executa uma vez (ou sempre que a biblioteca de sons mudar):

- Lê todos os arquivos brutos de `audio/ambience/raw/`
- Aplica EQ, normalização, trim e DC offset removal
- Salva versões processadas em `audio/ambience/prepared/`
- Gera `audio/ambience/prepared/_manifest.json` com metadados
- Tempo de execução: ~30-60 segundos

### 2.2 Room Tone Assembler (por episódio)
- Seleciona um room tone **já preparado** (sem EQ adicional)
- Faz loop com crossfade para cobrir a duração do episódio
- Aplica fade-in (2s) e fade-out (3s)
- Aplica "breathing" (ondulação de ganho ±1.5 dB)
- Ajusta volume para -30 dB relativo à voz

### 2.3 Foley Event Scheduler (por episódio)
- Carrega sons **já preparados** (sem normalização adicional)
- Distribui eventos aleatórios ao longo da timeline
- Densidade: 2-5 eventos por minuto (configurável)
- Respeita "zonas de silêncio" — não coloca eventos sobre pausas
- Cada episódio tem um seed aleatório diferente

### 2.4 Acoustic Glue — Reverb (por episódio)
- Carrega IR **já preparado** (EQ e trim já aplicados)
- Convoluição FFT rápida (scipy — ~0.5s para 15 min de áudio)
- Wet mix: 4% (default)

### 2.5 Mixer Final (por episódio)
- Soma as 3 faixas (voz + reverb, room tone, foley) em PCM
- Exporta WAV 44.1 kHz 16-bit mono

---

## 3. Fases de Implementação

### Fase 1 — Fundação + Prepare (Semana 1)
- [ ] Criar estrutura de diretórios (`audio/ambience/raw/`, `audio/ambience/prepared/`)
- [ ] Criar `config/studio_humanizer.yaml` com todos os parâmetros
- [ ] Criar `scripts/studio_humanizer.py` com classe principal + comando `prepare`
- [ ] Implementar pipeline de pré-processamento (EQ, normalização, trim)
- [ ] Implementar geração do `_manifest.json`
- [ ] Curar biblioteca inicial de sons (download de fontes CC0)
- [ ] Testes unitários do prepare

### Fase 2 — Montagem por Episódio (Semana 2)
- [ ] Implementar Room Tone Assembler (loop + crossfade + breathing)
- [ ] Implementar Foley Event Scheduler (distribuição temporal com seeds)
- [ ] Implementar Reverb de Convolução (usando IR preparado)
- [ ] Implementar Mixer Final
- [ ] Testes com episódios reais

### Fase 3 — Integração e Polimento (Semana 3)
- [ ] Integrar com `generate_gemini_tts_multi.py` (~8 linhas)
- [ ] A/B testing com 5 episódios (com vs. sem humanização)
- [ ] Calibração fina de volumes e frequências
- [ ] Flag `--no-humanize` para bypass em emergências
- [ ] Detecção automática: se `prepared/` não existe, rodar prepare automaticamente

### Fase 4 — Automação Completa (Semana 4)
- [ ] Rotação automática de ambiências (state file com `last_used`)
- [ ] Logging e métricas (manifesto JSON por episódio)
- [ ] Watcher: detectar mudanças em `raw/` e re-executar prepare
- [ ] Monitoramento: comparar métricas de retenção YouTube antes/depois

---

## 4. Dependências Técnicas

| Dependência | Uso | Status |
|---|---|---|
| `numpy` | Manipulação de arrays PCM, mixing | ✅ Já instalado |
| `scipy` | FFT convolution (reverb), filtros de EQ | ✅ Já instalado |
| `soundfile` / `wave` | Leitura/escrita WAV | ✅ Já instalado |
| `ffmpeg` | Pós-processamento final (loudnorm) | ✅ Já instalado |
| Sons de ambiência (CC0) | Room tones + Foley library | ⬜ Curar/baixar |
| IRs de reverb (CC0) | Impulse responses de salas | ⬜ Curar/baixar |

---

## 5. Estrutura de Diretórios

```
audio/ambience/
├── raw/                         # ← Arquivos BRUTOS (download direto)
│   ├── room-tones/              #    Não processados — fonte original
│   │   ├── estudio_podcast_01.wav
│   │   └── ...
│   ├── foley/
│   │   ├── escritorio/
│   │   │   ├── mouse_click_01.wav
│   │   │   └── ...
│   │   └── residencial/
│   │       └── ...
│   └── impulse-responses/
│       ├── small_studio_01.wav
│       └── ...
│
├── prepared/                    # ← Gerado pelo comando PREPARE
│   ├── _manifest.json           #    Metadados, checksums, timestamps
│   ├── room-tones/              #    EQ-ados, normalizados
│   │   ├── estudio_podcast_01.wav
│   │   └── ...
│   ├── foley/                   #    Normalizados, trimados
│   │   ├── escritorio/
│   │   │   ├── mouse_click_01.wav
│   │   │   └── ...
│   │   └── residencial/
│   │       └── ...
│   └── ir/                      #    EQ-ados, decay truncado
│       ├── small_studio_01.wav
│       └── ...
│
└── README.md                    # Licenças e fontes
```

---

## 6. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Ambiência perceptível demais | Média | Alto | Volume conservador (-32 dB default) + revisão A/B |
| Loop de room tone detectável | Alta | Médio | Múltiplos tones (>5), crossfade, variação de ganho |
| Foley em timing ruim (sobre fala) | Média | Alto | Análise de silêncios via RMS + zona de exclusão |
| Reverb torna voz "embaçada" | Baixa | Alto | Wet mix ≤ 6%, pré-delay 10ms, HPF no reverb |
| `prepared/` desatualizado | Baixa | Médio | Checksum dos raw → alerta se mudou sem re-prepare |
| Aumento de tempo de processamento | **Muito baixa** | Baixo | Prepare é offline; montagem ~2-3s (leitura + soma) |

---

## 7. Métricas de Sucesso

1. **Performance**: Montagem por episódio ≤ 3 segundos (benchmark target)
2. **Teste cego**: 3 pessoas não sabem qual episódio tem ambiência. Se ≥2 preferirem o humanizado → sucesso
3. **Retenção YouTube**: Comparar "Average View Duration" dos vídeos humanizados vs. anteriores
4. **Comentários**: Monitorar se alguém menciona "voz de IA" nos vídeos humanizados (redução = sucesso)
5. **Transparência**: Em nenhum momento a ambiência deve ser conscientemente perceptível
