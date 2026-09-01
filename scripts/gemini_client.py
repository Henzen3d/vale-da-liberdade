#!/usr/bin/env python3
"""
Módulo Cliente Gemini com Rate Limiting e Retry Autônomo.

Este módulo fornece a classe `GeminiClient` que envelopa a API oficial do Google GenAI
e implementa:
1. Backoff Exponencial com Jitter para retentativas em Erros 429 ou instabilidades.
2. Controle e travas de segurança locais de RPM (Requisições por Minuto), RPD (por Dia)
   e TPM (Tokens por Minuto) persistidos em arquivo compartilhado para sincronismo
   de processos concorrentes.
"""

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# RPD do AI Studio zera à meia-noite do Pacífico, não numa janela rolante de 24h.
PACIFIC = ZoneInfo("America/Los_Angeles")

# Logger dedicado do cliente Gemini
log = logging.getLogger("gemini-client")
if not log.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [gemini-client] %(message)s", "%H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

# Configuração de limites padrões por categoria de modelo
DEFAULT_LIMITS = {
    # Limites REAIS (máximos) da chave AI Studio do web-jornal (tabela do usuário, 2026-07-25).
    # Formato: <usado> / <limite> — usamos o LIMITE (máximo).
    # flash: gemini-3.6/2.5/3/3.5-flash = 5 RPM / 250K TPM / 20 RPD.
    "flash": {
        "rpm": 5,
        "rpd": 20,
        "tpm": 250000,
    },
    # lite: gemini-3.5/3.1-flash-lite = 15 RPM / 250K TPM / 500 RPD.
    "lite": {
        "rpm": 15,
        "rpd": 500,
        "tpm": 250000,
    },
    # tts: gemini-2.5/3.1-flash-tts = 3 RPM / 10K TPM / 10 RPD.
    "tts": {
        "rpm": 3,
        "rpd": 10,
        "tpm": 10000,
    },
}


def _get_model_category(model_name: str) -> str:
    """Classifica o modelo para determinar os limites apropriados."""
    model_lower = model_name.lower()
    if "tts" in model_lower:
        return "tts"
    elif "lite" in model_lower:
        return "lite"
    return "flash"


def _estimate_tokens(contents) -> int:
    """Estima a quantidade de tokens de forma conservadora antes da chamada."""
    if isinstance(contents, str):
        return int(len(contents.split()) * 1.5) + 50
    elif isinstance(contents, list):
        total = 0
        for item in contents:
            if isinstance(item, str):
                total += len(item.split()) * 1.5
            elif hasattr(item, "text") and isinstance(item.text, str):
                total += len(item.text.split()) * 1.5
            else:
                total += 100
        return int(total) + 50
    return 1000


def _load_usage(file_path: Path) -> dict:
    """Lê o arquivo de controle de uso com retentativas para evitar colisões de escrita no Windows."""
    for _ in range(30):
        try:
            if not file_path.exists():
                return {}
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, json.JSONDecodeError):
            time.sleep(random.uniform(0.02, 0.1))
    return {}


def _save_usage(file_path: Path, data: dict):
    """Escreve o arquivo de controle de uso de forma concorrente-segura no Windows."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(30):
        try:
            # Escrever em arquivo temporário e substituir para atomicidade
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if file_path.exists():
                file_path.unlink()
            temp_path.rename(file_path)
            return
        except PermissionError:
            time.sleep(random.uniform(0.02, 0.1))
    raise RuntimeError(f"Não foi possível salvar o banco de uso da API em {file_path} devido a bloqueio do arquivo.")


def _key_id(api_key: str) -> str:
    if len(api_key or "") >= 12:
        return api_key[:4] + "…" + api_key[-4:]
    return api_key or "default"


def _pacific_day_start(now_ts: float) -> float:
    now = datetime.fromtimestamp(now_ts, tz=PACIFIC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _next_pacific_midnight(now_ts: float) -> float:
    now = datetime.fromtimestamp(now_ts, tz=PACIFIC)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.timestamp()


def _requests_in_rpd_window(requests: list, now_ts: float) -> list:
    start = _pacific_day_start(now_ts)
    return [t for t in requests if t >= start]


def _collapse_fake_rpd_pad(requests: list) -> list:
    """Descarta o artefato `[now] * RPD` do mark_exhausted (timestamps idênticos).

    Chamadas reais de TTS/texto ficam ≥20s apart (3 RPM). Um bloco de timestamps
    iguais não é uso — é a saturação sintética que travava o Round Robin o dia todo.
    """
    if not requests:
        return []
    out: list = []
    i = 0
    n = len(requests)
    while i < n:
        j = i + 1
        while j < n and abs(float(requests[j]) - float(requests[i])) <= 0.05:
            j += 1
        if j - i == 1:
            out.append(requests[i])
        i = j
    return out


def _is_local_rpd_block(msg: str) -> bool:
    m = (msg or "").lower()
    return "limite diário atingido" in m


def _is_google_daily_quota_error(msg: str) -> bool:
    """True só quando o Google confirma cota do DIA (não 429 de RPM)."""
    m = (msg or "").lower()
    needles = (
        "per-day",
        "per day",
        "requests per day",
        "daily request",
        "daily quota",
        "daily limit",
        "quota exceeded for metric",
        "generaterequestsperday",
    )
    return any(n in m for n in needles)


def _is_daily_quota_error(msg: str) -> bool:
    """Failover de chave: trava local de RPD ou cota diária confirmada pelo Google."""
    return _is_local_rpd_block(msg) or _is_google_daily_quota_error(msg)


def _is_rate_error(msg: str) -> bool:
    m = (msg or "").lower()
    return (
        "429" in m
        or "too many requests" in m
        or "rate limit" in m
        or "resource_exhausted" in m
        or "resource exhausted" in m
        or "quota" in m
    )


class GeminiClient:
    """Wrapper cliente do Gemini com controle automático de limites de taxa e retentativas."""

    def __init__(self, api_key: str = None, usage_file: str = None):
        from google import genai
        # Inicializa o cliente real do SDK do Google GenAI
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

        # Define caminho do arquivo de persistência de limites
        project_root = Path(__file__).resolve().parents[1]
        if usage_file:
            self.usage_file = Path(usage_file)
        else:
            self.usage_file = project_root / "sources" / "gemini_usage.json"

        # Tentar carregar limites customizados das variáveis de ambiente
        self.limits = {}
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or ""
        for category, default_vals in DEFAULT_LIMITS.items():
            prefix = f"GEMINI_{category.upper()}_"
            self.limits[category] = {
                "rpm": int(os.environ.get(f"{prefix}RPM", default_vals["rpm"])),
                "rpd": int(os.environ.get(f"{prefix}RPD", default_vals["rpd"])),
                "tpm": int(os.environ.get(f"{prefix}TPM", default_vals["tpm"])),
            }

    def _get_limits(self, model: str) -> dict:
        category = _get_model_category(model)
        return self.limits[category]

    def _enforce_rate_limit(self, model: str, estimated_tokens: int):
        """Bloqueia a execução (dorme) até que haja cotas disponíveis OU levanta exceção caso estoure o limite diário.

        A quota é POR CHAVE (cada GEMINI_API_KEY tem sua própria cota).
        O arquivo de uso é indexado por chave mascarada.
        Retorna o timestamp reservado (para rollback se a API falhar).
        """
        limits = self._get_limits(model)
        rpm = limits["rpm"]
        rpd = limits["rpd"]
        tpm = limits["tpm"]
        key_id = _key_id(self.api_key)
        min_gap = 60.0 / max(1, rpm)

        while True:
            now = time.time()
            usage = _load_usage(self.usage_file)

            key_data = usage.setdefault(key_id, {})
            model_data = key_data.setdefault(model, {"requests": [], "tokens": []})

            real_requests = _collapse_fake_rpd_pad(model_data.get("requests") or [])
            requests_minute = [t for t in real_requests if now - t < 60]
            requests_day = _requests_in_rpd_window(real_requests, now)
            tokens_minute = [entry for entry in model_data["tokens"] if now - entry["timestamp"] < 60]

            model_data["requests"] = requests_day
            model_data["tokens"] = tokens_minute
            exhausted_until = float(model_data.get("exhausted_until") or 0)
            if exhausted_until and exhausted_until <= now:
                model_data["exhausted_until"] = 0
                exhausted_until = 0

            if exhausted_until > now or len(requests_day) >= rpd:
                raise RuntimeError(
                    f"Limite diário atingido (RPD de {rpd}) para o modelo {model}. "
                    f"Reset à meia-noite do Pacífico (AI Studio) ou alterne a chave."
                )

            # Timer por chave: não disparar mais cedo que 60/RPM (TTS 3.1 = 20s).
            if requests_day:
                last = max(requests_day)
                wait_gap = (last + min_gap) - now
                if wait_gap > 0.05:
                    log.warning(
                        f"Timer {key_id} {model}: intervalo mínimo {min_gap:.1f}s "
                        f"(RPM={rpm}). Dormindo {wait_gap:.2f}s..."
                    )
                    time.sleep(wait_gap)
                    continue

            if len(requests_minute) >= rpm:
                oldest_req = min(requests_minute)
                wait_time = max(0.1, 60 - (now - oldest_req) + 0.2)
                log.warning(
                    f"Rate Limiting: Limite RPM ({rpm}) atingido para {model}. "
                    f"Dormindo {wait_time:.2f} segundos..."
                )
                time.sleep(wait_time)
                continue

            current_tokens = sum(entry["tokens"] for entry in tokens_minute)
            if current_tokens + estimated_tokens >= tpm:
                oldest_token_ts = min(entry["timestamp"] for entry in tokens_minute)
                wait_time = max(0.1, 60 - (now - oldest_token_ts) + 0.2)
                log.warning(
                    f"Rate Limiting: Limite TPM ({current_tokens}/{tpm}) perto de estourar "
                    f"para {model} com estimativa de {estimated_tokens} tokens. "
                    f"Dormindo {wait_time:.2f} segundos..."
                )
                time.sleep(wait_time)
                continue

            reserved = time.time()
            model_data["requests"].append(reserved)
            model_data["tokens"].append({"timestamp": reserved, "tokens": estimated_tokens})
            _save_usage(self.usage_file, usage)
            return reserved

    def _rollback_rate_limit(self, model: str, request_time: float) -> None:
        """Solta a reserva se a API rejeitou (429 RPM / 503 / rede)."""
        try:
            usage = _load_usage(self.usage_file)
            key_id = _key_id(self.api_key)
            model_data = (usage.get(key_id) or {}).get(model)
            if not model_data:
                return
            model_data["requests"] = [
                t for t in model_data.get("requests", []) if abs(t - request_time) > 0.0001
            ]
            model_data["tokens"] = [
                e for e in model_data.get("tokens", [])
                if abs(e.get("timestamp", 0) - request_time) > 0.0001
            ]
            _save_usage(self.usage_file, usage)
            log.info(f"Rollback de reserva {key_id} {model}")
        except Exception as e:
            log.debug(f"Erro silencioso no rollback de taxa: {e}")

    def _mark_daily_quota_exhausted(self, model: str) -> None:
        """Trava a chave até o próximo reset do Pacífico — sem forjar N timestamps."""
        try:
            usage = _load_usage(self.usage_file)
            key_id = _key_id(self.api_key)
            key_data = usage.setdefault(key_id, {})
            model_data = key_data.setdefault(model, {"requests": [], "tokens": []})
            now = time.time()
            until = _next_pacific_midnight(now)
            model_data["exhausted_until"] = until
            model_data["requests"] = _collapse_fake_rpd_pad(
                _requests_in_rpd_window(model_data.get("requests") or [], now)
            )
            _save_usage(self.usage_file, usage)
            log.warning(
                f"RPD Google confirmado para {key_id} {model} — "
                f"chave travada até {datetime.fromtimestamp(until, tz=PACIFIC).isoformat()}"
            )
        except Exception as e:
            log.debug(f"Erro ao marcar quota diária esgotada: {e}")

    def _update_actual_tokens(self, model: str, request_time: float, actual_tokens: int):
        """Atualiza a estimativa de tokens do minuto pelo valor real retornado pela API."""
        try:
            usage = _load_usage(self.usage_file)
            key_id = _key_id(self.api_key)
            key_data = usage.get(key_id, {})
            model_data = key_data.get(model)
            if model_data and "tokens" in model_data:
                # Procura a transição mais próxima do request_time
                for entry in model_data["tokens"]:
                    if abs(entry["timestamp"] - request_time) < 1.0:
                        entry["tokens"] = actual_tokens
                        break
                _save_usage(self.usage_file, usage)
        except Exception as e:
            log.debug(f"Erro silencioso ao atualizar tokens reais: {e}")

    def generate_content(self, model: str, contents, config=None, max_retries: int = 2, **kwargs):
        """Gera conteúdo respeitando RPM/RPD e com retry curto.

        max_retries=2: a 2ª tentativa em 429 espera a janela de RPM (~20s no TTS),
        não metralha 5× com backoff de 2s.
        """
        estimated_tokens = _estimate_tokens(contents)
        reserved_at = self._enforce_rate_limit(model, estimated_tokens)
        last_exception = None
        call_succeeded = False
        base_delay = 2.0

        try:
            for attempt in range(1, max_retries + 1):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                        **kwargs
                    )
                    try:
                        if response.usage_metadata and response.usage_metadata.total_token_count:
                            self._update_actual_tokens(model, reserved_at, response.usage_metadata.total_token_count)
                    except Exception:
                        pass
                    call_succeeded = True
                    return response
                except Exception as exc:
                    last_exception = exc
                    error_msg = str(exc).lower()
                    is_transient = (
                        _is_rate_error(error_msg)
                        or "503" in error_msg
                        or "service unavailable" in error_msg
                    )
                    if not is_transient:
                        raise
                    if _is_google_daily_quota_error(error_msg):
                        self._mark_daily_quota_exhausted(model)
                        raise
                    if attempt == max_retries:
                        log.error(f"Todas as {max_retries} tentativas falharam para {model}.")
                        raise
                    if "429" in error_msg or "rate limit" in error_msg or "resource_exhausted" in error_msg:
                        rpm_limit = self._get_limits(model)["rpm"]
                        delay = max(20.0, 60.0 / max(1, rpm_limit)) + random.uniform(0.5, 2.0)
                    else:
                        jitter = random.uniform(-0.5, 0.5)
                        delay = max(0.5, (base_delay * (2 ** (attempt - 1))) + jitter)
                    log.warning(
                        f"Erro de taxa (429/transiente) na tentativa {attempt}/{max_retries} "
                        f"para {model}: {exc}. Aguardando {delay:.2f}s..."
                    )
                    time.sleep(delay)
            if last_exception:
                raise last_exception
        finally:
            if not call_succeeded:
                self._rollback_rate_limit(model, reserved_at)


class GeminiMultiClient:
    """Wrapper que intercala MÚLTIPLAS chaves Gemini (contas/projetos diferentes).

    Cada chave tem sua própria quota (3 RPM / 10 RPD na AI Studio).

    Estratégia (2026-08-03):
      1. ROUND-ROBIN por chamada — chunk 1 → key1, chunk 2 → key2, …
         Isso espalha RPM (3/min) e RPD (10/dia) entre as chaves, em vez
         de esgotar a primeira e só então cair na segunda.
      2. RPD / cota diária → failover na próxima chave.
         429 de RPM NÃO varre o anel: a chave da vez dorme no timer (60/RPM).

    Usado pelo TTS e pelo roteiro para multiplicar a capacidade.
    """
    def __init__(self, api_keys: list[str]):
        from typing import Any
        self._clients: list[Any] = [GeminiClient(api_key=k) for k in api_keys if k]
        if not self._clients:
            self._clients = [GeminiClient()]
        # Cursor round-robin PERSISTIDO entre execuções (sources/gemini_usage.json
        # → _meta.rr_index). Sem persistência, cada processo recomeçava na key[0]:
        # episódios curtos (BM com 2 metades) só tocavam as primeiras chaves e o
        # RPD diário não era diluído de forma uniforme entre execuções.
        self._usage_file = self._clients[0].usage_file
        self._rr_index = self._load_rr_cursor()

    def _load_rr_cursor(self) -> int:
        """Lê o cursor persistido (_meta.rr_index do arquivo de uso compartilhado)."""
        try:
            data = _load_usage(self._usage_file)
            val = (data.get("_meta") or {}).get("rr_index", 0)
            return int(val)
        except Exception:
            return 0

    def _save_rr_cursor(self):
        """Persiste o cursor para a próxima execução/processo continuar a rotação."""
        try:
            data = _load_usage(self._usage_file)
            meta = data.setdefault("_meta", {})
            meta["rr_index"] = self._rr_index
            _save_usage(self._usage_file, data)
        except Exception:
            pass  # falha de persistência não bloqueia a geração

    @property
    def models(self):
        return _ModelsProxy(self)

    def generate_content(self, model: str, contents, config=None, **kwargs):
        n = len(self._clients)
        if n == 1:
            return self._clients[0].generate_content(model, contents, config=config, **kwargs)

        # Round-robin: começa na próxima chave e tenta as N em ordem cíclica
        start = self._rr_index % n
        self._rr_index = (self._rr_index + 1) % n
        self._save_rr_cursor()

        last_exc = None
        for offset in range(n):
            idx = (start + offset) % n
            client = self._clients[idx]
            key_hint = _key_id(getattr(client, "api_key", "") or "")
            try:
                if offset == 0:
                    log.info(f"RR key[{idx}] {key_hint} para {model}")
                else:
                    log.warning(f"Failover RPD → key[{idx}] {key_hint} (tentativa {offset+1}/{n})")
                return client.generate_content(model, contents, config=config, **kwargs)
            except RuntimeError as exc:
                msg = str(exc).lower()
                if _is_daily_quota_error(msg):
                    log.warning(f"Chave {key_hint} esgotou RPD: {exc} — rotacionando...")
                    last_exc = exc
                    continue
                raise
            except Exception as exc:
                msg = str(exc).lower()
                if _is_google_daily_quota_error(msg):
                    try:
                        client._mark_daily_quota_exhausted(model)
                    except Exception:
                        pass
                    log.warning(f"Chave {key_hint} quota diária Google — rotacionando...")
                    last_exc = exc
                    continue
                if _is_rate_error(msg):
                    log.warning(
                        f"Chave {key_hint} 429 de taxa (não RPD) — sem varrer o anel: {exc}"
                    )
                    raise
                last_exc = exc
                log.warning(f"Chave {key_hint} erro: {exc} — tentando próxima...")
                continue
        raise last_exc or RuntimeError("Nenhuma chave Gemini disponível")


# Atributo models exposto para emular o comportamento do genai.Client
class _ModelsProxy:
    def __init__(self, client: GeminiClient):
        self._client = client

    def generate_content(self, model: str, contents, config=None, **kwargs):
        return self._client.generate_content(model, contents, config=config, **kwargs)


# Estender para suportar a notação `client.models.generate_content`
setattr(GeminiClient, "models", property(lambda self: _ModelsProxy(self)))
