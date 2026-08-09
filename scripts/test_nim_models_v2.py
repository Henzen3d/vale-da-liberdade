#!/usr/bin/env python3
"""
Sonda adaptativa NIM — segunda passada do teste Seção 2.3.

Aprendizados da 1ª passada (NIM_TEST_REPORT.md):
  - flux.1-dev: OK em https://ai.api.nvidia.com/v1/genai/{model_id} (payload SD-like).
  - flux.2-klein-4b: hospedado, exige cfg_scale <= 1.
  - flux.1-schnell: hospedado, exige cfg_scale <= 0.
  - flux.1-kontext-dev: hospedado, height/width presos a lista literal (ex.: 1328, 752...).
  - qwen-image e SD3.5-large: 404 no slug testado — sondar slugs alternativos +
    endpoint OpenAI-compatible /v1/images/generations.

Estratégia: para cada modelo, tentar candidatos; em HTTP 422, parsear o erro
pydantic e reajustar payload (dimensões permitidas, cfg/steps máximos) e retryar.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
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
TIMEOUT = 240

TEST_PROMPT = (
    "Editorial news cover illustration, minimalist black and white "
    "composition with a single burnt-amber gold accent color, a "
    "fragmented map symbolizing political tension, no human faces, "
    "no text, 16:9 aspect ratio, clean vector-editorial style"
)

GENAI = "https://ai.api.nvidia.com/v1/genai/{mid}"
OPENAI_IMAGES_GENAI = "https://ai.api.nvidia.com/v1/images/generations"
OPENAI_IMAGES_INTEGRATE = "https://integrate.api.nvidia.com/v1/images/generations"


def pick_16_9(allowed: list[int]) -> tuple[int, int] | None:
    """Escolhe par (width, height) ~16:9 dentro da lista literal permitida."""
    allowed = sorted(set(allowed))
    best = None
    for w in allowed:
        for h in allowed:
            if h <= 0:
                continue
            r = w / h
            if 1.5 < r < 2.0:
                score = abs(r - 16 / 9) - 0.0001 * (w + h)  # prefere exato, depois maior
                if best is None or score < best[0]:
                    best = (score, w, h)
    if best:
        return best[1], best[2]
    return None


class Probe:
    def __init__(self, name: str, env: str, model_ids: list[str]):
        self.name = name
        self.key = os.environ.get(env, "").strip()
        self.env = env
        self.model_ids = model_ids
        self.notes: list[str] = []
        self.result = {
            "model": name,
            "model_id_tried": model_ids,
            "endpoint_worked": None,
            "auth_ok": None,
            "success": False,
            "latency_ms": None,
            "native_16_9": None,
            "output_size": None,
            "image_path": None,
            "notes": self.notes,
        }

    def log(self, msg: str) -> None:
        print(f"    · {msg}")
        self.notes.append(msg)

    def post(self, url: str, payload: dict, label: str):
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            self.log(f"{label}: erro de rede {type(e).__name__}")
            return None, None
        latency = int((time.time() - t0) * 1000)
        return resp, latency

    def try_decode(self, resp, latency, label) -> bool:
        """Se resp 200 com imagem válida → grava e retorna True."""
        try:
            data = resp.json()
        except ValueError:
            self.log(f"{label}: 200 não-JSON ({len(resp.content)} bytes)")
            return False
        b64 = None
        if isinstance(data, dict):
            items = data.get("data")
            if isinstance(items, list) and items and isinstance(items[0], dict):
                b64 = items[0].get("b64_json") or items[0].get("image_base64")
                if not b64 and items[0].get("url"):
                    try:
                        r2 = requests.get(items[0]["url"], timeout=120)
                        if r2.status_code == 200:
                            b64 = base64.b64encode(r2.content).decode()
                    except requests.exceptions.RequestException:
                        pass
            arts = data.get("artifacts")
            if not b64 and isinstance(arts, list) and arts and isinstance(arts[0], dict):
                b64 = arts[0].get("base64") or arts[0].get("image_base64")
            if not b64:
                for k in ("image_base64", "b64_json"):
                    if isinstance(data.get(k), str):
                        b64 = data[k]
                        break
            if not b64 and isinstance(data.get("b64_images"), list) and data["b64_images"]:
                b64 = data["b64_images"][0]
        if not b64:
            keys = list(data)[:10] if isinstance(data, dict) else "?"
            self.log(f"{label}: 200 sem imagem reconhecível — keys={keys}")
            return False
        try:
            raw = base64.b64decode(b64)
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            img.verify()
            img = Image.open(io.BytesIO(raw))
            w, h = img.size
        except Exception as e:
            self.log(f"{label}: imagem inválida: {e}")
            return False
        if w <= 0 or h <= 0:
            self.log(f"{label}: dimensões zero")
            return False
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / f"{self.name}.png"
        from PIL import Image
        Image.open(io.BytesIO(raw)).convert("RGB").save(out_path, "PNG")
        ratio = w / h
        self.result.update({
            "auth_ok": True,
            "success": True,
            "endpoint_worked": label,
            "latency_ms": latency,
            "output_size": f"{w}x{h}",
            "native_16_9": abs(ratio - 16 / 9) < 0.06,
            "image_path": str(out_path.relative_to(PROJECT_ROOT)),
        })
        self.log(f"{label}: ✅ {w}x{h} em {latency}ms")
        return True

    def parse_422(self, resp) -> dict:
        """Extrai constraints de erro pydantic: {campo: {'le': x, 'literals': [...]}}."""
        out: dict = {}
        try:
            detail = resp.json().get("detail", [])
        except ValueError:
            return out
        for item in detail:
            if not isinstance(item, dict):
                continue
            loc = item.get("loc") or []
            field = loc[-1] if loc else None
            if not field:
                continue
            entry = out.setdefault(str(field), {})
            ctx = item.get("ctx") or {}
            if "le" in ctx:
                entry["le"] = ctx["le"]
            if "ge" in ctx:
                entry["ge"] = ctx["ge"]
            if item.get("type") == "literal_error" and "expected" in ctx:
                m = re.findall(r"-?\d+", str(ctx["expected"]))
                entry["literals"] = [int(x) for x in m]
            if item.get("type") == "extra_forbidden":
                entry["forbidden"] = True
        return out

    def build_payload(self, constraints: dict, mid: str, openai_style: bool) -> dict:
        """Monta payload respeitando constraints aprendidas."""
        w, h = 1344, 768
        if "height" in constraints and constraints["height"].get("literals"):
            pair = pick_16_9(constraints["height"]["literals"])
            if pair:
                w, h = pair
        if "width" in constraints and constraints["width"].get("literals"):
            pair = pick_16_9(constraints["width"]["literals"])
            if pair:
                w, h = pair
        payload: dict
        if openai_style:
            payload = {"prompt": TEST_PROMPT, "n": 1, "height": h, "width": w,
                       "response_format": "b64_json"}
            if not constraints.get("model", {}).get("forbidden"):
                pass  # model só é proibido no path genai; no /v1/images/generations é obrigatório
        else:
            payload = {"prompt": TEST_PROMPT, "height": h, "width": w, "seed": 42}
            cfg_max = constraints.get("cfg_scale", {}).get("le")
            if "cfg_scale" in constraints:
                payload["cfg_scale"] = float(cfg_max) if cfg_max is not None else 0.0
            else:
                payload["cfg_scale"] = 5.0
            steps_max = constraints.get("steps", {}).get("le")
            payload["steps"] = int(steps_max) if steps_max else 28
            # campos proibidos (extra_forbidden) são removidos
            payload = {k: v for k, v in payload.items()
                       if not constraints.get(k, {}).get("forbidden")}
        return payload

    def run(self) -> dict:
        if not self.key or self.key.startswith("***"):
            self.log(f"chave ausente/mascarada em {self.env}")
            return self.result

        for mid in self.model_ids:
            constraints: dict = {}
            for attempt in range(3):
                label = f"genai {mid}"
                url = GENAI.format(mid=mid)
                payload = self.build_payload(constraints, mid, openai_style=False)
                resp, latency = self.post(url, payload, label)
                if resp is None:
                    break
                if resp.status_code == 200 and self.try_decode(resp, latency, label):
                    return self.result
                if resp.status_code in (401, 403):
                    self.log(f"{label}: HTTP {resp.status_code} auth — {resp.text[:150]!r}")
                    self.result["auth_ok"] = False
                    return self.result
                if resp.status_code == 422:
                    new_constraints = self.parse_422(resp)
                    if not new_constraints or new_constraints == constraints:
                        self.log(f"{label}: 422 sem constraint nova — {resp.text[:250]!r}")
                        break
                    constraints.update(new_constraints)
                    self.log(f"{label}: 422 → ajustando {sorted(constraints)} (tentativa {attempt+2})")
                    continue
                if resp.status_code == 400:
                    self.log(f"{label}: 400 — {resp.text[:200]!r}")
                    break
                self.log(f"{label}: HTTP {resp.status_code} — {resp.text[:150]!r}")
                break

        # Candidatos OpenAI-compatible (qwen/SD3.5 podem só existir nesse formato)
        for base in (OPENAI_IMAGES_GENAI, OPENAI_IMAGES_INTEGRATE):
            for mid in self.model_ids:
                label = f"{base.split('//')[1]} model={mid}"
                payload = {"model": mid, "prompt": TEST_PROMPT, "n": 1,
                           "height": 768, "width": 1344, "response_format": "b64_json"}
                resp, latency = self.post(base, payload, label)
                if resp is None:
                    continue
                if resp.status_code == 200 and self.try_decode(resp, latency, label):
                    return self.result
                if resp.status_code in (401, 403):
                    self.log(f"{label}: HTTP {resp.status_code} auth — {resp.text[:150]!r}")
                    self.result["auth_ok"] = False
                    return self.result
                self.log(f"{label}: HTTP {resp.status_code} — {resp.text[:150]!r}")
        return self.result


MODELS = [
    Probe("qwen-image", "NVIDIA_API_KEY_QWEN_IMAGE",
          ["qwen/qwen-image", "qwen/qwen-image-2512", "qwen/qwen_image"]),
    Probe("stable-diffusion-3.5-large", "NVIDIA_API_KEY_SD35_LARGE",
          ["stabilityai/stable-diffusion-3.5-large", "stabilityai/sdxl-turbo",
           "stability-ai/stable-diffusion-3.5-large", "stabilityai/stable-diffusion-3-5-large"]),
    Probe("flux.2-klein-4b", "NVIDIA_API_KEY_FLUX2_KLEIN_4B",
          ["black-forest-labs/flux.2-klein-4b"]),
    Probe("flux.1-schnell", "NVIDIA_API_KEY_FLUX1_SCHNELL",
          ["black-forest-labs/flux.1-schnell"]),
    Probe("flux.1-dev", "NVIDIA_API_KEY_FLUX1_DEV",
          ["black-forest-labs/flux.1-dev"]),
    Probe("flux.1-kontext-dev", "NVIDIA_API_KEY_FLUX1_KONTEXT_DEV",
          ["black-forest-labs/flux.1-kontext-dev"]),
]


def main() -> int:
    results = []
    for p in MODELS:
        print(f"\n=== {p.name} ({p.env}) ===")
        results.append(p.run())

    # relatório
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# NIM_TEST_REPORT — Validação das chaves/modelos NVIDIA NIM",
        "",
        f"Gerado em {now} por `scripts/test_nim_models.py` (passada adaptativa).",
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
        for n in r["notes"] or ["- (sem observações)"]:
            lines.append(f"- {n}")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n📄 Relatório: {REPORT_PATH}")
    ok_count = sum(1 for r in results if r["success"])
    print(f"Resultado: {ok_count}/{len(results)} modelos OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
