# Branding do vídeo do YouTube

Coloque aqui a **abertura** e o **fechamento** que você criar. O pipeline
(`scripts/youtube_video_generator.py`) reutiliza estes dois arquivos em
**todos** os episódios — você só precisa criá-los uma vez.

## Arquivos esperados

| Arquivo | Papel |
|---------|-------|
| `intro.mp4` | Abertura do vídeo (logo, vinheta, etc.) |
| `outro.mp4` | Fechamento ("até amanhã", CTA para seguir, etc.) |

## Formato recomendado

- **Resolução:** 1280×720 (16:9)
- **Framerate:** 30 fps
- **Codec:** H.264 (libx264) + áudio AAC
- **Duração:** 5–8s cada (sugestão)

O script aceita qualquer formato que o ffmpeg entenda — ele re-encode tudo no
final para 1280×720/30fps/AAC, então não precisa ser perfeito, mas seguir o
padrão acima evita surpresas.

## Como funciona

```
[branding/intro.mp4] + [thumbnail + waveform + áudio do dia] + [branding/outro.mp4]
```

- Se `intro.mp4` **não existir** → o script gera o vídeo só com o episódio (não quebra o dia)
- Se `outro.mp4` **não existir** → idem
- Os dois podem existir ou não, independentemente

## Gerar o vídeo de um episódio

```bash
python3 scripts/youtube_video_generator.py --date 2026-08-07
# → /tmp/vld_yt_2026-08-07.mp4
```
