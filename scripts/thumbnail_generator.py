#!/usr/bin/env python3
"""
Geração automática de thumbnail/capa por episódio — Web Jornal Vale da Liberdade.

Fluxo (não-bloqueante no pipeline principal):
  A) Extrair pauta principal (1ª manchete / 1ª notícia do roteiro)
  B) Gerar prompt de imagem via Gemini Flash (texto)
  C) Cascata DashScope (Alibaba Model Studio): 8 modelos Qwen/Wan/Z-Image
  D) Pós-processar (16:9, webp+jpg) e salvar em thumbnails/{date}/{episode_id}.*
  E) Atualizar metadata do episódio com bloco "thumbnail"
  F) Fallback final: placeholder local (sem rede)

Uso:
  python3 scripts/thumbnail_generator.py --date 2026-08-05
  python3 scripts/thumbnail_generator.py --date 2026-08-05 --force
  python3 scripts/thumbnail_generator.py --episode-id bm_VIDEOID --headline "..." --summary "..."
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageStat

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
# Chave DashScope também pode estar no Hermes
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    load_dotenv(dotenv_path=_hermes_env, override=False)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
THUMBNAILS_DIR = PROJECT_ROOT / "thumbnails"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "thumbnail_generation.log"
QUOTA_DB = PROJECT_ROOT / "sources" / "image_quota_tracker.json"
EPISODES_DIR = PROJECT_ROOT / "episodes"
COVER_FALLBACK = PROJECT_ROOT / "public" / "assets" / "cover.jpg"
CASCADE_RANK_FILE = PROJECT_ROOT / "sources" / "thumbnail_cascade_rank.json"

# ---------------------------------------------------------------------------
# Logging (JSON lines)
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)


class _JsonLineHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "msg": record.getMessage(),
            }
            extra = getattr(record, "extra_data", None)
            if isinstance(extra, dict):
                payload.update(extra)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


log = logging.getLogger("thumbnail-generator")
if not log.handlers:
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [thumb] %(message)s", "%H:%M:%S"))
    log.addHandler(sh)
    log.addHandler(_JsonLineHandler())
    log.setLevel(logging.INFO)


def _log_event(msg: str, **data: Any) -> None:
    rec = log.makeRecord(log.name, logging.INFO, __file__, 0, msg, (), None)
    rec.extra_data = data
    log.handle(rec)


# ---------------------------------------------------------------------------
# Design tokens (editorial — preto/branco + âmbar)
# ---------------------------------------------------------------------------
AMBER = (184, 134, 59)       # #B8863B
BLACK = (20, 20, 19)
WHITE = (250, 249, 245)
GRAY = (120, 118, 110)
TARGET_W, TARGET_H = 1280, 720
WEBP_Q = 85
JPEG_Q = 85

# ---------------------------------------------------------------------------
# DashScope / Alibaba Model Studio
# ---------------------------------------------------------------------------
# Região intl (Singapore) — confirmada com DASHSCOPE_API_KEY do Hermes (sk-ws-*)
DASHSCOPE_BASE = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/api/v1",
).rstrip("/")
MM_ENDPOINT = f"{DASHSCOPE_BASE}/services/aigc/multimodal-generation/generation"
WAN_ENDPOINT = f"{DASHSCOPE_BASE}/services/aigc/image-generation/generation"
ASYNC_ENDPOINT = f"{DASHSCOPE_BASE}/services/aigc/text2image/image-synthesis"
TASK_ENDPOINT = f"{DASHSCOPE_BASE}/tasks/{{task_id}}"

# size 16:9 nativo preferido (Qwen 2.x/3.x / plus / max)
SIZE_16_9 = "1664*928"
SIZE_16_9_ALT = "1280*720"
SIZE_WAN = "1280*720"


@dataclass
class ImageModel:
    """Modelo de imagem na cascata de produção."""
    name: str                         # id canônico (= model id da API)
    model_id: str                     # id enviado à API
    env_key: str = "DASHSCOPE_API_KEY"
    api_style: str = "multimodal"     # multimodal | wan | async
    size: str = SIZE_16_9
    cost_usd: float = 0.03
    daily_quota: int = 40
    enabled: bool = True
    extra_params: dict = field(default_factory=dict)


# Cascata inicial (Seção 2.1). Pode ser reordenada por sources/thumbnail_cascade_rank.json
# após MODEL_TEST_REPORT.
DEFAULT_CASCADE: list[ImageModel] = [
    ImageModel(name="qwen-image-3.0", model_id="qwen-image-3.0",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.05, daily_quota=30),
    ImageModel(name="qwen-image-2.0-pro", model_id="qwen-image-2.0-pro",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.04, daily_quota=40),
    ImageModel(name="qwen-image-2.0", model_id="qwen-image-2.0",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.03, daily_quota=50),
    ImageModel(name="qwen-image-max", model_id="qwen-image-max",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.04, daily_quota=40),
    ImageModel(name="qwen-image-plus", model_id="qwen-image-plus",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.02, daily_quota=80),
    ImageModel(name="wan2.7-image-pro", model_id="wan2.7-image-pro",
               api_style="wan", size=SIZE_WAN, cost_usd=0.04, daily_quota=30),
    ImageModel(name="wan2.7-image", model_id="wan2.7-image",
               api_style="wan", size=SIZE_WAN, cost_usd=0.03, daily_quota=40),
    ImageModel(name="z-image-turbo", model_id="z-image-turbo",
               api_style="multimodal", size=SIZE_16_9, cost_usd=0.01, daily_quota=100),
]

PROMPT_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash"]
RETRY_BACKOFFS = (3.0, 8.0)
HTTP_TIMEOUT = 180
ASYNC_POLL_MAX = 60
ASYNC_POLL_SLEEP = 2.0


def _load_cascade() -> list[ImageModel]:
    """Carrega cascata padrão, reordenando se houver ranking empírico."""
    by_name = {m.name: m for m in DEFAULT_CASCADE}
    if CASCADE_RANK_FILE.exists():
        try:
            data = json.loads(CASCADE_RANK_FILE.read_text(encoding="utf-8"))
            order = data.get("order") or []
            enabled_map = data.get("enabled") or {}
            style_map = data.get("api_style") or {}
            size_map = data.get("size") or {}
            ordered: list[ImageModel] = []
            seen = set()
            for name in order:
                if name in by_name and name not in seen:
                    m = by_name[name]
                    if name in enabled_map:
                        m.enabled = bool(enabled_map[name])
                    if name in style_map:
                        m.api_style = str(style_map[name])
                    if name in size_map:
                        m.size = str(size_map[name])
                    ordered.append(m)
                    seen.add(name)
            for m in DEFAULT_CASCADE:
                if m.name not in seen:
                    ordered.append(m)
            return ordered
        except (json.JSONDecodeError, OSError, TypeError) as e:
            log.warning("falha ao ler cascade rank: %s", e)
    return list(DEFAULT_CASCADE)


PRODUCTION_CASCADE: list[ImageModel] = _load_cascade()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class SafetyRejected(Exception):
    """HTTP 400 / DataInspectionFailed — prompt rejeitado. Não reusar no próximo modelo."""


class ModelFailed(Exception):
    """Falha recuperável — cai para o próximo modelo."""


class AllModelsFailed(Exception):
    """Cascata inteira falhou."""


# ---------------------------------------------------------------------------
# Quota tracker (JSON, compartilhado entre pipelines)
# Reset: America/Sao_Paulo meia-noite (conservador; DashScope free tier costuma
# resetar em UTC 00:00 — documentado em DECISIONS.md).
# ---------------------------------------------------------------------------
def _today_key() -> str:
    brt = timezone(timedelta(hours=-3))
    return datetime.now(brt).strftime("%Y-%m-%d")


def _load_quota() -> dict:
    if not QUOTA_DB.exists():
        return {"day": _today_key(), "models": {}}
    try:
        data = json.loads(QUOTA_DB.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"day": _today_key(), "models": {}}
    if data.get("day") != _today_key():
        return {"day": _today_key(), "models": {}}
    return data


def _save_quota(data: dict) -> None:
    QUOTA_DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUOTA_DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(QUOTA_DB)


def quota_remaining(model_id: str, daily_limit: int) -> int:
    data = _load_quota()
    used = int(data.get("models", {}).get(model_id, {}).get("count", 0))
    return max(0, daily_limit - used)


def quota_increment(model_id: str) -> None:
    data = _load_quota()
    models = data.setdefault("models", {})
    entry = models.setdefault(model_id, {"count": 0})
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last"] = datetime.now(timezone.utc).isoformat()
    _save_quota(data)


def quota_snapshot(cascade: list[ImageModel] | None = None) -> dict[str, int]:
    cascade = cascade or PRODUCTION_CASCADE
    return {m.model_id: quota_remaining(m.model_id, m.daily_quota) for m in cascade}


# ---------------------------------------------------------------------------
# Etapa A — extrair pauta principal
# ---------------------------------------------------------------------------
def extract_main_story(
    date: str | None = None,
    episode_id: str | None = None,
    headline: str | None = None,
    summary: str | None = None,
) -> dict:
    """Retorna {headline, summary, episode_id, date} a partir do roteiro/JSON."""
    if headline:
        return {
            "headline": headline.strip(),
            "summary": (summary or headline).strip(),
            "episode_id": episode_id or date or "unknown",
            "date": date or datetime.now().strftime("%Y-%m-%d"),
        }

    if not date and episode_id and episode_id.startswith("ep_"):
        date = episode_id[3:13]
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            manchetes = data.get("manchetes") or []
            if manchetes:
                h = manchetes[0] if isinstance(manchetes[0], str) else manchetes[0].get("titulo", "")
                s = ""
                for bloco in (data.get("introducao") or []) + (data.get("quadros") or []):
                    if isinstance(bloco, dict) and bloco.get("texto"):
                        s = bloco["texto"]
                        break
                    if isinstance(bloco, dict) and isinstance(bloco.get("falas"), list):
                        for f in bloco["falas"]:
                            if isinstance(f, dict) and f.get("texto"):
                                s = f["texto"]
                                break
                        if s:
                            break
                if not s:
                    s = " ".join(
                        m if isinstance(m, str) else m.get("titulo", "")
                        for m in manchetes[:3]
                    )
                return {
                    "headline": h.strip(),
                    "summary": s.strip()[:600],
                    "episode_id": episode_id or f"ep_{date}",
                    "date": date,
                }
        except (json.JSONDecodeError, OSError) as e:
            log.warning("falha ao ler %s: %s", json_path, e)

    man_path = EPISODES_DIR / f"{date}-manchetes.txt"
    if man_path.exists():
        lines = [ln.strip(" -•\t") for ln in man_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            return {
                "headline": lines[0],
                "summary": " ".join(lines[:3])[:600],
                "episode_id": episode_id or f"ep_{date}",
                "date": date,
            }

    md_path = EPISODES_DIR / f"{date}.md"
    if md_path.exists():
        for ln in md_path.read_text(encoding="utf-8").splitlines():
            t = ln.strip().lstrip("#").strip()
            if len(t) > 30 and not t.lower().startswith("web jornal"):
                return {
                    "headline": t[:200],
                    "summary": t[:600],
                    "episode_id": episode_id or f"ep_{date}",
                    "date": date,
                }

    if episode_id and episode_id.startswith("bm_"):
        vid = episode_id[3:]
        bm_json = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes" / f"especial-{vid}.json"
        if bm_json.exists():
            try:
                data = json.loads(bm_json.read_text(encoding="utf-8"))
                h = data.get("titulo") or data.get("title") or f"Brasil e Mundo {vid}"
                s = data.get("resumo") or data.get("summary") or h
                return {
                    "headline": h,
                    "summary": str(s)[:600],
                    "episode_id": episode_id,
                    "date": date,
                }
            except (json.JSONDecodeError, OSError):
                pass

    return {
        "headline": f"Web Jornal Vale da Liberdade — {date}",
        "summary": "Edição diária de notícias do Vale do Itajaí com viés libertário.",
        "episode_id": episode_id or f"ep_{date}",
        "date": date,
    }


# ---------------------------------------------------------------------------
# Etapa B — meta-prompt → prompt de imagem (Gemini Flash)
# Incorpora guidelines de simbolismo (sem texto na imagem) + compliance Seção 6.
# ---------------------------------------------------------------------------
META_PROMPT_TEMPLATE = """Você é um diretor de arte de um portal de notícias editorial (estilo feed
minimalista preto/branco com acento âmbar). Sua tarefa é transformar a
notícia abaixo em um PROMPT DE IMAGEM em inglês, pronto para um modelo de
geração de imagens (Qwen-Image / Wan / Z-Image).

NOTÍCIA:
Título: {headline}
Resumo: {summary}

REGRAS OBRIGATÓRIAS DO PROMPT QUE VOCÊ VAI GERAR:
1. NUNCA descreva o rosto ou a aparência física de uma pessoa real,
   nomeada ou identificável (políticos, autoridades, celebridades).
   Em vez disso, use representações simbólicas/conceituais: silhuetas
   genéricas, ícones, objetos-símbolo, mapas, gráficos, arquitetura,
   bandeiras, elementos abstratos relacionados ao tema.
2. Nunca inclua violência gráfica, sangue, armas em uso, sofrimento
   humano explícito — mesmo que a notícia trate de um evento violento,
   represente de forma editorial/simbólica (ex: uma notícia sobre
   conflito armado vira uma imagem de mapa fragmentado ou silhueta de
   tensão, não uma cena de combate).
3. Composição: estilo fotografia editorial ou ilustração vetorial
   minimalista (escolha uma das duas por episódio, não misture).
   Paleta: preto, branco, cinza, com um único acento em âmbar/dourado
   queimado (#B8863B approximately). Sem gradientes chamativos, sem
   estética 3D/render, sem excesso de elementos.
4. NÃO inclua texto na imagem (nem manchete, nem legenda, nem marca,
   nem letras, nem tipografia). Toda comunicação visual é por simbolismo.
5. Formato: paisagem 16:9.
6. Inclua no final do prompt, literalmente:
   "16:9 landscape, no text, no letters, no typography, no words,
   editorial news aesthetic, subtle film grain, cinematic 35mm lens"
7. Saída: APENAS o prompt de imagem final, em inglês, uma única string,
   sem explicações, sem markdown, sem aspas.
"""

SAFE_REGEN_PROMPT = (
    "Violent tension with a public figure in conflict, no human faces, "
    "no identifiable people, 16:9 landscape, no text, no letters, no typography, "
    "burnt-amber accent color"
)


# Lista curta de nomes próprios/conceitos que devem ser neutralizados no
# prompt de regerenção para safety. Expanda conforme necessidade.
# Técnica: lookup exato (case-insensitive) em vez de regex greedy que
# pega instituições, locais e frases inteiras.
_NAMES_TO_SANITIZE = {
    "donald trump", "joe biden", "jair bolsonaro", "luis inácio lula da silva",
    "lula", "bolsonaro", "trump", "biden", "supreme court", "congress",
    "senate", "fbi", "cia", "white house", "pentagon", "eu commission",
    "european council", "onu", "pnud", "ipea", "ibge", "receita federal",
}


def _sanitize_prompt_once(prompt: str) -> str:
    """Versão mais genérica/segura: substitui nomes próprios conhecidos
    pela string fixa SAFE_REGEN_PROMPT, preserando o resto.
    Evita o regex greedy que transformava frases inteiras em 'a public figure'."""
    p = prompt.strip().strip('"').strip("'")
    p = re.sub(r"[`*_#]+", " ", p)
    # Sanitiza termos de violência
    violence = [
        r"\bblood\b", r"\bgore\b", r"\bgunshot\b", r"\bshooting\b", r"\bcorpse\b",
        r"\bdead body\b", r"\bwound\b", r"\bstabbing\b", r"\bmurder\b",
        r"\bweapon in use\b", r"\bcombat scene\b", r"\bexplosion\b",
        r"\bdead\b", r"\bkilled\b", r"\bbody\b",
    ]
    for pat in violence:
        p = re.sub(pat, "tension", p, flags=re.I)
    # Sanitiza nomes próprios/locais por lista negra (preserva frases)
    for name in _NAMES_TO_SANITIZE:
        p = re.sub(rf"\b{re.escape(name)}\b", "a public figure", p, flags=re.I)
    p = re.sub(r"\s+", " ", p).strip()
    if len(p) < 40:
        return SAFE_REGEN_PROMPT
    if "no human faces" not in p.lower():
        p += ", no human faces, no identifiable people"
    if "16:9" not in p:
        p += ", 16:9 landscape"
    if "no text" not in p.lower():
        p += ", no text, no letters, no typography"
    if "amber" not in p.lower() and "gold" not in p.lower():
        p += ", burnt-amber accent color"
    return p


def generate_image_prompt(headline: str, summary: str) -> tuple[str, str]:
    """Retorna (prompt, model_id_usado). Fallback local se Gemini falhar."""
    meta = META_PROMPT_TEMPLATE.format(headline=headline, summary=summary)

    try:
        from gemini_client import GeminiClient, GeminiMultiClient
        from generate_roteiro_llm import _candidate_keys
        keys = _candidate_keys("GEMINI_API_KEY")
        if keys:
            client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
            last_err = None
            for model in PROMPT_MODELS:
                try:
                    resp = client.generate_content(model=model, contents=meta)
                    text = getattr(resp, "text", None) or ""
                    if not text:
                        try:
                            cands = getattr(resp, "candidates", None) or []
                            if cands:
                                content = getattr(cands[0], "content", None)
                                parts = getattr(content, "parts", None) if content else None
                                if parts:
                                    text = getattr(parts[0], "text", "") or ""
                        except Exception:
                            text = ""
                    text = (text or "").strip().strip('"').strip("'")
                    text = re.sub(r"^```[a-z]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text).strip()
                    if len(text) > 40:
                        _log_event("prompt_generated", model=model, chars=len(text))
                        return text, model
                    last_err = f"resposta curta ({len(text)})"
                except Exception as e:
                    last_err = str(e)
                    log.warning("Gemini %s falhou no meta-prompt: %s", model, e)
            log.warning("todos os modelos Gemini falharam no meta-prompt: %s", last_err)
    except Exception as e:
        log.warning("Gemini indisponível para meta-prompt: %s", e)

    fallback = (
        f"Editorial news cover illustration about: {headline}. "
        f"Minimalist black and white composition with a single burnt-amber gold accent, "
        f"symbolic objects and abstract geometry representing the topic, no human faces, "
        f"no text overlay, 16:9 landscape, clean vector-editorial journalistic style. "
        f"Context: {summary[:200]}"
    )
    return _sanitize_prompt_once(fallback), "local-fallback"


# ---------------------------------------------------------------------------
# Etapa C — chamada DashScope + cascata
# ---------------------------------------------------------------------------
def _extract_image_url(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    out = data.get("output") or {}
    # multimodal: output.choices[0].message.content[].image
    try:
        content = out["choices"][0]["message"]["content"]
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("image"):
                    return c["image"]
    except (KeyError, IndexError, TypeError):
        pass
    # async / results
    results = out.get("results") or data.get("results") or []
    if isinstance(results, list) and results:
        r0 = results[0]
        if isinstance(r0, dict):
            return r0.get("url") or r0.get("image") or r0.get("output_image_url")
    # direct
    for k in ("image_url", "url", "image"):
        v = out.get(k) or data.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _validate_image_bytes(raw: bytes) -> Image.Image:
    """Abre com Pillow, checa dimensões e desvio padrão (anti-cinza)."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise ModelFailed(f"imagem corrompida: {e}") from e
    w, h = img.size
    if w < 256 or h < 256:
        raise ModelFailed(f"dimensões insuficientes: {w}x{h}")
    stat = ImageStat.Stat(img)
    mean_std = sum(stat.stddev) / max(1, len(stat.stddev))
    if mean_std < 5.0:
        raise ModelFailed(f"imagem quase monotônica (std={mean_std:.1f})")
    return img


def _download_image(url: str) -> Image.Image:
    try:
        r = requests.get(url, timeout=90)
    except requests.exceptions.RequestException as e:
        raise ModelFailed(f"download falhou: {e}") from e
    if r.status_code != 200:
        raise ModelFailed(f"download HTTP {r.status_code}")
    return _validate_image_bytes(r.content)


def _classify_error(status: int, data: dict | None, text: str) -> None:
    """Levanta SafetyRejected ou ModelFailed conforme status/corpo."""
    msg = ""
    code = ""
    if isinstance(data, dict):
        msg = str(data.get("message") or (data.get("output") or {}).get("message") or "")
        code = str(data.get("code") or (data.get("output") or {}).get("code") or "")
    blob = f"{code} {msg} {text}".lower()

    if status == 400 or "datainspectionfailed" in blob or "inappropriate" in blob or "content" in blob and "moderation" in blob:
        # DataInspectionFailed e afins = safety
        if any(x in blob for x in ("datainspection", "inappropriate", "moderation", "sensitive", "content_filter", "risk")):
            raise SafetyRejected(f"HTTP {status}: {code} {msg}"[:300])
        # 400 genérico também trata como safety (regra Seção 5)
        raise SafetyRejected(f"HTTP {status}: {code} {msg}"[:300])
    if status in (401, 403):
        raise ModelFailed(f"auth HTTP {status}: {msg or text}"[:200])
    if status == 429 or "throttl" in blob or "rate" in blob or "quota" in blob or "limit" in blob and "exceed" in blob:
        raise ModelFailed(f"rate_limited HTTP {status}: {code} {msg}"[:200])
    if status == 404 or "not found" in blob or "does not exist" in blob or "model_not_found" in blob:
        raise ModelFailed(f"endpoint/model 404: {code} {msg}"[:200])
    if status >= 500:
        raise ModelFailed(f"server HTTP {status}")
    raise ModelFailed(f"HTTP {status}: {code} {msg or text}"[:250])


def _call_multimodal(model: ImageModel, prompt: str, key: str) -> Image.Image:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model.model_id,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": prompt}]}
            ]
        },
        "parameters": {
            "prompt_extend": False,
            "watermark": False,
            "size": model.size,
            "n": 1,
            **model.extra_params,
        },
    }
    try:
        resp = requests.post(MM_ENDPOINT, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    except requests.exceptions.Timeout as e:
        raise ModelFailed(f"timeout {HTTP_TIMEOUT}s") from e
    except requests.exceptions.RequestException as e:
        raise ModelFailed(f"rede: {e}") from e

    try:
        data = resp.json()
    except ValueError:
        data = None

    if resp.status_code != 200:
        _classify_error(resp.status_code, data, resp.text[:300])

    url = _extract_image_url(data or {})
    if not url:
        raise ModelFailed(f"sem bloco de imagem — keys={list((data or {}).keys())[:8]}")
    return _download_image(url)


def _call_wan(model: ImageModel, prompt: str, key: str) -> Image.Image:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model.model_id,
        "input": {
            "messages": [
                {"role": "user", "content": [{"text": prompt}]}
            ]
        },
        "parameters": {
            "size": model.size,
            "n": 1,
            "watermark": False,
            **{k: v for k, v in model.extra_params.items() if k != "prompt_extend"},
        },
    }
    try:
        resp = requests.post(WAN_ENDPOINT, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    except requests.exceptions.Timeout as e:
        raise ModelFailed(f"timeout {HTTP_TIMEOUT}s") from e
    except requests.exceptions.RequestException as e:
        raise ModelFailed(f"rede: {e}") from e

    try:
        data = resp.json()
    except ValueError:
        data = None

    if resp.status_code != 200:
        _classify_error(resp.status_code, data, resp.text[:300])

    url = _extract_image_url(data or {})
    if not url:
        raise ModelFailed(f"sem bloco de imagem wan — keys={list((data or {}).keys())[:8]}")
    return _download_image(url)


def _call_async(model: ImageModel, prompt: str, key: str) -> Image.Image:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": model.model_id,
        "input": {"prompt": prompt},
        "parameters": {
            "size": model.size,
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
            **model.extra_params,
        },
    }
    try:
        resp = requests.post(ASYNC_ENDPOINT, headers=headers, json=payload, timeout=60)
    except requests.exceptions.Timeout as e:
        raise ModelFailed("timeout submit async") from e
    except requests.exceptions.RequestException as e:
        raise ModelFailed(f"rede: {e}") from e

    try:
        data = resp.json()
    except ValueError:
        data = None

    if resp.status_code != 200:
        _classify_error(resp.status_code, data, resp.text[:300])

    task_id = ((data or {}).get("output") or {}).get("task_id")
    if not task_id:
        raise ModelFailed(f"sem task_id: {json.dumps(data or {}, ensure_ascii=False)[:200]}")

    poll_url = TASK_ENDPOINT.format(task_id=task_id)
    for _ in range(ASYNC_POLL_MAX):
        time.sleep(ASYNC_POLL_SLEEP)
        try:
            pr = requests.get(poll_url, headers={"Authorization": f"Bearer {key}"}, timeout=30)
            pd = pr.json()
        except Exception:
            continue
        st = (pd.get("output") or {}).get("task_status")
        if st == "SUCCEEDED":
            url = _extract_image_url(pd)
            if not url:
                raise ModelFailed("async SUCCEEDED sem URL de imagem")
            return _download_image(url)
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            code = (pd.get("output") or {}).get("code") or pd.get("code") or ""
            msg = (pd.get("output") or {}).get("message") or pd.get("message") or st
            blob = f"{code} {msg}".lower()
            if any(x in blob for x in ("datainspection", "inappropriate", "moderation", "sensitive")):
                raise SafetyRejected(f"async safety: {code} {msg}"[:300])
            raise ModelFailed(f"async {st}: {code} {msg}"[:250])
    raise ModelFailed("async poll timeout")


def _call_model_once(model: ImageModel, prompt: str) -> tuple[Image.Image, int]:
    """Uma chamada. Retorna (Image, latency_ms)."""
    key = os.environ.get(model.env_key, "").strip()
    if not key or key.startswith("***"):
        # tenta fallback genérico
        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key or key.startswith("***"):
        raise ModelFailed(f"chave ausente: {model.env_key}")

    if quota_remaining(model.model_id, model.daily_quota) <= 0:
        raise ModelFailed(f"quota local esgotada para {model.model_id}")

    t0 = time.time()
    style = model.api_style
    try:
        if style == "wan":
            img = _call_wan(model, prompt, key)
        elif style == "async":
            img = _call_async(model, prompt, key)
        else:
            img = _call_multimodal(model, prompt, key)
    except (SafetyRejected, ModelFailed):
        raise
    except Exception as e:
        raise ModelFailed(f"erro inesperado: {e}") from e

    # Se multimodal falhou no sentido de "modelo não encontrado", o caller
    # já recebe ModelFailed. Aqui só contabiliza sucesso.
    latency = int((time.time() - t0) * 1000)
    quota_increment(model.model_id)
    return img, latency


def _call_model_with_retry(model: ImageModel, prompt: str) -> tuple[Image.Image, int, list[dict]]:
    """Até 2 tentativas por modelo com backoff 3s/8s."""
    attempts: list[dict] = []
    last_err: Exception | None = None
    for i, wait in enumerate((0.0,) + RETRY_BACKOFFS):
        if wait:
            time.sleep(wait)
        t0 = time.time()
        try:
            img, latency = _call_model_once(model, prompt)
            attempts.append({
                "model": model.model_id,
                "status": "success",
                "latency_ms": latency,
                "attempt": i + 1,
            })
            return img, latency, attempts
        except SafetyRejected:
            attempts.append({
                "model": model.model_id,
                "status": "safety_rejected",
                "latency_ms": int((time.time() - t0) * 1000),
                "attempt": i + 1,
            })
            raise
        except ModelFailed as e:
            last_err = e
            attempts.append({
                "model": model.model_id,
                "status": str(e)[:120],
                "latency_ms": int((time.time() - t0) * 1000),
                "attempt": i + 1,
            })
            msg = str(e).lower()
            if any(x in msg for x in ("auth", "404", "quota local", "chave ausente", "not found")):
                break
    raise ModelFailed(str(last_err) if last_err else "falhou") from last_err


# ---------------------------------------------------------------------------
# Etapa D — pós-processamento
# ---------------------------------------------------------------------------
def _crop_to_16_9(img: Image.Image) -> Image.Image:
    w, h = img.size
    target_ratio = 16 / 9
    current = w / h
    if abs(current - target_ratio) < 0.02:
        return img
    if current > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    return img


def postprocess_and_save(img: Image.Image, episode_id: str, date: str) -> dict:
    """Crop 16:9, resize 1280x720, salva webp+jpg. Retorna paths."""
    img = _crop_to_16_9(img.convert("RGB"))
    if img.size != (TARGET_W, TARGET_H):
        img = img.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)

    out_dir = THUMBNAILS_DIR / date
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = episode_id
    webp_path = out_dir / f"{stem}.webp"
    jpg_path = out_dir / f"{stem}.jpg"
    img.save(webp_path, "WEBP", quality=WEBP_Q, method=6)
    img.save(jpg_path, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)

    public_dir = PROJECT_ROOT / "public" / "thumbnails" / date
    try:
        public_dir.mkdir(parents=True, exist_ok=True)
        img.save(public_dir / f"{stem}.webp", "WEBP", quality=WEBP_Q, method=6)
        img.save(public_dir / f"{stem}.jpg", "JPEG", quality=JPEG_Q, optimize=True)
        for p in (public_dir / f"{stem}.webp", public_dir / f"{stem}.jpg"):
            try:
                p.chmod(0o644)
            except OSError:
                pass
    except OSError as e:
        log.warning("falha ao espelhar em public/: %s", e)

    return {
        "path": str(webp_path.relative_to(PROJECT_ROOT)),
        "path_jpg": str(jpg_path.relative_to(PROJECT_ROOT)),
        "width": TARGET_W,
        "height": TARGET_H,
        "bytes_webp": webp_path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Etapa F — placeholder local
# ---------------------------------------------------------------------------
def _find_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.ttf",
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:5]


def generate_placeholder(headline: str, date: str, episode_id: str) -> Image.Image:
    """Capa local: fundo preto, acento âmbar, título, data. Zero rede."""
    img = Image.new("RGB", (TARGET_W, TARGET_H), BLACK)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, TARGET_W, 8], fill=AMBER)
    draw.rectangle([0, TARGET_H - 8, TARGET_W, TARGET_H], fill=AMBER)
    draw.rectangle([0, 0, 6, TARGET_H], fill=AMBER)

    if COVER_FALLBACK.exists():
        try:
            logo = Image.open(COVER_FALLBACK).convert("RGB")
            logo.thumbnail((120, 120), Image.Resampling.LANCZOS)
            img.paste(logo, (TARGET_W - 140, 30))
        except Exception:
            pass

    brand_font = _find_font(22)
    draw.text((40, 40), "VALE DA LIBERDADE", font=brand_font, fill=AMBER)
    draw.text((40, 72), "WEB JORNAL", font=_find_font(16), fill=GRAY)

    title_font = _find_font(42)
    lines = _wrap_text(draw, headline, title_font, TARGET_W - 120)
    y = 220
    for ln in lines:
        draw.text((40, y), ln, font=title_font, fill=WHITE)
        y += 56

    draw.text((40, TARGET_H - 80), date, font=_find_font(20), fill=GRAY)
    return img


# ---------------------------------------------------------------------------
# Metadata update
# ---------------------------------------------------------------------------
def update_episode_metadata(date: str, episode_id: str, thumb_meta: dict) -> Path | None:
    """Mescla o bloco thumbnail no JSON de metadata existente."""
    meta_path = EPISODES_DIR / f"{date}-metadata.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        data["thumbnail"] = thumb_meta
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta_path

    if episode_id.startswith("bm_"):
        vid = episode_id[3:]
        bm = PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes" / f"especial-{vid}.json"
        if bm.exists():
            try:
                data = json.loads(bm.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            data["thumbnail"] = thumb_meta
            bm.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return bm

    side = THUMBNAILS_DIR / date / f"{episode_id}.meta.json"
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(json.dumps({"thumbnail": thumb_meta}, ensure_ascii=False, indent=2), encoding="utf-8")
    return side


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------
def generate_cover_image(
    prompt: str,
    episode_id: str,
    *,
    cascade: list[ImageModel] | None = None,
    allow_safety_regen: bool = True,
) -> tuple[Image.Image, dict]:
    """Cascata de modelos. Retorna (img, info)."""
    cascade = cascade or [m for m in _load_cascade() if m.enabled]
    all_attempts: list[dict] = []
    safety_hits = 0

    def _run_cascade(p: str) -> tuple[Image.Image, dict] | None:
        nonlocal all_attempts
        for level, model in enumerate(cascade):
            if not model.enabled:
                continue
            # checa cota ANTES de gastar chamada
            if quota_remaining(model.model_id, model.daily_quota) <= 0:
                all_attempts.append({
                    "model": model.model_id,
                    "status": "quota_exceeded",
                    "latency_ms": 0,
                })
                _log_event("quota_skip", model=model.model_id, episode_id=episode_id)
                continue
            try:
                img, latency, attempts = _call_model_with_retry(model, p)
                all_attempts.extend(attempts)
                _log_event(
                    "image_ok",
                    model=model.model_id,
                    episode_id=episode_id,
                    latency_ms=latency,
                    fallback_level=level,
                )
                return img, {
                    "image_model_used": model.model_id,
                    "fallback_level": level,
                    "is_placeholder": False,
                    "estimated_cost_usd": model.cost_usd,
                    "generation_attempts": list(all_attempts),
                }
            except SafetyRejected as e:
                all_attempts.append({
                    "model": model.model_id,
                    "status": "safety_rejected",
                    "detail": str(e)[:200],
                })
                _log_event("safety_rejected", model=model.model_id, episode_id=episode_id)
                raise
            except ModelFailed as e:
                all_attempts.append({
                    "model": model.model_id,
                    "status": "failed",
                    "detail": str(e)[:200],
                })
                _log_event("model_failed", model=model.model_id, episode_id=episode_id, error=str(e)[:200])
                continue
        return None

    try:
        result = _run_cascade(prompt)
        if result:
            return result
    except SafetyRejected:
        safety_hits += 1
        if allow_safety_regen and safety_hits <= 1:
            safe_prompt = _sanitize_prompt_once(prompt)
            _log_event("safety_regen", episode_id=episode_id, new_prompt=safe_prompt[:200])
            try:
                result = _run_cascade(safe_prompt)
                if result:
                    result[1]["image_prompt_sanitized"] = True
                    result[1]["image_prompt_used"] = safe_prompt
                    return result
            except SafetyRejected:
                pass

    raise AllModelsFailed(all_attempts)


def generate_thumbnail_for_episode(
    *,
    date: str | None = None,
    episode_id: str | None = None,
    headline: str | None = None,
    summary: str | None = None,
    force: bool = False,
) -> dict:
    """Pipeline completo A→F. Nunca levanta — sempre retorna metadata (mesmo placeholder)."""
    story = extract_main_story(date=date, episode_id=episode_id, headline=headline, summary=summary)
    date_s: str = str(story["date"])
    episode_id_s: str = str(story["episode_id"])
    headline_s: str = str(story["headline"])
    summary_s: str = str(story["summary"])

    out_webp = THUMBNAILS_DIR / date_s / f"{episode_id_s}.webp"
    if out_webp.exists() and not force:
        log.info("thumbnail já existe para %s (use --force para regenerar)", episode_id_s)
        existing = {
            "path": str(out_webp.relative_to(PROJECT_ROOT)),
            "image_model_used": "cached",
            "prompt_model_used": "cached",
            "image_prompt": "",
            "fallback_level": -1,
            "is_placeholder": False,
            "generated_at": datetime.fromtimestamp(out_webp.stat().st_mtime, tz=timezone.utc).isoformat(),
            "estimated_cost_usd": 0.0,
            "generation_attempts": [],
            "quota_remaining_today": quota_snapshot(),
            "skipped": True,
        }
        update_episode_metadata(date_s, episode_id_s, existing)
        return existing

    image_prompt, prompt_model = generate_image_prompt(headline_s, summary_s)
    log.info("prompt de imagem (%s, %d chars): %s…", prompt_model, len(image_prompt), image_prompt[:120])

    thumb_meta: dict = {
        "path": "",
        "image_model_used": "",
        "prompt_model_used": prompt_model,
        "image_prompt": image_prompt,
        "fallback_level": 99,
        "is_placeholder": True,
        "generated_at": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
        "estimated_cost_usd": 0.0,
        "generation_attempts": [],
        "headline": headline_s,
        "quota_remaining_today": {},
    }

    try:
        img, info = generate_cover_image(image_prompt, episode_id_s)
        thumb_meta.update(info)
    except AllModelsFailed as e:
        log.warning("cascata DashScope falhou para %s — gerando placeholder local", episode_id_s)
        thumb_meta["generation_attempts"] = list(e.args[0]) if e.args else []
        img = generate_placeholder(headline_s, date_s, episode_id_s)
        thumb_meta["image_model_used"] = "local-placeholder"
        thumb_meta["is_placeholder"] = True
        thumb_meta["fallback_level"] = 99
        thumb_meta["estimated_cost_usd"] = 0.0
    except Exception as e:
        log.error("erro inesperado na geração: %s\n%s", e, traceback.format_exc())
        img = generate_placeholder(headline_s, date_s, episode_id_s)
        thumb_meta["image_model_used"] = "local-placeholder"
        thumb_meta["is_placeholder"] = True
        thumb_meta["fallback_level"] = 99
        thumb_meta["error"] = str(e)[:300]

    try:
        paths = postprocess_and_save(img, episode_id_s, date_s)
        thumb_meta["path"] = paths["path"]
        thumb_meta["path_jpg"] = paths["path_jpg"]
        thumb_meta["width"] = paths["width"]
        thumb_meta["height"] = paths["height"]
        thumb_meta["bytes_webp"] = paths["bytes_webp"]
    except Exception as e:
        log.error("pós-processamento falhou: %s", e)
        thumb_meta["error"] = f"postprocess: {e}"

    thumb_meta["quota_remaining_today"] = quota_snapshot()

    meta_path = update_episode_metadata(date_s, episode_id_s, thumb_meta)
    thumb_meta["metadata_path"] = str(meta_path) if meta_path else None
    _log_event(
        "thumbnail_done",
        episode_id=episode_id_s,
        path=thumb_meta.get("path"),
        model=thumb_meta.get("image_model_used"),
        is_placeholder=thumb_meta.get("is_placeholder"),
        fallback_level=thumb_meta.get("fallback_level"),
    )
    log.info(
        "✅ thumbnail %s → %s (model=%s placeholder=%s)",
        episode_id_s, thumb_meta.get("path"), thumb_meta.get("image_model_used"),
        thumb_meta.get("is_placeholder"),
    )
    return thumb_meta


def generate_thumbnail_safe(**kwargs) -> dict:
    """Wrapper 100% à prova de exceção para o pipeline (nunca bloqueia)."""
    try:
        return generate_thumbnail_for_episode(**kwargs)
    except Exception as e:
        log.error("generate_thumbnail_safe engoliu: %s", e)
        return {
            "path": "",
            "image_model_used": "error",
            "is_placeholder": True,
            "error": str(e)[:300],
            "failed": True,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Gera thumbnail de episódio (DashScope + fallback local)")
    parser.add_argument("--date", help="YYYY-MM-DD do episódio diário")
    parser.add_argument("--episode-id", help="ID do episódio (default: ep_YYYY-MM-DD)")
    parser.add_argument("--headline", help="Manchete (override)")
    parser.add_argument("--summary", help="Resumo (override)")
    parser.add_argument("--force", action="store_true", help="Regenera mesmo se já existir")
    parser.add_argument("--placeholder-only", action="store_true", help="Só gera placeholder local (teste offline)")
    args = parser.parse_args()

    if not args.date and not args.episode_id and not args.headline:
        parser.error("informe --date e/ou --episode-id e/ou --headline")

    if args.placeholder_only:
        date = args.date or datetime.now().strftime("%Y-%m-%d")
        eid = args.episode_id or f"ep_{date}"
        story = extract_main_story(date=date, episode_id=eid, headline=args.headline, summary=args.summary)
        img = generate_placeholder(story["headline"], date, eid)
        paths = postprocess_and_save(img, eid, date)
        meta = {
            "path": paths["path"],
            "image_model_used": "local-placeholder",
            "is_placeholder": True,
            "fallback_level": 99,
            "generated_at": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
            "headline": story["headline"],
        }
        update_episode_metadata(date, eid, meta)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return 0

    result = generate_thumbnail_for_episode(
        date=args.date,
        episode_id=args.episode_id,
        headline=args.headline,
        summary=args.summary,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("path") else 1


if __name__ == "__main__":
    sys.exit(main())
