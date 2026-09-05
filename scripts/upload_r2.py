#!/usr/bin/env python3
"""
Upload de áudios para Cloudflare R2 + espelho local em public/audio/.

- Sobe o MP3 no bucket (API S3 / boto3)
- Garante cópia/hardlink em public/audio/{date}.mp3 (nginx + player)
- Lifecycle 90 dias é best-effort (Access Denied não aborta o upload)
- Retorna URL pública: R2 custom domain se configurado e ≠ SITE_URL;
  senão ./audio/{date}.mp3 (servido pelo site)

Uso:
  python3 scripts/upload_r2.py --date 2026-07-28 --file audio/2026-07-28.mp3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "web-jornal-liberdade")
R2_PUBLIC_DOMAIN = (os.getenv("R2_PUBLIC_DOMAIN") or "").rstrip("/")
SITE_URL = (os.getenv("SITE_URL") or "https://news.mob.tec.br").rstrip("/")

PUBLIC_AUDIO = PROJECT_ROOT / "public" / "audio"
META_DIR = PROJECT_ROOT / "episodes"


def get_r2_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        print("[ERRO] Biblioteca 'boto3' não encontrada. Instale com: pip install boto3")
        return None

    if not R2_ACCOUNT_ID or not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print(
            "[AVISO] Credenciais R2 ausentes "
            "(R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY) no .env"
        )
        return None

    endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def setup_r2_lifecycle_policy(s3_client, bucket_name: str, expiration_days: int = 90) -> bool:
    """Best-effort: token sem permissão de lifecycle não deve quebrar o upload."""
    if not s3_client:
        return False
    try:
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": f"ExpireEpisodesAfter{expiration_days}Days",
                        "Status": "Enabled",
                        "Filter": {"Prefix": "audio/"},
                        "Expiration": {"Days": expiration_days},
                    }
                ]
            },
        )
        print(f"[R2] Lifecycle {expiration_days}d aplicada em '{bucket_name}' (prefix audio/).")
        return True
    except Exception as e:
        print(f"[AVISO] Lifecycle R2 ignorada (sem permissão ou API): {e}")
        return False


def mirror_to_public(date_str: str, file_path: Path) -> Path:
    """Espelha o MP3 em public/audio/{date}.mp3 (hardlink se possível)."""
    PUBLIC_AUDIO.mkdir(parents=True, exist_ok=True)
    dest = PUBLIC_AUDIO / f"{date_str}.mp3"
    if dest.resolve() == file_path.resolve():
        return dest
    # remove symlink/dir leftovers
    if dest.is_symlink() or dest.exists():
        try:
            dest.unlink()
        except IsADirectoryError:
            pass
    try:
        os.link(file_path, dest)
    except OSError:
        import shutil

        shutil.copy2(file_path, dest)
    try:
        dest.chmod(0o644)
    except OSError:
        pass
    print(f"[R2] Espelho local: {dest} ({dest.stat().st_size} bytes)")
    return dest


def public_url_for(date_str: str, r2_key: str) -> str:
    """
    Se R2_PUBLIC_DOMAIN for um CDN próprio (≠ SITE_URL), usa ele.
    Caso contrário serve pelo nginx do site (./audio/{date}.mp3).
    """
    local = f"./audio/{date_str}.mp3"
    if not R2_PUBLIC_DOMAIN:
        return local
    # news.mob.tec.br com arquivo local espelhado = URL absoluta do site
    if R2_PUBLIC_DOMAIN.rstrip("/") == SITE_URL.rstrip("/"):
        return f"{SITE_URL}/audio/{date_str}.mp3"
    # domínio custom do bucket (ex.: https://audio.mob.tec.br)
    return f"{R2_PUBLIC_DOMAIN}/{r2_key}"


def save_sidecar(date_str: str, payload: dict) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    path = META_DIR / f"{date_str}-r2.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[R2] Sidecar: {path}")


def resolve_source_file(date_str: str, file_path: Path | None) -> Path | None:
    if file_path and file_path.exists():
        return file_path
    candidates = [
        PROJECT_ROOT / "audio" / f"{date_str}.mp3",
        PROJECT_ROOT / "audio" / f"{date_str}-vale-da-liberdade.mp3",
        PROJECT_ROOT / "audio" / f"{date_str}-completo.mp3",
        PROJECT_ROOT / "public" / "audio" / f"{date_str}.mp3",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 1000:
            return c
    return None


def upload_episode_audio(date_str: str, file_path: Path | None = None) -> str:
    """
    Upload + espelho local.
    Retorna URL para o catálogo (preferência: site local estável).
    """
    src = resolve_source_file(date_str, Path(file_path) if file_path else None)
    if not src:
        print(f"[ERRO] Arquivo de áudio não encontrado para {date_str}")
        return ""

    # chave canônica no bucket = nome que o player usa
    r2_key = f"audio/{date_str}.mp3"
    r2_key_alt = f"audio/{date_str}-vale-da-liberdade.mp3"
    size_mb = src.stat().st_size / (1024 * 1024)

    # sempre espelha local (nginx)
    mirror_to_public(date_str, src)

    s3 = get_r2_client()
    if not s3:
        url = f"./audio/{date_str}.mp3"
        save_sidecar(
            date_str,
            {
                "date": date_str,
                "local_url": url,
                "r2_uploaded": False,
                "source": str(src),
            },
        )
        print(f"[R2] Sem cliente — fallback local: {url}")
        return url

    print(f"[R2] Upload {src.name} ({size_mb:.2f} MB) → s3://{R2_BUCKET_NAME}/{r2_key}")
    setup_r2_lifecycle_policy(s3, R2_BUCKET_NAME, expiration_days=90)

    extra = {
        "ContentType": "audio/mpeg",
        "CacheControl": "public, max-age=31536000",
    }
    try:
        s3.upload_file(str(src), R2_BUCKET_NAME, r2_key, ExtraArgs=extra)
        # alias legado (opcional)
        try:
            s3.upload_file(str(src), R2_BUCKET_NAME, r2_key_alt, ExtraArgs=extra)
        except Exception as e:
            print(f"[AVISO] Alias legado R2 não enviado: {e}")

        url = public_url_for(date_str, r2_key)
        print(f"[R2 SUCCESS] {url}")
        save_sidecar(
            date_str,
            {
                "date": date_str,
                "local_url": f"./audio/{date_str}.mp3",
                "r2_key": r2_key,
                "r2_url": f"{R2_PUBLIC_DOMAIN}/{r2_key}" if R2_PUBLIC_DOMAIN else None,
                "catalog_url": url,
                "r2_uploaded": True,
                "bytes": src.stat().st_size,
                "source": str(src),
            },
        )
        try:
            from media_offload import after_r2

            after_r2(date_str)
        except Exception as exc:  # noqa: BLE001
            print(f"[AVISO] offload HD após R2 falhou: {exc}")
        return url
    except Exception as e:
        print(f"[ERRO R2] Falha no upload: {e}")
        url = f"./audio/{date_str}.mp3"
        save_sidecar(
            date_str,
            {
                "date": date_str,
                "local_url": url,
                "r2_uploaded": False,
                "error": str(e),
                "source": str(src),
            },
        )
        return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload de áudio para Cloudflare R2")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--file", help="Caminho do MP3 (opcional se audio/{date}.mp3 existir)")
    args = parser.parse_args()
    url = upload_episode_audio(args.date, Path(args.file) if args.file else None)
    if not url:
        return 1
    print(f"Resultado URL: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
