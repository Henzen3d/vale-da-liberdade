#!/usr/bin/env python3
"""
=============================================================================
MOTOR DE GERAÇÃO DE THUMBNAILS YOUTUBE · VALE DA LIBERDADE (HERMES AGENT)
=============================================================================
Este script automatiza a criação de thumbnails editoriais de alto impacto
para os episódios do canal Vale da Liberdade no YouTube.

Funcionalidades integradas:
1. Ciclo contínuo e automático do apresentador (Peter01 -> Peter02 -> ... -> PeterN -> volta ao Peter01).
   - Detecta automaticamente qualquer nova imagem adicionada à pasta Apresentador/.
2. Formatação / simplificação automática de títulos longos em manchetes curtas (com marca-texto amarelo).
3. Integração direta com a imagem de tema da pasta /thumbnails.
4. Geração do HTML autônomo e renderização de screenshot HD (1280x720) e 2X UHD (2560x1440).

Uso via Terminal:
  python3 scripts/hermes_youtube_thumbnail.py --video-id <ID> --title "<TITULO>" --highlight "<DESTAQUE>"
  python3 scripts/hermes_youtube_thumbnail.py --date 2026-08-24 --title "O imposto invisível que todos pagam."
=============================================================================
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Diretórios base
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR.parent.parent.parent

# Pastas de referências e apresentadores
APRESENTADOR_DIR_LOCAL = PROJECT_ROOT / "references" / "youtube" / "gerador-thumbnail" / "Apresentador"
APRESENTADOR_DIR_LINUX = Path("/home/osmar/web-jornal-vale-da-liberdade/references/youtube/gerador-thumbnail/Apresentador")
THUMBNAILS_DIR_LINUX = Path("/home/osmar/web-jornal-vale-da-liberdade/thumbnails")
THUMBNAILS_DIR_LOCAL = PROJECT_ROOT / "thumbnails"

STATE_FILE = PROJECT_ROOT / "logs" / ".peter_cycle_state.json"

# =============================================================================
# 1. SELEÇÃO DINÂMICA E ALEATÓRIA DE APRESENTADORES (PETER01 .. PETER10)
# =============================================================================
def get_presenter_images() -> List[Path]:
    """Descobre dinamicamente todas as imagens de Peter na pasta Apresentador, ordenadas numericamente."""
    target_dir = APRESENTADOR_DIR_LOCAL if APRESENTADOR_DIR_LOCAL.exists() else APRESENTADOR_DIR_LINUX
    if not target_dir.exists():
        target_dir = Path("references/youtube/gerador-thumbnail/Apresentador")

    if not target_dir.exists():
        return []

    valid_exts = {".jpeg", ".jpg", ".png", ".webp"}
    files = [f for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and f.name.lower().startswith("peter")]
    
    # Ordenação natural (peter01, peter02, ... peter08, peter09, peter10...)
    def natural_sort_key(p: Path):
        digits = re.findall(r'\d+', p.name)
        return int(digits[0]) if digits else p.name

    return sorted(files, key=natural_sort_key)


def get_random_presenter_image(advance_cycle: bool = True) -> Tuple[str, int, int]:
    """
    Retorna o caminho de uma imagem de Peter escolhida aleatoriamente,
    evitando repetir imediatamente a mesma foto do episódio anterior.
    """
    images = get_presenter_images()
    if not images:
        return ("Apresentador/peter01.jpeg", 0, 1)

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    last_img_name = ""

    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                last_img_name = data.get("last_image", "")
        except Exception:
            last_img_name = ""

    candidates = [img for img in images if img.name != last_img_name] or images
    selected_image = random.choice(candidates)
    selected_index = images.index(selected_image)

    if advance_cycle:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "last_index": selected_index,
                    "last_image": selected_image.name,
                    "total_images": len(images)
                }, f, indent=2)
        except Exception as e:
            print(f"[Aviso] Falha ao salvar estado do apresentador: {e}", file=sys.stderr)

    return (str(selected_image.as_posix()), selected_index, len(images))


# =============================================================================
# 2. ENCURTADOR E DESTAQUE DE MANCHETE (HEURÍSTICA & ALINHAMENTO)
# =============================================================================
def simplify_headline(full_title: str, max_words: int = 7) -> Tuple[str, str]:
    """
    Simplifica um título de vídeo para o formato conciso da thumbnail.
    Retorna (titulo_curto, palavra_destaque).
    """
    clean_title = full_title.strip().strip('"').strip("'")
    words = clean_title.split()

    if len(words) <= max_words:
        short_title = clean_title
    else:
        # Pega as primeiras palavras ou tenta quebrar no separador (: ou - ou |)
        separators = [":", "-", "—", "|"]
        found_cut = False
        for sep in separators:
            if sep in clean_title:
                parts = clean_title.split(sep)
                candidate = parts[0].strip()
                if 2 <= len(candidate.split()) <= max_words:
                    short_title = candidate
                    found_cut = True
                    break
        if not found_cut:
            short_title = " ".join(words[:max_words]) + "..."

    # Escolhe a melhor palavra ou frase final para o marca-texto amarelo
    short_words = short_title.replace("...", "").strip().split()
    if len(short_words) >= 2:
        highlight = " ".join(short_words[-2:])
    elif short_words:
        highlight = short_words[-1]
    else:
        highlight = ""

    return short_title, highlight


# =============================================================================
# 3. BUSCADOR DE IMAGEM DO TEMA (NOTÍCIA DE DESTAQUE + FALLBACK IA)
# =============================================================================
def fetch_news_featured_image(video_id: Optional[str] = None, episode_date: Optional[str] = None) -> Optional[str]:
    """
    Tenta localizar e baixar a imagem de destaque (og:image) do site da matéria jornalística.
    Retorna o caminho local da imagem baixada ou None se indisponível.
    """
    eps_dirs = [
        PROJECT_ROOT / "output" / "brasil_e_mundo" / "episodes",
        PROJECT_ROOT / "episodes",
        PROJECT_ROOT / "public" / "data",
    ]
    
    episode_data = None
    if video_id:
        for d in eps_dirs:
            p = d / f"especial-{video_id}.json"
            if p.exists():
                try:
                    episode_data = json.loads(p.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

    if not episode_data and episode_date:
        for d in eps_dirs:
            p = d / f"{episode_date}.json"
            if not p.exists():
                p = d / f"roteiro-{episode_date}.json"
            if p.exists():
                try:
                    episode_data = json.loads(p.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

    if not episode_data:
        return None

    # Extrai URLs de matérias (ignora links do YouTube e internos)
    urls = []
    refs = episode_data.get("fonte_referencias") or []
    for ref in refs:
        u = ref.get("url") if isinstance(ref, dict) else str(ref)
        if u and not any(ign in u.lower() for ign in ["youtube.com", "youtu.be", "mob.tec.br", "antonioveronese"]):
            urls.append(u)
    
    fonte_url = episode_data.get("fonte_url") or ""
    if fonte_url and not any(ign in fonte_url.lower() for ign in ["youtube.com", "youtu.be", "mob.tec.br"]):
        urls.insert(0, fonte_url)

    if not urls:
        return None

    import urllib.request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    og_re = re.compile(r'<meta[^>]+property=[\'"]og:image[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', re.I)
    og_re2 = re.compile(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+property=[\'"]og:image[\'"]', re.I)

    date_str = episode_date or (episode_data.get("date") or "news_leads")
    save_dir = PROJECT_ROOT / "thumbnails" / date_str
    save_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / f"news_lead_{video_id or 'lead'}.jpg"

    if save_file.exists() and save_file.stat().st_size > 15000:
        return str(save_file.resolve().as_posix())

    for page_url in urls[:4]:
        try:
            req = urllib.request.Request(page_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                m = og_re.search(html) or og_re2.search(html)
                if not m:
                    continue
                img_url = m.group(1).replace("&amp;", "&")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                img_req = urllib.request.Request(img_url, headers=headers)
                with urllib.request.urlopen(img_req, timeout=8) as img_resp:
                    content = img_resp.read()
                    if len(content) > 15000:  # Imagem com conteúdo real (>15KB)
                        save_file.write_bytes(content)
                        print(f"   📸 Imagem de destaque da notícia obtida com sucesso ({len(content)//1024} KB) de: {page_url}")
                        return str(save_file.resolve().as_posix())
        except Exception:
            continue

    return None


def find_topic_image(
    topic_query: Optional[str] = None,
    episode_date: Optional[str] = None,
    video_id: Optional[str] = None
) -> str:
    """
    Localiza o arquivo de imagem do tema da notícia com cascata inteligente:
    1. topic_query se fornecido explicitamente.
    2. Imagem de destaque do site de notícia (og:image).
    3. Fallback: imagens geradas por IA / thumbnails locais.
    """
    if topic_query and Path(topic_query).exists():
        return str(Path(topic_query).resolve().as_posix())

    # 1. Prioridade: Foto da Notícia Original
    news_img = fetch_news_featured_image(video_id=video_id, episode_date=episode_date)
    if news_img:
        return news_img

    # 2. Fallback: Imagens geradas pelo sistema / IA / locais
    candidates = []
    if video_id:
        candidates.extend([
            PROJECT_ROOT / "output" / "brasil_e_mundo" / "assets" / video_id / "image.jpg",
            THUMBNAILS_DIR_LINUX / f"bm_{video_id}.jpg",
            THUMBNAILS_DIR_LOCAL / f"bm_{video_id}.jpg",
        ])
        if episode_date:
            candidates.extend([
                THUMBNAILS_DIR_LOCAL / episode_date / f"bm_{video_id}.jpg",
            ])

    if episode_date:
        candidates.extend([
            THUMBNAILS_DIR_LINUX / f"ep_{episode_date}.jpg",
            THUMBNAILS_DIR_LOCAL / f"ep_{episode_date}.jpg",
            THUMBNAILS_DIR_LOCAL / episode_date / "cover.jpg",
            THUMBNAILS_DIR_LOCAL / episode_date / "cover.webp",
        ])

    candidates.extend([
        THUMBNAILS_DIR_LOCAL / "ep_2026-08-23.jpg",
        PROJECT_ROOT / "references" / "youtube" / "gerador-thumbnail" / "thumbnail" / "ep_2026-08-23.jpg",
        PROJECT_ROOT / "public" / "assets" / "cover.jpg"
    ])

    for cand in candidates:
        if cand.exists() and cand.stat().st_size > 1000:
            return str(cand.resolve().as_posix())

    return "thumbnail/ep_2026-08-23.jpg"


def _to_file_uri(path_str: str) -> str:
    """Converte um caminho local ou relativo em URL absoluta file:/// para garantir carregamento em qualquer diretório."""
    if not path_str:
        return ""
    if path_str.startswith("http://") or path_str.startswith("https://") or path_str.startswith("data:") or path_str.startswith("blob:"):
        return path_str
    if path_str.startswith("file://"):
        return path_str
    p = Path(path_str)
    if not p.is_absolute():
        p = (PROJECT_ROOT / path_str).resolve()
    else:
        p = p.resolve()
    return p.as_uri()


# =============================================================================
# 4. GERADOR DO TEMPLATE HTML AUTÔNOMO (PADRÃO 1280x720 VALE DA LIBERDADE)
# =============================================================================
def build_thumbnail_html(config: Dict) -> str:
    """Gera o HTML autônomo 1280x720 de ultra-alta fidelidade com suporte a todos os modos."""
    title = config.get("title", "A liberdade não se pede, se conquista.")
    highlight = config.get("highlight", "se conquista.")
    hl_color = config.get("highlightColor", "yellow")
    hl_color_code = "#ffe600" if hl_color == "yellow" else "#d4a017"
    hl_style = f"background: linear-gradient(180deg, transparent 12%, {hl_color_code} 12%, {hl_color_code} 92%, transparent 92%); color: #0c0d10 !important; padding: 0 8px; border-radius: 4px; box-decoration-break: clone; -webkit-box-decoration-break: clone; display: inline; position: relative; z-index: 0;"

    title_html = title
    if highlight and highlight.lower() in title.lower():
        reg = re.compile(f"({re.escape(highlight)})", re.IGNORECASE)
        title_html = reg.sub(r'<mark class="hl">\1</mark>', title)

    raw_presenter = config.get("presenterImage", "references/youtube/gerador-thumbnail/Apresentador/peter01.jpeg")
    raw_topic = config.get("topicImage", "references/youtube/gerador-thumbnail/thumbnail/ep_2026-08-23.jpg")
    presenter_img = _to_file_uri(raw_presenter)
    topic_img = _to_file_uri(raw_topic)

    mode = config.get("mode", "card-media")
    side = config.get("side", "right")
    card_theme = config.get("cardTheme", "white")
    font_family = config.get("fontFamily", "anton")
    logo_text = config.get("logoText", "VALE DA LIBERDADE")
    kicker = config.get("kicker", "ANÁLISE EXCLUSIVA")
    badge = config.get("topicOverlayBadge", "EM FOCO")
    author_name = config.get("presenterName", "Peter Albuquerque")
    author_handle = config.get("presenterHandle", "@peteralbuquerque")
    card_width = config.get("cardWidth", 720)
    card_tilt = config.get("cardTilt", -2)
    glow_opacity = config.get("glowOpacity", 45) / 100.0
    plant_type = config.get("plant", "none")
    plant_x = config.get("plantX", 18)
    plant_y = config.get("plantY", -126)
    plant_scale = config.get("plantScale", 1.25)
    plant_blur = config.get("plantBlur", 6.0)

    # Cores e temas do card
    if card_theme == "white":
        card_theme_css = "background: #fff; color: #111113;"
        user_name_color = "#111"
        user_handle_color = "#6b6e79"
        kicker_color = "#8a6204"
        footer_border = "#eaebee"
        footer_color = "#717684"
        headline_color = "#0c0d10"
    elif card_theme == "dark":
        card_theme_css = "background: linear-gradient(145deg, #18191e 0%, #111215 100%); color: #fff; border: 1px solid rgba(212,160,23,0.3);"
        user_name_color = "#fff"
        user_handle_color = "#8e909d"
        kicker_color = "#f6d168"
        footer_border = "rgba(255,255,255,0.08)"
        footer_color = "#989aa8"
        headline_color = "#fff"
    else:
        card_theme_css = "background: rgba(18,18,22,0.82); backdrop-filter: blur(28px); color: #fff; border: 1px solid rgba(246,209,104,0.35);"
        user_name_color = "#fff"
        user_handle_color = "#8e909d"
        kicker_color = "#f6d168"
        footer_border = "rgba(255,255,255,0.08)"
        footer_color = "#989aa8"
        headline_color = "#fff"

    if font_family == "anton":
        font_css = "'Anton', sans-serif"
        font_weight = "400"
        headline_font_size = "40px" if mode == "card-media" else "54px"
    elif font_family == "plus":
        font_css = "'Plus Jakarta Sans', sans-serif"
        font_weight = "800"
        headline_font_size = "34px" if mode == "card-media" else "46px"
    else:
        font_css = "'Inter', sans-serif"
        font_weight = "800"
        headline_font_size = "34px" if mode == "card-media" else "46px"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Thumbnail · {logo_text}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;600;700;800;900&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #000; width: 1280px; height: 720px; overflow: hidden; font-family: 'Inter', sans-serif; }}
  .stage {{ width: 1280px; height: 720px; position: relative; background: #0d0d0f; overflow: hidden; user-select: none; }}
  
  .stage-bg-image {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; {'transform: scaleX(-1);' if side == 'left' else ''} display: {'none' if mode == 'cutout' else 'block'}; }}
  .stage-cutout-presenter {{ position: absolute; bottom: -10px; height: 105%; z-index: 5; filter: drop-shadow(0 20px 40px rgba(0,0,0,0.85)); {'right: -30px;' if side == 'right' else 'left: -30px; transform: scaleX(-1);'} display: {'block' if mode == 'cutout' else 'none'}; }}
  
  .stage-vignette {{ position: absolute; inset: 0; z-index: 2; background: {'radial-gradient(circle at 75% 50%, rgba(0,0,0,0.04) 0%, rgba(5,5,8,0.4) 65%, rgba(5,5,8,0.85) 100%), linear-gradient(to right, rgba(8,8,10,0.92) 0%, rgba(8,8,10,0.5) 42%, rgba(8,8,10,0.04) 75%)' if side == 'right' else 'radial-gradient(circle at 25% 50%, rgba(0,0,0,0.04) 0%, rgba(5,5,8,0.4) 65%, rgba(5,5,8,0.85) 100%), linear-gradient(to left, rgba(8,8,10,0.92) 0%, rgba(8,8,10,0.5) 42%, rgba(8,8,10,0.04) 75%)'}; pointer-events: none; }}
  .stage-gold-aura {{ position: absolute; width: 750px; height: 750px; border-radius: 50%; background: radial-gradient(circle, rgba(246, 209, 104, 0.38) 0%, rgba(212, 160, 23, 0.14) 42%, transparent 70%); filter: blur(45px); z-index: 2; top: 50%; transform: translateY(-50%); {'right: 80px;' if side == 'right' else 'left: 80px;'} opacity: {glow_opacity}; }}
  .stage-logo-pill {{ position: absolute; top: 34px; {'left: 46px;' if side == 'right' else 'right: 46px;'} z-index: 25; display: flex; align-items: center; gap: 8px; background: rgba(12, 12, 15, 0.88); backdrop-filter: blur(12px); border: 1px solid rgba(212, 160, 23, 0.35); padding: 7px 14px; border-radius: 30px; }}
  .stage-logo-name {{ font-size: 13px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; color: #fff; }}
  .stage-logo-tag {{ font-size: 10px; font-weight: 700; background: #d4a017; color: #111; padding: 2px 6px; border-radius: 4px; }}
  
  .card-container {{ position: absolute; top: 50%; {'left: 48px;' if side == 'right' else 'right: 48px;'} z-index: 10; transform: translateY(-50%) rotate({card_tilt}deg); display: {'none' if mode == 'screen3d' else 'block'}; }}
  .card-modal {{ width: {card_width}px; border-radius: 28px; padding: {'30px 34px' if mode == 'card-media' else '38px 40px'}; display: flex; flex-direction: column; gap: {'14px' if mode == 'card-media' else '18px'}; box-shadow: 0 40px 90px -10px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.15); {card_theme_css} }}
  .card-header {{ display: flex; align-items: center; justify-content: space-between; width: 100%; }}
  .card-author-info {{ display: flex; align-items: center; gap: 12px; }}
  .card-avatar {{ width: 46px; height: 46px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(212,160,23,0.4); }}
  .card-user-name {{ font-weight: 800; font-size: 18px; color: {user_name_color}; }}
  .card-user-handle {{ font-size: 13px; color: {user_handle_color}; }}
  .card-kicker-badge {{ font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; padding: 5px 10px; border-radius: 8px; background: rgba(212,160,23,0.15); color: {kicker_color}; border: 1px solid rgba(212,160,23,0.35); }}
  .card-media-frame {{ width: 100%; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; position: relative; display: {'block' if mode == 'card-media' else 'none'}; }}
  .card-media-img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .card-media-overlay-badge {{ position: absolute; bottom: 10px; left: 10px; background: rgba(10,10,12,0.85); color: #f6d168; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid rgba(212, 160, 23, 0.4); }}
  .card-headline {{ font-family: {font_css}; font-weight: {font_weight}; font-size: {headline_font_size}; line-height: 1.24; color: {headline_color}; }}
  mark.hl {{ {hl_style} }}
  .card-footer {{ display: flex; align-items: center; justify-content: space-between; padding-top: 14px; font-size: 13px; font-weight: 600; border-top: 1px solid {footer_border}; color: {footer_color}; }}
  
  .stage-screen-3d {{ position: absolute; top: 50%; z-index: 10; width: 620px; aspect-ratio: 16 / 9; border-radius: 20px; overflow: hidden; box-shadow: 0 35px 80px rgba(0,0,0,0.85), 0 0 0 2px rgba(212, 160, 23, 0.4), 0 0 50px rgba(212, 160, 23, 0.2); background: #000; display: {'block' if mode == 'screen3d' else 'none'}; {'left: 48px; transform: translateY(-50%) perspective(1200px) rotateY(7deg) rotateX(1deg);' if side == 'right' else 'right: 48px; transform: translateY(-50%) perspective(1200px) rotateY(-7deg) rotateX(1deg);'} }}
  .screen-3d-img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .screen-3d-glass-reflect {{ position: absolute; inset: 0; background: linear-gradient(130deg, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.02) 40%, transparent 70%); pointer-events: none; }}
  .screen-3d-badge {{ position: absolute; top: 18px; left: 18px; background: rgba(15,15,18,0.9); border: 1px solid #d4a017; color: #f6d168; padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }}
  .screen-3d-caption {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 24px 20px 18px; background: linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.5) 70%, transparent 100%); color: #fff; font-size: 24px; font-weight: 800; line-height: 1.15; }}

  .foreground-depth-layer {{ position: absolute; bottom: {plant_y}px; {'left: ' + str(plant_x) + 'px; transform: scale(' + str(plant_scale) + ');' if side == 'right' else 'right: ' + str(plant_x) + 'px; transform: scaleX(-1) scale(' + str(plant_scale) + ');'} z-index: 22; display: {'none' if plant_type == 'none' else 'block'}; filter: drop-shadow(0 15px 30px rgba(0,0,0,0.75)); }}
  .depth-plant-svg {{ width: 320px; height: auto; display: block; }}
</style>
</head>
<body>
  <div class="stage">
    <img class="stage-bg-image" src="{presenter_img}" alt="Apresentador" />
    <img class="stage-cutout-presenter" src="{presenter_img}" alt="Recorte" />
    <div class="stage-gold-aura"></div>
    <div class="stage-vignette"></div>
    <div class="stage-logo-pill">
      <span style="color:#ffdc33">◆</span>
      <span class="stage-logo-name">{logo_text}</span>
      <span class="stage-logo-tag">4K</span>
    </div>
    
    <div class="card-container">
      <div class="card-modal">
        <div class="card-header">
          <div class="card-author-info">
            <img class="card-avatar" src="{presenter_img}" alt="Avatar" />
            <div style="display:flex; flex-direction:column; gap:2px;">
              <span class="card-user-name">{author_name} ✓</span>
              <span class="card-user-handle">{author_handle}</span>
            </div>
          </div>
          <div class="card-kicker-badge">{kicker}</div>
        </div>
        <div class="card-media-frame">
          <img class="card-media-img" src="{topic_img}" alt="Tema" />
          <div class="card-media-overlay-badge">{badge}</div>
        </div>
        <h2 class="card-headline">{title_html}</h2>
        <div class="card-footer">
          <div>💬 142 &nbsp; 🔁 580 &nbsp; ❤️ 3.4K</div>
          <div style="font-size:11px; letter-spacing:.08em; text-transform:uppercase;">NOTÍCIAS & ANÁLISE</div>
        </div>
      </div>
    </div>

    <div class="stage-screen-3d">
      <img class="screen-3d-img" src="{topic_img}" alt="Tema 3D" />
      <div class="screen-3d-glass-reflect"></div>
      <div class="screen-3d-badge">{kicker}</div>
      <div class="screen-3d-caption">{title_html}</div>
    </div>

    <div class="foreground-depth-layer">
      <svg class="depth-plant-svg" viewBox="0 0 500 360" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="plantBokehBlur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="{plant_blur}"/>
          </filter>
          <linearGradient id="jL1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#73a968"/><stop offset="60%" stop-color="#46763d"/><stop offset="100%" stop-color="#24441f"/></linearGradient>
          <linearGradient id="jL2" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#88be7c"/><stop offset="50%" stop-color="#55894b"/><stop offset="100%" stop-color="#2a4f23"/></linearGradient>
          <linearGradient id="jSt" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#46763d"/><stop offset="100%" stop-color="#183114"/></linearGradient>
          <linearGradient id="aG1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#82b477"/><stop offset="50%" stop-color="#4e7d44"/><stop offset="100%" stop-color="#1d3819"/></linearGradient>
          <linearGradient id="aG2" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#96ca8a"/><stop offset="50%" stop-color="#5a8d50"/><stop offset="100%" stop-color="#264821"/></linearGradient>
          <linearGradient id="aRb" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#b2e2a7"/><stop offset="100%" stop-color="#34592d"/></linearGradient>
        </defs>
        <g filter="url(#plantBokehBlur)">
          <path d="M 125 340 Q 120 180 110 50" stroke="url(#jSt)" stroke-width="12" stroke-linecap="round"/>
          <path d="M 40 280 C 25 240 70 210 120 235 C 130 275 80 300 40 280 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="4"/>
          <path d="M 125 250 C 175 220 215 250 205 290 C 160 305 125 280 125 250 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="4"/>
          <path d="M 35 220 C 30 175 80 155 120 180 C 125 215 75 235 35 220 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="4"/>
          <path d="M 115 190 C 165 160 195 190 185 225 C 145 240 115 215 115 190 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="4"/>
          <path d="M 60 155 C 55 115 100 100 125 125 C 125 155 90 170 60 155 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="4"/>
          <path d="M 110 135 C 150 110 175 135 165 165 C 130 180 110 155 110 135 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="4"/>
          <path d="M 85 95 C 80 65 115 50 130 75 C 130 100 105 110 85 95 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="3"/>
          <path d="M 105 80 C 135 60 155 80 145 105 C 120 115 105 95 105 80 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="3"/>
          <ellipse cx="110" cy="50" rx="18" ry="14" fill="url(#jL2)" stroke="#11220f" stroke-width="3"/>
          <ellipse cx="118" cy="38" rx="14" ry="10" fill="url(#jL1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 215 340 Q 220 250 230 150" stroke="url(#jSt)" stroke-width="9" stroke-linecap="round"/>
          <path d="M 170 270 C 160 235 195 220 225 240 C 225 270 195 285 170 270 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="3"/>
          <path d="M 220 245 C 255 225 275 250 265 275 C 235 285 215 265 220 245 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 185 210 C 180 180 210 165 230 185 C 230 210 205 225 185 210 Z" fill="url(#jL1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 225 190 C 255 170 270 195 260 215 C 235 225 220 205 225 190 Z" fill="url(#jL2)" stroke="#11220f" stroke-width="3"/>
          <ellipse cx="230" cy="150" rx="15" ry="11" fill="url(#jL2)" stroke="#11220f" stroke-width="3"/>
          <path d="M 285 340 Q 230 200 265 105 Q 295 180 320 340 Z" fill="url(#aG1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 345 340 Q 420 120 460 90 Q 425 190 380 340 Z" fill="url(#aG1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 360 340 Q 460 210 495 245 Q 430 280 375 340 Z" fill="url(#aG1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 300 340 Q 305 130 330 65 Q 355 150 345 340 Z" fill="url(#aG2)" stroke="#11220f" stroke-width="4"/>
          <path d="M 315 150 Q 325 80 330 65 Q 335 110 332 170" stroke="url(#aRb)" stroke-width="3" stroke-linecap="round"/>
          <path d="M 320 340 Q 360 80 395 35 Q 395 130 365 340 Z" fill="url(#aG2)" stroke="#11220f" stroke-width="4"/>
          <path d="M 350 160 Q 380 65 395 35 Q 385 110 370 190" stroke="url(#aRb)" stroke-width="3" stroke-linecap="round"/>
          <path d="M 330 340 Q 390 110 425 75 Q 410 170 370 340 Z" fill="url(#aG1)" stroke="#11220f" stroke-width="3"/>
          <path d="M 365 180 Q 405 105 425 75" stroke="url(#aRb)" stroke-width="2.5" stroke-linecap="round"/>
          <path d="M 285 340 Q 255 240 280 180 Q 310 240 315 340 Z" fill="url(#aG2)" stroke="#11220f" stroke-width="3"/>
          <path d="M 325 340 Q 375 220 405 185 Q 385 260 360 340 Z" fill="url(#aG2)" stroke="#11220f" stroke-width="3"/>
        </g>
      </svg>
    </div>
  </div>

  <script>
    window.__THUMB_READY__ = false;
    Promise.all([
      document.fonts ? document.fonts.ready : Promise.resolve(),
      new Promise(r => setTimeout(r, 120))
    ]).then(() => {{
      window.__THUMB_READY__ = true;
      document.documentElement.dataset.ready = "true";
    }});
  </script>
</body>
</html>"""


# =============================================================================
# 5. RENDERIZADOR AUTOMÁTICO (PLAYWRIGHT OU CHROMIUM HEADLESS)
# =============================================================================
def render_thumbnail_image(html_content: str, output_image_path: Path) -> bool:
    """Renderiza o HTML diretamente para um arquivo PNG/JPG via Playwright ou Chromium."""
    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    temp_html = output_image_path.with_suffix(".temp.html")

    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    success = False

    # Tentativa 1: Playwright Python
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
            page.goto(temp_html.resolve().as_uri())
            
            # Aguarda sinal determinístico de renderização completa
            try:
                page.wait_for_function("() => window.__THUMB_READY__ === true", timeout=10000)
            except Exception:
                page.wait_for_load_state("networkidle")
                
            page.screenshot(path=str(output_image_path))
            browser.close()
            success = True
    except Exception:
        pass

    # Tentativa 2: Google Chrome / Edge / Chromium via CLI
    if not success:
        chrome_bins = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "google-chrome",
            "chromium-browser",
            "chromium"
        ]
        for bin_path in chrome_bins:
            try:
                cmd = [
                    bin_path,
                    "--headless",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--window-size=1280,720",
                    f"--screenshot={output_image_path.resolve()}",
                    temp_html.resolve().as_uri()
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                if res.returncode == 0 and output_image_path.exists():
                    success = True
                    break
            except Exception:
                continue

    if temp_html.exists():
        temp_html.unlink()

    return success


# =============================================================================
# 6. FUNÇÃO PRINCIPAL / API PARA O HERMES AGENT
# =============================================================================
def generate_episode_thumbnail(
    title: Optional[str] = None,
    highlight: Optional[str] = None,
    topic_image: Optional[str] = None,
    episode_date: Optional[str] = None,
    video_id: Optional[str] = None,
    output_path: Optional[str] = None,
    mode: Optional[str] = None,
    plant: Optional[str] = None,
    font_family: Optional[str] = None,
    card_theme: Optional[str] = None,
    advance_presenter_cycle: bool = True
) -> Dict:
    """
    Função unificada chamada pelo Hermes para gerar a thumbnail do episódio.
    Aplica as regras:
    - 80% Card + Imagem 16:9 / 20% Card Editorial (Ali Abdaal)
    - 60% Sem planta / 25% Suculenta / 15% Eucalipto
    - Tipografia padrão: Anton (Impacto)
    - Apresentador aleatório sem repetição imediata
    - Imagem do tema: foto de destaque do site de notícia com fallback em IA
    """
    # 1. Determina Título e Destaque
    raw_title = title or "A liberdade não se pede, se conquista."
    if not highlight:
        formatted_title, detected_hl = simplify_headline(raw_title)
    else:
        formatted_title, detected_hl = raw_title, highlight

    # 2. Apresentador Aleatório (Peter01 .. Peter10)
    presenter_img, cycle_idx, total_cycle = get_random_presenter_image(advance_cycle=advance_presenter_cycle)

    # 3. Imagem do Tema (Destaque da Notícia com Fallback IA)
    topic_img = find_topic_image(topic_image, episode_date, video_id=video_id)

    # 4. Sorteio ponderado de Layout e Elementos de Profundidade
    chosen_mode = mode or random.choices(["card-media", "card"], weights=[80, 20])[0]
    chosen_plant = plant or random.choices(["none", "succulent", "eucalyptus"], weights=[60, 25, 15])[0]
    chosen_font = font_family or "anton"
    chosen_theme = card_theme or "white"

    config = {
        "mode": chosen_mode,
        "side": "right",
        "cardTheme": chosen_theme,
        "fontFamily": chosen_font,
        "title": formatted_title,
        "highlight": detected_hl,
        "highlightColor": "yellow",
        "kicker": "ANÁLISE EXCLUSIVA",
        "logoText": "VALE DA LIBERDADE",
        "presenterImage": presenter_img,
        "presenterName": "Peter Albuquerque",
        "presenterHandle": "@peteralbuquerque",
        "topicImage": topic_img,
        "topicOverlayBadge": "EM FOCO",
        "plant": chosen_plant,
        "plantX": 18,
        "plantY": -126,
        "plantScale": 1.25,
        "plantBlur": 6.0,
        "cardWidth": 720,
        "cardTilt": -2,
        "glowOpacity": 45,
        "cycleIndex": cycle_idx,
        "cycleTotal": total_cycle
    }

    # 5. Gera HTML e Renderiza
    html_content = build_thumbnail_html(config)

    if not output_path:
        date_str = episode_date or "undated"
        if video_id:
            output_file = PROJECT_ROOT / "thumbnails" / date_str / f"yt_bm_{video_id}.png"
        else:
            output_file = PROJECT_ROOT / "thumbnails" / f"thumb_youtube_{date_str}.png"
    else:
        output_file = Path(output_path)

    # Salva também o HTML pronto
    html_output_path = output_file.with_suffix(".html")
    html_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    render_success = render_thumbnail_image(html_content, output_file)

    return {
        "success": True,
        "rendered_image": str(output_file.as_posix()) if render_success else None,
        "html_template": str(html_output_path.as_posix()),
        "config": config,
        "presenter": presenter_img,
        "mode": chosen_mode,
        "plant": chosen_plant,
        "font": chosen_font,
        "topic_used": topic_img
    }


# =============================================================================
# 7. CLI ENTRYPOINT
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerador de Thumbnails YouTube Vale da Liberdade (Hermes)")
    parser.add_argument("--title", type=str, help="Título do episódio / manchete da thumbnail")
    parser.add_argument("--highlight", type=str, help="Palavra ou frase para destacar em amarelo")
    parser.add_argument("--topic", type=str, help="Caminho da imagem do tema (/thumbnails/ep_*.jpg)")
    parser.add_argument("--date", type=str, help="Data do episódio (ex: 2026-08-24)")
    parser.add_argument("--video-id", type=str, help="ID do vídeo BM (ex: 1jl8AEGXRr4)")
    parser.add_argument("--mode", type=str, choices=["card-media", "card", "screen3d", "cutout"], help="Força modo de layout")
    parser.add_argument("--plant", type=str, choices=["none", "succulent", "eucalyptus"], help="Força planta de profundidade")
    parser.add_argument("--font", type=str, choices=["anton", "inter", "plus"], help="Força tipografia")
    parser.add_argument("--output", type=str, help="Caminho do arquivo de saída (.png)")
    parser.add_argument("--no-advance", action="store_true", help="Não avança estado do apresentador")

    args = parser.parse_args()

    res = generate_episode_thumbnail(
        title=args.title,
        highlight=args.highlight,
        topic_image=args.topic,
        episode_date=args.date,
        video_id=args.video_id,
        mode=args.mode,
        plant=args.plant,
        font_family=args.font,
        output_path=args.output,
        advance_presenter_cycle=not args.no_advance
    )

    print(json.dumps(res, indent=2, ensure_ascii=False))
