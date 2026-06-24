#!/usr/bin/env python3
"""
Módulo Coletor do X (Twitter) — Web Jornal Vale da Liberdade.

Usa Playwright + stealth para navegar no X como um humano,
buscar notícias locais por termos-chave e perfis, e acumular
os tweets relevantes em um cache JSON para consumo pelo pipeline.

Arquitetura (schema 2.0):
    - XStealthBrowser   : engine anti-detecção + login (inalterada)
    - ProfileRegistry   : resolve handles em tiers (official/media/watch)
    - QueryBuilder      : monta URLs de busca com operadores avançados do X
    - TweetParser       : extrai dados do DOM (inalterado em essência)
    - TweetScorer       : score de relevância (tier + engajamento + idade)
                          + filtros de idioma/idade/blacklist
    - ContentDeduplicator: dedup por fingerprint (mesmo texto, IDs diferentes)
    - TweetCache        : cache rotativo (TTL), preserva collected_ids
    - Collectors        : XSearchCollector + XProfileCollector

Uso:
    # Coleta completa (termos + perfis)
    python x_collector.py --mode full

    # Apenas busca por termos
    python x_collector.py --mode search

    # Apenas perfis
    python x_collector.py --mode profiles

    # Apenas login (salvar cookies)
    python x_collector.py --mode login-only

    # Dry-run (mostra o que faria sem salvar)
    python x_collector.py --mode full --dry-run

    # Limitar termos específicos
    python x_collector.py --mode search --terms "Blumenau" "BR-470"

    # Limitar perfis específicos
    python x_collector.py --mode profiles --profiles "PrefBlumenau"
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from dotenv import load_dotenv

# Configuração de caminhos
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCES_DIR = PROJECT_ROOT / "sources"

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Forçar UTF-8 no stdout/stderr para suportar emojis no Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("x-collector")


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CACHE_SCHEMA_VERSION = "2.0"
TIER_ORDER = ("official", "media", "watch", "search")


def load_x_config() -> dict:
    """Carrega x_config.json com fallback gracioso para schema 1.0."""
    config_path = SOURCES_DIR / "x_config.json"
    if not config_path.exists():
        log.error(f"Configuração não encontrada: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return _normalize_config(config)


def _normalize_config(config: dict) -> dict:
    """Normaliza schema 1.0 → 2.0 em memória (sem regravar o arquivo).

    Schema 1.0 tinha `profiles: [handle, ...]` (lista plana).
    Schema 2.0 tem `profiles: {official/media/watch: {handles: [...]}}`.
    """
    profiles = config.get("profiles")
    if isinstance(profiles, list):
        log.info("📐 Config schema 1.0 detectado (profiles como lista). Migrando em memória para watch tier.")
        config["profiles"] = {
            "official": {"handles": []},
            "media": {"handles": []},
            "watch": {"handles": list(profiles)},
        }
    # Garantir chaves ausentes com defaults sensatos
    config.setdefault("search_operators", {})
    config.setdefault("blacklist", {"handles": [], "keywords_in_text": []})
    config.setdefault("settings", {})
    config["settings"].setdefault("scoring", {})
    return config


def _empty_cache() -> dict:
    """Estrutura padrão do cache (schema 2.0)."""
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "last_collection": None,
        "sessions_today": 0,
        "last_session_date": None,
        "tweets": [],
        "collected_ids": [],
        "content_fingerprints": {},
    }


def load_tweet_cache() -> dict:
    """Carrega o cache de tweets acumulados (com migração automática)."""
    config = load_x_config()
    cache_file = SOURCES_DIR / config["settings"]["tweet_cache_file"]
    if not cache_file.exists():
        return _empty_cache()
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        log.warning(f"Erro ao ler cache de tweets ({e}). Criando novo...")
        return _empty_cache()

    # Migração schema 1.0 → 2.0
    if cache.get("schema_version", "1.0") != CACHE_SCHEMA_VERSION:
        log.info(f"📦 Migrando cache schema {cache.get('schema_version', '?')} → {CACHE_SCHEMA_VERSION}")
        cache.setdefault("content_fingerprints", {})
        cache["schema_version"] = CACHE_SCHEMA_VERSION
        save_tweet_cache(cache)
    return cache


def save_tweet_cache(cache: dict):
    """Salva o cache de tweets."""
    config = load_x_config()
    cache_file = SOURCES_DIR / config["settings"]["tweet_cache_file"]
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Erro ao salvar cache de tweets: {e}")


# ---------------------------------------------------------------------------
# XStealthBrowser — Navegador com comportamento humano (inalterado)
# ---------------------------------------------------------------------------

class XStealthBrowser:
    """Gerencia uma sessão Playwright com stealth e delays humanos."""

    def __init__(self, config: dict, headless: bool = True):
        self.config = config
        self.settings = config["settings"]
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None

    def _get_random_viewport(self) -> dict:
        """Retorna um viewport aleatório da lista configurada."""
        return random.choice(self.settings["viewports"])

    def _get_random_user_agent(self) -> str:
        """Retorna um User-Agent aleatório."""
        return random.choice(self.settings["user_agents"])

    def _human_delay(self, min_sec: float = None, max_sec: float = None):
        """Pausa com delay humano aleatório."""
        if min_sec is None or max_sec is None:
            delays = self.settings["delay_between_actions_sec"]
            min_sec, max_sec = delays[0], delays[1]
        delay = random.uniform(min_sec, max_sec)
        log.debug(f"  💤 Delay humano: {delay:.1f}s")
        time.sleep(delay)

    def _human_type(self, locator, text: str):
        """Digita texto caractere a caractere com timing humano."""
        typing_delays = self.settings["typing_delay_ms"]
        locator.focus()
        for char in text:
            self.page.keyboard.type(char, delay=random.uniform(
                typing_delays[0], typing_delays[1]
            ))
            # Pequena chance de pausa extra (humano pensando)
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 0.8))

    def _random_scroll(self, direction: str = "down"):
        """Scroll suave com variação humana."""
        if not self.page:
            return
        scroll_delays = self.settings.get("scroll_delay_sec", [1, 3])
        pixels = random.randint(300, 800)
        if direction == "up":
            pixels = -pixels

        self.page.evaluate(f"""
            window.scrollBy({{
                top: {pixels},
                behavior: 'smooth'
            }});
        """)
        time.sleep(random.uniform(scroll_delays[0], scroll_delays[1]))

    def _maybe_distraction(self):
        """5% de chance de comportamento 'distraído' — scroll up, pausa longa."""
        if random.random() < 0.05:
            log.debug("  🧠 Simulando distração humana...")
            self._random_scroll("up")
            time.sleep(random.uniform(2, 5))
            self._random_scroll("down")

    def launch(self):
        """Inicia o browser Playwright com stealth."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("Playwright não está instalado. Execute: pip install playwright && playwright install chromium")
            sys.exit(1)

        self._playwright = sync_playwright().start()

        viewport = self._get_random_viewport()
        user_agent = self._get_random_user_agent()

        log.info(f"🌐 Iniciando browser (headless={self.headless}, viewport={viewport['width']}x{viewport['height']})")

        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
            ]
        )

        self.context = self.browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            color_scheme="dark",
            java_script_enabled=True,
            has_touch=False,
            is_mobile=False,
            permissions=["geolocation"],
            geolocation={"latitude": -26.9194, "longitude": -49.0661},  # Blumenau
        )

        # Aplicar stealth patches
        self._apply_stealth_patches()

        self.page = self.context.new_page()

        # Bloquear recursos de imagem apenas em modo headless para economizar banda/tempo, sem quebrar fontes/SVGs
        if self.headless:
            self.page.route("**/*.{png,jpg,jpeg,gif,ico}", lambda route: route.abort())

        log.info("✅ Browser iniciado com stealth ativo")

    def _apply_stealth_patches(self):
        """Aplica patches anti-detecção via JavaScript."""
        stealth_js = """
        // Ocultar webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Falsificar plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ]
        });

        // Falsificar languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['pt-BR', 'pt', 'en-US', 'en']
        });

        // Ocultar automação do chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Falsificar permissões
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Ajustar resolução de canvas (anti-fingerprint)
        const getContext = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function(type, attrs) {
            const context = getContext.call(this, type, attrs);
            if (type === '2d') {
                const originalGetImageData = context.getImageData;
                context.getImageData = function() {
                    const imageData = originalGetImageData.apply(this, arguments);
                    // Adicionar ruído sutil
                    for (let i = 0; i < imageData.data.length; i += 100) {
                        imageData.data[i] = imageData.data[i] ^ (Math.random() > 0.5 ? 1 : 0);
                    }
                    return imageData;
                };
            }
            return context;
        };
        """
        self.context.add_init_script(stealth_js)

    def _get_cookie_path(self) -> Path:
        """Retorna o caminho do arquivo de cookies."""
        return SOURCES_DIR / self.settings["cookie_file"]

    def save_cookies(self):
        """Salva cookies da sessão atual."""
        if not self.context:
            return
        cookies = self.context.cookies()
        cookie_path = self._get_cookie_path()
        with open(cookie_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log.info(f"🍪 Cookies salvos: {cookie_path} ({len(cookies)} cookies)")

    def load_cookies(self) -> bool:
        """Carrega cookies de sessão anterior. Retorna True se encontrou."""
        cookie_path = self._get_cookie_path()
        if not cookie_path.exists():
            log.info("🍪 Nenhum cookie salvo encontrado")
            return False
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            if not cookies:
                return False
            self.context.add_cookies(cookies)
            log.info(f"🍪 Cookies carregados: {len(cookies)} cookies")
            return True
        except Exception as e:
            log.warning(f"Erro ao carregar cookies: {e}")
            return False

    def _check_rate_limit(self) -> bool:
        """Verifica se o X exibiu mensagem de limite de acesso / rate limit."""
        if not self.page:
            return False
        try:
            page_text = self.page.inner_text("body")
            rate_limit_phrases = [
                "Limitamos temporariamente seu acesso",
                "We've temporarily limited your access",
                "Tente novamente mais tarde",
                "Please try again later",
                "Rate limit exceeded",
                "Too many requests"
            ]
            for phrase in rate_limit_phrases:
                if phrase.lower() in page_text.lower():
                    log.error(f"⚠️ [RATE LIMIT] O X bloqueou o acesso temporariamente: '{phrase}'")
                    log.error("👉 DICA: O X bloqueia o IP ou a conta temporariamente quando ocorrem muitas tentativas de login seguidas.")
                    log.error("   Por favor, aguarde de 15 a 30 minutos (ou algumas horas) antes de tentar novamente.")
                    log.error("   Tente fazer login manualmente pela interface do seu navegador normal para resolver CAPCHAs ou validações.")
                    return True
        except Exception:
            pass
        return False

    def is_logged_in(self) -> bool:
        """Verifica se a sessão atual está autenticada no X."""
        try:
            self.page.goto("https://x.com/home", wait_until="commit", timeout=60000)
            self._human_delay(5, 8)

            if self._check_rate_limit():
                return False

            current_url = self.page.url
            if "login" in current_url or "i/flow" in current_url:
                log.info("🔒 Sessão expirada — login necessário")
                return False

            try:
                self.page.wait_for_selector('[data-testid="SideNav_NewTweet_Button"]', timeout=10000)
                log.info("✅ Sessão ativa — login válido")
                return True
            except Exception:
                try:
                    self.page.wait_for_selector('[aria-label="Post"]', timeout=5000)
                    log.info("✅ Sessão ativa — login válido")
                    return True
                except Exception:
                    log.info("🔒 Não conseguiu confirmar login — refazendo...")
                    return False

        except Exception as e:
            log.warning(f"Erro ao verificar login: {e}")
            return False

    def login(self) -> bool:
        """Faz login no X com credenciais do .env."""
        username = os.environ.get("X_USERNAME")
        password = os.environ.get("X_PASSWORD")
        email = os.environ.get("X_EMAIL")

        if not username or not password:
            log.error("X_USERNAME e X_PASSWORD são obrigatórios no .env")
            return False

        log.info(f"🔐 Iniciando login no X como @{username}...")

        try:
            start_url = "https://x.com/"
            loaded = False
            for attempt in range(3):
                try:
                    log.info(f"  🌐 Navegando para x.com (tentativa {attempt + 1}/3)...")
                    self.page.goto(start_url, wait_until="commit", timeout=60000)
                    loaded = True
                    break
                except Exception as nav_err:
                    log.warning(f"  ⚠️  Navegação falhou na tentativa {attempt + 1}: {nav_err}")
                    if attempt < 2:
                        time.sleep(random.uniform(3, 6))

            if not loaded:
                log.error("❌ Não foi possível carregar o X após 3 tentativas")
                return False

            log.info("  ⏳ Aguardando página inicial renderizar...")
            self._human_delay(4, 7)

            if self._check_rate_limit():
                return False

            log.info("  🖱️ Clicando em 'Entrar' para abrir o modal de login...")
            login_trigger = self.page.locator(
                'a[href="/login"], '
                'a[data-testid="loginButton"], '
                'span:has-text("Log in"), '
                'span:has-text("Entrar")'
            )
            if login_trigger.count() > 0:
                login_trigger.first.click(force=True)
                self._human_delay(2, 4)
            else:
                log.warning("  ⚠️  Botão 'Entrar' não encontrado na home, tentando prosseguir de qualquer forma...")

            if self._check_rate_limit():
                return False

            log.info("  📝 Procurando campo de username...")
            username_selector = (
                'input[autocomplete*="username"], '
                'input[name="text"], '
                'input[name="username_or_email"]'
            )
            username_locators = self.page.locator(username_selector)
            try:
                username_locators.first.wait_for(state="visible", timeout=30000)
            except Exception as e:
                if self._check_rate_limit():
                    return False
                log.error(f"❌ Timeout ao aguardar campo de username: {e}")
                return False

            username_input = username_locators.last

            log.info("  📝 Digitando username...")
            self._human_delay(1, 2)
            username_input.focus()
            self._human_delay(0.5, 1)
            self._human_type(username_input, username)
            self._human_delay(1, 2)

            next_button = self.page.locator(
                'button:has-text("Next"), button:has-text("Avançar"), button:has-text("Próximo"), '
                'button:has-text("Continue"), button:has-text("Continuar"), '
                'p:has-text("Continuar"), p:has-text("Continue"), p:has-text("Next"), p:has-text("Avançar"), '
                'span:has-text("Continuar"), span:has-text("Continue"), span:has-text("Next"), span:has-text("Avançar")'
            )
            if next_button.count() > 0:
                next_button.last.click(force=True)
            else:
                self.page.keyboard.press("Enter")
            self._human_delay(2, 4)

            if self._check_rate_limit():
                return False

            try:
                challenge_locators = self.page.locator('input[data-testid="ocfEnterTextTextInput"]')
                challenge_locators.first.wait_for(state="visible", timeout=5000)
                challenge_input = challenge_locators.last

                log.info("  ⚠️  X pediu verificação adicional (email/telefone)...")
                if email:
                    log.info(f"  📧 Usando email: {email}")
                    challenge_input.focus()
                    self._human_delay(0.5, 1)
                    self._human_type(challenge_input, email)
                    self._human_delay(1, 2)
                    next_btn = self.page.locator(
                        'button:has-text("Next"), button:has-text("Avançar"), '
                        'p:has-text("Continuar"), p:has-text("Continue"), p:has-text("Next"), '
                        'span:has-text("Continuar"), span:has-text("Continue"), span:has-text("Next")'
                    )
                    if next_btn.count() > 0:
                        next_btn.last.click(force=True)
                    else:
                        self.page.keyboard.press("Enter")
                    self._human_delay(2, 4)
                else:
                    log.error("  ❌ X pediu verificação mas X_EMAIL não está configurado no .env")
                    return False
            except Exception:
                pass

            if self._check_rate_limit():
                return False

            log.info("  🔑 Procurando campo de senha...")
            password_selector = 'input[type="password"], input[name="password"]'
            password_locators = self.page.locator(password_selector)
            try:
                password_locators.first.wait_for(state="visible", timeout=15000)
            except Exception as e:
                if self._check_rate_limit():
                    return False
                log.error(f"❌ Timeout ao aguardar campo de senha: {e}")
                return False

            password_input = password_locators.last

            log.info("  🔑 Digitando senha...")
            self._human_delay(1, 2)
            password_input.focus()
            self._human_delay(0.5, 1)
            self._human_type(password_input, password)
            self._human_delay(1, 2)

            login_button = self.page.locator(
                'button[data-testid="LoginForm_Login_Button"], '
                'button:has-text("Log in"), '
                'button:has-text("Entrar"), '
                'p:has-text("Log in"), p:has-text("Entrar"), p:has-text("Continuar"), '
                'span:has-text("Log in"), span:has-text("Entrar"), span:has-text("Continuar")'
            )
            if login_button.count() > 0:
                login_button.last.click(force=True)
            else:
                self.page.keyboard.press("Enter")
            self._human_delay(3, 6)

            if self._check_rate_limit():
                return False

            try:
                twofa_locators = self.page.locator(
                    'input[data-testid="ocfEnterTextTextInput"], '
                    'input[autocomplete="one-time-code"]'
                )
                twofa_locators.first.wait_for(state="visible", timeout=5000)
                twofa_input = twofa_locators.last

                log.info("  🔐 2FA detectado! Insira o código no terminal:")
                code = input("     Código 2FA: ").strip()
                twofa_input.focus()
                self._human_delay(0.5, 1)
                self._human_type(twofa_input, code)
                self._human_delay(1, 2)
                next_btn = self.page.locator(
                    'button:has-text("Next"), button:has-text("Avançar"), button:has-text("Verify"), '
                    'p:has-text("Next"), p:has-text("Avançar"), p:has-text("Verify"), p:has-text("Confirmar"), '
                    'span:has-text("Next"), span:has-text("Avançar"), span:has-text("Verify"), span:has-text("Confirmar")'
                )
                if next_btn.count() > 0:
                    next_btn.last.click(force=True)
                else:
                    self.page.keyboard.press("Enter")
                self._human_delay(3, 5)
            except Exception:
                pass

            if self._check_rate_limit():
                return False

            self._human_delay(3, 5)
            current_url = self.page.url
            if "home" in current_url or "x.com" in current_url:
                try:
                    self.page.wait_for_selector(
                        '[data-testid="SideNav_NewTweet_Button"], [aria-label="Post"]',
                        timeout=10000
                    )
                    log.info("✅ Login realizado com sucesso!")
                    self.save_cookies()
                    return True
                except Exception:
                    if "login" not in current_url and "flow" not in current_url:
                        log.info("✅ Login provavelmente bem-sucedido (URL ok)")
                        self.save_cookies()
                        return True

            log.error(f"❌ Login falhou. URL atual: {current_url}")
            return False

        except Exception as e:
            if not self._check_rate_limit():
                log.error(f"❌ Erro durante login: {e}")
            return False

    def ensure_logged_in(self) -> bool:
        """Garante que estamos logados — tenta cookies primeiro, depois login fresh."""
        if self.load_cookies():
            if self.is_logged_in():
                return True
            log.info("Cookies expirados. Fazendo login fresh...")
        return self.login()

    def close(self):
        """Fecha o browser e libera recursos."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self._playwright:
                self._playwright.stop()
            log.info("🔒 Browser fechado")
        except Exception as e:
            log.warning(f"Erro ao fechar browser: {e}")


# ---------------------------------------------------------------------------
# ProfileRegistry — resolve handles em tiers de confiabilidade
# ---------------------------------------------------------------------------

class ProfileRegistry:
    """Resolve handles para seus tiers (official > media > watch)."""

    def __init__(self, config: dict):
        profiles_cfg = config.get("profiles", {})
        if isinstance(profiles_cfg, list):
            # Compatibilidade: trata lista plana como tier 'watch'
            profiles_cfg = {"watch": {"handles": list(profiles_cfg)}}
        self._tier_handles: Dict[str, List[str]] = {}
        self._handle_tier: Dict[str, str] = {}
        for tier in ("official", "media", "watch"):
            handles = profiles_cfg.get(tier, {}).get("handles", [])
            self._tier_handles[tier] = [h.lstrip("@").strip() for h in handles if h]
            for h in self._tier_handles[tier]:
                # Primeira ocorrência vence (prioridade do tier em ordem canônica)
                if h not in self._handle_tier:
                    self._handle_tier[h] = tier

    def all_handles(self) -> List[str]:
        """Todos os handles únicos, em ordem de tier."""
        seen = []
        for tier in TIER_ORDER:
            for h in self._tier_handles.get(tier, []):
                if h not in seen:
                    seen.append(h)
        return seen

    def handles_by_tier(self, tier: str) -> List[str]:
        return list(self._tier_handles.get(tier, []))

    def tier_of(self, handle: str) -> Optional[str]:
        return self._handle_tier.get(handle.lstrip("@").strip())

    def summary(self) -> Dict[str, int]:
        return {tier: len(self._tier_handles.get(tier, [])) for tier in TIER_ORDER}


# ---------------------------------------------------------------------------
# QueryBuilder — monta URLs de busca com operadores avançados do X
# ---------------------------------------------------------------------------

class QueryBuilder:
    """Constrói a query string para busca do X com operadores."""

    def __init__(self, config: dict):
        ops = config.get("search_operators", {})
        settings = config.get("settings", {})
        self.template = ops.get(
            "template",
            "{term} lang:{lang} min_faves:{min_faves} -filter:retweets -filter:replies since:{date}"
        )
        self.lang = ops.get("lang", settings.get("language_filter", "pt"))
        self.min_faves = ops.get("min_faves", 2)
        self.exclude_terms = ops.get("exclude_terms", [])

    def build(self, term: str) -> Tuple[str, str]:
        """Retorna (query_string, search_url) prontos para uso."""
        since_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        query = self.template.format(
            term=term,
            lang=self.lang,
            min_faves=self.min_faves,
            date=since_date,
        )
        # Excluir termos (aposta, idol, etc.)
        for ex in self.exclude_terms:
            query += f' -"{ex}"'
        encoded = self._url_encode_query(query)
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        return query, url

    @staticmethod
    def _url_encode_query(query: str) -> str:
        """Codifica query do X preservando operadores (espaços viram %20)."""
        from urllib.parse import quote
        return quote(query, safe=":")


# ---------------------------------------------------------------------------
# Parsing de Tweets
# ---------------------------------------------------------------------------

def parse_tweet_element(article_el) -> Optional[Dict[str, Any]]:
    """Extrai dados de um elemento de tweet do DOM."""
    try:
        tweet_data = {}

        # Tweet ID (extrair do link do tweet)
        try:
            link_els = article_el.query_selector_all('a[href*="/status/"]')
            for link_el in link_els:
                href = link_el.get_attribute("href") or ""
                match = re.search(r"/status/(\d+)", href)
                if match:
                    tweet_data["tweet_id"] = match.group(1)
                    break
        except Exception:
            pass

        if not tweet_data.get("tweet_id"):
            return None  # Sem ID = não é tweet válido

        # Autor (handle)
        try:
            user_link = article_el.query_selector('div[data-testid="User-Name"] a[role="link"]')
            if user_link:
                href = user_link.get_attribute("href") or ""
                tweet_data["author"] = href.strip("/").split("/")[-1]

            display_spans = article_el.query_selector_all('div[data-testid="User-Name"] span')
            if display_spans:
                tweet_data["author_name"] = display_spans[0].inner_text().strip()
        except Exception:
            tweet_data["author"] = "unknown"
            tweet_data["author_name"] = "Unknown"

        # Verificado
        try:
            verified = article_el.query_selector('[data-testid="icon-verified"]')
            tweet_data["author_verified"] = verified is not None
        except Exception:
            tweet_data["author_verified"] = False

        # Texto do tweet
        try:
            text_el = article_el.query_selector('[data-testid="tweetText"]')
            if text_el:
                tweet_data["text"] = text_el.inner_text().strip()
            else:
                tweet_data["text"] = ""
        except Exception:
            tweet_data["text"] = ""

        if not tweet_data["text"]:
            return None  # Tweet sem texto = skip

        # Timestamp
        try:
            time_el = article_el.query_selector("time")
            if time_el:
                tweet_data["timestamp"] = time_el.get_attribute("datetime") or ""
            else:
                tweet_data["timestamp"] = ""
        except Exception:
            tweet_data["timestamp"] = ""

        # Métricas de engajamento
        try:
            reply_btn = article_el.query_selector('[data-testid="reply"]')
            tweet_data["replies"] = _parse_metric(reply_btn)

            retweet_btn = article_el.query_selector('[data-testid="retweet"]')
            tweet_data["retweets"] = _parse_metric(retweet_btn)

            like_btn = article_el.query_selector('[data-testid="like"]')
            tweet_data["likes"] = _parse_metric(like_btn)

            views_el = article_el.query_selector('a[href*="/analytics"]')
            tweet_data["views"] = _parse_metric(views_el)
        except Exception:
            tweet_data.setdefault("replies", 0)
            tweet_data.setdefault("retweets", 0)
            tweet_data.setdefault("likes", 0)
            tweet_data.setdefault("views", 0)

        # URLs de mídia
        try:
            media_els = article_el.query_selector_all('[data-testid="tweetPhoto"] img')
            tweet_data["media_urls"] = []
            for img in media_els:
                src = img.get_attribute("src")
                if src:
                    tweet_data["media_urls"].append(src)
        except Exception:
            tweet_data["media_urls"] = []

        return tweet_data

    except Exception as e:
        log.debug(f"Erro ao parsear tweet: {e}")
        return None


def _parse_metric(element) -> int:
    """Extrai número de um elemento de métrica (likes, retweets, etc.)."""
    if not element:
        return 0
    try:
        text = element.inner_text().strip()
        if not text:
            return 0
        text = text.replace(",", "").replace(".", "")
        if "K" in text.upper():
            return int(float(text.upper().replace("K", "")) * 1000)
        elif "M" in text.upper():
            return int(float(text.upper().replace("M", "")) * 1000000)
        return int(text)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Text normalization + Content fingerprint
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def normalize_tweet_text(text: str) -> str:
    """Normaliza texto do tweet para armazenar/comparar.

    - Colapsa quebras de linha dentro de URLs (bug comum no X: link
      quebrado em duas linhas no DOM, ex: 'https://\\nnehannn.com/...')
    - Colapsa whitespace múltiplo
    - Remove espaços antes de pontuação
    """
    if not text:
        return ""
    # Remontar URLs quebradas por newline (caso clássico no cache atual)
    text = re.sub(r"(https?://)\s*\n\s*", r"\1", text)
    # Colapsar demais quebras de linha em espaço
    text = text.replace("\r", " ").replace("\n", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def content_fingerprint(text: str) -> str:
    """Gera fingerprint SHA-256 normalizado para dedup de conteúdo.

    Idêntico ao _content_fingerprint do news_collector.py para que tweets e
    artigos de portais possam ser deduplicados entre si quando o pipeline
    fundir as fontes.
    """
    if not text:
        return ""
    raw = text.lower()
    # Remover acentos
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    # Remover URLs (mesmo tweet citado por handles diferentes)
    raw = _URL_RE.sub(" ", raw)
    # Só alfanumérico + espaços
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    raw = _WS_RE.sub(" ", raw).strip()
    # Truncar para focar no lead (tw=280 chars, mas multi-tweet/excerpt podem ser maiores)
    raw = raw[:280]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# TweetScorer — score de relevância + filtros
# ---------------------------------------------------------------------------

class TweetScorer:
    """Aplica filtros e calcula score de relevância por tweet.

    Decisões:
      - BLACKLIST  -> descarta sempre
      - LANGUAGE   -> descarta se não for do idioma configurado
      - IDADE      -> descarta se mais antigo que hours_lookback
      - MIN_SCORE  -> descarta se abaixo do mínimo configurado
    Tweet oficial isento de filtro de engajamento (notícia primária).
    """

    # Heurística simples para detecção de idioma — se a maioria dos chars
    # não for latina/cyrillic comum ou contiver blocos CJK, é provavelmente
    # outro idioma. Útil para bloquear o caso real do cache (japonês).
    _CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
    _LATIN_RE = re.compile(r"[A-Za-zÀ-ÿ]")

    def __init__(self, config: dict, registry: ProfileRegistry):
        self.config = config
        self.registry = registry
        settings = config["settings"]
        scoring = settings.get("scoring", {})
        self.language_filter = settings.get("language_filter", "pt")
        self.hours_lookback = settings.get("hours_lookback", 24)
        self.min_score = scoring.get("min_score_to_keep", 5)
        # min_engagement: filtro duro para tiers não-oficiais. Tweets de
        # official/media são isentos (notícia primária/secundária confiável
        # mesmo sem engajamento). Para search/watch, exige engajamento mínimo.
        self.min_engagement = settings.get("min_engagement", 3)
        self.tiers_exempt_from_engagement = {"official", "media"}

        self.weights = {
            "tier_official": scoring.get("tier_official", 100),
            "tier_media": scoring.get("tier_media", 60),
            "tier_watch": scoring.get("tier_watch", 30),
            "tier_search": scoring.get("tier_search", 10),
            "engagement_multiplier": scoring.get("engagement_multiplier", 0.5),
            "verified_bonus": scoring.get("verified_bonus", 15),
            "has_media_bonus": scoring.get("has_media_bonus", 5),
            "recent_hours_bonus_threshold": scoring.get("recent_hours_bonus_threshold", 6),
            "recent_hours_bonus": scoring.get("recent_hours_bonus", 20),
        }

        bl = config.get("blacklist", {})
        self.blacklist_handles = {h.lower() for h in bl.get("handles", [])}
        self.blacklist_keywords = [k.lower() for k in bl.get("keywords_in_text", [])]

    def filter_and_score(self, tweet: Dict[str, Any], source_tier: str = "search") -> Tuple[Optional[Dict], int, str]:
        """Filtra tweet e calcula score.

        Returns:
            (tweet_enriquecido | None, score, motivo_descarte)
            - Se descartado: tweet é None.
        """
        author = (tweet.get("author") or "").lower().strip()
        text = tweet.get("text", "")

        # 1. Blacklist por handle
        if author in self.blacklist_handles:
            return None, 0, f"blacklist handle @{author}"

        # 2. Blacklist por keyword no texto (spam de apostas etc.)
        text_lower = text.lower()
        for kw in self.blacklist_keywords:
            if kw in text_lower:
                return None, 0, f"blacklist keyword '{kw}'"

        # 3. Filtro de idioma (proteção contra ruído como japonês do cache)
        if self.language_filter and not self._passes_language(text):
            return None, 0, "idioma não-pt"

        # 4. Filtro de idade (hours_lookback)
        age_hours = self._age_hours(tweet.get("timestamp", ""))
        if age_hours is not None and age_hours > self.hours_lookback:
            return None, 0, f"idade {age_hours:.0f}h > {self.hours_lookback}h"

        # 5. Filtro de engajamento mínimo (tiers não-oficiais)
        engagement = (
            tweet.get("likes", 0)
            + tweet.get("retweets", 0) * 2
            + tweet.get("replies", 0)
        )
        if source_tier not in self.tiers_exempt_from_engagement:
            # Antes do scoring: usa o tier de coleta (search/watch). Se o autor
            # for um perfil conhecido de tier maior, será promovido no scoring
            # mas continua sujeito ao filtro de engajamento do tier de origem.
            if engagement < self.min_engagement:
                return None, 0, f"engaj {engagement} < {self.min_engagement} (tier {source_tier})"

        # --- Passou dos filtros. Calcular score ---
        # Resolve tier efetivo: se coletado via profile, usa tier do perfil;
        # mas se o autor for um perfil conhecido mesmo numa coleta de busca,
        # promove ao tier dele.
        effective_tier = source_tier
        if source_tier == "search":
            profile_tier = self.registry.tier_of(tweet.get("author", ""))
            if profile_tier:
                effective_tier = profile_tier

        score = self._base_tier_score(effective_tier)

        # Engajamento (likes + 2*retweets + replies)
        engagement = (
            tweet.get("likes", 0)
            + tweet.get("retweets", 0) * 2
            + tweet.get("replies", 0)
        )
        score += int(engagement * self.weights["engagement_multiplier"])

        # Bônus conta verificada
        if tweet.get("author_verified"):
            score += self.weights["verified_bonus"]

        # Bônus tem mídia
        if tweet.get("media_urls"):
            score += self.weights["has_media_bonus"]

        # Bônus recente (últimas N horas)
        if age_hours is not None and age_hours <= self.weights["recent_hours_bonus_threshold"]:
            score += self.weights["recent_hours_bonus"]

        # Corte final
        if score < self.min_score:
            return None, score, f"score {score} < {self.min_score}"

        tweet = dict(tweet)
        tweet["tier"] = effective_tier
        tweet["score"] = score
        tweet["engagement"] = engagement
        tweet["text"] = normalize_tweet_text(text)
        return tweet, score, ""

    def _base_tier_score(self, tier: str) -> int:
        return {
            "official": self.weights["tier_official"],
            "media": self.weights["tier_media"],
            "watch": self.weights["tier_watch"],
            "search": self.weights["tier_search"],
        }.get(tier, self.weights["tier_search"])

    def _passes_language(self, text: str) -> bool:
        """Heurística: bloqueia texto dominantemente CJK/árabe/etc.

        Para 'pt', exigimos que existam caracteres latinos e nenhum CJK
        majoritário. (Detecção de idioma leve, sem dependência extra.)
        """
        if not text:
            return True
        cjk = len(self._CJK_RE.findall(text))
        latin = len(self._LATIN_RE.findall(text))
        # Se tem CJK comparável ou maior que latim, não é português
        if cjk > 0 and cjk >= latin:
            return False
        return True

    @staticmethod
    def _age_hours(timestamp: str) -> Optional[float]:
        """Idade do tweet em horas a partir do timestamp ISO do X."""
        if not timestamp:
            return None
        try:
            # X entrega ex: "2026-06-20T20:48:43.000Z"
            ts = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            return (now - ts).total_seconds() / 3600.0
        except Exception:
            return None


# ---------------------------------------------------------------------------
# ContentDeduplicator — dedup intra-rodada + inter-sessão por fingerprint
# ---------------------------------------------------------------------------

class ContentDeduplicator:
    """Deduplicação por ID e por fingerprint de conteúdo.

    Duas camadas:
      - by_id          : tweet_id (clássico)
      - by_fingerprint : texto normalizado (mata duplicatas com IDs
                         diferentes, ex: mesmo tweet do BenitoRodPerez
                         com IDs distintos no cache atual)
    """

    def __init__(self, existing_fingerprints: Optional[Dict[str, Any]] = None):
        self._seen_ids: set = set()
        self._seen_fps: set = set()
        if existing_fingerprints:
            for fp in existing_fingerprints.keys():
                self._seen_fps.add(fp)

    def is_duplicate(self, tweet: Dict[str, Any]) -> Tuple[bool, str]:
        tid = tweet.get("tweet_id")
        if tid and tid in self._seen_ids:
            return True, "id"
        fp = content_fingerprint(tweet.get("text", ""))
        if fp and fp in self._seen_fps:
            return True, "content"
        return False, ""

    def mark_seen(self, tweet: Dict[str, Any]):
        if tweet.get("tweet_id"):
            self._seen_ids.add(tweet["tweet_id"])
        fp = content_fingerprint(tweet.get("text", ""))
        if fp:
            self._seen_fps.add(fp)


# ---------------------------------------------------------------------------
# TweetCache — persistência rotativa com TTL
# ---------------------------------------------------------------------------

class TweetCache:
    """Wrapper do cache de tweets com rotação por TTL."""

    def __init__(self, config: dict):
        self.config = config
        settings = config["settings"]
        self.ttl_days = settings.get("cache_ttl_days", 7)
        self.max_ids = settings.get("max_collected_ids_kept", 5000)
        self.data = load_tweet_cache()

    def _prune_expired(self):
        """Remove tweets mais antigos que TTL e IDs correspondentes."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=self.ttl_days)
        kept_tweets = []
        for t in self.data.get("tweets", []):
            ts = t.get("timestamp") or t.get("collected_at", "")
            try:
                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= cutoff:
                    kept_tweets.append(t)
            except Exception:
                kept_tweets.append(t)  # Sem data parseável, mantém por segurança
        removed = len(self.data.get("tweets", [])) - len(kept_tweets)
        if removed:
            log.info(f"🧹 Cache: removidos {removed} tweets expirados (TTL {self.ttl_days}d)")
        self.data["tweets"] = kept_tweets

    def _trim_collected_ids(self):
        ids = self.data.get("collected_ids", [])
        if len(ids) > self.max_ids:
            # Mantém apenas os mais recentes (assumindo append em ordem temporal)
            self.data["collected_ids"] = ids[-self.max_ids:]
            log.debug(f"Cache: trimmed collected_ids para {self.max_ids}")

    def existing_fingerprints(self) -> Dict[str, Any]:
        return self.data.get("content_fingerprints", {})

    def existing_ids(self) -> set:
        return set(self.data.get("collected_ids", []))

    def save_new(self, new_tweets: List[Dict[str, Any]], dedup: ContentDeduplicator):
        """Persiste novos tweets, atualiza fingerprint/IDs e contador de sessão."""
        today = datetime.date.today().isoformat()

        if self.data.get("last_session_date") != today:
            self.data["sessions_today"] = 0
            self.data["last_session_date"] = today

        self.data["sessions_today"] = (self.data.get("sessions_today") or 0) + 1
        self.data["last_collection"] = datetime.datetime.now().isoformat()

        # Reconstrói fingerprints do estado atual dos tweets (pode ter sido
        # podado pelo TTL) para evitar colisão com tweets ainda vivos.
        live_fps = {
            content_fingerprint(t.get("text", "")): {
                "tweet_id": t.get("tweet_id"),
                "author": t.get("author"),
                "first_seen": t.get("collected_at"),
            }
            for t in self.data.get("tweets", [])
            if t.get("text")
        }

        existing_ids = set(self.data.get("collected_ids", []))
        for tweet in new_tweets:
            tid = tweet.get("tweet_id")
            if tid and tid in existing_ids:
                continue
            if tid:
                existing_ids.add(tid)
            self.data["tweets"].append(tweet)
            fp = content_fingerprint(tweet.get("text", ""))
            if fp and fp not in live_fps:
                live_fps[fp] = {
                    "tweet_id": tid,
                    "author": tweet.get("author"),
                    "first_seen": tweet.get("collected_at"),
                }

        self.data["collected_ids"] = list(existing_ids)
        self.data["content_fingerprints"] = live_fps

        self._trim_collected_ids()
        self._prune_expired()

        save_tweet_cache(self.data)
        log.info(
            f"💾 Cache salvo: +{len(new_tweets)} tweets | "
            f"total acumulado: {len(self.data['tweets'])} | "
            f"sessões hoje: {self.data['sessions_today']}"
        )


# ---------------------------------------------------------------------------
# Coletores
# ---------------------------------------------------------------------------

class XSearchCollector:
    """Busca tweets por termos-chave no X usando operadores avançados."""

    def __init__(self, browser: XStealthBrowser, config: dict,
                 registry: ProfileRegistry, query_builder: QueryBuilder):
        self.browser = browser
        self.config = config
        self.settings = config["settings"]
        self.registry = registry
        self.query_builder = query_builder

    def search_term(self, term: str, dedup: ContentDeduplicator,
                    scorer: TweetScorer, max_tweets: int = None) -> List[Dict]:
        """Busca um termo no X e retorna tweets válidos (filtrados+scored)."""
        if max_tweets is None:
            max_tweets = self.settings["max_tweets_per_search"]

        query, search_url = self.query_builder.build(term)
        log.info(f"  🔍 Buscando: \"{term}\"")
        log.info(f"     query: {query}")
        log.info(f"     alvo: até {max_tweets} tweets")

        collected: List[Dict] = []

        try:
            self.browser.page.goto(search_url, wait_until="commit", timeout=60000)
            self.browser._human_delay(3, 6)

            try:
                self.browser.page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
            except Exception:
                log.warning(f"  ⚠️  Nenhum resultado para \"{term}\"")
                return []

            scroll_attempts = 0
            max_scroll_attempts = 5
            discarded = 0

            while len(collected) < max_tweets and scroll_attempts < max_scroll_attempts:
                tweet_elements = self.browser.page.query_selector_all('[data-testid="tweet"]')

                for el in tweet_elements:
                    if len(collected) >= max_tweets:
                        break
                    raw = parse_tweet_element(el)
                    if not raw:
                        continue

                    scored, score, reason = scorer.filter_and_score(raw, source_tier="search")
                    if not scored:
                        discarded += 1
                        continue

                    is_dup, _ = dedup.is_duplicate(scored)
                    if is_dup:
                        continue

                    scored["source_type"] = "search"
                    scored["search_term"] = term
                    scored["collected_at"] = datetime.datetime.now().isoformat()
                    dedup.mark_seen(scored)
                    collected.append(scored)

                self.browser._random_scroll("down")
                self.browser._maybe_distraction()
                scroll_attempts += 1

                new_elements = self.browser.page.query_selector_all('[data-testid="tweet"]')
                if len(new_elements) == len(tweet_elements):
                    log.debug(f"  Sem novos tweets após scroll #{scroll_attempts}")
                    break

            log.info(f"  ✅ \"{term}\": {len(collected)} tweets válidos (descartados por filtro: {discarded})")
            return collected

        except Exception as e:
            log.error(f"  ❌ Erro na busca \"{term}\": {e}")
            return []

    def collect_all(self, terms: List[str], dedup: ContentDeduplicator,
                    scorer: TweetScorer) -> List[Dict]:
        if terms is None:
            terms = self.config.get("search_terms", [])

        all_tweets: List[Dict] = []
        delays = self.settings["delay_between_searches_sec"]

        for i, term in enumerate(terms):
            tweets = self.search_term(term, dedup, scorer)
            all_tweets.extend(tweets)
            if i < len(terms) - 1:
                delay = random.uniform(delays[0], delays[1])
                log.info(f"  ⏳ Aguardando {delay:.0f}s antes da próxima busca...")
                time.sleep(delay)

        log.info(f"📊 Total busca por termos: {len(all_tweets)} tweets de {len(terms)} termos")
        return all_tweets


class XProfileCollector:
    """Coleta tweets recentes de perfis específicos, iterando por tier."""

    def __init__(self, browser: XStealthBrowser, config: dict,
                 registry: ProfileRegistry):
        self.browser = browser
        self.config = config
        self.settings = config["settings"]
        self.registry = registry

    def fetch_profile(self, username: str, tier: str,
                      dedup: ContentDeduplicator, scorer: TweetScorer) -> List[Dict]:
        """Navega até o perfil e coleta tweets recentes."""
        max_tweets = self.settings.get(
            "max_tweets_per_profile_official" if tier == "official"
            else "max_tweets_per_profile",
            self.settings.get("max_tweets_per_profile", 10),
        )
        log.info(f"  👤 @{username} [tier={tier}] (máx: {max_tweets})")

        try:
            profile_url = f"https://x.com/{username}"
            self.browser.page.goto(profile_url, wait_until="commit", timeout=60000)
            self.browser._human_delay(3, 6)

            try:
                self.browser.page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
            except Exception:
                page_text = self.browser.page.inner_text("body")
                low = page_text.lower()
                if "doesn't exist" in low or "não existe" in low:
                    log.warning(f"  ⚠️  Perfil @{username} não existe")
                elif "protected" in low or "protegido" in low:
                    log.warning(f"  ⚠️  Perfil @{username} é protegido/privado")
                else:
                    log.warning(f"  ⚠️  Sem tweets visíveis para @{username}")
                return []

            collected: List[Dict] = []
            scroll_attempts = 0
            max_scroll_attempts = 3
            discarded = 0

            while len(collected) < max_tweets and scroll_attempts < max_scroll_attempts:
                tweet_elements = self.browser.page.query_selector_all('[data-testid="tweet"]')

                for el in tweet_elements:
                    if len(collected) >= max_tweets:
                        break
                    raw = parse_tweet_element(el)
                    if not raw:
                        continue

                    scored, score, reason = scorer.filter_and_score(raw, source_tier=tier)
                    if not scored:
                        discarded += 1
                        continue

                    is_dup, _ = dedup.is_duplicate(scored)
                    if is_dup:
                        continue

                    scored["source_type"] = "profile"
                    scored["search_term"] = None
                    scored["collected_at"] = datetime.datetime.now().isoformat()
                    dedup.mark_seen(scored)
                    collected.append(scored)

                self.browser._random_scroll("down")
                scroll_attempts += 1

                new_elements = self.browser.page.query_selector_all('[data-testid="tweet"]')
                if len(new_elements) == len(tweet_elements):
                    break

            log.info(f"  ✅ @{username}: {len(collected)} tweets (descartados: {discarded})")
            return collected

        except Exception as e:
            log.error(f"  ❌ Erro ao coletar @{username}: {e}")
            return []

    def collect_all(self, profiles: List[str], dedup: ContentDeduplicator,
                    scorer: TweetScorer) -> List[Dict]:
        """Itera sobre perfis — ou lista fornecida, ou todos os tiers em ordem."""
        all_tweets: List[Dict] = []
        delays = self.settings["delay_between_searches_sec"]

        if profiles is not None:
            targets = [(h, self.registry.tier_of(h) or "watch") for h in profiles]
        else:
            targets = []
            for tier in ("official", "media", "watch"):
                for h in self.registry.handles_by_tier(tier):
                    targets.append((h, tier))

        for i, (handle, tier) in enumerate(targets):
            tweets = self.fetch_profile(handle, tier, dedup, scorer)
            all_tweets.extend(tweets)
            if i < len(targets) - 1:
                delay = random.uniform(delays[0], delays[1])
                log.info(f"  ⏳ Aguardando {delay:.0f}s antes do próximo perfil...")
                time.sleep(delay)

        log.info(f"📊 Total perfis: {len(all_tweets)} tweets de {len(targets)} perfis")
        return all_tweets


# ---------------------------------------------------------------------------
# Função de consumo para o pipeline
# ---------------------------------------------------------------------------

def consume_x_tweets_for_pipeline() -> List[Dict]:
    """Consome tweets acumulados do cache e converte para formato de artigo.

    IMPORTANTE (fix do bug v1.0): NÃO zera mais `collected_ids` nem
    `content_fingerprints` — apenas remove da fila `tweets`. Assim um tweet
    já coletado não volta a entrar na próxima rodada.
    """
    cache_data = load_tweet_cache()
    tweets = cache_data.get("tweets", [])

    if not tweets:
        log.info("📱 Nenhum tweet do X no cache para consumir")
        return []

    # Ordenar por score decrescente para que o filtro de IA veja os melhores 1º
    tweets_sorted = sorted(tweets, key=lambda t: t.get("score", 0), reverse=True)

    articles = []
    for tweet in tweets_sorted:
        engagement = t_engagement(tweet)

        content_parts = [tweet.get("text", "")]
        tier = tweet.get("tier", "search")
        if tier == "official":
            content_parts.append("[FONTE OFICIAL]")
        elif tier == "media":
            content_parts.append("[VEÍCULO DE IMPRENSA]")
        if tweet.get("author_verified"):
            content_parts.append("[Conta Verificada]")
        content_parts.append(
            f"[Engajamento: {engagement} | likes: {tweet.get('likes', 0)} | RTs: {tweet.get('retweets', 0)} | score: {tweet.get('score', 0)}]"
        )
        if tweet.get("search_term"):
            content_parts.append(f"[Encontrado via busca: \"{tweet['search_term']}\"]")
        if tweet.get("source_type") == "profile":
            content_parts.append(f"[Perfil monitorado: @{tweet.get('author', '')} ({tier})]")

        article = {
            "title": f"[X/@{tweet.get('author', 'unknown')}] {tweet.get('text', '')[:120]}",
            "link": f"https://x.com/{tweet.get('author', 'unknown')}/status/{tweet.get('tweet_id', '')}",
            "published": tweet.get("timestamp") or tweet.get("collected_at", ""),
            "content": " | ".join(content_parts),
            "source_id": "x_twitter",
        }
        articles.append(article)

    # Consumir: esvaziar fila mas PRESERVAR collected_ids/fingerprints
    cache_data["tweets"] = []
    cache_data["last_consumed_at"] = datetime.datetime.now().isoformat()
    save_tweet_cache(cache_data)

    log.info(f"📱 {len(articles)} tweets do X convertidos para formato pipeline (collected_ids preservado)")
    return articles


def t_engagement(tweet: Dict[str, Any]) -> int:
    return (
        tweet.get("likes", 0)
        + tweet.get("retweets", 0) * 2
        + tweet.get("replies", 0)
    )


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def run_collection(
    mode: str = "full",
    terms: List[str] = None,
    profiles: List[str] = None,
    dry_run: bool = False,
    headless: bool = True
):
    """Executa a coleta do X conforme o modo especificado."""
    config = load_x_config()
    settings = config["settings"]
    registry = ProfileRegistry(config)
    cache = TweetCache(config)

    # Verificar limite de sessões diárias
    today = datetime.date.today().isoformat()
    if cache.data.get("last_session_date") == today:
        sessions_today = cache.data.get("sessions_today", 0)
        max_sessions = settings.get("max_sessions_per_day", 4)
        if sessions_today >= max_sessions:
            log.warning(f"⚠️  Limite de sessões diárias atingido ({sessions_today}/{max_sessions}). Abortando.")
            log.info("   Dica: aumente 'max_sessions_per_day' em x_config.json se necessário.")
            return

    log.info(f"🚀 Iniciando coleta do X (modo: {mode}, dry_run: {dry_run})")
    log.info(f"   Sessões hoje: {cache.data.get('sessions_today', 0)}/{settings.get('max_sessions_per_day', 4)}")
    log.info(f"   Perfis: {registry.summary()}")

    # Modo login-only
    if mode == "login-only":
        browser = XStealthBrowser(config, headless=False)  # Mostrar browser para login
        browser.launch()
        try:
            success = browser.login()
            if success:
                log.info("✅ Login realizado e cookies salvos!")
            else:
                log.error("❌ Login falhou")
        finally:
            browser.close()
        return

    # Instanciar helpers de scoring/dedup compartilhados
    scorer = TweetScorer(config, registry)
    dedup = ContentDeduplicator(existing_fingerprints=cache.existing_fingerprints())

    # Modos de coleta
    browser = XStealthBrowser(config, headless=headless)
    browser.launch()

    try:
        if not browser.ensure_logged_in():
            log.error("❌ Não foi possível autenticar no X. Abortando coleta.")
            return

        all_tweets: List[Dict] = []

        # Busca por termos
        if mode in ("full", "search"):
            log.info("═" * 50)
            log.info("📋 FASE 1: Busca por termos-chave")
            log.info("═" * 50)
            search_collector = XSearchCollector(browser, config, registry, QueryBuilder(config))
            all_tweets.extend(search_collector.collect_all(terms, dedup, scorer))

            if mode == "full":
                pause = random.uniform(20, 40)
                log.info(f"⏳ Pausa entre fases: {pause:.0f}s")
                time.sleep(pause)

        # Monitoramento de perfis
        if mode in ("full", "profiles"):
            log.info("═" * 50)
            log.info("👥 FASE 2: Monitoramento de perfis")
            log.info("═" * 50)
            profile_collector = XProfileCollector(browser, config, registry)
            all_tweets.extend(profile_collector.collect_all(profiles, dedup, scorer))

        # Salvar cookies atualizados
        browser.save_cookies()

        # Resumo
        log.info("═" * 50)
        log.info("📊 RESUMO DA COLETA")
        log.info("═" * 50)
        log.info(f"Total coletado (pós-filtro/score): {len(all_tweets)} tweets")

        # Distribuição por tier
        tier_counts: Dict[str, int] = {}
        for t in all_tweets:
            tier_counts[t.get("tier", "?")] = tier_counts.get(t.get("tier", "?"), 0) + 1
        for tier in TIER_ORDER:
            if tier_counts.get(tier):
                log.info(f"   {tier:8s}: {tier_counts[tier]}")

        # Ordenar por score (debug melhor)
        all_tweets.sort(key=lambda t: t.get("score", 0), reverse=True)

        if dry_run:
            log.info("🔍 [DRY-RUN] Top tweets que seriam salvos:")
            for t in all_tweets[:15]:
                log.info(
                    f"  [{t.get('tier', '?'):8s}] score={t.get('score', 0):4d} @{t.get('author', '?')}: "
                    f"{t.get('text', '')[:80]}..."
                )
            if len(all_tweets) > 15:
                log.info(f"  ... e mais {len(all_tweets) - 15} tweets")
        else:
            if all_tweets:
                cache.save_new(all_tweets, dedup)
            else:
                log.info("Nenhum tweet novo para salvar.")
                # Atualizar contador de sessão mesmo sem novos tweets
                if cache.data.get("last_session_date") != today:
                    cache.data["sessions_today"] = 1
                    cache.data["last_session_date"] = today
                else:
                    cache.data["sessions_today"] = (cache.data.get("sessions_today") or 0) + 1
                cache.data["last_collection"] = datetime.datetime.now().isoformat()
                save_tweet_cache(cache.data)

    finally:
        browser.close()

    log.info("✅ Coleta do X finalizada!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Coletor do X (Twitter) — Web Jornal Vale da Liberdade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modos:
  full         Busca por termos + perfis (padrão)
  search       Apenas busca por termos-chave
  profiles     Apenas monitoramento de perfis
  login-only   Apenas fazer login e salvar cookies
  status       Mostra status do cache atual

Exemplos:
  python x_collector.py --mode full
  python x_collector.py --mode search --terms "Blumenau" "BR-470"
  python x_collector.py --mode profiles --profiles "PrefBlumenau"
  python x_collector.py --mode full --dry-run
  python x_collector.py --mode login-only
  python x_collector.py --mode status
        """
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["full", "search", "profiles", "login-only", "status"],
        default="full",
        help="Modo de operação (padrão: full)"
    )
    parser.add_argument(
        "--terms", "-t",
        nargs="+",
        help="Termos de busca específicos (sobrescreve x_config.json)"
    )
    parser.add_argument(
        "--profiles", "-p",
        nargs="+",
        help="Perfis específicos para monitorar (sobrescreve x_config.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria coletado sem salvar"
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Mostra o browser durante a coleta (headless=False)"
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        help="Número máximo de tweets por busca/perfil"
    )
    args = parser.parse_args()

    # Modo status
    if args.mode == "status":
        cache = load_tweet_cache()
        config = load_x_config()
        registry = ProfileRegistry(config)
        print("\n📊 Status do Coletor do X (schema 2.0)")
        print("═" * 50)
        print(f"  Schema:            {cache.get('schema_version', '?')}")
        print(f"  Última coleta:     {cache.get('last_collection', 'nunca')}")
        print(f"  Sessões hoje:      {cache.get('sessions_today', 0)}/{config['settings']['max_sessions_per_day']}")
        print(f"  Tweets na fila:    {len(cache.get('tweets', []))}")
        print(f"  IDs no cache:      {len(cache.get('collected_ids', []))}")
        print(f"  Fingerprints:      {len(cache.get('content_fingerprints', {}))}")
        print(f"  Termos config.:    {len(config.get('search_terms', []))}")
        print(f"  Perfis:            {registry.summary()}")

        tweets = cache.get("tweets", [])
        if tweets:
            print(f"\n  📝 Top tweets por score:")
            sorted_t = sorted(tweets, key=lambda t: t.get("score", 0), reverse=True)
            for t in sorted_t[:5]:
                print(
                    f"    [{t.get('tier', '?'):8s}] s={t.get('score', 0):4d} "
                    f"@{t.get('author', '?')}: {t.get('text', '')[:60]}..."
                )
        print()
        return

    # Atualizar max_tweets se especificado
    if args.max_tweets:
        config = load_x_config()
        config["settings"]["max_tweets_per_search"] = args.max_tweets
        config["settings"]["max_tweets_per_profile"] = args.max_tweets
        # Reescrever config em memória não persiste — por simplicidade,
        # passamos via argparse para o orquestrador? Mantemos workaround:
        # como o orquestrador recarrega o config, aplicamos em memória
        # através de variável de módulo.
        global _OVERRIDE_MAX_TWEETS
        _OVERRIDE_MAX_TWEETS = args.max_tweets

    run_collection(
        mode=args.mode,
        terms=args.terms,
        profiles=args.profiles,
        dry_run=args.dry_run,
        headless=not args.show_browser
    )


# Override opcional de max_tweets vindo do CLI (evita regravar config)
_OVERRIDE_MAX_TWEETS: Optional[int] = None


if __name__ == "__main__":
    main()
