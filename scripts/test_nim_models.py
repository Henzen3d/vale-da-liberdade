#!/usr/bin/env python3
"""
Teste isolado (Seção 2.3 do prompt de thumbnails) — valida as 6 chaves NVIDIA NIM
ANTES de codificar a cascata de produção.

Para cada modelo:
  1. Tenta múltiplos candidatos de endpoint (hosted genai + OpenAI-compatible),
     pois o catálogo build.nvidia.com não usa um padrão único.
  2. Usa o MESMO prompt de teste para todos (comparação justa).
  3. Confirma: (a) autenticação sem 401/403, (b) imagem válida via Pillow,
     (c) latência, (d) suporte nativo a 16:9 vs necessidade de crop.
  4. Salva a imagem em test_output/nim_models/{nome}.png
  5. Escreve NIM_TEST_REPORT.md na raiz do projeto.

Uso:
  python3 scripts/test_nim_models.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

OUT_DIR = PROJECT_ROOT / "test_output" / "nim_models"
REPORT_PATH = PROJECT_ROOT / "NIM_TEST_REPORT.md"

TEST_PROMPT = (
    "Editorial news cover illustration, minimalist black and white "
    "composition with a single burnt-amber gold accent color, a "
    "fragmented map symbolizing political tension, no human faces, "
    "no text, 16:9 aspect ratio, clean vector-editorial style"
)

HOSTED_GENAI = "https://ai.api.nvidia.com/v1/genai/{model_id}"
HOSTED_OPENAI = "https://ai.api.nvidia.com/v1/images/generations"

# Model ID → (env var da chave, dimensões nativas 16:9 candidatas)
MODELS = {
    "qwen-image": {
        "env": "NVIDIA_API_KEY_QWEN_IMAGE",
        "hosted_ids": ["qwen/qwen-image"],
        "sizes": [(1344, 768), (1328, 744)],
        "aspect_ratio_param": "aspect_ratio",
    },
    "stable-diffusion-3.5-large": {
        "env": "NVIDIA_API_KEY_SD35_LARGE",
        "hosted_ids": ["stabilityai/stable-diffusion-3.5-large"],
        "sizes": [(1344, 768), (1024, 576)],
        "aspect_ratio_param": None,
    },
    "flux.2-klein-4b": {
        "env": "NVIDIA_API_KEY_FLUX2_KLEIN_4B",
        "hosted_ids": ["black-forest-labs/flux.2-klein-4b"],
        "sizes": [(1344, 768), (1024, 576)],
        "aspect_ratio_param": None,
    },
    "flux.1-schnell": {
        "env": "NVIDIA_API_KEY_FLUX1_SCHNELL",
        "hosted_ids": ["black-forest-labs/flux.1-schnell"],
        "sizes": [(1344, 768), (1024, 576)],
        "aspect_ratio_param": None,
    },
    "flux.1-dev": {
        "env": "NVIDIA_API_KEY_FLUX1_DEV",
        "hosted_ids": ["black-forest-labs/flux.1-dev"],
        "sizes": [(1344, 768), (1024, 576)],
        "aspect_ratio_param": None,
    },
    "flux.1-kontext-dev": {
        "env": "NVIDIA_API_KEY_FLUX1_KONTEXT_DEV",
        "hosted_ids": ["black-forest-labs/flux.1-kontext-dev"],
        "sizes": [(1344, 768), (1024, 576)],
        "aspect_ratio_param": None,
    },
}

TIMEOUT = 180


def _extract_image_b64(data: dict) -> str | None:
    """Extrai b64 de formatos conhecidos de resposta NIM/OpenAI."""
    if not isinstance(data, dict):
        return None
    # OpenAI-compatible: {"data": [{"b64_json": "..."}]}
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            if first.get("b64_json"):
                return first["b64_json"]
            if first.get("image_base64"):
                return first["image_base64"]
    # hosted genai: {"artifacts": [{"base64": "..."}]}
    arts = data.get("artifacts")
    if isinstance(arts, list) and arts:
        first = arts[0]
        if isinstance(first, dict):
            for k in ("base64", "image_base64", "b64"):
                if first.get(k):
                    return first[k]
    # resposta direta {"image_base64": ...} ou {"b64_images": [...]}
    for k in ("image_base64", "b64_json", "image"):
        v = data.get(k)
        if isinstance(v, str) and len(v) > 200:
            return v
    arr = data.get("b64_images")
    if isinstance(arr, list) and arr and isinstance(arr[0], str):
        return arr[0]
    return None


def _extract_image_url(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    items = data.get("data")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        if items[0].get("url"):
            return items[0]["url"]
    if isinstance(data.get("image_url"), str):
        return data["image_url"]
    return None


def _validate_b64(b64: str) -> tuple[bool, str]:
    from PIL import Image

    try:
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img2 = Image.open(io.BytesIO(raw))
        w, h = img2.size
        if w <= 0 or h <= 0:
            return False, "dimensões zero"
        return True, f"{w}x{h}"
    except Exception as e:
        return False, f"imagem inválida: {e}"


def probe_model(name: str, cfg: dict) -> dict:
    key = os.environ.get(cfg["env"], "").strip()
    result = {
        "model": name,
        "model_id_tried": [],
        "endpoint_worked": None,
        "auth_ok": None,
        "success": False,
        "latency_ms": None,
        "native_16_9": None,
        "output_size": None,
        "image_path": None,
        "notes": [],
    }
    if not key or key.startswith("***"):
        result["notes"].append(f"chave ausente/mascarada em {cfg['env']}")
        return result

    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    candidates: list[tuple[str, str, dict]] = []  # (url, label, payload)
    w16, h16 = cfg["sizes"][0]

    # A) hosted genai, por model_id do catálogo, payload estilo SD
    for mid in cfg["hosted_ids"]:
        result["model_id_tried"].append(mid)
        candidates.append((
            HOSTED_GENAI.format(model_id=mid),
            f"hosted-genai {mid} (width/height)",
            {
                "prompt": TEST_PROMPT,
                "height": h16,
                "width": w16,
                "cfg_scale": 5.0,
                "steps": 28,
                "seed": 42,
            },
        ))
        if cfg.get("aspect_ratio_param"):
            candidates.append((
                HOSTED_GENAI.format(model_id=mid),
                f"hosted-genai {mid} (aspect_ratio=16:9)",
                {
                    "prompt": TEST_PROMPT,
                    "aspect_ratio": "16:9",
                    "seed": 42,
                },
            ))
    # B) OpenAI-compatible no mesmo path genai
    for mid in cfg["hosted_ids"]:
        candidates.append((
            HOSTED_GENAI.format(model_id=mid),
            f"hosted-genai-openai {mid}",
            {"model": mid, "prompt": TEST_PROMPT, "n": 1,
             "height": h16, "width": w16, "response_format": "b64_json"},
        ))
    # C) endpoint OpenAI-compatível global /v1/images/generations
    for mid in cfg["hosted_ids"]:
        candidates.append((
            HOSTED_OPENAI,
            f"openai-compat /v1/images/generations model={mid}",
            {"model": mid, "prompt": TEST_PROMPT, "n": 1,
             "height": h16, "width": w16, "response_format": "b64_json"},
        ))

    for url, label, payload in candidates:
        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            result["notes"].append(f"{label}: TIMEOUT ({TIMEOUT}s)")
            continue
        except requests.exceptions.RequestException as e:
            result["notes"].append(f"{label}: erro de rede {e}")
            continue
        latency = int((time.time() - t0) * 1000)

        if resp.status_code in (401, 403):
            result["auth_ok"] = False
            result["notes"].append(f"{label}: HTTP {resp.status_code} (auth) — {resp.text[:180]!r}")
            # mesma chave não vai autenticar em outro path; encerra este modelo
            return result

        if resp.status_code == 400:
            result["notes"].append(f"{label}: HTTP 400 — {resp.text[:220]!r}")
            continue
        if resp.status_code == 404:
            result["notes"].append(f"{label}: HTTP 404 (modelo/endpoint não hospedado)")
            continue
        if resp.status_code == 429:
            result["notes"].append(f"{label}: HTTP 429 rate-limit — {resp.text[:160]!r}")
            continue
        if resp.status_code >= 500:
            result["notes"].append(f"{label}: HTTP {resp.status_code} server")
            continue
        if resp.status_code != 200:
            result["notes"].append(f"{label}: HTTP {resp.status_code} — {resp.text[:180]!r}")
            continue

        try:
            data = resp.json()
        except ValueError:
            result["notes"].append(f"{label}: resposta não-JSON ({len(resp.content)} bytes)")
            continue

        b64 = _extract_image_b64(data)
        if not b64:
            img_url = _extract_image_url(data)
            if img_url:
                try:
                    r2 = requests.get(img_url, timeout=120)
                    b64 = base64.b64encode(r2.content).decode() if r2.status_code == 200 else None
                except requests.exceptions.RequestException:
                    b64 = None
        if not b64:
            result["notes"].append(f"{label}: 200 sem bloco de imagem reconhecível — keys={list(data)[:8]}")
            continue

        ok, size_info = _validate_b64(b64)
        if not ok:
            result["notes"].append(f"{label}: bytes retornados mas {size_info}")
            continue

        # sucesso
        result["auth_ok"] = True
        result["success"] = True
        result["endpoint_worked"] = label
        result["latency_ms"] = latency
        result["output_size"] = size_info
        w, h = (int(x) for x in size_info.split("x"))
        ratio = w / h if h else 0
        result["native_16_9"] = abs(ratio - 16 / 9) < 0.06
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"{name}.png"
        from PIL import Image
        raw = base64.b64decode(b64)
        Image.open(io.BytesIO(raw)).convert("RGB").save(out_path, "PNG")
        result["image_path"] = str(out_path.relative_to(PROJECT_ROOT))
        return result

    # nenhuma candidata funcionou, mas se houve só 400/429/404 a chave pode estar ok
    if result["auth_ok"] is None:
        result["notes"].append("nenhum endpoint retornou imagem; auth não confirmada")
    return result


def write_report(results: list[dict]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# NIM_TEST_REPORT — Validação das chaves/modelos NVIDIA NIM",
        "",
        f"Gerado em {now} por `scripts/test_nim_models.py`.",
        f"Prompt de teste (idêntico para todos): {TEST_PROMPT!r}",
        "",
        "| Modelo | Sucesso | Endpoint | Latência | 16:9 nativo | Dimensões | Imagem |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ok = "✅" if r["success"] else "❌"
        ar = "sim" if r["native_16_9"] else ("não" if r["native_16_9"] is False else "—")
        lines.append(
            f"| {r['model']} | {ok} | {r['endpoint_worked'] or '—'} | "
            f"{r['latency_ms'] if r['latency_ms'] is not None else '—'} ms | {ar} | "
            f"{r['output_size'] or '—'} | {r['image_path'] or '—'} |"
        )
    lines.append("")
    lines.append("## Observações por modelo")
    for r in results:
        lines.append(f"\n### {r['model']}")
        if r["notes"]:
            for n in r["notes"]:
                lines.append(f"- {n}")
        else:
            lines.append("- (sem observações)")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n📄 Relatório: {REPORT_PATH}")


def main() -> int:
    results = []
    for name, cfg in MODELS.items():
        print(f"\n=== Testando {name} ({cfg['env']}) ===")
        r = probe_model(name, cfg)
        results.append(r)
        if r["success"]:
            print(f"  ✅ OK via {r['endpoint_worked']} | {r['latency_ms']}ms | {r['output_size']} | 16:9={r['native_16_9']}")
        else:
            print(f"  ❌ falhou — {r['notes'][-2:] if r['notes'] else '?'}")
    write_report(results)
    ok_count = sum(1 for r in results if r["success"])
    print(f"\nResultado final: {ok_count}/{len(results)} modelos OK")
    return 0 if ok_count >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
