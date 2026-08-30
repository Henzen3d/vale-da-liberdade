#!/usr/bin/env python3
"""
Gera episodes/roteiro-{date}.json a partir de raw-{date}.md.

Usa o prompt canônico de generate_script.build_script_prompt().
Prioridade de backend:
  1) Gemini (GEMINI_API_KEY) via GeminiClient
  2) OpenRouter (OPENROUTER_API_KEY) com modelos free/robustos

Keys: tenta .env do projeto e ~/.hermes/.env (pula key 401).

Uso:
  python3 scripts/generate_roteiro_llm.py --date 2026-07-23
  python3 scripts/generate_roteiro_llm.py --date 2026-07-23 --force
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(Path.home() / ".hermes" / ".env", override=False)


def _read_env_file_keys(path: Path, prefix: str = "GEMINI_API_KEY") -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            # Aceita GEMINI_API_KEY e variações GEMINI_API_KEY_2, _3, etc.
            if (k == prefix or (k.startswith(prefix + "_") and k[len(prefix)+1:].isdigit())) and v and "***" not in v:
                out[k] = v
    except Exception:
        pass
    return out


def _candidate_keys(env_name: str) -> list[str]:
    """Env atual + .env projeto + .env Hermes (dedupe). Aceita GEMINI_API_KEY e GEMINI_API_KEY_2, _3..."""
    seen: set[str] = set()
    keys: list[str] = []
    # 1) env direto (GEMINI_API_KEY e variações _2, _3...)
    for k, v in os.environ.items():
        if k == env_name or (k.startswith(env_name + "_") and k[len(env_name)+1:].isdigit()):
            if v and v.strip():
                sources = [v.strip()]
            else:
                sources = []
            for kk in sources:
                if kk and "***" not in kk and kk not in seen:
                    seen.add(kk)
                    keys.append(kk)
    # 2) arquivos .env
    for path in (PROJECT_ROOT / ".env", Path.home() / ".hermes" / ".env"):
        d = _read_env_file_keys(path, env_name)
        for kk in d.values():
            if kk and "***" not in kk and kk not in seen:
                seen.add(kk)
                keys.append(kk)
    return keys


def _key_label(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if len(key) >= 12 else "(curta)"


from generate_script import (  # noqa: E402
    EPISODES_DIR,
    RoteiroCompleto,
    build_script_prompt,
    format_script,
    load_raw,
    parse_raw,
)
from naturalize_roteiro import critical_issues, polish_roteiro_dict  # noqa: E402

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter: preferir modelos que devolvem JSON válido.
# Free (nemotron etc.) costumam raciocinar em aberto e quebrar o parse.
OPENROUTER_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
    "poolside/laguna-m.1:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

GEMINI_MODELS = [
    "gemini-3.6-flash",        # primário: melhor qualidade editorial e nuance
    "gemini-3-flash-preview",  # fallback capaz e rápido
    "gemini-3.5-flash-lite",   # alta velocidade / 500 RPD
    "gemini-3.1-flash-lite",   # backup leve (15 RPM / 500 RPD)
    "gemma-4-31b-it",          # backup aberto (30 RPM / alta cota)
]


def extract_json_object(text: str) -> dict:
    """Extrai o primeiro objeto JSON válido da resposta do modelo."""
    if not text:
        raise ValueError("resposta vazia do modelo")

    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))

    start = text.find("{")
    if start < 0:
        raise ValueError("nenhum objeto JSON encontrado na resposta")

    depth = 0
    in_str = False
    esc = False
    last_ok = None
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_ok = text[start : i + 1]
                break
    if not last_ok:
        end = text.rfind("}")
        if end > start:
            last_ok = text[start : end + 1]
        else:
            raise ValueError("JSON incompleto na resposta")

    try:
        return json.loads(last_ok)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", last_ok)
        return json.loads(cleaned)


def _validate_roteiro(data: dict) -> RoteiroCompleto:
    required = ("manchetes", "introducao", "quadros", "fechamento")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"JSON sem chaves obrigatórias: {missing}")
    if not data.get("manchetes"):
        raise ValueError("manchetes vazias")
    intro = data.get("introducao") or []
    quadros = data.get("quadros") or []
    fechamento = data.get("fechamento") or []
    if len(intro) < 2 or len(quadros) < 6 or len(fechamento) < 2:
        raise ValueError(
            f"seções insuficientes (intro={len(intro)}, quadros={len(quadros)}, fech={len(fechamento)})"
        )
    all_turns = intro + quadros + fechamento
    speakers = {it.get("speaker") for it in all_turns if isinstance(it, dict)}
    if not {"Peter", "Ricardo"}.issubset(speakers):
        raise ValueError(f"roteiro unilateral: esperado Peter e Ricardo, encontrado {speakers}")
    total_words = 0
    for it in all_turns:
        txt = (it.get("texto") or "").strip() if isinstance(it, dict) else ""
        if len(txt) < 15:
            raise ValueError(f"fala muito curta ou vazia em {it.get('quadro') if isinstance(it, dict) else '?'}: {txt!r}")
        total_words += len(txt.split())
    if total_words < 800:
        raise ValueError(f"roteiro muito curto no JSON ({total_words} palavras, mínimo 800)")
    return RoteiroCompleto(**data)


def _call_gemini(prompt: str) -> str:
    keys = _candidate_keys("GEMINI_API_KEY")
    if not keys:
        raise RuntimeError("GEMINI_API_KEY ausente ou mascarada")
    from gemini_client import GeminiClient, GeminiMultiClient
    import time as _time
    last_err: Exception | None = None
    # GeminiMultiClient intercala chaves por quota (RPD/RPM por conta)
    client = GeminiMultiClient(keys) if len(keys) > 1 else GeminiClient(api_key=keys[0])
    for model in GEMINI_MODELS:
        try:
            print(f"  → Gemini: {model}")
            resp = client.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": 0.7,
                    "max_output_tokens": 32768,
                    "response_mime_type": "application/json",
                },
            )
            text = getattr(resp, "text", None) or ""
            candidates = getattr(resp, "candidates", None) or []
            if not text and candidates:
                parts = []
                for c in candidates:
                    content = getattr(c, "content", None)
                    cparts = getattr(content, "parts", None) if content else None
                    if cparts:
                        for p in cparts:
                            t = getattr(p, "text", None)
                            if t:
                                parts.append(t)
                text = "\n".join(parts)
            if text and text.strip():
                print(f"  ✓ Gemini {model}: {len(text)} chars")
                return text
            last_err = RuntimeError(f"{model}: resposta vazia")
        except Exception as exc:
            print(f"  ⚠ Gemini {model}: {exc}")
            last_err = exc
            msg = str(exc).lower()
            # Cota/limite: pula para o próximo modelo em vez de quebrar tudo
            if "429" in msg or "quota" in msg or "rate" in msg or "resource_exhausted" in msg:
                print(f"  ↳ {model} esgotou cota — tentando próximo modelo...")
                _time.sleep(1.5)
                continue
            if "api key" in msg or "invalid" in msg or "401" in msg or "403" in msg:
                break
        # cooldown defensivo (chave AI Studio tem cotas baixas: 2 RPD no 3.6 Flash)
        _time.sleep(1.5)
    raise RuntimeError(f"Gemini falhou: {last_err}")


def _call_openrouter(prompt: str) -> str:
    import requests

    keys = _candidate_keys("OPENROUTER_API_KEY")
    if not keys:
        raise RuntimeError("OPENROUTER_API_KEY ausente ou mascarada")

    last_err: Exception | None = None
    for ki, api_key in enumerate(keys, start=1):
        if len(keys) > 1:
            print(f"  → OpenRouter key #{ki} ({_key_label(api_key)})")
        key_dead = False
        for model in OPENROUTER_MODELS:
            try:
                print(f"  → OpenRouter: {model}")
                body = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a JSON API that writes Brazilian Portuguese podcast scripts. "
                                "Output ONLY a single valid JSON object. "
                                "No markdown, no commentary, no chain-of-thought, no preamble. "
                                "Start with { and end with }. "
                                "Schema keys EXACTLY: manchetes, introducao, quadros, fechamento. "
                                "Each speech item: {quadro, speaker, texto}."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                prompt
                                + "\n\nRESPONDA APENAS COM O JSON FINAL. "
                                "Não explique. Não raciocine em aberto. Só o objeto JSON."
                            ),
                        },
                    ],
                    "temperature": 0.4,
                    "max_tokens": 12000,
                    "response_format": {"type": "json_object"},
                }
                resp = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                        "X-Title": "Web Jornal Pipeline",
                    },
                    json=body,
                    timeout=240,
                )
                if resp.status_code >= 400:
                    try:
                        err_data = resp.json()
                    except Exception:
                        err_data = {"raw": resp.text[:300]}
                    err = json.dumps(err_data, ensure_ascii=False)[:400]
                    if resp.status_code in (401, 403):
                        print(f"  ⚠ OpenRouter auth fail HTTP {resp.status_code}: {err}")
                        last_err = RuntimeError(f"HTTP {resp.status_code}: {err}")
                        key_dead = True
                        break
                    # retry without response_format
                    print("  ⚠ retry OpenRouter sem response_format")
                    body.pop("response_format", None)
                    resp = requests.post(
                        OPENROUTER_URL,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                            "X-Title": "Web Jornal Pipeline",
                        },
                        json=body,
                        timeout=240,
                    )
                    if resp.status_code >= 400:
                        err2 = json.dumps(resp.json(), ensure_ascii=False)[:300]
                        if resp.status_code in (401, 403):
                            last_err = RuntimeError(f"HTTP {resp.status_code}: {err2}")
                            key_dead = True
                            break
                        raise RuntimeError(f"HTTP {resp.status_code}: {err2}")

                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"sem choices: {json.dumps(data, ensure_ascii=False)[:300]}")
                text = (choices[0].get("message") or {}).get("content") or ""
                if not text.strip():
                    raise RuntimeError("conteúdo vazio")
                if "{" not in text:
                    raise RuntimeError(f"resposta sem JSON: {text[:120]!r}")
                # reject pure chain-of-thought
                stripped = text.lstrip()
                if not stripped.startswith("{") and not stripped.startswith("```"):
                    # try extract; if fails later
                    if text.count("{") < 1:
                        raise RuntimeError(f"resposta não-JSON: {text[:120]!r}")
                print(f"  ✓ OpenRouter {model}: {len(text)} chars")
                return text
            except Exception as exc:
                print(f"  ⚠ OpenRouter {model}: {exc}")
                last_err = exc
        if key_dead:
            continue
    raise RuntimeError(f"OpenRouter falhou: {last_err}")


def _call_llm(prompt: str) -> str:
    errors: list[str] = []
    for backend, fn in (("gemini", _call_gemini), ("openrouter", _call_openrouter)):
        try:
            return fn(prompt)
        except Exception as exc:
            errors.append(f"{backend}: {exc}")
            print(f"⚠️  Backend {backend} indisponível: {exc}")
    raise RuntimeError("todos os backends de LLM falharam: " + " | ".join(errors))


def _naturalidade_feedback(crit: list[str]) -> str:
    bullets = "\n".join(f"- {c}" for c in crit[:12])
    return (
        "\n\n=== CORREÇÃO OBRIGATÓRIA (sua versão anterior FALHOU o validador) ===\n"
        "Reescreva o JSON inteiro corrigindo TODOS os pontos abaixo.\n"
        "Regras 7.1: sem telejornal; reagir à fala anterior; 2–3 frases máx; "
        "variar Peter; trocas curtas; transições reais; chamar Peter/Ricardo pelo nome.\n"
        f"Falhas detectadas:\n{bullets}\n"
        "Responda SOMENTE com o JSON corrigido.\n"
    )


def generate_roteiro_json(date: str, force: bool = False, max_attempts: int = 2) -> Path:
    """Gera (ou reutiliza) episodes/roteiro-{date}.json."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EPISODES_DIR / f"roteiro-{date}.json"

    if out_path.exists() and not force:
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            _validate_roteiro(data)
            print(f"✅ Roteiro JSON já existe e é válido: {out_path}")
            return out_path
        except Exception as exc:
            print(f"⚠️  JSON existente inválido ({exc}); regenerando...")

    raw_text = load_raw(date)
    parsed = parse_raw(raw_text)
    total_items = sum(len(v) for v in parsed.values())
    if total_items < 3:
        raise RuntimeError(
            f"raw-{date}.md tem poucas notícias parseáveis ({total_items}). "
            f"Rode 'python3 scripts/pipeline.py init --date {date}' primeiro."
        )

    base_prompt = build_script_prompt(date, parsed)
    expansao_obrigatoria = (
        "\n\n=== EXPANSÃO OBRIGATÓRIA ===\n"
        "Este episódio DEVE atingir entre 2000 e 2500 palavras NO TOTAL (rogue script + JSON). "
        "Aprofunde cada notícia com mais contexto, números e réplicas curtas. "
        "NÃO resuma demais. Mantenha as regras 7.1 (2-3 frases por fala), mas INCREMENTE o número de trocas por notícia para bater a meta de palavras.\n"
    )
    prompt = base_prompt + expansao_obrigatoria
    print(f"🧠 Gerando roteiro JSON para {date} ({total_items} notícias, prompt {len(prompt)} chars)")

    last_payload = None
    last_crit: list[str] = []

    for attempt in range(1, max_attempts + 1):
        print(f"--- tentativa {attempt}/{max_attempts} ---")
        content = _call_llm(prompt)
        try:
            data = extract_json_object(content)
            roteiro = _validate_roteiro(data)
        except Exception as exc:
            print(f"  ⚠ parse/validação falhou: {exc}")
            # save raw for debug
            debug = EPISODES_DIR / f"roteiro-{date}.raw_llm.txt"
            debug.write_text(content, encoding="utf-8")
            print(f"  ⚠ raw salvo em {debug}")
            if attempt < max_attempts:
                prompt = (
                    base_prompt + expansao_obrigatoria
                    + "\n\nA resposta anterior NÃO era JSON válido do schema. "
                    "Responda SOMENTE com { ... } usando chaves: "
                    "manchetes, introducao, quadros, fechamento.\n"
                )
                continue
            raise

        payload = roteiro.model_dump() if hasattr(roteiro, "model_dump") else roteiro.dict()
        try:
            payload = polish_roteiro_dict(payload)
            print("  ✓ polish_roteiro_dict aplicado")
        except Exception as exc:
            print(f"  ⚠ polish falhou (seguindo sem): {exc}")

        md = format_script(date, RoteiroCompleto(**payload))
        crit = critical_issues(md)
        last_payload = payload
        last_crit = crit

        if not crit:
            print("  ✓ naturalidade OK (0 críticos)")
            break

        print(f"  ⚠ naturalidade: {len(crit)} crítico(s)")
        for c in crit[:6]:
            print(f"    {c}")
        if attempt < max_attempts:
            prompt = base_prompt + expansao_obrigatoria + _naturalidade_feedback(crit)
            print("  → regenerando com feedback de naturalidade...")
        else:
            print("  ⚠ esgotaram tentativas — NÃO salvando JSON oficial (ainda com críticos)")

    assert last_payload is not None
    if last_crit:
        debug = EPISODES_DIR / f"roteiro-{date}.invalid.json"
        debug.write_text(json.dumps(last_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(
            f"roteiro ainda tem {len(last_crit)} crítico(s) de naturalidade após {max_attempts} tentativa(s); "
            f"rascunho em {debug}: {last_crit[0]}"
        )
    out_path.write_text(json.dumps(last_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Roteiro salvo: {out_path}")
    print(f"   Manchetes: {len(last_payload['manchetes'])}")
    print(f"   Introdução: {len(last_payload['introducao'])} falas")
    print(f"   Quadros: {len(last_payload['quadros'])} falas")
    print(f"   Fechamento: {len(last_payload['fechamento'])} falas")
    if last_crit:
        print(f"   ⚠ Ainda há {len(last_crit)} crítico(s) de naturalidade — pipeline validate pode bloquear")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera roteiro-{date}.json via LLM")
    parser.add_argument("--date", required=True, help="Data YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Regenera mesmo se JSON válido existir")
    parser.add_argument("--attempts", type=int, default=2, help="Tentativas LLM com feedback 7.1")
    args = parser.parse_args()
    try:
        generate_roteiro_json(args.date, force=args.force, max_attempts=max(1, args.attempts))
        return 0
    except Exception as exc:
        print(f"❌ FALHA ao gerar roteiro JSON: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
