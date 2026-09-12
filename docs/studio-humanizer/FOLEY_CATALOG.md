# 📦 Catálogo de Sons — Foley & Ambiências

> **Referência para curadoria e organização da biblioteca de sons do Studio Humanizer**

---

## 1. Estrutura de Diretórios — Modelo Híbrido (raw → prepared)

Os sons são organizados em dois diretórios espelhados:
- **`raw/`** — Downloads brutos, sem processamento (você edita aqui)
- **`prepared/`** — Gerado automaticamente pelo `studio_humanizer.py prepare`

```
audio/ambience/
├── raw/                               # ← EDITAR AQUI (downloads brutos)
│   ├── room-tones/                    # Ambiências contínuas de sala
│   │   ├── estudio_podcast_01.wav
│   │   ├── estudio_podcast_02.wav
│   │   ├── escritorio_ac_leve.wav
│   │   ├── escritorio_hum_eletrico.wav
│   │   ├── sala_silenciosa_01.wav
│   │   └── sala_computador_01.wav
│   │
│   ├── foley/                         # Eventos discretos
│   │   ├── escritorio/
│   │   │   ├── mouse_click_01.wav
│   │   │   ├── mouse_click_02.wav
│   │   │   ├── mouse_click_03.wav
│   │   │   ├── teclado_curto_01.wav
│   │   │   ├── teclado_curto_02.wav
│   │   │   ├── teclado_curto_03.wav
│   │   │   ├── teclado_longo_01.wav
│   │   │   ├── teclado_longo_02.wav
│   │   │   ├── cadeira_range_01.wav
│   │   │   ├── cadeira_range_02.wav
│   │   │   ├── papel_vira_01.wav
│   │   │   ├── papel_pega_01.wav
│   │   │   ├── caneta_mesa_01.wav
│   │   │   ├── caneta_mesa_02.wav
│   │   │   ├── gole_agua_01.wav
│   │   │   └── limpar_garganta_01.wav
│   │   │
│   │   └── residencial/
│   │       ├── passaro_01.wav
│   │       ├── passaro_02.wav
│   │       ├── passaro_03.wav
│   │       ├── carro_distante_01.wav
│   │       ├── carro_distante_02.wav
│   │       ├── cachorro_distante_01.wav
│   │       ├── vento_janela_01.wav
│   │       ├── sirene_distante_01.wav
│   │       └── porta_vizinho_01.wav
│   │
│   └── impulse-responses/
│       ├── small_studio_01.wav
│       ├── small_studio_02.wav
│       ├── home_office_01.wav
│       ├── vocal_booth_01.wav
│       └── office_medium_01.wav
│
├── prepared/                          # ← GERADO AUTOMATICAMENTE
│   ├── _manifest.json                 #    Checksums, metadados, timestamps
│   ├── room-tones/                    #    EQ-ados (HPF+LPF+notch), normalizados
│   │   ├── estudio_podcast_01.wav
│   │   └── ...
│   ├── foley/                         #    Normalizados (peak -6dBFS), trimados
│   │   ├── escritorio/
│   │   │   ├── mouse_click_01.wav
│   │   │   └── ...
│   │   └── residencial/
│   │       └── ...
│   └── ir/                            #    EQ-ados (HPF+LPF), decay truncado
│       ├── small_studio_01.wav
│       └── ...
│
└── README.md                          # Licenças e fontes de cada arquivo
```

> **Workflow:** Baixe sons → coloque em `raw/` → rode `python scripts/studio_humanizer.py prepare` → `prepared/` é gerado automaticamente. Cada episódio lê apenas de `prepared/`.


---

## 2. Especificações Técnicas dos Arquivos

### Formato obrigatório

| Propriedade | Valor | Motivo |
|---|---|---|
| Formato | **WAV PCM** | Sem perda de qualidade na mixagem |
| Sample Rate | **44100 Hz** | Compatível com o pipeline existente |
| Bit Depth | **16-bit** | Suficiente para ambiência (ruidosa por natureza) |
| Canais | **Mono** | Pipeline é mono; stereo seria descartado |
| Normalização | **Peak -6 dBFS** | Headroom para processamento posterior |
| DC Offset | **Removido** | Evitar clicks no corte/crossfade |

### Duração por tipo

| Tipo | Duração Mínima | Duração Ideal | Nota |
|---|---|---|---|
| Room Tone | 30 segundos | 60-120 segundos | Mais longo = menos repetição |
| Foley (curto) | 0.1s | 0.2-1.0s | Mouse, caneta, etc. |
| Foley (médio) | 0.5s | 1.0-3.0s | Teclado, papel, pássaro |
| Foley (longo) | 2.0s | 3.0-8.0s | Carro passando, sirene |
| Impulse Response | 0.2s | 0.3-0.8s | RT60 da sala simulada |

---

## 3. Catálogo Detalhado por Categoria

### 3.1 Room Tones — Estúdio / Escritório

| ID | Nome | Descrição | Duração | Prioridade |
|---|---|---|---|---|
| RT-01 | `estudio_podcast_01` | Ambiente de estúdio com tratamento acústico. Ruído residual de equipamentos ligados. | 90s | ⭐⭐⭐ |
| RT-02 | `estudio_podcast_02` | Variação do estúdio. Leve hum de 60 Hz de monitor ligado. | 60s | ⭐⭐⭐ |
| RT-03 | `escritorio_ac_leve` | Ar condicionado em potência baixa. Ruído branco filtrado e contínuo. | 120s | ⭐⭐ |
| RT-04 | `escritorio_hum_eletrico` | Apenas o zumbido elétrico de lâmpada fluorescente e PC. | 60s | ⭐⭐ |
| RT-05 | `sala_silenciosa_01` | Sala em silêncio. Gravação do "nada" real — microimpurezas. | 90s | ⭐⭐⭐ |
| RT-06 | `sala_computador_01` | Desktop ligado com ventoinha padrão. Som constante e quente. | 60s | ⭐⭐ |

### 3.2 Foley — Escritório (Perfil Primário)

| ID | Nome | Descrição | Duração | Variações |
|---|---|---|---|---|
| FO-E01 | `mouse_click` | Clique único de mouse USB. Seco e curto. | 0.15s | 3 |
| FO-E02 | `teclado_curto` | 2-4 teclas pressionadas rapidamente (digitação breve). | 0.4s | 3 |
| FO-E03 | `teclado_longo` | Sequência de digitação de 5-15 teclas (escrever algo). | 1.2s | 2 |
| FO-E04 | `cadeira_range` | Cadeira de escritório fazendo um ajuste. Leve, não agudo. | 0.8s | 2 |
| FO-E05 | `papel_vira` | Uma folha de papel sendo virada/consultada. | 0.5s | 1 |
| FO-E06 | `papel_pega` | Pegar e soltar uma folha na mesa. | 0.6s | 1 |
| FO-E07 | `caneta_mesa` | Caneta sendo largada na mesa (som sutil). | 0.2s | 2 |
| FO-E08 | `gole_agua` | Beber um gole de água (para transições). | 0.6s | 1 |
| FO-E09 | `limpar_garganta` | Pigarro ultra-sutil (raramente usado). | 0.4s | 1 |

### 3.3 Foley — Residencial (Perfil Secundário)

| ID | Nome | Descrição | Duração | Variações |
|---|---|---|---|---|
| FO-R01 | `passaro` | Pássaro comum cantando ao fundo (janela fechada). | 2.0s | 3 |
| FO-R02 | `carro_distante` | Carro passando em rua movimentada distante. | 3.5s | 2 |
| FO-R03 | `cachorro_distante` | 1-2 latidos de cachorro muito distante. | 1.0s | 1 |
| FO-R04 | `vento_janela` | Brisa passando pela fresta da janela. | 4.0s | 1 |
| FO-R05 | `sirene_distante` | Sirene de ambulância muito ao fundo. | 5.0s | 1 |
| FO-R06 | `porta_vizinho` | Porta sendo fechada em apartamento vizinho. | 0.4s | 1 |

### 3.4 Impulse Responses

| ID | Nome | Descrição | RT60 | Fonte sugerida |
|---|---|---|---|---|
| IR-01 | `small_studio_01` | Estúdio de podcast ~15m², tratamento acústico parcial. | 0.25s | OpenAIR / gravar |
| IR-02 | `small_studio_02` | Quarto/home office ~12m², carpete + cortinas. | 0.30s | EchoThief |
| IR-03 | `home_office_01` | Escritório doméstico ~18m², piso duro. | 0.35s | Voxengo |
| IR-04 | `vocal_booth_01` | Cabine vocal (reverb mínimo). Ideal para "quase seco". | 0.12s | Fokke van Saane |
| IR-05 | `office_medium_01` | Escritório médio ~25m² (mais espaçoso). | 0.40s | OpenAIR |

---

## 4. Fontes de Sons Gratuitos (CC0 / Royalty-Free)

### Room Tones
| Fonte | URL | Licença | Nota |
|---|---|---|---|
| Freesound.org | freesound.org | CC0 / CC-BY | Maior biblioteca. Filtrar por "room tone", "office ambience" |
| BBC Sound Effects | sound-effects.bbcrewind.co.uk | RemArc licence | Uso não-comercial; para ref. |
| Zapsplat | zapsplat.com | Royalty-free (conta gratuita) | Boa qualidade |
| SoundBible | soundbible.com | CC0 / Public Domain | Seleção menor mas limpa |

### Foley
| Fonte | URL | Licença | Nota |
|---|---|---|---|
| Freesound.org | freesound.org | CC0 / CC-BY | Buscar "keyboard typing", "mouse click" |
| Sonniss GDC Audio | sonniss.com/gameaudiogdc | Royalty-free | Pack anual gratuito, alta qualidade |
| Pixabay Audio | pixabay.com/sound-effects | Pixabay License | Livre para uso comercial |

### Impulse Responses
| Fonte | URL | Licença | Nota |
|---|---|---|---|
| OpenAIR | openairlib.net | CC-BY / academic | IRs de salas reais |
| EchoThief | echothief.com | Free | Coleção curada |
| Voxengo | voxengo.com/impulses | Free | Pack clássico |
| Fokke van Saane | fokkie.home.xs4all.nl | Free | IRs de cabines e salas |

---

## 5. Processo de Curadoria

### Checklist para cada som adicionado

- [ ] Formato correto (WAV 44.1kHz 16-bit mono)?
- [ ] DC offset removido?
- [ ] Peak normalizado a -6 dBFS?
- [ ] Silêncio excessivo no início/fim cortado?
- [ ] Licença verificada (CC0, CC-BY, ou royalty-free)?
- [ ] Soa natural e não "produzido"?
- [ ] Consistente com o ambiente (estúdio de podcast)?
- [ ] Não contém música, vozes ou logos sonoros?
- [ ] Adicionado ao manifesto `_catalog.json`?

### Formato do manifesto `_catalog.json`

```json
{
  "version": "1.0",
  "updated": "2026-09-07",
  "room_tones": [
    {
      "id": "RT-01",
      "file": "room-tones/estudio_podcast_01.wav",
      "duration_s": 90.0,
      "description": "Estúdio de podcast com tratamento acústico",
      "source": "freesound.org/s/123456",
      "license": "CC0",
      "rms_db": -42.0,
      "tags": ["studio", "quiet", "electric_hum"]
    }
  ],
  "foley": [
    {
      "id": "FO-E01",
      "file": "foley/escritorio/mouse_click_01.wav",
      "duration_s": 0.15,
      "category": "escritorio",
      "type": "mouse_click",
      "source": "freesound.org/s/789012",
      "license": "CC0",
      "peak_db": -6.0,
      "tags": ["click", "mouse", "office"]
    }
  ],
  "impulse_responses": [
    {
      "id": "IR-01",
      "file": "impulse-responses/small_studio_01.wav",
      "rt60_s": 0.25,
      "description": "Estúdio de podcast ~15m²",
      "source": "openairlib.net",
      "license": "CC-BY",
      "tags": ["small", "studio", "treated"]
    }
  ]
}
```
