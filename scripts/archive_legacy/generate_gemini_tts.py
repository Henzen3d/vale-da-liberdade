#!/usr/bin/env python3
"""
Gera áudio single-speaker para o Web Jornal Vale da Liberdade via Gemini TTS.

Melhorias sobre a versão anterior:
- Integração com tts_preprocessor para substituições obrigatórias da SKILL
- Retry com backoff exponencial para rate limiting da API
- Logging estruturado
- Validação do conteúdo antes de enviar
"""

import argparse
import logging
import os
import sys
import time
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from gemini_client import GeminiClient

# Importar pré-processador TTS
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_preprocessor import preprocess_for_tts

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gemini-tts")

VOZES = {
    "peter": "Charon",
    "ricardo": "Kore",
}

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # segundos


def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    """Salva dados PCM raw como arquivo WAV."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def generate_with_retry(client, prompt, voice_name):
    """Gera áudio através do GeminiClient (que gerencia retries e rate limiting)."""
    response = client.models.generate_content(
        model="gemini-3.1-flash-tts-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        ),
    )
    data = response.candidates[0].content.parts[0].inline_data.data
    log.info(f"Áudio recebido: {len(data)} bytes")
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Gera áudio do Web Jornal Vale da Liberdade via Gemini TTS"
    )
    parser.add_argument(
        "--voz", required=True, choices=VOZES.keys(),
        help="Apresentador: peter ou ricardo"
    )
    parser.add_argument("--texto", required=True, help="Caminho do arquivo de texto do episódio")
    parser.add_argument("--saida", help="Caminho completo do arquivo de saída .wav (opcional)")
    parser.add_argument(
        "--skip-preprocess", action="store_true",
        help="Pular pré-processamento TTS (usar se o texto já foi processado)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("FALHA: defina GEMINI_API_KEY antes de executar.")
        sys.exit(2)

    texto_path = Path(args.texto)
    if not texto_path.exists():
        log.error(f"FALHA: arquivo não encontrado: {texto_path}")
        sys.exit(2)

    conteudo = texto_path.read_text(encoding="utf-8").strip()
    if not conteudo:
        log.error("FALHA: arquivo de texto vazio.")
        sys.exit(2)

    # Pré-processamento TTS (substituições obrigatórias da SKILL)
    if not args.skip_preprocess:
        log.info("Aplicando pré-processamento TTS...")
        conteudo = preprocess_for_tts(conteudo)
        log.info(f"Texto processado: {len(conteudo.split())} palavras")

    voice_name = VOZES[args.voz]
    project_root = Path(__file__).resolve().parents[1]
    audio_dir = project_root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if args.saida:
        out_path = Path(args.saida)
    else:
        stem = texto_path.stem
        out_path = audio_dir / f"{stem}-{args.voz}.wav"

    client = GeminiClient()

    prompt = (
        "Leia em português do Brasil, no estilo de apresentador de podcast "
        f"jornalístico:\n\n{conteudo}"
    )

    data = generate_with_retry(client, prompt, voice_name)
    wave_file(str(out_path), data)
    log.info(f"OK {out_path}")


if __name__ == "__main__":
    main()
