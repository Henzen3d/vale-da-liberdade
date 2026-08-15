#!/usr/bin/env python3
"""
bm_assets_review.py — Revisão dos assets coletados ANTES do render (gate de qualidade).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ASSETS_DIR = ROOT / "output" / "brasil_e_mundo" / "assets"
MIN_WIDTH = 640


def review_quadro(q: dict) -> dict:
    """Avalia um quadro do manifest. Retorna {status, motivos}."""
    motivos: list[str] = []
    status = "ok"
    img_path = q.get("image_path")
    if not img_path:
        return {"status": "sem_imagem", "motivos": ["image_path ausente no manifest"]}
    p = Path(img_path)
    if not p.is_absolute():
        p = ROOT / img_path
        if not p.exists():
            p = ASSETS_DIR.parent.parent.parent / img_path
    if not p.exists():
        proto = ROOT / "references" / "youtube" / "prototype" / img_path
        p = proto if proto.exists() else p
    if not p.exists():
        return {"status": "sem_imagem", "motivos": [f"arquivo não existe: {img_path}"]}

    if Image is not None:
        try:
            with Image.open(p) as im:
                w, h = im.size
            if max(w, h) < MIN_WIDTH:
                motivos.append(f"imagem pequena ({w}x{h} < {MIN_WIDTH}px)")
            if h > w * 1.1:
                motivos.append(f"orientação retrato ({w}x{h}) — tela do quadro é 16:9")
        except Exception as e:
            motivos.append(f"não abre como imagem: {e}")

    src = q.get("image_source")
    if not isinstance(src, dict):
        motivos.append("sem image_source registrado")
        src = {}
    kind = src.get("kind") or ""
    if kind == "wikimedia":
        rel = src.get("relevance") or 0
        try:
            rel = float(rel)
        except Exception:
            rel = 0
        if rel < 2:
            motivos.append(f"wikimedia com relevância fraca (rel={rel}) — stock poderia ser melhor")
    if kind == "og:image" and not src.get("veiculo"):
        motivos.append("og:image sem veículo/origem identificada")

    qtype = q.get("type") or ""
    if qtype == "comentario_materia":
        ss = q.get("screenshot_path") or q.get("screenshot_materia")
        if not ss:
            motivos.append("quadro de comentário sem screenshot da matéria")
        ss_url = (q.get("screenshot_fonte_url") or q.get("fonte_url") or src.get("fonte_url") or "")
        img_url = src.get("image_url") or ""
        if "youtube.com" in ss_url or "youtu.be" in ss_url or "youtube.com" in img_url:
            motivos.append("screenshot/imagem aponta para YouTube (não é print da matéria)")

    if motivos:
        status = "revisar"
    return {"status": status, "motivos": motivos}


def main_impl(opts) -> dict:
    """Núcleo da revisão (reutilizável pelo pipeline)."""
    assets_ep = ASSETS_DIR / opts.video_id
    mpath = assets_ep / "manifest.json"
    if not mpath.exists():
        raise SystemExit(f"❌ manifest não encontrado: {mpath} — rode bm_pipeline.py assets primeiro")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    quadros = manifest.get("quadros") or []
    results = []
    n_ok = n_revisar = n_sem = 0
    for q in quadros:
        r = review_quadro(q)
        r["id"] = q.get("id")
        results.append(r)
        if r["status"] == "ok":
            n_ok += 1
        elif r["status"] == "sem_imagem":
            n_sem += 1
        else:
            n_revisar += 1

    has_issues = n_revisar > 0 or n_sem > 0
    if getattr(opts, "force_approve", False):
        status = "approved_forced"
    elif getattr(opts, "approve", False) and not has_issues:
        status = "approved"
    elif getattr(opts, "approve", False) and has_issues:
        status = "approved_with_caveats"
    elif has_issues:
        status = "changes_requested"
    else:
        status = "pending"

    review = {
        "status": status,
        "resumo": {"ok": n_ok, "revisar": n_revisar, "sem_imagem": n_sem},
        "quadros": results,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "aprovado_por": "dono" if getattr(opts, "approve", False) or getattr(opts, "force_approve", False) else None,
        "episode": f"especial-{opts.video_id}",
    }
    rpath = assets_ep / "review.json"
    rpath.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    if getattr(opts, "json", False):
        print(json.dumps(review, ensure_ascii=False))
        return review

    print(f"📋 Revisão de assets — especial-{opts.video_id}")
    print(f"   status: {status}")
    print(f"   resumo: {n_ok} ok · {n_revisar} revisar · {n_sem} sem imagem")
    for r in results:
        mark = "✅" if r["status"] == "ok" else ("❌" if r["status"] == "sem_imagem" else "⚠️")
        motivos = "; ".join(r.get("motivos") or [])
        extra = f": {motivos}" if motivos else ""
        print(f"   {mark} {r.get('id')} {r['status']}{extra}")
    print(f"\n💾 review.json: {rpath}")
    if status in ("approved", "approved_forced", "approved_with_caveats"):
        print("✅ Aprovado — o render do HyperFrames pode rodar")
    else:
        print("➡️  Antes do render: revise o contact_sheet.jpg e rode com --approve (ou --force-approve para override consciente)")
    return review


def main() -> int:
    ap = argparse.ArgumentParser(description="Revisão de assets antes do render (gate)")
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--approve", action="store_true", help="Marcar como aprovado (dono revisou o contact sheet)")
    ap.add_argument("--force-approve", action="store_true", help="Aprovar mesmo com quadros em 'revisar' (override)")
    ap.add_argument("--json", action="store_true", help="Saída JSON (p/ automação)")
    args = ap.parse_args()
    main_impl(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
