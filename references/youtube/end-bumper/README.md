# End Bumper — Brasil e Mundo

Esta pasta é o slot reservado para o vídeo de encerramento drop-in do especial Brasil e Mundo.

## Contrato do Arquivo

- **Arquivo esperado:** `references/youtube/end-bumper/outro.mp4`
- **Vídeo:** 1920×1080, yuv420p, 30fps, H.264
- **Áudio:** AAC 48kHz (música + CTA visual; Peter NÃO fala por cima)
- **Duração sugerida:** 8–12s
- **Comportamento do pipeline:** `ffmpeg concat` após o vídeo onair gerado; se o arquivo `outro.mp4` não existir, o pipeline segue normalmente sem encerramento extra (no-op).
