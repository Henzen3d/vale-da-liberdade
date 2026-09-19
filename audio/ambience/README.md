# 🎙️ Biblioteca de Áudio — Studio Humanizer

Diretório de ambiências acústicas, micro-eventos incidentais (foley) e Impulse Responses (IR) para o Vale da Liberdade.

## Estrutura

```
audio/ambience/
├── raw/                         # ← Sons originais (downloads diretos)
│   ├── room-tones/              #    Ambiências contínuas de estúdio / sala
│   ├── foley/                   #    Micro-eventos (mouse, teclado, cadeira, etc.)
│   │   ├── escritorio/
│   │   └── residencial/
│   └── impulse-responses/       #    Impulse responses para reverb de convolução
│
├── prepared/                    # ← Sons processados pelo comando `prepare`
│   ├── _manifest.json           #    Metadados, checksums e durações
│   ├── room-tones/
│   ├── foley/
│   └── ir/
```

## Como preparar a biblioteca

1. Baixe arquivos WAV em licença permissiva (CC0 / Public Domain / Royalty-Free) de sites como:
   - [FreeSound.org](https://freesound.org/)
   - [EchoThief](https://www.echothief.com/) (IRs)
   - [Pixabay Sound Effects](https://pixabay.com/sound-effects/)
2. Coloque os arquivos nas respectivas subpastas de `audio/ambience/raw/`.
3. Execute o comando de pré-processamento (executado apenas uma vez ou quando a biblioteca mudar):

```bash
python scripts/studio_humanizer.py prepare
```

O comando converterá automaticamente qualquer arquivo para mono 44.1 kHz 16-bit, aplicará os filtros EQ de isolamento e salvará versões normalizadas prontas para mixagem ultrarrápida em `audio/ambience/prepared/`.
