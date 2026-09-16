#!/usr/bin/env python3
"""Módulo de detecção e tradução automática de tweets/posts de redes sociais.

Garante que publicações em idiomas estrangeiros (inglês, espanhol, etc.) sejam
traduzidas para português do Brasil com qualidade jornalística antes de serem
enviadas ao mockup de vídeo.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

logger = logging.getLogger("bm-video-translation")

CACHE_PATH = ROOT / "output" / "brasil_e_mundo" / "x_translations_cache.json"

# Palavras marcadoras distintivas do português
PT_STOPWORDS = {
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "por", "pelo", "pela", "pelos", "pelas", "com", "para", "uma", "um",
    "umas", "uns", "não", "este", "esta", "estes", "estas", "esse", "essa",
    "esses", "essas", "aquele", "aquela", "aqueles", "aquelas", "isso", "isto",
    "aquilo", "está", "estão", "estava", "estavam", "são", "era", "foram", "foi",
    "mais", "como", "sobre", "governo", "brasil", "brasileiro", "brasileira",
    "segundo", "deputado", "senador", "ministro", "stf", "porque", "porquê",
    "então", "também", "qualquer", "onde", "quando", "entre", "após", "muito",
    "muitos", "muita", "muitas", "mesmo", "mesma", "nesta", "neste", "disse",
    "hoje", "ontem", "nacional", "justiça", "decisão", "eleição", "projeto"
}

# Palavras marcadoras distintivas do inglês
EN_STOPWORDS = {
    "the", "is", "are", "was", "were", "and", "of", "to", "in", "that", "for",
    "on", "with", "as", "this", "by", "from", "they", "at", "be", "have", "has",
    "had", "not", "what", "all", "we", "when", "your", "can", "said", "there",
    "use", "which", "she", "how", "their", "will", "would", "about", "out",
    "breaking", "today", "official", "statement", "president", "court", "bill",
    "law", "news", "people", "state", "senate", "house", "border", "federal"
}

# Palavras marcadoras que NUNCA existem em português (exclusivas do espanhol)
ES_EXCLUSIVE_WORDS = {
    "el", "del", "al", "hoy", "muy", "pero", "ahora", "hace", "hizo", "cuando",
    "tambien", "gobierno", "donde", "quien", "año", "años", "despues", "aqui",
    "estos", "estas", "nuestra", "nuestro", "todos", "todas", "bueno", "buena"
}


def _load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Falha ao ler cache de tradução {CACHE_PATH}: {exc}")
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Falha ao salvar cache de tradução {CACHE_PATH}: {exc}")


def is_portuguese(text: str) -> bool:
    """Verifica se o texto já está em língua portuguesa."""
    t = (text or "").strip()
    if not t:
        return True

    # 1. Caracteres distintivos fortes do português (ç, ã, õ, à, ê, ô)
    # Espanhol NUNCA tem 'ã', 'õ', 'ê', 'ô', 'à', 'ç'
    has_pt_exclusive_chars = bool(re.search(r"[ãõêôàçÃÕÊÔÀÇ]", t))
    has_es_exclusive_chars = bool(re.search(r"[ñ¿¡Ñ]", t))

    if has_es_exclusive_chars and not has_pt_exclusive_chars:
        return False

    # Extrai tokens alfanuméricos minúsculos
    words = re.findall(r"\b[a-zA-ZáàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇñÑ]+\b", t.lower())
    if not words:
        return True

    # Termos 100% espanhóis ("el presidente", "del gobierno", "hoy", etc.)
    es_strict_hits = sum(1 for w in words if w in ES_EXCLUSIVE_WORDS)
    if es_strict_hits >= 1 and not has_pt_exclusive_chars:
        # Se tem 'el' ou 'del' ou 'hoy' e não tem nenhum caractere exclusivo do PT, é espanhol
        return False

    pt_hits = sum(1 for w in words if w in PT_STOPWORDS)
    en_hits = sum(1 for w in words if w in EN_STOPWORDS)
    es_hits = es_strict_hits

    # Se contém caracteres exclusivos do português e não tem palavras estritas em espanhol
    if has_pt_exclusive_chars and es_strict_hits == 0:
        return True

    # Se há predominância clara de inglês
    if en_hits >= 2 and en_hits > pt_hits:
        return False

    # Se há predominância de espanhol
    if es_hits >= 1 and not has_pt_exclusive_chars:
        return False

    # Se mais de 1 termo típico do português estiver presente
    if pt_hits >= 2 and pt_hits >= en_hits:
        return True

    # Para textos curtos: se tiver inglês explícito
    if en_hits >= 1 and pt_hits == 0:
        return False

    # Default: se não identificado como estrangeiro, assume português
    return True


def translate_to_portuguese(text: str) -> tuple[str, bool]:
    """Traduz texto estrangeiro para português brasileiro.

    Retorna tupla (texto_final, foi_traduzido).
    """
    clean = (text or "").strip()
    if not clean or len(clean) < 4:
        return clean, False

    # Remove URLs antes de testar idioma para evitar falso positivo
    clean_no_urls = re.sub(r"https?://\S+", "", clean).strip()
    if not clean_no_urls:
        return clean, False

    if is_portuguese(clean_no_urls):
        return clean, False

    # Consulta o cache local
    cache_key = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    cache = _load_cache()
    if cache_key in cache:
        cached_val = cache[cache_key]
        if cached_val and cached_val != clean:
            return cached_val, True

    prompt = (
        "Você é um editor sênior de jornalismo internacional.\n"
        "Traduza a seguinte postagem de rede social/tweet para o português brasileiro "
        "com tom jornalístico, direto e natural.\n"
        "Diretrizes estritas:\n"
        "- Mantenha nomes próprios, menções (@handle), hashtags (#), links e números exatamente como estão.\n"
        "- Não adicione aspas ao redor da resposta.\n"
        "- Retorne APENAS o texto traduzido final, sem introdução ou explicações.\n\n"
        f"{clean}"
    )

    try:
        from youtube_captions import _gemini_text
        translated = _gemini_text(prompt)
        translated = (translated or "").strip()
        # Remove aspas externas se o modelo colocou
        if translated.startswith('"') and translated.endswith('"') and len(translated) > 2:
            translated = translated[1:-1].strip()

        if translated and translated != clean:
            cache[cache_key] = translated
            _save_cache(cache)
            logger.info(f"  🌐 Tweet traduzido com sucesso: '{clean[:40]}...' → '{translated[:40]}...'")
            return translated, True
    except Exception as exc:
        logger.warning(f"  ⚠️  Tradução Gemini falhou para o tweet: {exc}")

    return clean, False


def enrich_x_post_translation(x_post: dict) -> dict:
    """Enriquece o dicionário x_post garantindo que o texto esteja em português."""
    xp = dict(x_post or {})
    text = xp.get("text") or xp.get("content") or ""
    if not text:
        return xp

    # Se já passou por tradução prévia e possui original_text
    if xp.get("is_translated") is True and xp.get("original_text"):
        return xp

    translated, was_translated = translate_to_portuguese(text)
    if was_translated:
        xp["original_text"] = text
        xp["text"] = translated
        xp["is_translated"] = True
    else:
        xp["is_translated"] = False

    return xp
