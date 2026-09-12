#!/usr/bin/env python3
"""
scripts/isolate_voice.py — Isolador de Voz / Redução de Ruído com ElevenLabs Voice Isolator API.

Remove ruídos de fundo, eco, vento, chiados e imperfeições de microfone,
deixando a voz cristalina como se tivesse sido gravada em estúdio profissional.

Uso:
  # 1. Consultar saldo de créditos disponível:
  python scripts/isolate_voice.py --check-credits

  # 2. Limpar áudio de um arquivo (.wav, .mp3, .m4a):
  python scripts/isolate_voice.py branding/audio/outro/minha_fala.wav

  # 3. Limpar áudio direto de um vídeo MP4 (substitui o áudio com o som tratado):
  python scripts/isolate_voice.py branding/encerramento/gravacoes/take01.mp4 --out branding/encerramento/gravacoes/take01_limpo.mp4

Configuração:
  Adicione sua chave no arquivo .env:
  ELEVENLABS_API_KEY=sua_chave_aqui
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Erro: Biblioteca 'requests' não encontrada. Instale com: pip install requests")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.elevenlabs.io/v1/audio-isolation"
USER_URL = "https://api.elevenlabs.io/v1/user/subscription"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_env_key() -> str:
    """Lê a chave da API ElevenLabs do ambiente ou dos arquivos .env."""
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY")
    if key:
        return key.strip()

    env_paths = [ROOT / ".env", Path.home() / ".hermes" / ".env", Path(".env")]
    for p in env_paths:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().upper()
                if k in ("ELEVENLABS_API_KEY", "XI_API_KEY"):
                    val = v.strip().strip("'").strip('"')
                    if val:
                        return val
    return ""


def get_audio_duration(file_path: Path) -> float:
    """Obtém duração do arquivo de áudio/vídeo em segundos usando ffprobe."""
    if not shutil.which("ffprobe"):
        return 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path)
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(r.stdout.strip() or 0.0)
    except Exception:
        return 0.0


def check_credits(api_key: str) -> None:
    """Consulta saldo e informações de assinatura na ElevenLabs."""
    headers = {"xi-api-key": api_key}
    try:
        res = requests.get(USER_URL, headers=headers, timeout=15)
        if res.status_code == 401:
            print("❌ Erro de Autenticação: Chave de API inválida ou expirada.")
            return
        res.raise_for_status()
        data = res.json()
        tier = data.get("tier", "free")
        limit = data.get("character_limit", 0)
        used = data.get("character_count", 0)
        remaining = max(0, limit - used)

        print("\n" + "═" * 55)
        print("🎙️  ELEVENLABS — SALDO DE CRÉDITOS E STATUS")
        print("═" * 55)
        print(f" Plano:             {tier.upper()}")
        print(f" Limite Total:      {limit:,} créditos")
        print(f" Utilizado no mês:  {used:,} créditos")
        print(f" Disponível:        {remaining:,} créditos")
        print("═" * 55)
        # O isolador consome ~1.000 créditos por minuto (16,6 créditos/segundo)
        minutos_disp = remaining / 1000.0
        print(f"💡 Você pode isolar aprox. {minutos_disp:.1f} minutos de áudio!")
        print(f"   (Equivale a cerca de {int(remaining / 250)} takes de encerramento de 15s)\n")
    except requests.exceptions.RequestException as e:
        print(f"❌ Falha ao consultar créditos na ElevenLabs: {e}")


def isolate_voice(input_path: Path, output_path: Path, api_key: str) -> bool:
    """Envia arquivo para a API Voice Isolator da ElevenLabs e salva o áudio limpo."""
    if not input_path.is_file():
        print(f"❌ Arquivo de entrada não encontrado: {input_path}")
        return False

    dur = get_audio_duration(input_path)
    creditos_estimados = int((dur / 60.0) * 1000) if dur > 0 else 0

    print(f"\n🎧 Arquivo: {input_path.name}")
    if dur > 0:
        print(f"⏱️  Duração: {dur:.1f}s (~{creditos_estimados} créditos necessários)")

    is_video = input_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm", ".avi"]
    temp_audio_file = None
    upload_file_path = input_path

    # Se for vídeo e não temos ferramenta para enviar vídeo direto, extrai áudio wav primeiro
    if is_video:
        print("🎬 Vídeo detectado. Extraindo áudio temporário para envio...")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            temp_audio_file = Path(tf.name)
        cmd_extract = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(temp_audio_file)
        ]
        r = subprocess.run(cmd_extract, capture_output=True, text=True)
        if r.returncode != 0:
            print("❌ Falha ao extrair áudio do vídeo via ffmpeg.")
            if temp_audio_file.exists():
                temp_audio_file.unlink()
            return False
        upload_file_path = temp_audio_file

    print("🚀 Enviando para ElevenLabs Voice Isolator...")
    headers = {"xi-api-key": api_key}

    temp_clean_audio = None
    try:
        with open(upload_file_path, "rb") as f:
            files = {"audio": (upload_file_path.name, f, "audio/mpeg")}
            response = requests.post(API_URL, headers=headers, files=files, timeout=120)

        if response.status_code != 200:
            print(f"❌ Erro da API ElevenLabs (HTTP {response.status_code}):")
            try:
                err_data = response.json()
                print(f"   Mensagem: {err_data.get('detail', err_data)}")
            except Exception:
                print(f"   {response.text[:300]}")
            return False

        # Se a saída desejada for um vídeo, salvamos o áudio limpo e multiplexamos de volta
        if is_video and output_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                temp_clean_audio = Path(tf.name)
            temp_clean_audio.write_bytes(response.content)

            print("🎬 Reincorporando áudio limpo no vídeo original...")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cmd_remux = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-i", str(temp_clean_audio),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                str(output_path)
            ]
            r = subprocess.run(cmd_remux, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"❌ Falha ao mixar vídeo final com ffmpeg: {r.stderr[-300:]}")
                return False
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)

        print(f"✅ Áudio isolado com sucesso salvo em: {output_path}")
        return True

    finally:
        if temp_audio_file and temp_audio_file.exists():
            temp_audio_file.unlink()
        if temp_clean_audio and temp_clean_audio.exists():
            temp_clean_audio.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Isolador de Voz ElevenLabs — Remove ruídos e eco de gravações de voz."
    )
    parser.add_argument("input", nargs="?", help="Arquivo de entrada (.wav, .mp3, .mp4, etc.)")
    parser.add_argument("-o", "--out", help="Arquivo de saída limpo (se omitido, salva com sufixo _isolado)")
    parser.add_argument("--check-credits", action="store_true", help="Consulta o saldo de créditos da conta")
    parser.add_argument("--api-key", help="Chave da API ElevenLabs (opcional, pode vir do .env)")

    args = parser.parse_args()
    api_key = args.api_key or load_env_key()

    if not api_key:
        print("\n⚠️  Chave da ElevenLabs não encontrada!")
        print("Você pode:")
        print("1. Adicionar no arquivo .env do projeto: ELEVENLABS_API_KEY=sua_chave_aqui")
        print("2. Ou passar via parâmetro: python scripts/isolate_voice.py --api-key sua_chave ...\n")
        sys.exit(1)

    if args.check_credits:
        check_credits(api_key)
        if not args.input:
            return

    if not args.input:
        parser.print_help()
        sys.exit(0)

    in_file = Path(args.input)
    if args.out:
        out_file = Path(args.out)
    else:
        out_file = in_file.with_stem(f"{in_file.stem}_isolado")
        if in_file.suffix.lower() not in [".mp3", ".wav", ".mp4"]:
            out_file = out_file.with_suffix(".mp3")

    ok = isolate_voice(in_file, out_file, api_key)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
