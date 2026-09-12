# 🔗 Mapa de Integração — Studio Humanizer no Pipeline Existente

> **Onde exatamente o humanizer entra no código atual e quais arquivos são modificados**  
> **Modelo:** Híbrido (prepare offline + montagem rápida por episódio)

---

## 1. Pipeline Atual (ANTES do Humanizer)

### Jornal Diário (Dois Locutores: Peter + Ricardo)

```
generate_gemini_tts_multi.py::main()
    │
    ├─ 1. Lê episódio.txt (roteiro com marcadores de locutor)
    ├─ 2. Divide em chunks por [PAUSA] / [PAUSA_CURTA]
    ├─ 3. Para cada chunk:
    │      └─ Gemini TTS API → PCM 24kHz
    ├─ 4. Concatena chunks + silêncios → WAV completo
    │      └─ concatenate_wavs() → {date}-completo.wav          ← ★ PONTO A
    ├─ 5. run_ffmpeg_chain_2pass(completo.wav, output.mp3)      ← ★ PONTO B
    │      └─ highpass + compressor + EQ + loudnorm 2-pass
    └─ 6. Entrega: {date}-vale-da-liberdade.mp3
```

### Pipeline Brasil e Mundo (BM — Peter Solo)

```
bm_pipeline.py::step_audio()
    │
    ├─ 1. Gera áudio via generate_gemini_tts_multi.py (subprocess)
    ├─ 2. Resultado: audio/{video_id}_{date}.mp3
    └─ 3. bm_mockup_video.py mux o MP3 no vídeo final
```

---

## 2. Duas Fases do Modelo Híbrido

### Fase 0 — PREPARE (executado offline, uma vez)

```
studio_humanizer.py prepare
    │
    ├─ 1. Lê todos os sons brutos de audio/ambience/raw/
    │      ├─ raw/room-tones/*.wav     (room tones sem processar)
    │      ├─ raw/foley/**/*.wav       (foley sounds sem processar)
    │      └─ raw/impulse-responses/*.wav (IRs sem processar)
    │
    ├─ 2. Processa cada arquivo:
    │      ├─ Room Tones:  HPF 100Hz + LPF 6kHz + Notch 3kHz + Normalize
    │      ├─ Foley:       Normalize peak -6dBFS + Trim silêncio + Remove DC
    │      └─ IRs:         HPF 200Hz + LPF 8kHz + Truncar decay a -60dB
    │
    ├─ 3. Salva em audio/ambience/prepared/
    │      ├─ prepared/room-tones/     (prontos para loop direto)
    │      ├─ prepared/foley/          (prontos para inserção direta)
    │      └─ prepared/ir/             (prontos para convolução direta)
    │
    └─ 4. Gera prepared/_manifest.json
           (checksums, duração, metadados de cada arquivo)

Tempo: ~30-60 segundos (uma vez)
Quando re-executar: ao adicionar/remover sons da pasta raw/
```

### Fase 1 — HUMANIZE (por episódio, ~2-3 segundos)

```
generate_gemini_tts_multi.py::main()
    │
    ├─ 1-4. [SEM MUDANÇA] → {date}-completo.wav
    │
    ├─ 4.5 ★ NOVO ★ studio_humanizer.humanize()
    │      │
    │      ├─ Carrega arquivos JÁ PREPARADOS (leitura pura, sem EQ):
    │      │   ├─ prepared/room-tones/estudio_podcast_02.wav  (rotação)
    │      │   ├─ prepared/foley/escritorio/*.wav              (pool)
    │      │   └─ prepared/ir/small_studio_01.wav              (fixo)
    │      │
    │      ├─ Operações LEVES (fresh por episódio):
    │      │   ├─ Loop room tone na duração certa + crossfade
    │      │   ├─ FFT convolve voz com IR → mix 4% wet
    │      │   ├─ Sorteia posições aleatórias para foley events
    │      │   └─ Soma tudo → WAV humanizado
    │      │
    │      ├─ Input:  {date}-completo.wav
    │      ├─ Output: {date}-completo-humanized.wav
    │      └─ Tempo: ~2-3 segundos ⚡
    │
    ├─ 5. run_ffmpeg_chain_2pass(completo-humanized.wav, output.mp3)
    │      └─ [SEM MUDANÇA no ffmpeg chain]
    └─ 6. Entrega: {date}-vale-da-liberdade.mp3
```

---

## 3. Arquivos Modificados

### 3.1 `scripts/generate_gemini_tts_multi.py` — Modificação mínima

**Localização:** Após `concatenate_wavs()` (linha ~395) e antes de `run_ffmpeg_chain_2pass()` (linha ~415)

```python
# ── CÓDIGO EXISTENTE ────────────────────────────────────
final_wav = concatenate_wavs(chunk_wavs, ...)
# ── INSERÇÃO NOVA ───────────────────────────────────────
from studio_humanizer import StudioHumanizer

humanizer = StudioHumanizer()  # lê config/studio_humanizer.yaml
if humanizer.enabled:
    humanized_wav = final_wav.with_stem(final_wav.stem + "-humanized")
    humanizer.humanize(input_wav=final_wav, output_wav=humanized_wav)
    final_wav = humanized_wav
    log.info(f"✅ Studio Humanizer aplicado → {humanized_wav}")
# ── CÓDIGO EXISTENTE (sem mudança) ──────────────────────
run_ffmpeg_chain_2pass(final_wav, output_mp3)
```

**Total de linhas adicionadas:** ~8 linhas  
**Risco de regressão:** Mínimo (gated por `humanizer.enabled`)

### 3.2 `scripts/studio_humanizer.py` — Arquivo NOVO

Módulo principal com dois modos de operação. Estimativa: ~500-600 linhas.

```python
class StudioHumanizer:
    """Adiciona camadas orgânicas de áudio para humanizar vozes de IA.
    
    Modelo híbrido:
    - prepare(): pré-processa sons brutos → prepared/ (uma vez)
    - humanize(): monta a mixagem usando prepared/ (por episódio)
    """
    
    def __init__(self, config_path=None):
        self.cfg = load_config(config_path)
        self.enabled = self.cfg.get("enabled", True)
        self.prepared_dir = PROJECT_ROOT / "audio" / "ambience" / "prepared"
    
    def prepare(self) -> None:
        """Pré-processa todos os sons brutos → prepared/.
        
        Executar UMA VEZ ou quando a biblioteca mudar.
        Aplica EQ, normalização, trim em cada arquivo.
        Gera _manifest.json com checksums e metadados.
        """
        raw_dir = PROJECT_ROOT / "audio" / "ambience" / "raw"
        
        # 1. Processar room tones (HPF + LPF + notch + normalize)
        self._prepare_room_tones(raw_dir / "room-tones")
        
        # 2. Processar foley (normalize + trim + DC offset)
        self._prepare_foley(raw_dir / "foley")
        
        # 3. Processar IRs (HPF + LPF + decay trim)
        self._prepare_impulse_responses(raw_dir / "impulse-responses")
        
        # 4. Gerar manifesto
        self._write_manifest()
    
    def humanize(self, input_wav: Path, output_wav: Path) -> Path:
        """Montagem rápida usando arquivos JÁ PREPARADOS.
        
        Sem EQ/normalização pesada — apenas leitura, loop, 
        posicionamento e soma. ~2-3 segundos.
        """
        # Auto-prepare se prepared/ não existe
        if not self.prepared_dir.exists():
            log.warning("prepared/ não encontrado — executando prepare()...")
            self.prepare()
        
        voice = load_audio(input_wav)
        
        # 1. Reverb: convolui voz com IR JÁ PREPARADO
        voice_wet = self._apply_reverb(voice)
        
        # 2. Room Tone: loop de arquivo JÁ PREPARADO
        room = self._assemble_room_tone(len(voice_wet))
        
        # 3. Foley: posiciona sons JÁ PREPARADOS (posições fresh)
        foley = self._schedule_foley(len(voice_wet), voice_wet)
        
        # 4. Mix final: soma das 3 camadas
        output = self._mix_layers(voice_wet, room, foley)
        save_audio(output, output_wav)
        return output_wav
```

### 3.3 `config/studio_humanizer.yaml` — Arquivo NOVO

Configuração completa com seção de prepare (vide [`CONFIG_SPEC.md`](./CONFIG_SPEC.md)).

### 3.4 `scripts/bm_pipeline.py` — Nenhuma mudança necessária

A humanização é automática via `generate_gemini_tts_multi.py`.

---

## 4. Arquivos NÃO Modificados

| Arquivo | Motivo |
|---|---|
| `run_ffmpeg_chain_2pass()` | Funciona inalterado — recebe WAV (humanizado ou não) |
| `ricardo_voice_fx.py` | Efeitos vocais do Ricardo são **antes** do humanizer |
| `bm_mockup_video.py` | Consome MP3 final — indiferente à fonte |
| `youtube_uploader.py` | Upload — indiferente ao conteúdo do áudio |
| `tts_preprocessor.py` | Pré-processamento de texto — sem relação |
| `build_outro.py` | Outro/encerramento — áudio separado |

---

## 5. Fluxo de Dados Completo

```
  ┌─────────────────────────────────────────────────────────────┐
  │  PREPARE (offline, uma vez)                                  │
  │                                                              │
  │  audio/ambience/raw/          audio/ambience/prepared/       │
  │  ├── room-tones/*.wav   ──►   ├── room-tones/*.wav (EQ-ado) │
  │  ├── foley/**/*.wav     ──►   ├── foley/**/*.wav (norm.)     │
  │  └── impulse-responses/ ──►   └── ir/*.wav (EQ+trim)         │
  └─────────────────────────────────────────────────────────────┘
                                          │
                         (arquivos ficam em disco, reutilizados)
                                          │
  ┌───────────────────────────────────────▼──────────────────────┐
  │  POR EPISÓDIO                                                 │
  │                                                               │
  │  ┌───────────────────────┐                                    │
  │  │  Gemini TTS API       │                                    │
  │  │  (PCM 24kHz chunks)   │                                    │
  │  └───────────┬───────────┘                                    │
  │              │                                                │
  │  ┌───────────▼───────────┐                                    │
  │  │  concatenate_wavs()    │                                   │
  │  │  → {date}-completo.wav │                                   │
  │  └───────────┬───────────┘                                    │
  │              │                                                │
  │  ┌───────────▼──────────────────────────────────────┐         │
  │  │  studio_humanizer.humanize()  ⚡ ~2-3s            │         │
  │  │                                                   │         │
  │  │  Lê prepared/ (sem processar novamente):          │         │
  │  │  ├─ Loop room tone na duração certa               │         │
  │  │  ├─ FFT convolve voz com IR preparado             │         │
  │  │  ├─ Sorteia posições de foley (fresh random)      │         │
  │  │  └─ Soma tudo → WAV humanizado                    │         │
  │  └───────────┬──────────────────────────────────────┘         │
  │              │                                                │
  │  ┌───────────▼───────────┐                                    │
  │  │ run_ffmpeg_chain_2pass │                                   │
  │  │ (loudnorm + EQ + comp) │                                   │
  │  └───────────┬───────────┘                                    │
  │              │                                                │
  │  ┌───────────▼───────────┐                                    │
  │  │  MP3 final 192kbps    │                                    │
  │  └───────────┬───────────┘                                    │
  │              │                                                │
  │  ┌───────────▼──────────────┐                                 │
  │  │  bm_mockup_video.py      │                                 │
  │  │  (mux audio + video)     │                                 │
  │  └───────────┬──────────────┘                                 │
  │              │                                                │
  │  ┌───────────▼───────────┐                                    │
  │  │  youtube_uploader.py   │                                   │
  │  └───────────────────────┘                                    │
  └───────────────────────────────────────────────────────────────┘
```

---

## 6. CLI e Flags

### Comando prepare (executado uma vez)

```bash
# Pré-processar todos os sons brutos
python scripts/studio_humanizer.py prepare

# Re-processar apenas room tones (após adicionar novos)
python scripts/studio_humanizer.py prepare --only room-tones

# Re-processar tudo com force (ignora checksums)
python scripts/studio_humanizer.py prepare --force

# Verificar integridade do prepared/ sem re-processar
python scripts/studio_humanizer.py prepare --verify
```

### Integração no `generate_gemini_tts_multi.py`

```
Novo argumento:
  --humanize / --no-humanize    Habilita/desabilita o Studio Humanizer
                                 (default: segue config/studio_humanizer.yaml)
  --humanizer-profile PROFILE   Perfil de cena: "escritorio" (default) ou "residencial"
```

### Script standalone para testes

```bash
# Humanizar um WAV manualmente (usa prepared/)
python scripts/studio_humanizer.py humanize \
  --input audio/2026-09-07-completo.wav \
  --output audio/2026-09-07-humanized.wav \
  --profile escritorio

# Comparação A/B (gera ambos)
python scripts/studio_humanizer.py ab-test \
  --input audio/2026-09-07-completo.wav \
  --output-dir test_output/ab-test/
```

---

## 7. Custo por Episódio — Benchmark

| Operação | Tempo estimado | Nota |
|---|---|---|
| Carregar room tone preparado | ~50 ms | Leitura de disco (WAV ~1 MB) |
| Loop + crossfade | ~100 ms | Operação numpy simples |
| Carregar IR preparado | ~10 ms | IR é curto (~0.3s) |
| FFT convolução | ~500 ms | scipy.fftconvolve, ~15 min de áudio |
| Carregar foley sounds | ~100 ms | Pool de ~15 WAVs curtos |
| Posicionar foley events | ~50 ms | Soma em array numpy |
| Mix final + escrita WAV | ~200 ms | Soma + wav.write |
| **TOTAL** | **~1-2 segundos** | Bem abaixo do target de 3s |

Comparação: o pipeline TTS em si leva 3-8 **minutos**. O humanizer adiciona **<1%** do tempo total.
