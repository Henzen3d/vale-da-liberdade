# Brasil e Mundo — layout oficial do vídeo (aprovado 2026-08-22)

Spec vigente do compositor YouTube. Se `scripts/bm_mockup_video.py` sumir ou for reescrito, **repor estes números**. Não voltar para HyperFrames.

Cópia machine-readable: `docs/bm-video-layout.json`.

## Decisão

Pipeline oficial: mockup-browser + avatar Peter + lower third na frente + wallpaper por episódio + thumbnail do site + upload unlisted.

- Cron: `web-jornal-brasil-mundo-hourly` (`30 * * * *`) → `scripts/bm-hourly-pipeline.sh`
- Script: `scripts/bm_mockup_video.py`
- Skill: `vale-bm-mockup-video`
- Autopilot HyperFrames (`bm_video_autopilot.py`, job `e5d6df754c19`) permanece **pausado**
- Primeiro unlisted de prova: https://youtu.be/Zpvk1ZD113k (ainda sem este layout; o layout v6 vale a partir do commit `f99dd8a`)

## Canvas

| Item | Valor |
|---|---|
| Resolução | 1920×1080 |
| FPS do avatar | 30 |
| Áudio | o MP3 do episódio BM (−16 LUFS). **Ignorar** o áudio do loop do avatar |

## Avatar Peter (aprovado v6)

Arquivo (fora do git — pasta `youtube/` é gitignored):

```
references/youtube/Apresentadores/Peter Albuquerque/Peter-Loop-Picsart-BackgroundRemover.mp4
```

Fonte: 964×720, fundo Picsart `#007E00` (não é chroma `#00FF00`).

| Constante | Valor | Por quê |
|---|---|---|
| `AVATAR_CROP` | `910:720:54:0` | 1/18 da largura à esquerda (964/18 ≈ 54). 1/9 comia o braço; 1/6 pior. 1/18 à direita depois do 1/9 = este crop |
| `AVATAR_SCALE` | `546:432` | altura 432 = 720 × 0.6 (dobro do 1/4 inicial + 20%). Largura acompanha o crop |
| `AVATAR_OVERLAY` | `0:H-h+38` | encostado na esquerda; 38px ≈ 1/7 de 432 para baixo (parte do peito sob o lower third) |
| chromakey | `0x007E00:0.10:0.03` | verde real do Picsart |
| alpha | `lut=a='if(lt(val,230),0,255)'` | sem transparência no paletó sobre fundo branco |

ffmpeg (referência):

```
[1:v]crop=910:720:54:0,format=rgba,colorkey=0x007E00:0.10:0.03,lut=a='if(lt(val\,230)\,0\,255)',scale=546:432:flags=lanczos[av]
[0:v][av]overlay=0:H-h+38:format=auto:shortest=1[base]
```

## Lower third

Engine: `youtube/Lower-third-engine/obs-overlay.html` via `scripts/faceless_lower_third.py`.

- Preset: `vdl-brasil-mundo`
- Chromakey do overlay: `#00ff00` (`0x00FF00:0.10:0.22`)
- Sempre **na frente** do avatar
- Karaoke palavra-a-palavra: **proibido**

## Wallpaper

Pasta (gitignored):

```
references/youtube/mockup-browser/wallpaper/
```

- Extensões: `.jpg` `.jpeg` `.png` `.webp`. **Sem** `.gif`
- Escolha: `md5(video_id) % n` — o mesmo episódio sempre pega o mesmo fundo
- O mockup aplica em `#sceneWallpaper` (`object-fit: cover`)
- HTML do mockup: `references/youtube/mockup-browser/mockup-brower.html` (typo no nome)

## Captura das matérias

`prepare_capture` em `bm_mockup_video.py`:

- **BBC:** esconde hero cinza vazio, rola até o `h1`
- **G1:** esconde hero branco vazio, ancora no `h1` mais longo abaixo do header sticky
- **Instagram:** fecha modal “Cadastre-se” no X; não tratar o header Entrar como login-wall

Não capturar YouTube, ANCAPSU, nem páginas `news.mob.tec.br/ep/`.

## YouTube

| Campo | Regra |
|---|---|
| Privacidade | `unlisted` |
| Título | `titulo` do `especial-{id}.json` (máx. 100) |
| Thumbnail | `thumbnails/YYYY-MM-DD/bm_{id}.jpg` (mesma do site). Se faltar, o upload continua |
| Descrição | resumo da `abertura` (≤380 caracteres, corta em frase) + linha `Ouça no app: https://news.mob.tec.br` + `Fontes:` (sem YouTube/ANCAPSU) |
| Canal | Libertarian Life — OAuth em `credentials/token.json` |

## Limites do hourly

- 1 vídeo/hora, janela 2 dias, áudio ≤ 480 s
- Falha de vídeo **não** derruba `process-queue`
- Python do vídeo: `.venv` do **projeto** (Playwright)
- Python da fila: venv do Hermes

## Como repor se o código sumir

1. Recriar as constantes no topo de `scripts/bm_mockup_video.py` a partir de `docs/bm-video-layout.json`
2. Conferir que o loop do Peter e a pasta `wallpaper/` ainda existem nos paths acima
3. `python3 scripts/test_bm_mockup_video.py`
4. Dry-run: `scripts/bm_mockup_video.py --video-id <ID> --dry-run`
5. Não religar HyperFrames
