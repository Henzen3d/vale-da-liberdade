"""screenshots — Sistema modular de captura limpa de portais de notícias.

Cada site tem seu próprio handler em ``sites/<dominio>.py`` com lógica
cirúrgica para remoção de paywall, anúncios e overlays.  O ``runner.py``
despacha qualquer URL para o handler correto (ou fallback genérico).

Uso rápido::

    python -m scripts.screenshots.runner --url "https://www.estadao.com.br/..."

"""
from __future__ import annotations


def capture(*args, **kwargs):
    """Atalho para ``scripts.screenshots.runner.capture``."""
    from .runner import capture as _capture
    return _capture(*args, **kwargs)
