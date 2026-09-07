#!/usr/bin/env python3
"""
cleanup_r2_redundancies.py
Auditoria e limpeza segura de arquivos redundantes no Cloudflare R2 e no disco local.

Problemas tratados:
1. Chunks intermediários de TTS (*-ricardo-*.mp3, *-peter-*.mp3, *-edge-*.mp3, *.filelist.txt, etc.)
   que subiram indevidamente para o R2 ou ficaram no disco local.
2. Arquivos duplicados com sufixo legado (*-vale-da-liberdade.mp3) quando o arquivo canônico
   (YYYY-MM-DD.mp3) já existe.

Segurança:
- Modo padrão é --dry-run (apenas audita e lista, sem deletar nada).
- Uma duplicata só é deletada se o arquivo canônico correspondente existir e for válido.
- Nunca apaga arquivos de episódios canônicos (YYYY-MM-DD.mp3 ou especial-*.mp3).

Uso:
  # 1. Apenas auditar R2 e local (modo seguro / simulação):
  python scripts/cleanup_r2_redundancies.py --local

  # 2. Executar limpeza real no Cloudflare R2:
  python scripts/cleanup_r2_redundancies.py --apply

  # 3. Executar limpeza real no R2 e também nas pastas locais (audio/ e public/audio/):
  python scripts/cleanup_r2_redundancies.py --apply --local --clean-wavs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "web-jornal-liberdade")


def get_s3_client():
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        print("❌ Credenciais do R2 não configuradas no .env")
        return None
    try:
        import boto3
        from botocore.config import Config

        endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    except Exception as exc:
        print(f"❌ Falha ao inicializar boto3 para R2: {exc}")
        return None


def is_chunk_filename(name: str) -> bool:
    """Verifica se o nome corresponde a um chunk de processamento TTS intermediário ou arquivo de teste antigo."""
    if re.search(r"-(peter|ricardo|edge|moss|el)-\d+", name, re.I):
        return True
    if "-filelist.txt" in name or name.endswith(".filelist.txt"):
        return True
    if "-concat.mp3" in name or "-fx.mp3" in name:
        return True
    if "edge-tts-test" in name or name.startswith("ep_packed"):
        return True
    if re.search(r"\b\d{4}-\d{2}-\d{2}-(edge-tts|kokoro|piper)-", name):
        return True
    return False


def is_duplicate_named(name: str) -> str | None:
    """Retorna o nome canônico se o arquivo for uma duplicata com sufixo -vale-da-liberdade ou -completo."""
    if name.endswith("-vale-da-liberdade.mp3"):
        stem = name[:-len("-vale-da-liberdade.mp3")]
        # Diários: 2026-07-24-vale-da-liberdade.mp3 -> 2026-07-24.mp3
        # Especiais: especial-XXXX-vale-da-liberdade.mp3 -> especial-XXXX.mp3
        if re.match(r"^\d{4}-\d{2}-\d{2}$", stem) or stem.startswith("especial-"):
            return f"{stem}.mp3"
    if name.endswith("-completo.mp3"):
        stem = name[:-len("-completo.mp3")]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", stem) or stem.startswith("especial-"):
            return f"{stem}.mp3"
    return None


def audit_r2(s3) -> tuple[list[dict], list[dict], list[dict]]:
    """Varre o bucket R2 e classifica os objetos."""
    print(f"\n🔍 [R2] Auditando bucket '{R2_BUCKET_NAME}'...")
    paginator = s3.get_paginator("list_objects_v2")

    all_objects = {}
    for page in paginator.paginate(Bucket=R2_BUCKET_NAME, Prefix="audio/"):
        for item in page.get("Contents", []):
            all_objects[item["Key"]] = item

    print(f"   Total de objetos em audio/: {len(all_objects)}")

    chunks_to_delete = []
    duplicates_to_delete = []
    canonical_kept = []

    for key, item in all_objects.items():
        name = key.replace("audio/", "")
        size = item.get("Size", 0)

        # 1. Chunks intermediários
        if is_chunk_filename(name):
            chunks_to_delete.append({"key": key, "name": name, "size": size})
            continue

        # 2. Duplicatas com nome longo
        canonical_target = is_duplicate_named(name)
        if canonical_target:
            canonical_key = f"audio/{canonical_target}"
            # REGRA DE SEGURANÇA: Só apaga a duplicata se o canônico existir no R2
            if canonical_key in all_objects:
                duplicates_to_delete.append({
                    "key": key,
                    "name": name,
                    "size": size,
                    "canonical_key": canonical_key,
                })
            else:
                print(f"   ⚠️ Preservando {key}: canônico {canonical_key} não encontrado no R2")
                canonical_kept.append({"key": key, "name": name, "size": size})
            continue

        # 3. Canônicos
        canonical_kept.append({"key": key, "name": name, "size": size})

    return chunks_to_delete, duplicates_to_delete, canonical_kept


def delete_r2_objects(s3, objects_to_del: list[dict]) -> int:
    """Deleta objetos do R2 em lotes de 1000."""
    if not objects_to_del:
        return 0
    total_deleted = 0
    batch_size = 1000
    for i in range(0, len(objects_to_del), batch_size):
        batch = objects_to_del[i:i + batch_size]
        delete_payload = {"Objects": [{"Key": obj["key"]} for obj in batch]}
        try:
            resp = s3.delete_objects(Bucket=R2_BUCKET_NAME, Delete=delete_payload)
            deleted = len(resp.get("Deleted", []))
            total_deleted += deleted
            if resp.get("Errors"):
                for err in resp["Errors"]:
                    print(f"   ❌ Erro ao deletar {err.get('Key')}: {err.get('Message')}")
        except Exception as exc:
            print(f"   ❌ Falha na exclusão do lote: {exc}")
    return total_deleted


def audit_and_clean_local(apply: bool = False, clean_wavs: bool = False):
    """Audita e opcionalmente limpa chunks e duplicatas no disco local."""
    scan_dirs = [
        PROJECT_ROOT / "public" / "audio",
        PROJECT_ROOT / "audio",
    ]

    print(f"\n💻 [LOCAL] Auditando pastas locais...")
    local_chunks = []
    local_dups = []
    local_wavs = []

    for d in scan_dirs:
        if not d.exists():
            continue

        # Chunks
        for p in d.glob("*"):
            if not p.is_file():
                continue
            if is_chunk_filename(p.name):
                local_chunks.append(p)
            else:
                canon = is_duplicate_named(p.name)
                if canon:
                    canon_path = d / canon
                    # Se canônico existe, este é duplicado redundante
                    if canon_path.exists() and canon_path.stat().st_size > 100_000:
                        local_dups.append((p, canon_path))

        # WAVs intermediários
        if clean_wavs:
            for w in d.glob("*.wav"):
                if w.is_file():
                    # Preserva vozes de referência
                    if "voices" in str(w) or "kokoro" in str(w):
                        continue
                    # Se existe mp3 correspondente
                    m1 = d / (w.stem.replace("-completo", "") + ".mp3")
                    m2 = PROJECT_ROOT / "public" / "audio" / (w.stem.replace("-completo", "") + ".mp3")
                    if (m1.exists() and m1.stat().st_size > 100_000) or (m2.exists() and m2.stat().st_size > 100_000):
                        local_wavs.append(w)

    chunk_bytes = sum(p.stat().st_size for p in local_chunks if p.exists())
    dup_bytes = sum(p.stat().st_size for p, _ in local_dups if p.exists())
    wav_bytes = sum(w.stat().st_size for w in local_wavs if w.exists())

    print(f"   Chunks locais encontrados: {len(local_chunks)} ({chunk_bytes / 1e6:.2f} MB)")
    print(f"   Duplicatas locais encontradas: {len(local_dups)} ({dup_bytes / 1e6:.2f} MB)")
    if clean_wavs:
        print(f"   WAVs intermediários prontos para remoção: {len(local_wavs)} ({wav_bytes / 1e6:.2f} MB)")

    total_local_bytes = chunk_bytes + dup_bytes + wav_bytes
    print(f"   Total recuperável no disco local: {total_local_bytes / 1e6:.2f} MB ({total_local_bytes / 1e9:.2f} GB)")

    if apply:
        print("\n   🗑️ Deletando arquivos locais redundantes...")
        del_count = 0
        for p in local_chunks:
            try:
                p.unlink()
                del_count += 1
            except Exception as e:
                print(f"      Falha ao remover chunk {p.name}: {e}")
        for p, _ in local_dups:
            try:
                p.unlink()
                del_count += 1
            except Exception as e:
                print(f"      Falha ao remover duplicata {p.name}: {e}")
        for w in local_wavs:
            try:
                w.unlink()
                del_count += 1
            except Exception as e:
                print(f"      Falha ao remover wav {w.name}: {e}")
        print(f"   ✅ {del_count} arquivos locais removidos com sucesso!")
    else:
        print("   ℹ️  Modo dry-run ativo: nenhum arquivo local foi alterado.")


def main():
    parser = argparse.ArgumentParser(description="Auditoria e limpeza de redundâncias de áudio (R2 e Local)")
    parser.add_argument("--apply", action="store_true", help="Executa a exclusão real (padrão é dry-run seguro)")
    parser.add_argument("--skip-r2", action="store_true", help="Pula a auditoria/limpeza do Cloudflare R2")
    parser.add_argument("--local", action="store_true", help="Também audita/limpa pastas locais (audio/ e public/audio/)")
    parser.add_argument("--clean-wavs", action="store_true", help="Na limpeza local, também remove WAVs que já possuem MP3 final")
    args = parser.parse_args()

    mode_str = "APLICAÇÃO REAL (--apply)" if args.apply else "DRY-RUN (Simulação segura)"
    print("=" * 65)
    print(f"🧹 VALE DA LIBERDADE - LIMPEZA DE REDUNDÂNCIAS")
    print(f"   Modo: {mode_str}")
    print("=" * 65)

    if not args.skip_r2:
        s3 = get_s3_client()
        if s3:
            chunks, dups, canonical = audit_r2(s3)
            chunk_bytes = sum(c["size"] for c in chunks)
            dup_bytes = sum(d["size"] for d in dups)
            canon_bytes = sum(k["size"] for k in canonical)

            print(f"\n📊 [R2 RESUMO]")
            print(f"   ✅ Arquivos Canônicos (PRESERVADOS): {len(canonical)} ({canon_bytes / 1e6:.1f} MB / {canon_bytes / 1e9:.2f} GB)")
            print(f"   🗑️ Chunks intermediários:          {len(chunks)} ({chunk_bytes / 1e6:.1f} MB)")
            print(f"   🗑️ Duplicatas (-vale-da-liberdade): {len(dups)} ({dup_bytes / 1e6:.1f} MB / {dup_bytes / 1e9:.2f} GB)")

            total_redundant = len(chunks) + len(dups)
            total_redundant_bytes = chunk_bytes + dup_bytes
            print(f"\n   💾 Espaço total recuperável no R2: {total_redundant_bytes / 1e6:.1f} MB ({total_redundant_bytes / 1e9:.2f} GB)")

            if args.apply:
                to_delete = chunks + dups
                print(f"\n🚀 Executando exclusão de {len(to_delete)} objetos redundantes no R2...")
                deleted = delete_r2_objects(s3, to_delete)
                print(f"✅ Sucesso: {deleted} objetos removidos do R2.")
                print(f"🎉 Economizados ~{total_redundant_bytes / 1e9:.2f} GB no R2!")
            else:
                print(f"\nℹ️  Para aplicar a exclusão no R2, execute com a flag: --apply")

    if args.local:
        audit_and_clean_local(apply=args.apply, clean_wavs=args.clean_wavs)

    print("\n" + "=" * 65)
    print("✅ Operação concluída.")
    print("=" * 65)


if __name__ == "__main__":
    main()
