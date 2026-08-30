# Biblioteca de B-Roll — Brasil e Mundo

Esta pasta armazena clipes curtos de transição de vídeo utilizados pelo compositor de Brasil e Mundo (`bm_mockup_video.py`) entre diferentes matérias/cenas.

## Contrato dos Arquivos

- **Resolução:** 1920×1080
- **FPS:** 30fps
- **Duração:** 0.8s a 1.5s
- **Codec:** H.264 (MP4)
- **Áudio:** Mudo ou ignorado no mux
- **Conteúdo:** Sem marcas d'água de terceiros, sem pessoas reconhecíveis em close, sem logos de canais.
- **Tags recomendadas:** `city`, `paper`, `gavel`, `market`, `protest`, `night`, `map`, `tech`, `money`

## Manifesto Machine-Readable

Os clipes disponíveis devem ser cadastrados no arquivo `_index.json` desta pasta:

```json
{
  "clips": [
    {
      "id": "broll-city-01",
      "file": "broll-city-01.mp4",
      "tags": ["city", "night"],
      "dur_s": 1.2
    }
  ]
}
```

Se a lista de clipes estiver vazia (`"clips": []`), o pipeline realiza corte direto ou transição padrão sem gerar erros.
