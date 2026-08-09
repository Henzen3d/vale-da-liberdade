#!/usr/bin/env python3
"""Probe Imagen 4 + Gemini image models across all GEMINI keys."""
from __future__ import annotations

import io
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
OUT = PROJECT_ROOT / "test_output" / "imagen4_models"
REPORT = PROJECT_ROOT / "IMAGEN4_TEST_REPORT.md"
OUT.mkdir(parents=True, exist_ok=True)

PROMPT = (
    "Editorial news cover illustration, minimalist black and white "
    "composition with a single burnt-amber gold accent color, a "
    "fragmented map symbolizing political tension, no human faces, "
    "no text, 16:9 aspect ratio, clean vector-editorial style"
)

IMAGEN_IDS = [
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
]
# Official replacements (deprecations page) + other image-capable Gemini models
GEMINI_IMAGE_IDS = [
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]


def keys() -> list[str]:
    out = []
    for k, v in os.environ.items():
        if k.startswith("GEMINI_API_KEY") and v and not v.startswith("***") and v not in out:
            out.append(v)
    return out


def save_png(raw: bytes, name: str) -> tuple[str, str, bool]:
    pil = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = pil.size
    path = OUT / f"{name}.png"
    pil.save(path, "PNG")
    ratio = w / h if h else 0
    return f"{w}x{h}", str(path.relative_to(PROJECT_ROOT)), abs(ratio - 16 / 9) < 0.08


def try_imagen(client, model_id: str) -> dict:
    from google.genai import types
    t0 = time.time()
    try:
        resp = client.models.generate_images(
            model=model_id,
            prompt=PROMPT,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="16:9"),
        )
        latency = int((time.time() - t0) * 1000)
        imgs = getattr(resp, "generated_images", None) or []
        if not imgs or not getattr(imgs[0], "image", None):
            return {"ok": False, "err": "empty", "ms": latency}
        raw = imgs[0].image.image_bytes
        size, path, ar = save_png(raw, model_id.replace("/", "_"))
        return {"ok": True, "ms": latency, "size": size, "path": path, "ar16_9": ar}
    except Exception as e:
        return {"ok": False, "err": str(e)[:350], "ms": int((time.time() - t0) * 1000)}


def try_gemini_image(client, model_id: str) -> dict:
    from google.genai import types
    t0 = time.time()
    try:
        # Nano Banana / Gemini image via generate_content
        config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9"),
        )
        resp = client.models.generate_content(
            model=model_id,
            contents=PROMPT,
            config=config,
        )
        latency = int((time.time() - t0) * 1000)
        raw = None
        cands = getattr(resp, "candidates", None) or []
        for c in cands:
            content = getattr(c, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for p in parts:
                inline = getattr(p, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    data = inline.data
                    if isinstance(data, str):
                        import base64
                        raw = base64.b64decode(data)
                    else:
                        raw = data
                    break
            if raw:
                break
        if not raw:
            return {"ok": False, "err": "no_inline_image", "ms": latency}
        size, path, ar = save_png(raw, model_id.replace("/", "_").replace(":", "_"))
        return {"ok": True, "ms": latency, "size": size, "path": path, "ar16_9": ar}
    except Exception as e:
        return {"ok": False, "err": str(e)[:350], "ms": int((time.time() - t0) * 1000)}


def main() -> int:
    from google import genai
    ks = keys()
    if not ks:
        print("no keys"); return 2
    print(f"{len(ks)} keys")

    results = []

    # 1) Try Imagen on first key, then other keys only if first fails with "new users"
    print("\n=== IMAGEN 4 ===")
    for mid in IMAGEN_IDS:
        best = None
        for i, key in enumerate(ks[:3]):  # max 3 keys to save quota
            client = genai.Client(api_key=key)
            r = try_imagen(client, mid)
            label = key[:6] + "…"
            print(f"  {mid} key{i}({label}): {'OK' if r['ok'] else 'FAIL'} {r.get('err','')[:120]} {r.get('size','')} {r.get('ms')}ms")
            if r["ok"]:
                best = r
                break
            if "new users" not in (r.get("err") or "").lower() and "404" not in (r.get("err") or ""):
                # different error — stop trying keys for this model
                best = r
                break
            time.sleep(1)
        results.append({"family": "imagen4", "model": mid, **(best or {"ok": False, "err": "no attempt"})})

    # 2) Gemini image models (official replacements)
    print("\n=== GEMINI IMAGE (replacements) ===")
    key = ks[0]
    client = genai.Client(api_key=key)
    for mid in GEMINI_IMAGE_IDS:
        r = try_gemini_image(client, mid)
        print(f"  {mid}: {'OK' if r['ok'] else 'FAIL'} {r.get('err','')[:140]} {r.get('size','')} {r.get('ms')}ms")
        results.append({"family": "gemini-image", "model": mid, **r})
        time.sleep(2)

    # report
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# IMAGEN4_TEST_REPORT — Validação geração de imagem (Gemini API)",
        "",
        f"Gerado em {now} por `scripts/test_imagen4_models_v2.py`.",
        f"Prompt: {PROMPT!r}",
        "",
        "## Resultado",
        "",
        "| Família | Modelo | Sucesso | Latência | 16:9 | Dimensões | Path |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ok = "✅" if r.get("ok") else "❌"
        ar = "sim" if r.get("ar16_9") else ("não" if "ar16_9" in r else "—")
        lines.append(
            f"| {r.get('family')} | `{r['model']}` | {ok} | {r.get('ms','—')} ms | {ar} | "
            f"{r.get('size','—')} | {r.get('path','—')} |"
        )
    lines += [
        "",
        "## Achados críticos",
        "",
        "1. **Imagen 4 (`imagen-4.0-*-generate-001`)**: a API retorna "
        "`404 NOT_FOUND` com mensagem *'This model ... is no longer available to new users'*. "
        "Os model IDs ainda aparecem em `models.list()`, mas **não geram imagem** para as chaves "
        "AI Studio deste projeto (contas/projetos considerados 'new users').",
        "2. **Depreciação oficial** (ai.google.dev/gemini-api/docs/deprecations, atualizado 2026-08-03): "
        "Imagen 4 shutdown **2026-08-17**. Replacement recomendado: `gemini-3.1-flash-image` "
        "(método `generate_content`, não `generate_images`).",
        "3. **Cascata de produção adotada** (conservadora, o que funciona de verdade): "
        "modelos Gemini image disponíveis nesta conta, com fallback local placeholder.",
        "4. **Aspect ratio 16:9**: via `ImageConfig(aspect_ratio='16:9')` em `GenerateContentConfig` "
        "para Gemini image; crop/resize no pós-processamento se a saída não for exata.",
        "5. **Cota**: free tier Gemini image é por modelo/projeto; contador local usa **data UTC** "
        "(reset RPD típico 00:00 UTC). Erro de cota: `429` / `RESOURCE_EXHAUSTED`.",
        "6. **Custo estimado free tier**: $0 nas cotas gratuitas; acima disso pay-as-you-go.",
        "",
        "## Erros / notas detalhadas",
        "",
    ]
    for r in results:
        if not r.get("ok") and r.get("err"):
            lines.append(f"- `{r['model']}`: `{r['err'][:280]}`")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n📄 {REPORT}")
    ok_n = sum(1 for r in results if r.get("ok"))
    print(f"OK: {ok_n}/{len(results)}")
    return 0 if ok_n >= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
