#!/usr/bin/env python3
"""Backfill de referências — Pipeline Brasil e Mundo.

Adiciona `fonte_referencias` aos especiais BM já existentes (gerados antes da
extração focada na seção "Referências:" da descrição do YouTube):

1. Re-extrai os links da seção "Referências:" da descrição armazenada no raw;
2. Fallback: fonte_urls antigos (filtrando autopromoção/redes);
3. Acrescenta os links do nosso próprio site (página do episódio + matéria
   transcrita);
4. Corrige `fonte_veiculo` (primeiro veículo externo, sem o ruído tipo
   "ANCAP.SU"/"Visão Libertária");
5. Regenera o .md (que agora renderiza o bloco "> Referências:") e reconstrói
   o índice consolidado output/brasil_e_mundo/referencias.json (base futura
   para fundos/imagens de background dos vídeos do YouTube).

Uso:
    python scripts/bm_backfill_referencias.py            # só os que faltam
    python scripts/bm_backfill_referencias.py --force    # reescreve todos
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from bm_condensador import (  # noqa: E402
    EPS_DIR,
    RAW_DIR,
    enrich_referencias,
    render_roteiro_md,
    write_referencias_index,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reescreve fonte_referencias mesmo nos que já têm",
    )
    args = parser.parse_args()

    updated = 0
    skipped = 0
    missing_raw = 0
    for p in sorted(EPS_DIR.glob("especial-*.json")):
        video_id = p.name[len("especial-"): -len(".json")]
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ⚠️  {p.name}: JSON inválido ({exc}) — pulando")
            skipped += 1
            continue

        if data.get("fonte_referencias") and not args.force:
            skipped += 1
            continue

        raw_path = RAW_DIR / f"{video_id}.json"
        if not raw_path.exists():
            print(f"  ⚠️  {video_id}: raw ausente — pulando")
            missing_raw += 1
            skipped += 1
            continue

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if args.force:
            # --force = reconstrói do zero (enrich_referencias pula se já existe)
            data.pop("fonte_referencias", None)
        if not enrich_referencias(data, raw, video_id):
            print(f"  ⚠️  {video_id}: nenhuma referência derivável — pulando")
            skipped += 1
            continue

        refs = data["fonte_referencias"]
        externas = [r for r in refs if not r.get("self")]

        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        md_out = EPS_DIR / f"especial-{video_id}.md"
        md_out.write_text(render_roteiro_md(data, video_id), encoding="utf-8")
        n_ext = len(externas)
        print(
            f"  ✅ {video_id}: {len(refs)} referências "
            f"({n_ext} externas) · fonte: {data['fonte_veiculo']}"
        )
        updated += 1

    idx_path = write_referencias_index()
    index = json.loads(idx_path.read_text(encoding="utf-8"))
    total = len(index.get("episodes", {}))
    print(f"\n📊 Atualizados: {updated} · já ok/sem raw: {skipped} (raw ausente: {missing_raw})")
    print(f"🗂️  Índice consolidado: {idx_path} ({total} episódios)")
    print("➡️  Rode publish_site.py depois para o site refletir as referências.")


if __name__ == "__main__":
    main()
