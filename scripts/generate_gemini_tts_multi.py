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

from dotenv import load_dotenv
from google import genai
from google.genai import types
from gemini_client import GeminiClient, GeminiMultiClient

# Importar pré-processador TTS
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from tts_preprocessor import preprocess_for_tts, _normalize_currency

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)
load_dotenv()


def _candidate_gemini_keys() -> list[str]:
    """Coleta GEMINI_API_KEY do ambiente e dos .env (projeto + Hermes)."""
    seen: set[str] = set()
    keys: list[str] = []
    sources = [os.environ.get("GEMINI_API_KEY", "").strip()]
    for path in (PROJECT_ROOT / ".env", Path.home() / ".hermes" / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                # Aceita GEMINI_API_KEY e variações GEMINI_API_KEY_2, _3, etc.
                if not line.startswith("GEMINI_API_KEY") or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    sources.append(v)
        except Exception:
            pass
    for k in sources:
        if not k or "***" in k or k in seen:
            continue
        seen.add(k)
        keys.append(k)
    return keys


def _make_gemini_client() -> "GeminiClient | GeminiMultiClient":
    keys = _candidate_gemini_keys()
    if not keys:
        # tenta ADC / env default do SDK
        return GeminiClient()
    if len(keys) == 1:
        return GeminiClient(api_key=keys[0])
    # Múltiplas chaves (contas/projetos diferentes) → intercala por quota
    log.info(f"GeminiMultiClient com {len(keys)} chaves (intercalamento por RPD/RPM)")
    return GeminiMultiClient(keys)


try:
    import edge_tts  # type: ignore
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    edge_tts = None  # type: ignore
    _EDGE_TTS_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gemini-tts-multi")

SPEAKERS = {
    "Peter": "Charon",
    "Ricardo": "Kore",  # feminina — avaliação de troca de locutor (não permanente)
}

# Inverso de SPEAKERS: voice_name → speaker (para system_instruction single)
_VOICE_TO_SPEAKER = {v: k for k, v in SPEAKERS.items()}


def _speaker_for_voice(voice_name: str) -> str:
    """Resolve o speaker (ex.: 'Peter') a partir do voice_name (ex.: 'Charon')."""
    return _VOICE_TO_SPEAKER.get(voice_name, "Peter")

# Sotaque pt-BR: neutro (sul suave) — NÃO carioca, NÃO gaúcho carregado, NÃO manezinho/Floripa
ACCENT_GUIDANCE = (
    "SOTAQUE (obrigatório para TODOS os locutores): português brasileiro NEUTRO, "
    "próximo do padrão de telejornal/podcast nacional com leve coloração do Sul "
    "(Santa Catarina / Vale do Itajaí), mas SEM sotaque carregado. "
    "PROIBIDO: sotaque carioca (chiado em /s/, melodia do Rio); "
    "sotaque gaúcho/RS forte (melodia e léxico típicos); "
    "sotaque manezinho/florianopolitano carregado; "
    "sotaque nordestino, paulistano interiorano marcado ou português de Portugal. "
    "Dicção clara, ritmo de rádio noticioso, vogais abertas naturais do pt-BR, "
    "sem chiado carioca e sem cadência cantada regional."
)

# Persona descriptions for TTS style guidance (tom/atitude — o sotaque vem de ACCENT_GUIDANCE)
SPEAKER_PERSONAS = {
    "Peter": (
        "Tom irônico, provocador e libertário. Fala como quem desafia o status quo, "
        "destaca coerção estatal, questiona burocracia, rejeita soluções do governo. "
        "Entonação confiante, cética, às vezes sarcástica. Evite soar acelerado ou teatral; "
        "a ironia vem do subtexto e do timing, não de gritaria. Atitude NÃO é neutra — "
        "mas o SOTAQUE continua o pt-BR neutro definido acima."
    ),
    "Ricardo": (
        "Tom super animado, elétrico e expressivo de comentarista de rádio ao vivo. "
        "Contraponto analítico baseado em dados reais, fatos econômicos e bom senso prático, "
        "mas sempre com sensação de urgência, presença e calor humano. "
        "Ritmo muito vivo, com pausas inteligentes, ataques de energia nas palavras-chave "
        "e variação clara de intenção entre uma frase e outra. "
        "Transmite indignação lúcida com o desperdício estatal e a burocracia, "
        "sem nunca soar monótono, robótico, desanimado ou burocrático. "
        "REGRAS OPERACIONAIS (importante): fuja completamente de nota oficial/assessoria; "
        "use micro-pausas antes de números/dados; destaque uma palavra-chave por frase; "
        "abra cada fala com um salto leve de energia (como quem pega o ar no estúdio); "
        "mantenha um tempo ligeiramente mais rápido que o Peter; use perguntas retóricas "
        "curtas quando ajudar a criar impulso. "
        "SOTAQUE: mesmo pt-BR neutro (não regionalizar)."
    ),
}

MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # segundos
CHUNK_TARGET_WORDS = 300  # ~5 chunks p/ 1500 palavras → cabe nos 10 RPD/chave; 3 keys × RR ≈ 30 RPD efetivos
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
# Default = Diário multi-locutor. BM (Peter solo) sobrescreve com
# --model gemini-3.1-flash-tts-preview em bm_pipeline.step_audio.
TTS_MODEL = DEFAULT_TTS_MODEL

# Duração dos silêncios (em segundos)
PAUSA_LONGA_S = 1.5    # [PAUSA] — entre quadros
PAUSA_CURTA_S = 0.5    # [PAUSA_CURTA] — entre falas longas

# Temperatura TTS (Gemini): global (mesmo valor para todos os chunks/speakers).
# 0.9 = mais expressivo/animado (pode introduzir variação maior de entonação).
TTS_TEMPERATURE = 0.90

SAMPLE_RATE = 44100    # Hz — qualidade podcast (Fase 0.5)
SAMPLE_WIDTH = 2       # bytes (16-bit PCM)
CHANNELS = 1           # mono
GEMINI_PCM_RATE = 24000

# Chunks "vazios"/quase silêncio: ~0.35s @ 24kHz 16-bit mono ≈ 16800 bytes
MIN_CHUNK_PCM_BYTES_24K = 16_000
# Texto mínimo para gastar uma chamada TTS
MIN_CHUNK_WORDS = 3
# MP3 final mínimo (entrega)
MIN_FINAL_MP3_BYTES = 1_000_000
MIN_FINAL_DURATION_S = 7 * 60  # ~7 min piso duro (meta 8–15)


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
    """Constrói o prompt (corpo) para o Gemini TTS.

    As personas/diretrizes (Audio Profile + Director's Notes) vivem no campo
    system_instruction (build_system_instruction) — enviado em toda chamada.
    O corpo fica enxuto: só a ordem de leitura + o texto segmentado.
    """
    speakers = speakers or list(SPEAKERS.keys())
    clean_text = segment_text.strip()

    if len(speakers) == 1:
        sp = speakers[0]
        return (
            "Você é um sistema de síntese de voz para podcast com locutor solo. "
            "Siga o Audio Profile e as diretrizes das system instructions. "
            "Leia exatamente o texto abaixo, sem adicionar, remover ou alterar nenhuma palavra. "
            f"O texto já contém o rótulo '{sp}:' antes de cada fala. "
            "Mantenha a entonação natural, contínua e expressiva.\n\n"
            "---\n\n" + clean_text
        )

    return (
        "Você é um sistema de síntese de voz para podcast jornalístico com dois apresentadores. "
        "Siga o Audio Profile e as diretrizes das system instructions. "
        "Leia exatamente o texto abaixo, sem adicionar, remover ou alterar nenhuma palavra. "
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
        f"acompressor=threshold=-22dB:ratio=2.2:attack=25:release=150,"
        f"equalizer=f=3500:width_type=h:width=1200:g=2.5,"
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


def build_system_instruction(speakers: list[str] | None = None) -> str:
    """System Instruction formal (Audio Profile + Director's Notes).

    Recomendação dev gemini-3.1-flash-tts-preview (2026-08-09): diretrizes no
    campo system_instruction dão mais peso que no corpo do prompt e garantem
    consistência de timbre entre chunks. Enviada em TODA chamada do episódio.
    """
    speakers = speakers or list(SPEAKERS.keys())
    persona_lines = []
    for sp in speakers:
        if sp in SPEAKER_PERSONAS:
            persona_lines.append(f"- {sp} ({SPEAKERS.get(sp, sp)}): {SPEAKER_PERSONAS[sp]}")
    personas_text = "\n".join(persona_lines) if persona_lines else "- Peter (Charon), Ricardo (Kore)"
    return (
        "# Audio Profile\n"
        f"{personas_text}\n\n"
        "# Scene\n"
        "Estúdio de podcast jornalístico profissional, ambiente dinâmico e expressivo.\n\n"
        "# Director's Notes\n"
        "- Leia o texto EXATAMENTE como fornecido, sem adicionar, remover ou alterar palavras.\n"
        "- Mantenha a troca de turnos natural, como rádio ao vivo; respire nas pausas.\n"
        "- Atuação de Ricardo (Kore): voz feminina distinta da de Peter (Charon). Entusiasmo de rádio ao vivo, ritmo ágil, variações de entonação, pausas curtas antes de números-chave. Jamais soar igual ao Peter, monocórdico ou como leitor de notas oficiais.\n"
        f"{ACCENT_GUIDANCE}"
    )


def generate_with_retry(client, prompt, speaker_voice_configs, model: str | None = None, temperature: float | None = None):
    """Gera áudio multi-locutor através do GeminiClient (que gerencia retries e rate limiting)."""
    model = model or TTS_MODEL
    temperature = TTS_TEMPERATURE if temperature is None else float(temperature)
    speakers = [cfg.speaker for cfg in speaker_voice_configs]
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            temperature=temperature,
            system_instruction=build_system_instruction(speakers),
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=speaker_voice_configs
                )
            ),
        ),
    )
    data = response.candidates[0].content.parts[0].inline_data.data
    log.info(f"Áudio multi recebido ({model}): {len(data)} bytes ({len(data) / (24000 * 2):.1f}s @ 24kHz estimados)")
    return data


def generate_single_speaker_pcm(client, text: str, voice_name: str, model: str | None = None) -> bytes:
    """TTS de uma fala com UMA voz pré-definida (Charon/Kore).

    Mais confiável que multi-speaker: o Gemini multi frequentemente colapsa
    em uma única voz no episódio inteiro.
    """
    text = text.strip()
    if not text:
        return b""
    model = model or TTS_MODEL
    # Instrução mínima de idioma + sotaque; o voice_name carrega o timbre.
    # system_instruction com Audio Profile garante consistência de timbre
    # ENTRE chamadas (chunks/halves) — sem isso a voz varia a cada chamada.
    prompt = (
        "Leia em português do Brasil, de forma natural, apenas o texto a seguir, "
        "sem adicionar palavras. "
        f"{ACCENT_GUIDANCE} "
        "Texto:\n\n" + text
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            temperature=TTS_TEMPERATURE,  # default; pode ser ajustado por chunk no modo PACKED
            system_instruction=build_system_instruction([_speaker_for_voice(voice_name)]),
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
    return data


def sanitize_tts_text(text: str) -> str:
    """Sanitiza texto p/ TTS: remove links/emojis e expande símbolos comuns.

    Recomendação do dev gemini-2.5-flash-preview-tts (2026-08-09): símbolos
    e marcações complexas degradam a articulação (ex.: "%" lido errado).
    R$ precisa vir antes de $ para não virar "R dólares".
    """
    if not text:
        return text
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    # emojis e símbolos pictográficos (faixas unicode comuns)
    text = re.sub(
        r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
        r"\U0000FE0F\U00002190-\U000021FF]",
        " ", text,
    )
    # Moeda DEPOIS do valor (pt-BR): R$ 50 mil → "50 mil reais", nunca "reais 50 mil".
    text = _normalize_currency(text)
    text = re.sub(r"R\$", " reais ", text)
    text = re.sub(r"US\$|U\$S|U\$", " dólares ", text)
    text = re.sub(r"(?<![A-Za-z])\$", " dólares ", text)
    text = text.replace("€", " euros ")
    text = text.replace("£", " libras ")
    text = text.replace("%", " por cento ")
    text = text.replace("&", " e ")
    text = text.replace("+", " mais ")
    # re-une pontuação aos tokens expandidos ("3 por cento ." → "3 por cento.")
    text = re.sub(r"\s+([.!?;:,])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_speaker_turns(text: str) -> list[tuple[str, str]]:
    """Extrai turnos (speaker, fala) preservando ordem. Ignora marcadores de pausa."""
    turns: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("["):
            continue
        m = re.match(r"^(Peter|Ricardo)\s*:\s*(.*)$", line, re.I)
        if not m:
            continue
        sp = "Peter" if m.group(1).lower() == "peter" else "Ricardo"
        body = m.group(2).strip()
        body = re.sub(r"\[PAUSA(?:_CURTA)?\]", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        if len(body.split()) < MIN_CHUNK_WORDS:
            continue
        turns.append((sp, body))
    return turns


def generate_episode_multi(client, episode_text: str, speaker_voice_configs: list) -> bytes:
    """Gera o EPISÓDIO INTEIRO numa ÚNICA chamada multi-speaker (Gemini TTS).

    Mantém os rótulos 'Peter:'/'Ricardo:' no texto para o modelo distinguir
    os locutores. Não colapsa em voz única (confirmado pelo usuário na chave
    AI Studio). Economiza drasticamente o RPD (1 chamada por episódio em vez
    de 1 por fala). O texto é limpo dos marcadores de pausa, que são tratados
    como breves silêncios naturais pelo próprio modelo.
    """
    clean_text = re.sub(r"\[PAUSA(?:_CURTA)?\]", " ", episode_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    speakers_list = [cfg.speaker for cfg in speaker_voice_configs] if speaker_voice_configs else list(SPEAKERS.keys())
    prompt = build_prompt(clean_text, speakers_list)
    log.info(f"Gerando episódio INTEIRO em 1 chamada multi-speaker (~{len(clean_text.split())} palavras)")
    data = generate_with_retry(client, prompt, speaker_voice_configs)
    return data


def split_text_halves(text: str) -> list[str]:
    """Divide texto em 2 blocos ~equilibrados (por palavras), cortando em fim de sentença.

    Retorna 1 bloco se o texto for curto demais para valer a pena dividir.
    """
    words = text.split()
    if len(words) < 2 * MIN_CHUNK_WORDS:
        return [text]
    mid = len(words) // 2
    # Procura fim de sentença mais próximo do meio (retrocede até 60 palavras)
    for i in range(mid, max(mid - 60, 1), -1):
        if words[i - 1][-1:] in ".!?;:":
            return [" ".join(words[:i]), " ".join(words[i:])]
    # Fallback: corte simples no meio
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def generate_halves_pcm(
    client,
    episode_text: str,
    voice_name: str,
    model: str | None = None,
) -> bytes:
    """Gera PCM 24kHz em 2 chamadas single-speaker com a MESMA voz.

    Uso: BM solo Peter. Junta todos os turnos em um texto único, divide em 2
    metades (~equilibradas em palavras) e faz 1 chamada por metade com a mesma
    voz (Charon). Evita a variação de voz do modo TURNS (1 chamada por fala
    com fallback Edge por fala) e custa só 2 chamadas Gemini por episódio.
    """
    turns = parse_speaker_turns(episode_text)
    if not turns:
        raise RuntimeError("Nenhum turno Peter/Ricardo encontrado no texto TTS")

    joined = " ".join(body for _, body in turns)
    joined = sanitize_tts_text(joined)  # 2026-08-09: %→"por cento", $→"dólares", sem links/emojis
    halves = split_text_halves(joined)
    log.info(
        "Modo HALVES — 2 chamadas single-speaker (%s): %s",
        voice_name,
        " + ".join(f"{len(h.split())} palavras" for h in halves),
    )

    def silence_24k(seconds: float) -> bytes:
        n = int(GEMINI_PCM_RATE * seconds) * SAMPLE_WIDTH
        return b"\x00" * n

    gap = silence_24k(0.45)
    all_pcm = b""
    missing_halves: list[int] = []
    for i, half in enumerate(halves, start=1):
        if len(half.split()) < MIN_CHUNK_WORDS:
            continue
        log.info(f"  Metade {i}/{len(halves)}: {len(half.split())} palavras")
        pcm = b""
        # 2026-08-10: retry 1x antes do fallback edge — metade com ruído/silêncio
        # (RMS baixo) não passa mais no _pcm_is_usable e precisa ser regerada.
        for attempt in (1, 2):
            try:
                pcm = generate_single_speaker_pcm(client, half, voice_name, model)
            except Exception as exc:
                log.warning(f"  Gemini halves {i} tentativa {attempt} falhou: {exc}")
                pcm = b""
            if _pcm_is_usable(pcm):
                break
            log.warning(f"  halves {i} tentativa {attempt}: áudio vazio/ruído (RMS baixo) — regerando")
            pcm = b""
        if not _pcm_is_usable(pcm):
            # Fallback edge (voz distinta, mas fala real — melhor que silêncio)
            log.warning(f"  halves {i}: Gemini falhou de vez — fallback edge-tts")
            try:
                style = EDGE_SPEAKER_STYLE.get("Peter") or {
                    "voice": _FALLBACK_EDGE_TTS_VOICE,
                    "rate": "+0%",
                    "pitch": "+0Hz",
                }
                pcm = _edge_tts_generate_audio(
                    half,
                    voice=style["voice"],
                    rate=style["rate"],
                    pitch=style["pitch"],
                )
            except Exception as fb:
                log.error(f"  halves {i} falhou de vez: {fb}")
                pcm = b""
        if not _pcm_is_usable(pcm):
            log.error(f"  halves {i}: NENHUM áudio utilizável — metade faltando no episódio")
            missing_halves.append(i)
            continue
        all_pcm += pcm + gap

    # 2026-08-10: episódio incompleto NÃO vai ao ar (era o caso do LULINHA 13:07
    # com ~10 min de ruído: a 2ª metade falhava e o resto era concatenado assim).
    if missing_halves:
        raise RuntimeError(
            f"PCM halves incompleto: metades {missing_halves} sem áudio utilizável "
            f"(geradas: {len(halves) - len(missing_halves)}/{len(halves)}). "
            f"Episódio não publicado para evitar ruído/silêncio no ar."
        )
    if len(all_pcm) < MIN_CHUNK_PCM_BYTES_24K * 10:
        raise RuntimeError(f"PCM halves insuficiente ({len(all_pcm)} bytes)")
    return all_pcm


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


async def _edge_tts_stream_audio(
    text: str,
    voice: str = _FALLBACK_EDGE_TTS_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> bytes:
    if not _EDGE_TTS_AVAILABLE or edge_tts is None:
        raise RuntimeError(
            "edge_tts não instalado neste Python. Use o venv Hermes: "
            "/home/osmar/.hermes/hermes-agent/venv/bin/python3"
        )
    communicator = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    audio_bytes = b""
    async for chunk in communicator.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


def _edge_tts_generate_audio(
    text: str,
    voice: str = _FALLBACK_EDGE_TTS_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> bytes:
    text = text.replace("Peter:", "").replace("Ricardo:", "").strip()
    # Remove marcadores de pausa residuais
    text = re.sub(r"\[PAUSA(?:_CURTA)?\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text.split()) < MIN_CHUNK_WORDS:
        return b""
    try:
        mp3_bytes = asyncio.run(
            _edge_tts_stream_audio(text, voice=voice, rate=rate, pitch=pitch)
        )
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


# Diferenciação Edge quando Gemini TTS não está disponível
EDGE_SPEAKER_STYLE = {
    "Peter": {"voice": "pt-BR-AntonioNeural", "rate": "+12%", "pitch": "+0Hz"},
    "Ricardo": {"voice": "pt-BR-FranciscaNeural", "rate": "+6%", "pitch": "+0Hz"},
}


def generate_fallback_edge_tts(text: str) -> bytes:
    """Fallback single-voice para quando Gemini falhar (usado em modos antigos)."""
    if not _EDGE_TTS_AVAILABLE:
        raise RuntimeError(
            "Fallback edge-tts indisponível: módulo edge_tts não encontrado. "
            "Rode com /home/osmar/.hermes/hermes-agent/venv/bin/python3 "
            "ou: pip install edge-tts"
        )
    try:
        log.warning("⚠️  Gemini TTS indisponível. Acionando fallback edge-tts (voz única)...")
        audio = _edge_tts_generate_audio(text)
        if not audio or len(audio) < MIN_CHUNK_PCM_BYTES_24K:
            raise RuntimeError(
                f"edge-tts retornou áudio vazio/curto ({len(audio) if audio else 0} bytes)"
            )
        log.info(f"Fallback edge-tts OK: {len(audio)} bytes")
        return audio
    except Exception as exc:
        log.error(f"Fallback edge-tts também falhou: {exc}")
        raise


def generate_fallback_edge_per_turn(text: str) -> bytes:
    """Fallback edge-tts POR FALA (Peter/Ricardo com estilos diferentes).

    Usado quando o modo PACKED (1 chamada Gemini) falha: mantém a diferenciação
    dos locutores gerando cada turno separadamente com a voz/rate/pitch de
    EDGE_SPEAKER_STYLE, exatamente como o modo TURNS fazia antes.
    """
    if not _EDGE_TTS_AVAILABLE:
        raise RuntimeError(
            "Fallback edge-tts indisponível: módulo edge_tts não encontrado. "
            "Rode com /home/osmar/.hermes/hermes-agent/venv/bin/python3 "
            "ou: pip install edge-tts"
        )
    turns = parse_speaker_turns(text)
    if not turns:
        # sem rótulos de locutor: cai no fallback single-voice
        return generate_fallback_edge_tts(text)
    log.warning("⚠️  Gemini PACKED falhou. Fallback edge-tts POR FALA (estilos distintos)...")

    def silence_24k(seconds: float) -> bytes:
        n = int(GEMINI_PCM_RATE * seconds) * SAMPLE_WIDTH
        return b"\x00" * n

    gap = silence_24k(0.28)
    all_pcm = b""
    skipped = 0
    for i, (speaker, body) in enumerate(turns, start=1):
        style = EDGE_SPEAKER_STYLE.get(speaker) or EDGE_SPEAKER_STYLE["Peter"]
        try:
            pcm = _edge_tts_generate_audio(
                body, voice=style["voice"], rate=style["rate"], pitch=style["pitch"]
            )
        except Exception as exc:
            log.error(f"  turno {i} edge falhou: {exc}")
            skipped += 1
            continue
        if not _pcm_is_usable(pcm):
            skipped += 1
            continue
        all_pcm += pcm + gap
    if skipped:
        log.info(f"Turnos pulados no fallback edge: {skipped}")
    if len(all_pcm) < MIN_CHUNK_PCM_BYTES_24K * 10:
        raise RuntimeError(f"Fallback edge per-turn insuficiente ({len(all_pcm)} bytes)")
    log.info(f"Fallback edge-tts POR FALA OK: {len(all_pcm)} bytes")
    return all_pcm


def _pcm_is_usable(pcm: bytes, rate: int = GEMINI_PCM_RATE) -> bool:
    """Rejeita chunks vazios, quase-silêncio E blobs de ruído antes do concat.

    Critérios (2026-08-10, BUG ruído BM 13:07): o antigo teste (>1% bytes
    não-zero) deixava passar ~10 min de piso de ruído (RMS ~50 vs ~5000 da
    fala). Agora exige RMS médio mínimo de fala (~ -33 dBFS) e rejeita
    qualquer coisa com energia de piso.
    """
    if not pcm or len(pcm) < MIN_CHUNK_PCM_BYTES_24K:
        return False
    # RMS sobre amostras 16-bit (s16le) — amostra espaçada por 16 bytes (8 amostras)
    n_bytes = len(pcm) - (len(pcm) % 2)
    pairs = memoryview(pcm[:n_bytes]).cast("h")[::8]
    if len(pairs) < 50:
        return False
    sum_sq = 0
    nonzero = 0
    for s in pairs:
        sum_sq += s * s
        if s != 0:
            nonzero += 1
    if nonzero / len(pairs) < 0.01:
        return False
    rms = math.sqrt(sum_sq / len(pairs))
    # Fala real: RMS ~2000–9000 @24kHz s16. Piso de ruído: ~20–150.
    # Limiar 300 ≈ -40 dBFS: rejeita ruído/Silêncio sem cortar fala suave.
    return rms >= 300


def _ffprobe_duration(path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        return None
    return None


def publish_final_mp3(mp3_path: Path, date_stem: str | None = None) -> Path:
    """
    Garante audio/YYYY-MM-DD.mp3 (alias de entrega) a partir do MP3 processado.
    date_stem: '2026-07-22' extraído do nome quando possível.
    """
    audio_dir = mp3_path.parent
    stem = date_stem
    if not stem:
        # tenta 2026-07-22-vale-da-liberdade ou 2026-07-22-completo
        m = re.match(r"(\d{4}-\d{2}-\d{2})", mp3_path.name)
        stem = m.group(1) if m else mp3_path.stem.split("-vale")[0].split("-completo")[0]
    delivery = audio_dir / f"{stem}.mp3"
    if mp3_path.resolve() != delivery.resolve():
        delivery.write_bytes(mp3_path.read_bytes())
        log.info(f"Alias de entrega: {delivery}")
    return delivery


def _fraction_silence(audio_path: Path, min_silence_s: float = 1.0) -> float:
    """Fração do áudio que é silêncio longo (silencedetect, -35dB, d>=1s).

    2026-08-10 (BUG ruído BM): rede de segurança pós-produção — episódio com
    >40% de silêncio é anormal (LULINHA tinha 81% de silêncio/ruído após a 2ª
    metade falhar). Pausas normais entre quadros somam ~5-10% no máximo.
    """
    try:
        dur = _ffprobe_duration(audio_path)
        if not dur or dur <= 0:
            return 0.0
        proc = subprocess.run(
            ["ffmpeg", "-nostats", "-i", str(audio_path),
             "-af", f"silencedetect=noise=-35dB:d={min_silence_s}",
             "-f", "null", "-"],
            capture_output=True, text=True,
        )
        total = 0.0
        for start_m, end_m in re.findall(
            r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", proc.stderr, re.S
        ):
            total += float(end_m) - float(start_m)
        return min(total / dur, 1.0)
    except Exception as exc:
        log.warning(f"Falha ao medir fração de silêncio de {audio_path.name}: {exc}")
        return 0.0


def assert_final_audio_ok(mp3_path: Path) -> None:
    """Gate de qualidade do MP3 final (tamanho + duração + silêncio)."""
    if not mp3_path.exists():
        raise RuntimeError(f"MP3 final ausente: {mp3_path}")
    size = mp3_path.stat().st_size
    if size < MIN_FINAL_MP3_BYTES:
        raise RuntimeError(
            f"MP3 final pequeno demais: {size} bytes (mín. {MIN_FINAL_MP3_BYTES}). "
            f"Arquivo: {mp3_path}"
        )
    dur = _ffprobe_duration(mp3_path)
    if dur is not None and dur < MIN_FINAL_DURATION_S:
        raise RuntimeError(
            f"MP3 final curto demais: {dur:.1f}s (mín. {MIN_FINAL_DURATION_S}s ≈ 7 min). "
            f"Arquivo: {mp3_path}"
        )
    silence = _fraction_silence(mp3_path)
    if silence > 0.40:
        raise RuntimeError(
            f"MP3 final com {silence*100:.0f}% de silêncio (>40%) — áudio degradado. "
            f"Arquivo: {mp3_path}"
        )
    log.info(
        f"✅ Gate de áudio OK: {mp3_path.name} ({size/1e6:.2f} MB"
        + (f", {dur/60:.1f} min" if dur else "")
        + f", silêncio {silence*100:.0f}%)"
    )


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
        help="Desabilitar chunking por pausas (gera áudio em uma única chamada TTS multi)"
    )
    parser.add_argument(
        "--mode",
        choices=["packed", "halves", "multi"],
        default="packed",
        help=(
            "packed=multi-speaker por CHUNKS (padrão diário, evita colapso de voz); "
            "halves=2 chamadas single-speaker com a MESMA voz (padrão BM, solo Peter); "
            "multi= API multi-speaker legado (pode colapsar em 1 voz)"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Modelo TTS Gemini (default: gemini-2.5-flash-preview-tts, Diário). "
            "BM Peter solo: gemini-3.1-flash-tts-preview"
        ),
    )
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Não apagar o WAV intermediário após gerar o MP3 final (default: apaga)",
    )
    parser.add_argument(
        "--single-speaker",
        help="Define locutor solo, ex: Peter (ignora outros locutores)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Temperatura do TTS Gemini (default: 0.5). Mais alto = mais expressão/emoção, "
             "mais baixo = tom mais estável (0.2 deixava monótono)."
    )
    # (REMOVIDO) Temperatura por speaker/chunk: mantemos temperatura global.
    args = parser.parse_args()

    # Modelo TTS (global do módulo — usado por generate_* )
    global TTS_MODEL, TTS_TEMPERATURE
    if args.model:
        TTS_MODEL = args.model.strip()
    if args.temperature is not None:
        TTS_TEMPERATURE = args.temperature
    log.info(f"Modelo TTS: {TTS_MODEL} | CHUNK_TARGET_WORDS={CHUNK_TARGET_WORDS} | temperatura={TTS_TEMPERATURE}")

    keys = _candidate_gemini_keys()
    if not keys and not os.environ.get("GEMINI_API_KEY"):
        log.error("FALHA: defina GEMINI_API_KEY (ou GEMINI_API_KEY_2/_3) antes de executar.")
        sys.exit(2)
    if keys:
        log.info(f"Chaves Gemini disponíveis: {len(keys)} (round-robin se >1)")

    episode_path = Path(args.episode)
    if not episode_path.exists():
        log.error(f"FALHA: episódio não encontrado: {episode_path}")
        sys.exit(2)

    episode_text = read_episode(episode_path)
    if args.single_speaker:
        speakers = [args.single_speaker]
    else:
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

    client = _make_gemini_client()

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

    # ── Geração ──────────────────────────────────────────────────────────
    skipped_empty = 0
    if args.mode == "packed":
        # PADRÃO (2026-07-26): multi-speaker EM CHUNKS.
        # 1 chamada só colapsa em voz única em texto longo (Gemini perde
        # o contexto de 2 locutores no meio/fim). Chunking por pausa +
        # sub-chunking por CHUNK_TARGET_WORDS (~300 palavras) mantém o modelo
        # coerente. ~5 chunks/episódio → cabe nos 10 RPD da chave AI Studio.
        log.info("Modo PACKED — multi-speaker por CHUNKS (evita colapso em 1 voz)")
        chunks = split_into_chunks(episode_text)
        all_pcm = b""
        for i, (chunk_text, pause_after_s) in enumerate(chunks, start=1):
            has_speaker = any(f"{sp}:" in chunk_text for sp in speakers)
            word_count = len(chunk_text.split())
            if (not has_speaker) or word_count < MIN_CHUNK_WORDS:
                log.info(f"Chunk {i}/{len(chunks)}: pulando TTS (speaker={has_speaker}, words={word_count})")
                skipped_empty += 1
                if pause_after_s > 0:
                    all_pcm += generate_silence_wav(min(pause_after_s, 0.4))
                continue
            log.info(f"Chunk {i}/{len(chunks)}: {word_count} palavras, pausa_após={pause_after_s}s")
            prompt = build_prompt(chunk_text, speakers)
            chunk_pcm = b""
            # 2026-08-10: retry 1x — chunk com ruído/RMS baixo é regerado,
            # não silenciado (silêncio = furo no meio do episódio).
            for attempt in (1, 2):
                try:
                    chunk_pcm = generate_with_retry(client, prompt, speaker_voice_configs)
                except Exception as exc:
                    log.warning(f"Gemini PACKED falhou no chunk {i} (tentativa {attempt}): {exc}")
                    chunk_pcm = b""
                if _pcm_is_usable(chunk_pcm):
                    break
                log.warning(f"Chunk {i} tentativa {attempt}: áudio vazio/ruído (RMS baixo) — regerando")
                chunk_pcm = b""
            if not _pcm_is_usable(chunk_pcm):
                log.warning(f"Gemini PACKED falhou no chunk {i} — fallback edge por-fala")
                try:
                    chunk_pcm = generate_fallback_edge_per_turn(chunk_text)
                except Exception as fb_exc:
                    raise RuntimeError(f"Fallback edge por-fala também falhou no chunk {i}: {fb_exc}") from fb_exc
            if not _pcm_is_usable(chunk_pcm):
                log.warning(f"Chunk {i}: áudio vazio/quase silêncio ({len(chunk_pcm) if chunk_pcm else 0} bytes) — NÃO concatenado")
                skipped_empty += 1
                if pause_after_s > 0:
                    all_pcm += generate_silence_wav(min(pause_after_s, 0.4))
                continue
            chunk_pcm_44k = resample_pcm(chunk_pcm, from_rate=GEMINI_PCM_RATE, to_rate=SAMPLE_RATE)
            all_pcm += chunk_pcm_44k
            if pause_after_s > 0:
                all_pcm += generate_silence_wav(pause_after_s)
                log.info(f"  → Silêncio de {pause_after_s}s inserido após chunk {i}")
        if skipped_empty:
            log.info(f"Chunks pulados (vazios/curtos): {skipped_empty}")
        if len(all_pcm) < MIN_CHUNK_PCM_BYTES_24K * 10:
            raise RuntimeError(f"PCM combinado insuficiente ({len(all_pcm)} bytes) — todos os chunks falharam ou ficaram vazios.")
        duration_est = len(all_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
        log.info(f"PCM combinado: {len(all_pcm)} bytes (~{duration_est:.1f}s @ {SAMPLE_RATE}Hz)")
        wave_file(str(out_path), all_pcm)
        log.info(f"OK {out_path}")
    elif args.mode == "halves":
        # PADRÃO BM (2026-08-09): 2 chamadas single-speaker com a MESMA voz.
        # Junta todos os turnos, divide em 2 metades e chama a voz fixa
        # (Charon=Peter). Substitui o antigo TURNS (1 chamada por fala), que
        # variava de voz entre falas (fallback Edge por fala).
        log.info("Modo HALVES — 2 chamadas single-speaker (mesma voz)")
        voice_name = SPEAKERS.get(speakers[0], "Charon") if speakers else "Charon"
        try:
            data_24k = generate_halves_pcm(client, episode_text, voice_name)
        except Exception as exc:
            log.warning(f"Modo halves falhou: {exc} — tentando multi/edge")
            try:
                clean_text = re.sub(r"\[PAUSA(?:_CURTA)?\]", "", episode_text)
                clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
                prompt = build_prompt(clean_text, speakers)
                data_24k = generate_with_retry(client, prompt, speaker_voice_configs)
            except Exception as exc2:
                log.warning(f"Multi também falhou: {exc2}")
                data_24k = generate_fallback_edge_tts(episode_text)
        if not _pcm_is_usable(data_24k):
            raise RuntimeError("Nenhum áudio utilizável gerado (vazio/quase silêncio).")
        pcm_44k = resample_pcm(data_24k, from_rate=GEMINI_PCM_RATE, to_rate=SAMPLE_RATE)
        wave_file(str(out_path), pcm_44k)
        log.info(f"OK {out_path}")
    elif args.no_chunk or args.mode == "multi":
        # multi-speaker (legado / opcional)
        log.info("Modo MULTI-SPEAKER Gemini (pode colapsar em 1 voz)...")
        clean_text = re.sub(r"\[PAUSA(?:_CURTA)?\]", "", episode_text)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
        # Se multi com chunking
        if args.no_chunk or args.mode == "multi" and args.no_chunk:
            prompt = build_prompt(clean_text, speakers)
            try:
                data = generate_with_retry(client, prompt, speaker_voice_configs)
            except Exception as exc:
                log.warning(f"Gemini falhou (--no-chunk/multi): {exc}")
                data = generate_fallback_edge_tts(clean_text)
            if not _pcm_is_usable(data):
                raise RuntimeError("Nenhum áudio utilizável gerado (vazio/quase silêncio).")
            pcm_44k = resample_pcm(data, from_rate=GEMINI_PCM_RATE, to_rate=SAMPLE_RATE)
            wave_file(str(out_path), pcm_44k)
            log.info(f"OK {out_path}")
        else:
            # chunking multi (legado)
            chunks = split_into_chunks(episode_text)
            all_pcm = b""

            for i, (chunk_text, pause_after_s) in enumerate(chunks, start=1):
                has_speaker = any(f"{sp}:" in chunk_text for sp in speakers)
                word_count = len(chunk_text.split())
                if (not has_speaker) or word_count < MIN_CHUNK_WORDS:
                    log.info(
                        f"Chunk {i}/{len(chunks)}: pulando TTS "
                        f"(speaker={has_speaker}, words={word_count})"
                    )
                    skipped_empty += 1
                    if pause_after_s > 0:
                        silence = generate_silence_wav(pause_after_s)
                        all_pcm += silence
                    continue

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
                    chunk_pcm = fallback_data

                if not _pcm_is_usable(chunk_pcm):
                    log.warning(
                        f"Chunk {i}: áudio vazio/quase silêncio "
                        f"({len(chunk_pcm) if chunk_pcm else 0} bytes) — NÃO concatenado"
                    )
                    skipped_empty += 1
                    if pause_after_s > 0:
                        silence = generate_silence_wav(min(pause_after_s, 0.4))
                        all_pcm += silence
                    continue

                chunk_pcm_44k = resample_pcm(chunk_pcm, from_rate=GEMINI_PCM_RATE, to_rate=SAMPLE_RATE)
                all_pcm += chunk_pcm_44k

                if pause_after_s > 0:
                    silence = generate_silence_wav(pause_after_s)
                    all_pcm += silence
                    log.info(f"  → Silêncio de {pause_after_s}s inserido após chunk {i}")

            if skipped_empty:
                log.info(f"Chunks pulados (vazios/curtos): {skipped_empty}")

            if len(all_pcm) < MIN_CHUNK_PCM_BYTES_24K * 10:
                raise RuntimeError(
                    f"PCM combinado insuficiente ({len(all_pcm)} bytes) — "
                    f"todos os chunks falharam ou ficaram vazios."
                )

            duration_est = len(all_pcm) / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)
            log.info(f"PCM combinado: {len(all_pcm)} bytes (~{duration_est:.1f}s @ {SAMPLE_RATE}Hz)")
            wave_file(str(out_path), all_pcm)
            log.info(f"OK {out_path}")
    else:
        # default already handled turns
        pass

    # ── Pós-processamento EBU R128 2-pass (Fase 0.5) ────────────────────────
    # Diário canônico: audio/{date}-vale-da-liberdade.mp3 + alias audio/{date}.mp3
    # BM / caminhos custom (--out fora de audio/ ou --single-speaker):
    # grava o MP3 AO LADO do WAV e NÃO sobrescreve o episódio diário.
    out_path = Path(out_path).resolve()
    default_audio_dir = (project_root / "audio").resolve()
    is_custom_out = bool(args.out) and out_path.parent.resolve() != default_audio_dir
    is_single = bool(args.single_speaker)

    if is_custom_out or is_single:
        # Sibling do WAV: foo-completo.wav → foo.mp3  |  foo.wav → foo.mp3
        name = out_path.name
        if name.endswith("-completo.wav"):
            mp3_name = name[: -len("-completo.wav")] + ".mp3"
        elif name.endswith(".wav"):
            mp3_name = name[:-4] + ".mp3"
        else:
            mp3_name = out_path.stem.replace("-completo", "") + ".mp3"
        mp3_path = out_path.parent / mp3_name
        make_daily_alias = False
        # Especiais BM ~5 min — gate de 7 min do diário não se aplica
        min_duration_s = 60.0
        min_bytes = 100_000
    else:
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", out_path.name + " " + episode_path.name)
        date_stem = date_m.group(1) if date_m else out_path.stem.replace("-completo", "")
        mp3_path = default_audio_dir / f"{date_stem}-vale-da-liberdade.mp3"
        make_daily_alias = True
        min_duration_s = MIN_FINAL_DURATION_S
        min_bytes = MIN_FINAL_MP3_BYTES

    try:
        run_ffmpeg_chain_2pass(out_path, mp3_path)
        log.info(f"✅ MP3 final com EBU R128 2-pass: {mp3_path}")
        if make_daily_alias:
            date_m = re.search(r"(\d{4}-\d{2}-\d{2})", out_path.name + " " + episode_path.name)
            date_stem = date_m.group(1) if date_m else out_path.stem.replace("-completo", "")
            delivery = publish_final_mp3(mp3_path, date_stem=date_stem)
            assert_final_audio_ok(delivery)
        else:
            # Gate relaxado (sem alias diário)
            if not mp3_path.exists():
                raise RuntimeError(f"MP3 final ausente: {mp3_path}")
            size = mp3_path.stat().st_size
            if size < min_bytes:
                raise RuntimeError(
                    f"MP3 final pequeno demais: {size} bytes (mín. {min_bytes}). "
                    f"Arquivo: {mp3_path}"
                )
            dur = _ffprobe_duration(mp3_path)
            if dur is not None and dur < min_duration_s:
                raise RuntimeError(
                    f"MP3 final curto demais: {dur:.1f}s (mín. {min_duration_s}s). "
                    f"Arquivo: {mp3_path}"
                )
            # 2026-08-10: gate de silêncio também no BM/custom (LULINHA 13:07
            # tinha 81% de silêncio/ruído e passava no gate antigo de tamanho).
            silence = _fraction_silence(mp3_path)
            if silence > 0.40:
                raise RuntimeError(
                    f"MP3 final com {silence*100:.0f}% de silêncio (>40%) — "
                    f"áudio degradado (2ª metade falhou?). Arquivo: {mp3_path}"
                )
            log.info(
                f"✅ Gate BM/custom OK: {mp3_path.name} ({size/1e6:.2f} MB"
                + (f", {dur/60:.1f} min" if dur else "")
                + f", silêncio {silence*100:.0f}%)"
            )
        # Limpeza: apaga WAV intermediário após MP3 OK (economiza ~80–110 MB/ep)
        if not args.keep_wav and out_path.exists() and out_path.suffix.lower() == ".wav":
            try:
                sz = out_path.stat().st_size
                out_path.unlink()
                log.info(f"🧹 WAV intermediário removido: {out_path.name} ({sz/1e6:.1f} MB liberados)")
            except OSError as rm_err:
                log.warning(f"Não foi possível apagar WAV {out_path}: {rm_err}")
    except Exception as e:
        log.error(f"Falha no pós-processamento / gate de áudio: {e}")
        log.info(f"WAV sem pós-processamento disponível em: {out_path}")
        sys.exit(3)


if __name__ == "__main__":
    main()
