# APIs gratuitas / chaves de produção

Credenciais **nunca** entram no git. Este arquivo só documenta *onde* cada chave mora e *quem* a consome.

## ElevenLabs (`ELEVENLABS_API_KEY`)

| | |
|---|---|
| Variável | `ELEVENLABS_API_KEY` (alias `XI_API_KEY`) |
| Onde | `.env` do projeto **ou** `~/.hermes/.env` (o segundo é o que o servidor usa hoje) |
| Header | `xi-api-key` |
| Consumidores | `scripts/tts_fallback_elevenlabs.py` (TTS fallback), `scripts/isolate_voice.py` (Voice Isolator) |

### Voice Isolator

- Endpoint: `POST https://api.elevenlabs.io/v1/audio-isolation`
- Corpo: `multipart/form-data` com o campo `audio` (WAV/MP3 ou faixa extraída de MP4 via ffmpeg)
- Cota: `GET https://api.elevenlabs.io/v1/user/subscription` — **não** gasta créditos

```bash
python3 scripts/isolate_voice.py --check-credits
python3 scripts/isolate_voice.py branding/encerramento/gravacoes/final01.mp4 --out /tmp/final01_limpo.mp4
```

Não commitar a chave. Se precisar rotacionar, edite o `.env` correspondente e **não** mostre o valor no chat.

## Outras chaves (já no `.env` do projeto)

Gemini, OpenRouter, R2, Supabase, Tavily, Pexels/Pixabay, Cloudflare — ver nomes em `.env` (não listar valores aqui).
