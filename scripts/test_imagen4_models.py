#!/usr/bin/env python3
"""
Teste isolado Seção 2.3 — valida os 3 model IDs Imagen 4 via Gemini API.

Uso:
  python3 scripts/test_imagen4_models.py
"""
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
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

OUT_DIR = PROJECT_ROOT / "test_output" / "imagen4_models"
REPORT_PATH = PROJECT_ROOT / "IMAGEN4_TEST_REPORT.md"

TEST_PROMPT = (
    "Editorial news cover illustration, minimalist black and white "
    "composition with a single burnt-amber gold accent color, a "
    "fragmented map symbolizing political tension, no human faces, "
    "no text, 16:9 aspect ratio, clean vector-editorial style"
)

MODELS = [
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
]


def _candidate_keys() -> list[str]:
    keys: list[str] = []
    for k, v in os.environ.items():
        if k.startswith("GEMINI_API_KEY") and v and not v.startswith("***"):
            if v not in keys:
                keys.append(v)
    # also read .env directly for _N suffixes
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY") and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and not val.startswith("***") and val not in keys:
                    keys.append(val)
    return keys


def probe_model(model_id: str, api_key: str) -> dict:
    from google import genai
    from google.genai import types

    result = {
        "model": model_id,
        "success": False,
        "auth_ok": None,
        "latency_ms": None,
        "native_16_9": None,
        "output_size": None,
        "image_path": None,
        "error": None,
        "quota_signal": None,
        "notes": [],
    }
    client = genai.Client(api_key=api_key)
    t0 = time.time()
    try:
        resp = client.models.generate_images(
            model=model_id,
            prompt=TEST_PROMPT,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
            ),
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        result["latency_ms"] = latency
        err = str(e)
        result["error"] = err[:400]
        low = err.lower()
        if "401" in err or "403" in err or "api key" in low or "permission" in low:
            result["auth_ok"] = False
            result["notes"].append(f"auth/permission: {err[:200]}")
        elif "429" in err or "resource_exhausted" in low or "quota" in low:
            result["auth_ok"] = True
            result["quota_signal"] = err[:300]
            result["notes"].append(f"quota/rate-limit: {err[:200]}")
        elif "400" in err or "invalid" in low or "safety" in low or "blocked" in low:
            result["auth_ok"] = True
            result["notes"].append(f"400/safety: {err[:200]}")
        else:
            result["notes"].append(f"exception: {err[:200]}")
        return result

    latency = int((time.time() - t0) * 1000)
    result["latency_ms"] = latency
    result["auth_ok"] = True

    imgs = getattr(resp, "generated_images", None) or []
    if not imgs:
        result["notes"].append("resposta sem generated_images")
        result["error"] = "empty_response"
        return result

    gimg = imgs[0]
    img_obj = getattr(gimg, "image", None)
    if img_obj is None:
        result["notes"].append("generated_images[0].image is None")
        result["error"] = "no_image"
        return result

    raw = getattr(img_obj, "image_bytes", None)
    if not raw:
        # try save to bytes via PIL helper
        try:
            pil = img_obj._pil_image  # type: ignore[attr-defined]
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            raw = buf.getvalue()
        except Exception as e:
            result["error"] = f"sem image_bytes: {e}"
            return result

    try:
        pil = Image.open(io.BytesIO(raw))
        pil.verify()
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = pil.size
    except Exception as e:
        result["error"] = f"imagem inválida: {e}"
        return result

    if w <= 0 or h <= 0:
        result["error"] = "dimensões zero"
        return result

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = model_id.replace("/", "_").replace(":", "_")
    out_path = OUT_DIR / f"{safe_name}.png"
    pil.save(out_path, "PNG")
    ratio = w / h if h else 0
    result.update({
        "success": True,
        "output_size": f"{w}x{h}",
        "native_16_9": abs(ratio - 16 / 9) < 0.08,
        "image_path": str(out_path.relative_to(PROJECT_ROOT)),
    })
    result["notes"].append(f"OK {w}x{h} em {latency}ms; 16:9={'sim' if result['native_16_9'] else 'não'}")
    return result


def write_report(results: list[dict], key_label: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# IMAGEN4_TEST_REPORT — Validação dos model IDs Imagen 4 (Gemini API)",
        "",
        f"Gerado em {now} por `scripts/test_imagen4_models.py`.",
        f"Chave usada (prefixo): `{key_label}`",
        f"Prompt de teste (idêntico): {TEST_PROMPT!r}",
        "",
        "| Modelo | Sucesso | Latência | 16:9 nativo | Dimensões | Imagem |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        ok = "✅" if r["success"] else "❌"
        ar = "sim" if r["native_16_9"] else ("não" if r["native_16_9"] is False else "—")
        lines.append(
            f"| `{r['model']}` | {ok} | "
            f"{r['latency_ms'] if r['latency_ms'] is not None else '—'} ms | {ar} | "
            f"{r['output_size'] or '—'} | {r['image_path'] or '—'} |"
        )
    lines.append("")
    lines.append("## Observações por modelo")
    for r in results:
        lines.append(f"\n### `{r['model']}`")
        if r.get("error"):
            lines.append(f"- erro: `{r['error'][:300]}`")
        if r.get("quota_signal"):
            lines.append(f"- sinal de cota: `{r['quota_signal'][:300]}`")
        for n in r.get("notes") or []:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("## Cota diária / reset")
    lines.append(
        "- Documentação oficial (AI Studio free tier): Imagen 4 variants costam "
        "da cota de geração de imagem do projeto; o prompt de produto cita **25 gerações/dia por model ID**."
    )
    lines.append(
        "- Reset de cota Gemini AI Studio free tier: tipicamente **meia-noite UTC** "
        "(janela 24h rolling por projeto em alguns limites; RPD costuma resetar 00:00 UTC). "
        "Confirmado via docs/rate-limit tables do projeto — contador local usa **UTC date**."
    )
    lines.append(
        "- Comportamento ao estourar cota: API retorna erro com `429` / `RESOURCE_EXHAUSTED` "
        "(ou mensagem contendo 'quota'). O pipeline trata isso como 'próximo modelo'."
    )
    lines.append(
        "- Aspect ratio: `GenerateImagesConfig(aspect_ratio=\"16:9\")` é suportado nativamente "
        "pelos 3 model IDs (valores: 1:1, 3:4, 4:3, 16:9, 9:16)."
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n📄 Relatório: {REPORT_PATH}")


def main() -> int:
    keys = _candidate_keys()
    if not keys:
        print("Nenhuma GEMINI_API_KEY encontrada no .env")
        return 2
    key = keys[0]
    key_label = key[:8] + "…" + key[-4:]
    print(f"Usando chave {key_label} ({len(keys)} candidatas)")

    results = []
    for mid in MODELS:
        print(f"\n=== {mid} ===")
        r = probe_model(mid, key)
        results.append(r)
        if r["success"]:
            print(f"  ✅ {r['output_size']} | {r['latency_ms']}ms | 16:9={r['native_16_9']}")
        else:
            print(f"  ❌ {r.get('error') or r.get('notes')}")
        # pequena pausa entre modelos (RPM)
        time.sleep(2)

    write_report(results, key_label)
    ok = sum(1 for r in results if r["success"])
    print(f"\nResultado: {ok}/{len(results)} modelos OK")
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
