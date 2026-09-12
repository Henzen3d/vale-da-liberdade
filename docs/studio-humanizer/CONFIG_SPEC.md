# ⚙️ Especificação do Config — `studio_humanizer.yaml`

> **Arquivo de configuração completo com todos os parâmetros do Studio Humanizer**  
> **Modelo:** Híbrido (prepare offline + montagem por episódio)  
> **Localização:** `config/studio_humanizer.yaml`

---

## Arquivo Completo Anotado

```yaml
# ═══════════════════════════════════════════════════════════════
# Studio Humanizer — Configuração
# Humanização do estúdio virtual do Vale da Liberdade
# ═══════════════════════════════════════════════════════════════

# Liga/desliga o humanizer globalmente.
# Se false, o pipeline ignora completamente (bypass total).
enabled: true

# Perfil de cena ativo. Define quais sons são usados.
# Opções: "escritorio" | "residencial"
# Para o Vale da Liberdade (estúdio de podcast): usar "escritorio".
profile: "escritorio"

# ─── PREPARE (pré-processamento offline) ─────────────────────

prepare:
  # Diretório com os sons BRUTOS (downloads diretos, sem processamento).
  raw_dir: "audio/ambience/raw"

  # Diretório de saída dos sons PREPARADOS (EQ-ados, normalizados).
  # Gerado pelo comando: python scripts/studio_humanizer.py prepare
  prepared_dir: "audio/ambience/prepared"

  # Se true, executa prepare automaticamente quando prepared/ não existe.
  # Se false, falha com erro se prepared/ não existe.
  auto_prepare: true

  # Verificar checksums dos raw/ para detectar mudanças.
  # Se um raw mudou desde o último prepare, emite WARNING no log.
  verify_checksums: true


# ─── ROOM TONE (ambiência contínua) ──────────────────────────
# NOTA: O EQ é aplicado durante o PREPARE. Durante a montagem por episódio,
#       o room tone já vem pronto — apenas loop + crossfade + volume.

room_tone:
  enabled: true

  # Volume relativo à voz (em dB). Quanto mais negativo, mais sutil.
  # Recomendado: -30. Range: -28 a -38.
  volume_db: -30

  # Crossfade em segundos no ponto de loop do room tone.
  crossfade_s: 4.0

  # Fade-in no início do áudio (em segundos).
  fade_in_s: 2.0

  # Fade-out no final do áudio (em segundos).
  fade_out_s: 3.0

  # EQ do room tone.
  eq:
    highpass_hz: 100      # Remove graves que embolariam com a voz
    lowpass_hz: 6000      # Remove frequências brilhantes
    notch_hz: 3000        # Centro do notch para abrir espaço vocal
    notch_db: -3          # Atenuação do notch (negativo = corta)
    notch_q: 1.5          # Q do notch (largura da faixa)

  # Ondulação de ganho ("breathing") para simular variações naturais.
  breathing:
    enabled: true
    amplitude_db: 1.5     # ±1.5 dB de variação
    period_s: 25          # Período da ondulação sinusoidal (segundos)

  # Rotação: evitar repetição em episódios consecutivos.
  # O humanizer salva qual room tone usou no estado.
  rotation:
    enabled: true
    state_file: "output/studio_humanizer_state.json"


# ─── FOLEY (eventos incidentais) ─────────────────────────────

foley:
  enabled: true

  # NOTA: Os sons já vêm normalizados do prepare.
  # Aqui apenas controlamos posicionamento e volume.

  # Volume base relativo à voz (em dB).
  volume_db: -35

  # Variação aleatória de volume entre eventos (±dB).
  volume_variation_db: 3

  # Densidade de eventos (por minuto). O scheduler distribui aleatoriamente.
  events_per_minute_min: 2
  events_per_minute_max: 5

  # Espaçamento mínimo entre dois eventos consecutivos (segundos).
  min_gap_s: 3.0

  # Zona de exclusão: não colocar foley dentro de N ms de uma troca de locutor.
  speaker_change_exclusion_ms: 500

  # Zona de exclusão: não colocar foley sobre silêncios/pausas.
  silence_exclusion:
    enabled: true
    rms_threshold_db: -40   # Trechos abaixo disso são considerados "silêncio"
    window_ms: 200          # Janela de análise RMS

  # Limite máximo de eventos por minuto (hard cap).
  max_events_per_minute: 6

  # EQ aplicado a todos os eventos foley DURANTE O PREPARE.
  # Valores aqui são usados quando o prepare roda.
  eq:
    highpass_hz: 100
    lowpass_hz: 8000

  # Pesos por tipo de evento (influenciam a probabilidade de seleção).
  # Maior peso = mais frequente. 0 = desabilitado.
  weights:
    mouse_click: 3
    teclado_curto: 3
    teclado_longo: 1
    cadeira_range: 1
    papel_vira: 1
    papel_pega: 1
    caneta_mesa: 1
    gole_agua: 0.5          # Raro — apenas em transições
    limpar_garganta: 0.2    # Muito raro

  # Perfis de peso alternativos (sobrescrevem os pesos acima).
  profiles:
    escritorio:
      mouse_click: 3
      teclado_curto: 3
      teclado_longo: 1
      cadeira_range: 1
      papel_vira: 1
      caneta_mesa: 1
      gole_agua: 0.5
      limpar_garganta: 0.2
    residencial:
      passaro: 3
      carro_distante: 2
      cachorro_distante: 0.5
      vento_janela: 1
      sirene_distante: 0.3
      porta_vizinho: 0.5


# ─── REVERB (cola acústica) ──────────────────────────────────

reverb:
  enabled: true

  # NOTA: O IR já vem EQ-ado e truncado do prepare.
  # Aqui apenas controlamos wet_mix e pre_delay.

  # Proporção do sinal wet (reverb) misturado com o dry (voz).
  # 0.04 = 4%. Range: 0.03 a 0.06.
  wet_mix: 0.04

  # Pre-delay em milissegundos (atraso antes do reverb iniciar).
  pre_delay_ms: 10

  # EQ aplicado ao IR durante o PREPARE (não por episódio).
  # Valores aqui são usados quando o prepare roda.
  ir_eq:
    highpass_hz: 200        # Mais agressivo (graves reverberados = lama)
    lowpass_hz: 8000        # Remove "shhh" metálico

  # Limiar para cortar a cauda do IR durante o PREPARE.
  decay_trim_db: -60

  # IR preferida (se não encontrar, usa a primeira do diretório).
  preferred_ir: "small_studio_01.wav"


# ─── OUTPUT ──────────────────────────────────────────────────

output:
  # Formato do WAV de saída.
  sample_rate: 44100
  bit_depth: 16
  channels: 1

  # Sufixo adicionado ao nome do arquivo.
  # Ex.: "2026-09-07-completo.wav" → "2026-09-07-completo-humanized.wav"
  suffix: "-humanized"

  # Manter o WAV original (sem humanização) como backup?
  keep_original: true

  # Logging detalhado dos sons usados em cada episódio.
  log_manifest: true
  manifest_dir: "output/studio_humanizer_manifests"


# ─── DEBUG ───────────────────────────────────────────────────

debug:
  # Exportar cada layer separadamente (para diagnóstico).
  export_layers: false

  # Diretório para layers separados.
  layers_dir: "test_output/humanizer_layers"

  # Gerar visualização waveform (requer matplotlib).
  plot_waveforms: false
```

---

## Tabela de Referência Rápida

| Parâmetro | Default | Range | Unidade |
|---|---|---|---|
| `room_tone.volume_db` | -30 | -28 a -38 | dB |
| `room_tone.crossfade_s` | 4.0 | 2.0 a 8.0 | segundos |
| `room_tone.eq.highpass_hz` | 100 | 60 a 150 | Hz |
| `room_tone.eq.lowpass_hz` | 6000 | 4000 a 8000 | Hz |
| `foley.volume_db` | -35 | -30 a -45 | dB |
| `foley.events_per_minute_min` | 2 | 1 a 4 | eventos/min |
| `foley.events_per_minute_max` | 5 | 3 a 8 | eventos/min |
| `foley.min_gap_s` | 3.0 | 1.5 a 6.0 | segundos |
| `reverb.wet_mix` | 0.04 | 0.03 a 0.06 | proporção |
| `reverb.pre_delay_ms` | 10 | 5 a 15 | ms |
| `reverb.ir_eq.highpass_hz` | 200 | 150 a 300 | Hz |
| `reverb.ir_eq.lowpass_hz` | 8000 | 6000 a 10000 | Hz |

---

## Variáveis de Ambiente (Override)

Qualquer parâmetro YAML pode ser sobrescrito via variável de ambiente com o prefixo `STUDIO_HUMANIZER_`:

```bash
# Desabilitar humanização globalmente
export STUDIO_HUMANIZER_ENABLED=false

# Mudar perfil
export STUDIO_HUMANIZER_PROFILE=residencial

# Ajustar volume do room tone
export STUDIO_HUMANIZER_ROOM_TONE_VOLUME_DB=-32

# Desabilitar foley (manter apenas room tone + reverb)
export STUDIO_HUMANIZER_FOLEY_ENABLED=false
```

Útil para testes e para o cron (desabilitar temporariamente sem editar o YAML).
