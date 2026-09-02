"""Registry de scrapers por domínio com auto-descoberta automática de módulos.

Cada módulo em ``sites/`` registra seus domínios usando o decorador ``@register("dominio.com")``.
O ``sites/__init__.py`` descobre e importa dinamicamente todos os módulos ``sites/*.py``,
portanto ao criar um novo site basta criar o arquivo em ``sites/`` sem precisar editar o ``__init__.py``.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.screenshots.base import BaseScraper

# Mapa domínio → classe do scraper (preenchido por register()).
_REGISTRY: dict[str, type] = {}


def register(*domains: str):
    """Decorador que registra uma classe de scraper para um ou mais domínios.

    Uso::

        @register("g1.globo.com", "globo.com")
        class G1Scraper(BaseScraper):
            ...
    """
    def _decorator(cls: type) -> type:
        for d in domains:
            _REGISTRY[d.lower().removeprefix("www.")] = cls
        return cls
    return _decorator


def get_scraper(domain: str) -> "BaseScraper | None":
    """Retorna instância do scraper registrado para o domínio, ou None.

    Casa o host exato primeiro e depois sobe os pais (ex.: ``economia.uol.com.br``
    → ``uol.com.br``). Assim um registro em ``uol.com.br`` cobre subdomínios
    sem roubar handlers mais específicos (``folha.uol.com.br``, ``piaui.uol.com.br``).
    """
    key = domain.lower().removeprefix("www.")
    if not key:
        return None
    parts = key.split(".")
    candidates = [".".join(parts[i:]) for i in range(0, max(len(parts) - 1, 1))]
    for cand in candidates:
        cls = _REGISTRY.get(cand)
        if cls is not None:
            return cls()
    return None


def list_registered() -> list[str]:
    """Lista todos os domínios registrados."""
    return sorted(_REGISTRY.keys())


# ---- Auto-import dinâmico de todos os módulos de sites --------------------
# Varre a pasta sites/ e importa todos os arquivos .py (exceto os que começam com _)
# garantindo que todos os decoradores @register rodem automaticamente.

_sites_dir = Path(__file__).parent
for _, _mod_name, _ in pkgutil.iter_modules([str(_sites_dir)]):
    if not _mod_name.startswith("_"):
        importlib.import_module(f".{_mod_name}", package=__name__)
