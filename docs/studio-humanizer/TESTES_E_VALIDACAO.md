# 🧪 Plano de Testes e Validação — Studio Humanizer

> **Estratégia completa de testes, métricas de qualidade e validação A/B**

---

## 1. Testes Unitários (`test_studio_humanizer.py`)

### 1.1 Testes de Configuração

| Teste | Descrição | Critério de Sucesso |
|---|---|---|
| `test_load_default_config` | Carrega config YAML com valores padrão | Todos os campos obrigatórios presentes |
| `test_config_disabled` | `enabled: false` faz bypass total | Output = input (bit-identical) |
| `test_env_override` | Variável de ambiente sobrescreve YAML | Valor da env vence |
| `test_invalid_config` | Config com valores inválidos | Erro claro, sem crash |
| `test_missing_audio_dir` | Diretório de ambiência não existe | Warning + bypass gracioso |

### 1.2 Testes do Room Tone Generator

| Teste | Descrição | Critério de Sucesso |
|---|---|---|
| `test_room_tone_duration` | Room tone cobre toda a duração da voz | `len(room_tone) == len(voice)` |
| `test_room_tone_level` | Volume está dentro do range esperado | RMS entre -28 dB e -38 dB rel. |
| `test_room_tone_crossfade` | Ponto de loop não tem click/pop | Análise de descontinuidade < threshold |
| `test_room_tone_eq` | HPF e LPF aplicados corretamente | Energia abaixo de 100 Hz < -40 dB |
| `test_room_tone_breathing` | Ondulação de ganho funciona | Variação de RMS em janelas ≈ ±1.5 dB |
| `test_room_tone_rotation` | Não repete o mesmo tone consecutivamente | State file rastreia `last_used` |

### 1.3 Testes do Foley Scheduler

| Teste | Descrição | Critério de Sucesso |
|---|---|---|
| `test_foley_density` | Número de eventos por minuto no range | 2-5 eventos/min (default) |
| `test_foley_min_gap` | Espaçamento mínimo respeitado | Nenhum par de eventos < 3.0s |
| `test_foley_no_consecutive_repeat` | Mesmo sample não usado 2x seguidas | Nenhuma repetição consecutiva |
| `test_foley_exclusion_zone` | Eventos não caem sobre silêncios | RMS do trecho > threshold |
| `test_foley_volume_variation` | Volume varia entre eventos | Desvio padrão > 0 |
| `test_foley_profile_switch` | Mudar perfil altera os sons usados | Sons do perfil correto selecionados |
| `test_foley_max_cap` | Hard cap de eventos/minuto respeitado | Nunca > 6/min |
| `test_foley_weights` | Pesos influenciam distribuição | Eventos de peso 3 aparecem ~3x mais que peso 1 |

### 1.4 Testes do Reverb de Convolução

| Teste | Descrição | Critério de Sucesso |
|---|---|---|
| `test_reverb_wet_mix` | Mix correto (dry+wet) | Energia proporcional ao wet_mix |
| `test_reverb_preserves_length` | Output tem mesma duração que input | `len(output) == len(input)` |
| `test_reverb_ir_eq` | HPF/LPF aplicados ao IR | Frequências fora do range atenuadas |
| `test_reverb_pre_delay` | Pre-delay correto | Pico do reverb atrasa N samples |
| `test_reverb_bypass` | `reverb.enabled: false` = sem reverb | Output = input |

### 1.5 Testes do Mixer Final

| Teste | Descrição | Critério de Sucesso |
|---|---|---|
| `test_mix_output_format` | WAV 44.1kHz 16-bit mono | Header WAV correto |
| `test_mix_no_clipping` | Sem clipping na soma | Peak ≤ 0 dBFS |
| `test_mix_preserves_voice` | Voz é claramente dominante | SNR voz vs. ambiência > 20 dB |
| `test_full_pipeline` | Pipeline completo funciona | Output WAV válido e reproduzível |

---

## 2. Testes de Integração

### 2.1 Com o Pipeline TTS

| Teste | Descrição | Setup |
|---|---|---|
| `test_integration_diario` | Episódio do Jornal Diário completo | Usar episódio real recente |
| `test_integration_bm` | Episódio Brasil e Mundo completo | Usar episódio BM real |
| `test_integration_bypass` | Flag `--no-humanize` funciona | Pipeline normal, sem humanização |
| `test_integration_ffmpeg` | WAV humanizado passa pelo loudnorm sem erro | `run_ffmpeg_chain_2pass()` |

### 2.2 Com o Pipeline de Vídeo

| Teste | Descrição | Setup |
|---|---|---|
| `test_video_mux` | MP3 humanizado muxa corretamente no vídeo | `bm_mockup_video.py` |
| `test_video_sync` | Áudio continua sincronizado com o vídeo | Verificar timing de cenas |

---

## 3. Testes A/B (Validação Perceptual)

### 3.1 Protocolo do Teste Cego

**Objetivo:** Verificar se a humanização é imperceptível mas melhora a percepção geral.

**Setup:**
1. Selecionar 5 episódios recentes (já publicados)
2. Gerar versão humanizada de cada um
3. Preparar pares A/B (random: qual é A e qual é B)

**Participantes:** 3-5 pessoas (família, amigos, ou o próprio)

**Perguntas do teste:**

```
Para cada par (A vs. B), ouça 2 minutos de cada e responda:

1. Qual das duas versões soa mais natural?        [ A / B / Igual ]
2. Você percebe algum som de fundo?               [ Sim / Não ] (em qual?)
3. Qual você prefere para ouvir por 10 minutos?   [ A / B / Igual ]
4. Alguma das versões soa "robótica" ou "de IA"?  [ A / B / Nenhuma ]
5. Em uma escala de 1-5, quão natural soa cada uma?
   - Versão A: [ 1-5 ]
   - Versão B: [ 1-5 ]
```

**Critérios de sucesso:**
- ✅ ≥60% dos participantes preferem a versão humanizada
- ✅ ≤20% detectam o som de fundo conscientemente
- ✅ Score médio de naturalidade da versão humanizada > versão seca
- ❌ Se >40% reclamam de ruído perceptível → reduzir volume

### 3.2 Teste Interno Rápido (Self-Check)

Antes de qualquer teste com outras pessoas, fazer o auto-teste:

```
1. Abrir episódio humanizado em headphones de qualidade
2. Ouvir 3 minutos sem prestar atenção no fundo
3. Em algum momento mutar a faixa de ambiência
   → Se percebeu a mudança: ✅ volume ok
   → Se NÃO percebeu: ambiência pode ser mais alta
   → Se a ambiência era óbvia: reduzir volume

4. Ouvir novamente focando no fundo
   → Consegue identificar os sons individualmente? Se sim → muito alto
   → Percebe uma "presença" vaga? → perfeito
```

---

## 4. Métricas Automatizadas

### 4.1 Métricas de Áudio

```python
class HumanizationMetrics:
    """Métricas calculadas automaticamente após cada humanização."""
    
    # SNR (Signal-to-Noise Ratio): voz vs. ambiência
    snr_db: float          # Target: > 25 dB
    
    # RMS do room tone
    room_rms_db: float     # Target: -28 a -38 dB
    
    # Número de eventos foley
    foley_count: int       # Target: 2-5 por minuto
    foley_per_minute: float
    
    # Duração total
    duration_s: float
    
    # Peak level (anti-clipping)
    peak_dbfs: float       # Target: ≤ -0.5 dBFS
    
    # LUFS integrado (pré-loudnorm)
    lufs_integrated: float
    
    # Room tone selecionado
    room_tone_file: str
    
    # IR selecionada
    ir_file: str
    
    # Foley manifest (quais sons, em quais tempos)
    foley_manifest: list[dict]
```

### 4.2 Manifesto de Episódio

Cada episódio humanizado gera um JSON de manifesto:

```json
{
  "episode_date": "2026-09-07",
  "humanizer_version": "1.0",
  "profile": "escritorio",
  "config_hash": "abc123",
  "metrics": {
    "snr_db": 28.5,
    "room_rms_db": -31.2,
    "foley_count": 42,
    "foley_per_minute": 3.1,
    "duration_s": 812.0,
    "peak_dbfs": -1.2
  },
  "room_tone": {
    "file": "estudio_podcast_02.wav",
    "volume_db": -30
  },
  "reverb": {
    "ir_file": "small_studio_01.wav",
    "wet_mix": 0.04
  },
  "foley_events": [
    {"time_s": 12.3, "type": "mouse_click", "file": "mouse_click_02.wav", "volume_db": -36},
    {"time_s": 18.7, "type": "teclado_curto", "file": "teclado_curto_01.wav", "volume_db": -34},
    "..."
  ]
}
```

---

## 5. Monitoramento Pós-Deploy

### 5.1 Métricas YouTube (comparar antes/depois)

| Métrica | Onde encontrar | O que observar |
|---|---|---|
| Average View Duration | YouTube Studio → Analytics | Retenção deve manter ou melhorar |
| Audience Retention Curve | YouTube Studio → Analytics | Curva não deve cair no início (som estranho) |
| Like/Dislike Ratio | YouTube Studio | Deve manter ou melhorar |
| Comentários sobre "voz de IA" | Comentários | Redução = sucesso |
| CTR (Click-Through Rate) | YouTube Studio | Não deve ser afetado (é visual) |

### 5.2 Alertas Automatizados

```yaml
# Regras de alerta no log do humanizer

alerts:
  # Alertar se SNR cair muito (ambiência alta demais)
  - condition: "snr_db < 20"
    severity: "WARNING"
    message: "SNR muito baixo — ambiência pode estar alta demais"

  # Alertar se não encontrar room tones
  - condition: "room_tone_count == 0"
    severity: "ERROR"
    message: "Nenhum room tone encontrado — humanização impossível"

  # Alertar se foley density anormal
  - condition: "foley_per_minute > 8"
    severity: "WARNING"
    message: "Densidade de foley muito alta — pode poluir o áudio"

  # Alertar se clipping detectado
  - condition: "peak_dbfs > -0.3"
    severity: "ERROR"
    message: "Clipping detectado — reduzir volumes"
```

---

## 6. Plano de Rollback

Se os testes ou métricas pós-deploy indicarem problemas:

### Nível 1: Ajuste fino
→ Reduzir volumes no YAML (`-32 dB` room, `-38 dB` foley)

### Nível 2: Desabilitar camadas
→ `foley.enabled: false` (manter apenas room tone + reverb)

### Nível 3: Desabilitar tudo
→ `enabled: false` no YAML ou `STUDIO_HUMANIZER_ENABLED=false` no env

### Nível 4: Reverter código
→ Remover as ~8 linhas de integração no `generate_gemini_tts_multi.py`

Cada nível é progressivamente mais drástico. Começar pelo 1 e escalar se necessário.
