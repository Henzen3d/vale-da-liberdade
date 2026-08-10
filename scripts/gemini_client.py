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
from pathlib import Path

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

        A quota é POR CHAVE (cada GEMINI_API_KEY tem sua própria cota de
        3 RPM / 10 RPD na AI Studio). O arquivo de uso é indexado por
        chave mascarada para isolar a contagem de cada conta/projeto.
        """
        limits = self._get_limits(model)
        rpm = limits["rpm"]
        rpd = limits["rpd"]
        tpm = limits["tpm"]
        key_id = (self.api_key[:4] + "…" + self.api_key[-4:]) if len(self.api_key) >= 12 else (self.api_key or "default")

        while True:
            now = time.time()
            usage = _load_usage(self.usage_file)

            # Contagem isolation por chave
            key_data = usage.setdefault(key_id, {})
            model_data = key_data.setdefault(model, {"requests": [], "tokens": []})

            # Filtrar e manter apenas requisições da última 1 hora (para RPD de 24h, limpamos separadamente)
            # Na verdade, RPD monitora as últimas 24 horas (86.400s)
            requests_minute = [t for t in model_data["requests"] if now - t < 60]
            requests_day = [t for t in model_data["requests"] if now - t < 86400]
            
            # Filtrar tokens do último minuto
            tokens_minute = [entry for entry in model_data["tokens"] if now - entry["timestamp"] < 60]

            # Atualizar os dados sanitizados no arquivo
            model_data["requests"] = requests_day
            model_data["tokens"] = tokens_minute

            # 1. Verificar Limite Diário (RPD)
            if len(requests_day) >= rpd:
                raise RuntimeError(
                    f"Limite diário atingido (RPD de {rpd}) para o modelo {model}. "
                    f"Aguarde o reset da janela de 24h ou alterne para outro modelo."
                )

            # 2. Verificar Limite por Minuto (RPM)
            if len(requests_minute) >= rpm:
                oldest_req = min(requests_minute)
                wait_time = max(0.1, 60 - (now - oldest_req) + 0.2)
                log.warning(
                    f"Rate Limiting: Limite RPM ({rpm}) atingido para {model}. "
                    f"Dormindo {wait_time:.2f} segundos..."
                )
                time.sleep(wait_time)
                continue  # Reavalia após dormir

            # 3. Verificar Limite de Tokens por Minuto (TPM)
            current_tokens = sum(entry["tokens"] for entry in tokens_minute)
            if current_tokens + estimated_tokens >= tpm:
                # Achar a transição de janela mais antiga
                oldest_token_ts = min(entry["timestamp"] for entry in tokens_minute)
                wait_time = max(0.1, 60 - (now - oldest_token_ts) + 0.2)
                log.warning(
                    f"Rate Limiting: Limite TPM ({current_tokens}/{tpm}) perto de estourar para {model} com estimativa de {estimated_tokens} tokens. "
                    f"Dormindo {wait_time:.2f} segundos..."
                )
                time.sleep(wait_time)
                continue  # Reavalia após dormir

            # Cota disponível! Grava o consumo
            model_data["requests"].append(now)
            model_data["tokens"].append({"timestamp": now, "tokens": estimated_tokens})
            _save_usage(self.usage_file, usage)
            break

    def _update_actual_tokens(self, model: str, request_time: float, actual_tokens: int):
        """Atualiza a estimativa de tokens do minuto pelo valor real retornado pela API."""
        try:
            usage = _load_usage(self.usage_file)
            key_id = (self.api_key[:4] + "…" + self.api_key[-4:]) if len(self.api_key) >= 12 else (self.api_key or "default")
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

    def generate_content(self, model: str, contents, config=None, max_retries: int = 5, **kwargs):
        """
        Executa `generate_content` respeitando as travas de rate limits e com mecanismo de retry com backoff exponencial.
        """
        estimated_tokens = _estimate_tokens(contents)
        
        # Garante cota sob os limites RPM/RPD/TPM (por chave)
        self._enforce_rate_limit(model, estimated_tokens)
        
        request_time = time.time()
        last_exception = None
        base_delay = 2.0  # Começa com 2 segundos conforme o requisito
        
        for attempt in range(1, max_retries + 1):
            try:
                # Executa a chamada real da API
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                    **kwargs
                )
                
                # Se obtivermos metadados reais de uso, atualiza o arquivo
                try:
                    if response.usage_metadata and response.usage_metadata.total_token_count:
                        self._update_actual_tokens(model, request_time, response.usage_metadata.total_token_count)
                except Exception:
                    pass

                return response

            except Exception as exc:
                last_exception = exc
                error_msg = str(exc).lower()

                # Verifica se é erro de limites ou instabilidade temporária
                is_transient = (
                    "429" in error_msg
                    or "too many requests" in error_msg
                    or "rate limit" in error_msg
                    or "resource exhausted" in error_msg
                    or "503" in error_msg
                    or "service unavailable" in error_msg
                    or "quota" in error_msg
                )

                if not is_transient:
                    # Erro de negócio/parâmetro, levanta de imediato
                    raise exc

                if attempt == max_retries:
                    log.error(f"Todas as {max_retries} tentativas falharam para {model}.")
                    raise exc

                # Cálculo de backoff exponencial com Jitter aleatório (±0.5s)
                jitter = random.uniform(-0.5, 0.5)
                delay = (base_delay * (2 ** (attempt - 1))) + jitter
                delay = max(0.5, delay)  # impede atraso negativo

                log.warning(
                    f"Erro de taxa (429/transiente) na tentativa {attempt}/{max_retries} para {model}: {exc}. "
                    f"Aguardando {delay:.2f}s antes de tentar novamente..."
                )
                time.sleep(delay)

        # Caso saia do loop sem retornar (incomum por causa do raise exc acima)
        if last_exception:
            raise last_exception


class GeminiMultiClient:
    """Wrapper que intercala MÚLTIPLAS chaves Gemini (contas/projetos diferentes).

    Cada chave tem sua própria quota (3 RPM / 10 RPD na AI Studio).

    Estratégia (2026-08-03):
      1. ROUND-ROBIN por chamada — chunk 1 → key1, chunk 2 → key2, …
         Isso espalha RPM (3/min) e RPD (10/dia) entre as chaves, em vez
         de esgotar a primeira e só então cair na segunda.
      2. Se a chave escolhida estoura RPD/RPM/quota, tenta as demais em
         ordem (failover). RPM local dorme dentro de GeminiClient antes
         de levantar; RPD levanta RuntimeError e cai no failover.

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
            key_hint = (client.api_key[:4] + "…" + client.api_key[-4:]) if len(getattr(client, "api_key", "") or "") >= 12 else f"#{idx}"
            try:
                if offset == 0:
                    log.info(f"RR key[{idx}] {key_hint} para {model}")
                else:
                    log.warning(f"Failover → key[{idx}] {key_hint} (tentativa {offset+1}/{n})")
                return client.generate_content(model, contents, config=config, **kwargs)
            except RuntimeError as exc:
                msg = str(exc).lower()
                # Quota/RPD estourada nesta chave → tenta a próxima
                if "limite diário" in msg or "rpd" in msg or "quota" in msg or "resource_exhausted" in msg or "429" in msg:
                    log.warning(f"Chave {key_hint} estourou quota: {exc} — tentando próxima...")
                    last_exc = exc
                    continue
                raise
            except Exception as exc:
                msg = str(exc).lower()
                # 429 / resource exhausted da API Google também deve rotacionar
                if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
                    log.warning(f"Chave {key_hint} 429/quota da API: {exc} — tentando próxima...")
                    last_exc = exc
                    continue
                last_exc = exc
                # Erros de rede/auth transitórios: tenta próxima; se todas falharem, re-raise
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
