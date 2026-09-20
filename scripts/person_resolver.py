#!/usr/bin/env python3
"""
Módulo de Resolução de Personagens e Imagens de Matérias (Etapa 2).

- Mantém catálogo e cache local em references/figures/<slug>.jpg
- Identifica menções a figuras políticas/econômicas no roteiro
- Fornece payload contextual para o componente person-photo com Ken Burns
- Extrai og:image de páginas de notícias como evidência contextual
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("person_resolver")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT_ROOT / "references" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ValeDaLiberdade/1.0"

PERSON_CATALOG: list[dict[str, Any]] = [
    {
        "slug": "donald-trump",
        "name": "Donald Trump",
        "wiki_title": "Donald_Trump",
        "wiki_lang": "en",
        "patterns": [re.compile(r'\b(?:donald\s+)?trump\b', re.I | re.U)],
        "role": "Presidente dos Estados Unidos",
    },
    {
        "slug": "alexandre-de-moraes",
        "name": "Alexandre de Moraes",
        "wiki_title": "Alexandre_de_Moraes",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:alexandre\s+de\s+)?moraes\b|\bxandão\b', re.I | re.U)],
        "role": "Ministro do STF",
    },
    {
        "slug": "lula",
        "name": "Luiz Inácio Lula da Silva",
        "wiki_title": "Luiz_In%C3%A1cio_Lula_da_Silva",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:presidente\s+)?lula\b', re.I | re.U)],
        "role": "Presidente do Brasil",
    },
    {
        "slug": "fernando-haddad",
        "name": "Fernando Haddad",
        "wiki_title": "Fernando_Haddad",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:fernando\s+)?haddad\b', re.I | re.U)],
        "role": "Ministro da Fazenda",
    },
    {
        "slug": "javier-milei",
        "name": "Javier Milei",
        "wiki_title": "Javier_Milei",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:javier\s+)?milei\b', re.I | re.U)],
        "role": "Presidente da Argentina",
    },
    {
        "slug": "elon-musk",
        "name": "Elon Musk",
        "wiki_title": "Elon_Musk",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:elon\s+)?musk\b', re.I | re.U)],
        "role": "Empresário e Líder Tecnológico",
    },
    {
        "slug": "jerome-powell",
        "name": "Jerome Powell",
        "wiki_title": "Jerome_Powell",
        "wiki_lang": "en",
        "patterns": [re.compile(r'\b(?:jerome\s+)?powell\b', re.I | re.U)],
        "role": "Presidente do Federal Reserve",
    },
    {
        "slug": "gabriel-galipolo",
        "name": "Gabriel Galípolo",
        "wiki_title": "Gabriel_Gal%C3%ADpolo",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:gabriel\s+)?galípolo\b|\bgalipolo\b', re.I | re.U)],
        "role": "Presidente do Banco Central",
    },
    {
        "slug": "roberto-campos-neto",
        "name": "Roberto Campos Neto",
        "wiki_title": "Roberto_Campos_Neto",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:roberto\s+)?campos\s+neto\b', re.I | re.U)],
        "role": "Economista e Ex-Presidente do BC",
    },
    {
        "slug": "tarcisio-de-freitas",
        "name": "Tarcísio de Freitas",
        "wiki_title": "Tarc%C3%ADsio_de_Freitas",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:tarcísio|tarcisio)(?:\s+de\s+freitas)?\b', re.I | re.U)],
        "role": "Governador de São Paulo",
    },
    {
        "slug": "jair-bolsonaro",
        "name": "Jair Bolsonaro",
        "wiki_title": "Jair_Bolsonaro",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:jair\s+)?bolsonaro\b', re.I | re.U)],
        "role": "Ex-Presidente do Brasil",
    },
    {
        "slug": "flavio-dino",
        "name": "Flávio Dino",
        "wiki_title": "Fl%C3%A1vio_Dino",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:flávio|flavio)\s+dino\b', re.I | re.U)],
        "role": "Ministro do STF",
    },
    {
        "slug": "gilmar-mendes",
        "name": "Gilmar Mendes",
        "wiki_title": "Gilmar_Mendes",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:gilmar\s+)?mendes\b', re.I | re.U)],
        "role": "Ministro do STF",
    },
    {
        "slug": "luis-roberto-barroso",
        "name": "Luís Roberto Barroso",
        "wiki_title": "Lu%C3%ADs_Roberto_Barroso",
        "wiki_lang": "pt",
        "patterns": [re.compile(r'\b(?:luís|luis)?\s*roberto\s+barroso\b', re.I | re.U)],
        "role": "Presidente do STF",
    },
]


def get_figure_image_path(slug: str) -> Path:
    """Retorna o caminho local esperado da foto da figura."""
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        cand = FIGURES_DIR / f"{slug}{ext}"
        if cand.is_file() and cand.stat().st_size > 5000:
            return cand
    return FIGURES_DIR / f"{slug}.jpg"


def download_figure_portrait(slug: str, wiki_title: str, lang: str = "pt") -> Path | None:
    """Baixa o retrato oficial da Wikimedia se ainda não existir localmente."""
    dest = FIGURES_DIR / f"{slug}.jpg"
    if dest.is_file() and dest.stat().st_size > 5000:
        return dest

    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        f"action=query&titles={wiki_title}&prop=pageimages&format=json&pithumbsize=1000"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for _, page in pages.items():
                thumb_url = page.get("thumbnail", {}).get("source")
                if thumb_url:
                    img_req = urllib.request.Request(thumb_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                        content = img_resp.read()
                        if len(content) > 5000:
                            dest.write_bytes(content)
                            log.info("Foto de %s baixada com sucesso (%d KB)", slug, len(content) // 1024)
                            return dest
    except Exception as exc:
        log.warning("Falha ao baixar retrato de %s da Wikimedia: %s", slug, exc)
    return None


def resolve_person_for_text(text: str, auto_download: bool = True) -> dict[str, Any] | None:
    """Detecta menção a uma personalidade do catálogo no texto e retorna os dados de person-photo."""
    if not text:
        return None

    for entry in PERSON_CATALOG:
        for pat in entry["patterns"]:
            if pat.search(text):
                slug = entry["slug"]
                photo_path = get_figure_image_path(slug)
                if not photo_path.is_file() and auto_download:
                    photo_path = download_figure_portrait(
                        slug,
                        entry["wiki_title"],
                        entry.get("wiki_lang", "pt"),
                    )

                if photo_path and photo_path.is_file() and photo_path.stat().st_size > 5000:
                    return {
                        "slug": slug,
                        "name": entry["name"],
                        "role": entry.get("role", "Figura Pública"),
                        "photo_path": photo_path,
                        "photo_src": str(photo_path.resolve()),
                        "photo": f"/shots/figure-{photo_path.name}",
                        "tag": "PERSONAGEM EM FOCO",
                        "veiculo": "Arquivo / Imprensa Oficial",
                    }
    return None


def extract_og_image_from_url(url: str, timeout: int = 8) -> str | None:
    """Extrai a URL da imagem de destaque (og:image / twitter:image) de uma matéria jornalística."""
    if not url or not url.startswith("http"):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_html = resp.read(131072).decode("utf-8", errors="ignore")
            # 1. og:image
            m = re.search(r'<meta[^>]+(?:property|name)=["\']og:image(?::url|:secure_url)?["\'][^>]+content=["\']([^"\']+)["\']', raw_html, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image(?::url|:secure_url)?["\']', raw_html, re.I)
            # 2. twitter:image
            if not m:
                m = re.search(r'<meta[^>]+(?:property|name)=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']', raw_html, re.I)
            if not m:
                m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']twitter:image(?::src)?["\']', raw_html, re.I)
            # 3. link rel=image_src
            if not m:
                m = re.search(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']', raw_html, re.I)
            if m:
                img_url = m.group(1).strip()
                if img_url and not img_url.startswith("data:"):
                    return urllib.parse.urljoin(url, img_url)
    except Exception:
        pass
    return None


def download_article_image(url: str, dest_path: Path, timeout: int = 12) -> bool:
    """Extrai og:image/twitter:image de uma URL e baixa para dest_path.

    Retorna True se baixou com sucesso uma imagem válida (> 8000 bytes).
    """
    img_url = extract_og_image_from_url(url, timeout=timeout)
    if not img_url:
        return False
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            if len(content) > 8000:
                dest_path.write_bytes(content)
                return True
    except Exception:
        pass
    return False

