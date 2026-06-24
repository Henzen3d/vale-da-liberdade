#!/usr/bin/env python3
"""
Gera áudio multi-locutor (Peter + Ricardo) para o Web Jornal Vale da Liberdade.

[FASE 0.4] Pausas acústicas reais via chunking por marcadores:
  - Divide o texto nos marcadores [PAUSA] (1.5s) e [PAUSA_CURTA] (0.5s)
  - Gera áudio por segmento (chamada TTS independente por chunk)
  - Concatena chunks com silêncio real via ffmpeg
  - Resolve CHUNK_TARGET_WORDS (300 palavras) que era código morto

[FASE 0.5] Pós-processamento profissional:
  - Loudnorm EBU R128 de 2 passos (mede → aplica), substituindo o passo único
  - Sample rate 44.1kHz (up de 24kHz) para qualidade podcast
  - Highpass + compressor + EQ mantidos

Melhorias sobre versão anterior:
  - Retry com backoff exponencial para rate limiting da API
  - Logging estruturado
  - Validação: verifica se ambos os locutores têm falas no texto
  - Chunking por pausa: episódios longos divididos em segmentos com silêncio real
"""
import argparse
import asyncio
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import edge_tts
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Importar pré-processador TTS
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_preprocessor import preprocess_for_tts

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gemini-tts-multi")

SPEAKERS = {
    "Peter": "Charon",
    "Ricardo": "Schedar",
}

# Persona descriptions for TTS style guidance
SPEAKER_PERSONAS = {
    "Peter": (
        "Tom irônico, provocador e libertário. Fala como quem desafia o status quo, "
        "destaca coerção estatal, questiona burocracia, rejeita soluções do governo. "
        "Entonação confiante, cética, às vezes sarcástica. Não soa neutro."
    ),
    "Ricardo": (
        "Tom analítico, ponderado, institucional. Contraponto racional baseado em dados "
        "e evidências. Reconhece problemas mas contextualiza com perspectivas práticas. "
        "Entonação calma, medida, equilibrada. Soa como analista sério."
    ),
}

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # segundos
CHUNK_TARGET_WORDS = 300  # limite por bloco para evitar degradação TTS

# Duração dos silêncios (em segundos)
PAUSA_LONGA_S = 1.5    # [PAUSA] — entre quadros
PAUSA_CURTA_S = 0.5    # [PAUSA_CURTA] — entre falas longas

SAMPLE_RATE = 44100    # Hz — qualidade podcast (Fase 0.5)
SAMPLE_WIDTH = 2       # bytes (16-bit PCM)
CHANNELS = 1           # mono


def read_episode(path: Path) -> str:
    """Lê o arquivo de episódio."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Arquivo de episódio vazio.")
    return text


def validate_speakers(text: str, speakers: list[str]) -> list[str]:
    """Verifica se todos os speakers esperados têm falas no texto."""
    missing = []
    for speaker in speakers:
        if f"{speaker}:" not in text:
            missing.append(speaker)
    return missing


def build_prompt(segment_text: str, speakers: list[str] | None = None) -> str:
    """Constrói o prompt para o Gemini TTS com instruções de estilo por speaker.
    
    Recebe um segmento de texto (já sem marcadores de pausa — eles foram usados
    para dividir os chunks). O áudio de cada chunk é gerado independentemente e
    concatenado com silêncio real pelo pipeline.
    """
    speakers = speakers or list(SPEAKERS.keys())
    persona_lines = []
    for sp in speakers:
        if sp in SPEAKER_PERSONAS:
            persona_lines.append(f"- {sp}: {SPEAKER_PERSONAS[sp]}")
    personas_text = "\n".join(persona_lines)

    # Segmento já está limpo de marcadores de pausa (split aconteceu antes)
    clean_text = segment_text.strip()

    return (
        "Você é um sistema de síntese de voz para podcast jornalístico com dois apresentadores.\n"
        "Leia exatamente o texto abaixo, sem adicionar, remover ou alterar nenhuma palavra.\n"
        "Aplique a entonação e personalidade indicada para cada locutor:\n\n"
        f"{personas_text}\n\n"
        "O texto já contém os rótulos 'Peter:' e 'Ricardo:' antes de cada fala. "
        "Mantenha a troca natural de turnos como em um programa de rádio ao vivo.\n\n"
        "---\n\n" + clean_text
    )


def split_large_chunk(text: str, max_words: int) -> list[str]:
    """
    Sub-divide um pedaço de texto que é muito longo para evitar degradação do TTS.
    Tenta dividir em linhas (limite de turnos de falas) ou sentenças.
    Garante que cada sub-chunk tenha o rótulo do locutor ativo no início,
    se não começar com um rótulo de locutor.
    """
    lines = text.splitlines()
    sub_chunks = []
    current_lines = []
    current_words = 0
    active_speaker = None
    
    # Função auxiliar para detectar speaker no início da linha
    def get_speaker(line_str: str) -> str | None:
        for sp in SPEAKERS:
            if line_str.startswith(f"{sp}:"):
                return sp
        return None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Detecta se a linha muda o locutor ativo
        line_speaker = get_speaker(line)
        if line_speaker:
            active_speaker = line_speaker
            
        line_words = len(line.split())
        
        if current_words + line_words > max_words and current_lines:
            sub_chunks.append("\n".join(current_lines))
            current_lines = []
            current_words = 0
            
        if line_words > max_words:
            # Se a própria linha excede o limite, divide por sentenças
            sentences = re.split(r'(?<=[.!?])\s+', line)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sent_words = len(sentence.split())
                
                # Se a frase excede ou se precisamos fechar o chunk atual
                if current_words + sent_words > max_words and current_lines:
                    sub_chunks.append("\n".join(current_lines))
                    current_lines = []
                    current_words = 0
                
                # Se estamos iniciando um sub-chunk e a frase não tem o prefixo do speaker
                if not current_lines and active_speaker and not get_speaker(sentence):
                    sentence = f"{active_speaker}: {sentence}"
                    sent_words = len(sentence.split())
                    
                current_lines.append(sentence)
                current_words += sent_words
        else:
            # Se estamos iniciando um sub-chunk e a linha não tem o prefixo do speaker
            if not current_lines and active_speaker and not line_speaker:
                line = f"{active_speaker}: {line}"
                line_words = len(line.split())
                
            current_lines.append(line)
            current_words += line_words
            
    if current_lines:
        sub_chunks.append("\n".join(current_lines))
        
    return sub_chunks


def split_into_chunks(text: str) -> list[tuple[str, float]]:
    """
    Divide o texto nos marcadores de pausa e por limite de palavras (CHUNK_TARGET_WORDS),
    retornando lista de (chunk_text, pause_after_s).
    
    O último chunk tem pause_after_s = 0.0 (sem silêncio após o final).
    """
    # Regex para capturar o marcador e saber qual tipo é
    pattern = re.compile(r"\[(PAUSA_CURTA|PAUSA)\]")
    
    chunks: list[tuple[str, float]] = []
    pos = 0
    
    for match in pattern.finditer(text):
        marker_type = match.group(1)
        pause_s = PAUSA_CURTA_S if marker_type == "PAUSA_CURTA" else PAUSA_LONGA_S
        
        chunk = text[pos:match.start()].strip()
        if chunk:  # Ignorar chunks vazios (duplos marcadores)
            chunks.append((chunk, pause_s))
        pos = match.end()
    
    # Último segmento (após o último marcador, ou o texto todo se não houver marcadores)
    remainder = text[pos:].strip()
    if remainder:
        chunks.append((remainder, 0.0))
    
    if not chunks:
        chunks = [(text.strip(), 0.0)]
    
    log.info(f"Texto dividido em {len(chunks)} chunk(s) com marcadores de pausa.")
    
    # Sub-chunking por CHUNK_TARGET_WORDS para evitar degradação do TTS
    final_chunks = []
    for chunk_text, pause_after_s in chunks:
        word_count = len(chunk_text.split())
        if word_count > CHUNK_TARGET_WORDS:
            log.info(f"Chunk com {word_count} palavras excede o limite de {CHUNK_TARGET_WORDS}. Sub-dividindo...")
            sub_chunks = split_large_chunk(chunk_text, CHUNK_TARGET_WORDS)
            for j, sub_chunk in enumerate(sub_chunks):
                # O último sub-chunk herda a pausa original; os intermediários têm 0 de pausa
                sub_pause = pause_after_s if j == len(sub_chunks) - 1 else 0.0
                final_chunks.append((sub_chunk, sub_pause))
        else:
            final_chunks.append((chunk_text, pause_after_s))
            
    log.info(f"Após sub-chunking por limite de palavras, total de chunks: {len(final_chunks)}")
    return final_chunks


def generate_silence_wav(duration_s: float, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Gera dados PCM de silêncio para a duração especificada."""
    num_samples = int(math.ceil(duration_s * sample_rate))
    # 16-bit PCM = 2 bytes por amostra
    return b"\x00" * (num_samples * SAMPLE_WIDTH * CHANNELS)


def wave_file(filename, pcm, channels=CHANNELS, rate=SAMPLE_RATE, sample_width=SAMPLE_WIDTH):
    """Salva dados PCM raw como arquivo WAV."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def resample_pcm(pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """
    Reamostrage simples de PCM 16-bit mono via ffmpeg.
    O Gemini TTS retorna 24kHz; precisamos de 44.1kHz para EBU R128.
    """
    if from_rate == to_rate:
        return pcm_data
    
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp_in:
        tmp_in.write(pcm_data)
        tmp_in_path = tmp_in.name
    
    tmp_out_path = tmp_in_path + ".resampled.raw"
    
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "s16le", "-ar", str(from_rate), "-ac", str(CHANNELS),
            "-i", tmp_in_path,
            "-f", "s16le", "-ar", str(to_rate), "-ac", str(CHANNELS),
            tmp_out_path
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            log.warning(f"ffmpeg resample falhou, usando PCM original: {proc.stderr.decode()}")
            return pcm_data
        
        with open(tmp_out_path, "rb") as f:
            return f.read()
    finally:
        for p in [tmp_in_path, tmp_out_path]:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


def run_ffmpeg_chain_2pass(input_wav: Path, output_mp3: Path) -> None:
    """
    Pós-processamento profissional com loudnorm EBU R128 de 2 passos.
    
    Passo 1: Medir LUFS/LRA/true-peak do arquivo.
    Passo 2: Aplicar loudnorm linear com os valores medidos (mais preciso que passo único).
    Também: highpass, compressor, EQ, 44.1kHz, 192kbps MP3.
    """
    log.info("Aplicando pós-processamento EBU R128 (2 passos) e gerando MP3 final...")

    # ── Passo 1: medir loudness ──────────────────────────────────────────────
    cmd_measure = [
        "ffmpeg", "-y",
        "-i", str(input_wav),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    proc1 = subprocess.run(
        cmd_measure, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    # Extrair JSON do stderr do ffmpeg (loudnorm imprime para stderr)
    measured_il = "-23.0"
    measured_lra = "7.0"
    measured_tp = "-2.0"
    measured_thresh = "-33.0"
    measured_offset = "0.0"
    
    try:
        stderr_text = proc1.stderr
        json_match = re.search(r"\{[^{}]+\}", stderr_text, re.S)
        if json_match:
            loudnorm_data = json.loads(json_match.group(0))
            measured_il = loudnorm_data.get("input_i", measured_il)
            measured_lra = loudnorm_data.get("input_lra", measured_lra)
            measured_tp = loudnorm_data.get("input_tp", measured_tp)
            measured_thresh = loudnorm_data.get("input_thresh", measured_thresh)
            measured_offset = loudnorm_data.get("target_offset", measured_offset)
            log.info(
                f"Loudnorm medido: I={measured_il} LUFS, LRA={measured_lra}, "
                f"TP={measured_tp}, offset={measured_offset}"
            )
    except Exception as e:
        log.warning(f"Não foi possível parsear dados de loudnorm: {e}. Usando valores padrão.")

    # ── Passo 2: aplicar loudnorm linear + filtros ───────────────────────────
    loudnorm_filter = (
        f"loudnorm=I=-16:TP=-1.5:LRA=11:"
        f"measured_I={measured_il}:measured_LRA={measured_lra}:"
        f"measured_TP={measured_tp}:measured_thresh={measured_thresh}:"
        f"offset={measured_offset}:linear=true:print_format=summary"
    )
    audio_filter = (
        f"highpass=f=80,"
        f"acompressor=threshold=-25dB:ratio=3:attack=50:release=200,"
        f"equalizer=f=3000:width_type=h:width=1000:g=3,"
        f"{loudnorm_filter}"
    )

    cmd_apply = [
        "ffmpeg", "-y",
        "-i", str(input_wav),
        "-af", audio_filter,
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-acodec", "libmp3lame",
        "-b:a", "192k",
        str(output_mp3),
    ]
    proc2 = subprocess.run(cmd_apply, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc2.returncode != 0:
        raise RuntimeError(f"ffmpeg (passo 2) falhou:\n{proc2.stderr}")
    
    log.info(f"✅ Loudnorm EBU R128 2-pass aplicado → {output_mp3}")


def generate_with_retry(client, prompt, speaker_voice_configs, max_retries=MAX_RETRIES):
    """Gera áudio multi-locutor com retry e backoff exponencial."""
    for attempt in range(1, max_retries + 1):
        try:
            speakers_str = ", ".join(
                f"{svc.speaker}={svc.voice_config.prebuilt_voice_config.voice_name}"
                for svc in speaker_voice_configs
            )
            log.info(f"Tentativa {attempt}/{max_retries} — speakers: {speakers_str}")

            response = client.models.generate_content(
                model="gemini-3.1-flash-tts-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=speaker_voice_configs
                        )
                    ),
                ),
            )

            data = response.candidates[0].content.parts[0].inline_data.data
            log.info(f"Áudio recebido: {len(data)} bytes ({len(data) / (24000 * 2):.1f}s @ 24kHz estimados)")
            return data

        except Exception as exc:
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            log.warning(f"Erro na tentativa {attempt}: {exc}")
            if attempt < max_retries:
                log.info(f"Aguardando {delay}s antes de retry...")
                time.sleep(delay)
            else:
                log.error(f"Todas as {max_retries} tentativas falharam.")
                raise


_FALLBACK_EDGE_TTS_VOICE = "pt-BR-AntonioNeural"


def _mp3_to_pcm_24k(mp3_path: Path) -> bytes:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(mp3_path),
        "-f", "s16le",
        "-ac", "1",
        "-ar", "24000",
        "-acodec", "pcm_s16le",
        "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg converteu MP3→PCM com erro: {proc.stderr.decode()[:200]}")
    return proc.stdout


async def _edge_tts_stream_audio(text: str, voice: str = _FALLBACK_EDGE_TTS_VOICE) -> bytes:
    communicator = edge_tts.Communicate(text=text, voice=voice)
    audio_bytes = b""
    async for chunk in communicator.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


def _edge_tts_generate_audio(text: str, voice: str = _FALLBACK_EDGE_TTS_VOICE) -> bytes:
    text = text.replace("Peter:", "").replace("Ricardo:", "").strip()
    if not text:
        return b""
    try:
        mp3_bytes = asyncio.run(_edge_tts_stream_audio(text, voice=voice))
    except Exception as exc:
        raise RuntimeError(f"edge-tts stream falhou: {exc}")
    if not mp3_bytes:
        return b""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    tmp_path.write_bytes(mp3_bytes)
    try:
        return _mp3_to_pcm_24k(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def generate_fallback_edge_tts(text: str) -> bytes:
    """Fallback single-voice para quando Gemini falhar."""
    try:
        log.warning("⚠️  Gemini TTS indisponível. Acionando fallback edge-tts (voz única)...")
        audio = _edge_tts_generate_audio(text)
        log.info(f"Fallback edge-tts OK: {len(audio)} bytes")
        return audio
    except Exception as exc:
        log.error(f"Fallback edge-tts também falhou: {exc}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Gera áudio multi-locutor do Web Jornal Vale da Liberdade"
    )
    parser.add_argument("--episode", required=True, help="Caminho do episódio (.md ou .txt)")
    parser.add_argument("--out", help="Caminho completo do .wav de saída")
    parser.add_argument(
        "--speakers", nargs="*", default=None,
        help="Nomes dos speakers, ex: Peter Ricardo"
    )
    parser.add_argument(
        "--skip-preprocess", action="store_true",
        help="Pular pré-processamento TTS (usar se o texto já foi processado)"
    )
    parser.add_argument(
        "--no-chunk", action="store_true",
        help="Desabilitar chunking por pausas (gera áudio em uma única chamada TTS)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("FALHA: defina GEMINI_API_KEY antes de executar.")
        sys.exit(2)

    episode_path = Path(args.episode)
    if not episode_path.exists():
        log.error(f"FALHA: episódio não encontrado: {episode_path}")
        sys.exit(2)

    episode_text = read_episode(episode_path)
    speakers = args.speakers or list(SPEAKERS.keys())

    # Pré-processamento TTS (substituições obrigatórias da SKILL)
    if not args.skip_preprocess:
        log.info("Aplicando pré-processamento TTS...")
        episode_text = preprocess_for_tts(episode_text)
        log.info(f"Texto processado: {len(episode_text.split())} palavras")

    # Validar que ambos os speakers têm falas
    missing = validate_speakers(episode_text, speakers)
    if missing:
        log.warning(
            f"⚠️  Speakers sem falas no texto: {', '.join(missing)}. "
            f"O áudio pode ficar incompleto."
        )

    project_root = Path(__file__).resolve().parents[1]
    audio_dir = project_root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.out) if args.out else audio_dir / f"{episode_path.stem}-completo.wav"

    client = genai.Client()

    speaker_voice_configs = []
    for speaker in speakers:
        if speaker not in SPEAKERS:
            log.error(f"Speaker desconhecido: {speaker}")
            sys.exit(2)
        speaker_voice_configs.append(
            types.SpeakerVoiceConfig(
                speaker=speaker,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=SPEAKERS[speaker]
                    )
                ),
            )
        )

    # ── Chunking por pausas (Fase 0.4) ──────────────────────────────────────
    if args.no_chunk:
        # Modo legado: texto inteiro em uma chamada (sem chunking)
        log.info("Modo sem chunking (--no-chunk): gerando áudio em chamada única...")
        clean_text = re.sub(r"\[PAUSA(?:_CURTA)?\]", "", episode_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
        prompt = build_prompt(clean_text, speakers)
        try:
            data = generate_with_retry(client, prompt, speaker_voice_configs)
        except Exception as exc:
            log.warning(f"Gemini falhou (--no-chunk): {exc}")
            data = generate_fallback_edge_tts(clean_text)
        # Resample 24kHz → 44.1kHz quando Gemini retornar bytes
        if data:
            pcm_44k = resample_pcm(data, from_rate=24000, to_rate=SAMPLE_RATE)
            wave_file(str(out_path), pcm_44k)
            log.info(f"OK {out_path}")
        else:
            raise RuntimeError("Nenhum áudio gerado (fallback edge-tts retornou vazio).")
    else:
        # Modo chunking: divide por [PAUSA]/[PAUSA_CURTA], insere silêncio real
        chunks = split_into_chunks(episode_text)
        all_pcm = b""

        for i, (chunk_text, pause_after_s) in enumerate(chunks, start=1):
            # Ignorar chunks que não têm falas de speakers
            has_speaker = any(f"{sp}:" in chunk_text for sp in speakers)
            if not has_speaker:
                log.debug(f"Chunk {i}: sem speaker, pulando geração TTS")
                if pause_after_s > 0:
                    silence = generate_silence_wav(pause_after_s)
                    all_pcm += silence
                continue

            word_count = len(chunk_text.split())
            log.info(f"Chunk {i}/{len(chunks)}: {word_count} palavras, pausa_após={pause_after_s}s")

            prompt = build_prompt(chunk_text, speakers)
            try:
                chunk_pcm = generate_with_retry(client, prompt, speaker_voice_configs)
            except Exception as exc:
                log.warning(f"Gemini TTS falhou no chunk {i}: {exc}")
                try:
                    fallback_data = generate_fallback_edge_tts(chunk_text)
                except Exception as fb_exc:
                    raise RuntimeError(
                        f"Fallback edge-tts também falhou no chunk {i}: {fb_exc}"
                    ) from fb_exc
                if not fallback_data:
                    raise RuntimeError(f"Fallback edge-tts vazio no chunk {i}.")
                chunk_pcm = fallback_data

            # Resample 24kHz → 44.1kHz
            chunk_pcm_44k = resample_pcm(chunk_pcm, from_rate=24000, to_rate=SAMPLE_RATE)
            all_pcm += chunk_pcm_44k

            # Inserir silêncio real após o chunk
            if pause_after_s > 0:
                silence = generate_silence_wav(pause_after_s)
                all_pcm += silence
                log.info(f"  → Silêncio de {pause_after_s}s inserido após chunk {i}")

        duration_est = len(all_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
        log.info(f"PCM combinado: {len(all_pcm)} bytes (~{duration_est:.1f}s @ {SAMPLE_RATE}Hz)")
        wave_file(str(out_path), all_pcm)
        log.info(f"OK {out_path}")

    # ── Pós-processamento EBU R128 2-pass (Fase 0.5) ────────────────────────
    mp3_path = out_path.with_suffix(".mp3")
    mp3_path = mp3_path.with_name(out_path.stem.replace("-completo", "") + "-vale-da-liberdade.mp3")
    try:
        run_ffmpeg_chain_2pass(out_path, mp3_path)
        log.info(f"✅ MP3 final com EBU R128 2-pass: {mp3_path}")
    except Exception as e:
        log.error(f"Falha no pós-processamento: {e}")
        log.info(f"WAV sem pós-processamento disponível em: {out_path}")


if __name__ == "__main__":
    main()
