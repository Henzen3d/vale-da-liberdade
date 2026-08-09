#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera /noticias/ — home (destaque + grade densa) + artigos por episódio.

Referência estrutural: BBC News / El País América (destaque + grade, hairline,
hierarquia por peso/tamanho). Identidade da marca: preto puro, Inter, âmbar #e8a23d.
Corpo SEM prefixos de locutor (quem lê, lê a notícia). Fontes citadas no rodapé.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from noticias_templates import ARTICLE_TMPL, HOME_CSS, HOME_TMPL, SHARED_CSS

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
EPISODES_DIR = ROOT / "episodes"
NOTICIAS_DIR = PUBLIC / "noticias"
BASE = "https://news.mob.tec.br"
GENERIC_IMG = f"{BASE}/assets/cover-1200.webp"

EDITORIAS = {
    "diario": ("Diário", "Jornal Diário"),
    "bm": ("Brasil e Mundo", "Brasil e Mundo"),
    "economia": ("Economia", "Economia"),
    "tecnologia": ("Tecnologia", "Tecnologia"),
}


def slugify(title: str) -> str:
    s = title.lower().strip()
    for a, b in (("àáâãä", "a"), ("èéêë", "e"), ("ìíîï", "i"), ("òóôõö", "o"),
                 ("ùúûü", "u"), ("ç", "c")):
        for ch in a:
            s = s.replace(ch, b)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:90] or "noticia"


def editoria_of(ep: dict) -> str:
    if ep.get("type") == "especial":
        return "bm"
    q = [str(x).lower() for x in (ep.get("quadros") or [])]
    if any(x in q for x in ("economia", "investimentos", "mercado")):
        return "economia"
    if any(x in q for x in ("tecnologia", "cultura", "ciência", "ciencia")):
        return "tecnologia"
    return "diario"


def date_br(iso: str) -> str:
    parts = (iso or "").split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return iso or ""


def md_to_html(md_text: str) -> str:
    """Markdown mínimo do roteiro -> HTML de leitura, SEM prefixo de locutor."""
    out: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in md_text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "---" or stripped.startswith(">"):
            close_list()
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            close_list()
            level = len(m.group(1))
            txt = html.escape(m.group(2))
            if level >= 3 or txt.startswith("📋") or txt.upper() == txt:
                out.append(f'<h2 class="quadro">{txt}</h2>')
            elif level == 2:
                out.append(f"<h2>{txt}</h2>")
            else:
                out.append(f"<h3>{txt}</h3>")
            continue

        m = re.match(r"^\[QUADRO:\s*(.*?)\]\s*$", stripped)
        if m:
            close_list()
            out.append(f'<h2 class="quadro">{html.escape(m.group(1))}</h2>')
            continue

        if stripped.startswith(("• ", "- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(stripped[2:])}</li>")
            continue

        close_list()
        # Remove o prefixo "Nome:" do locutor — leitura, não roteiro
        text = stripped
        m = re.match(r"^[A-ZÀ-Úa-zà-ú]+\s*:\s*(.*)$", text)
        if m and m.group(1).strip():
            text = m.group(1).strip()
        out.append(f"<p>{html.escape(text)}</p>")

    close_list()
    return "\n".join(out)


def load_sources_map() -> dict:
    try:
        data = json.loads((ROOT / "sources" / "sources.json").read_text(encoding="utf-8"))
        return {s.get("id"): s.get("name") for s in data.get("sources", []) if s.get("id")}
    except Exception:
        return {}


def extract_fonte(md_text: str) -> str:
    """Frontmatter -> 'Fonte: X' (ex.: especiais têm '> Fonte: Visão Libertária')."""
    for line in md_text.splitlines()[:12]:
        m = re.match(r"^>\s*Fonte:\s*(.+?)\s*$", line.strip())
        if m:
            return m.group(1)
    return ""


def strip_frontmatter(md_text: str) -> str:
    """Remove o cabeçalho do roteiro (até o primeiro '---')."""
    lines = md_text.splitlines()
    for i, raw in enumerate(lines):
        if raw.strip() == "---":
            return "\n".join(lines[i + 1:])
    return md_text


def build_article(ep: dict, md_text: str, src_names: dict) -> tuple[str, str]:
    eid = str(ep.get("id") or "")
    title = ep.get("title") or f"Edição {ep.get('date') or ''}"
    excerpt = ep.get("excerpt") or ""
    if not excerpt and isinstance(ep.get("manchetes"), list) and ep["manchetes"]:
        excerpt = ep["manchetes"][0]
    desc = (excerpt or "").strip()[:160] or "Leia e ouça o Vale da Liberdade."
    img = ep.get("cover_url_abs") or GENERIC_IMG
    slug = slugify(title)
    url = f"{BASE}/noticias/{slug}.html"
    player_url = f"{BASE}/?ep={eid}"
    ed = editoria_of(ep)
    ed_label, kicker = EDITORIAS[ed]
    dur = ep.get("duration_min")
    duracao = str(dur) if dur else "—"
    md_clean = strip_frontmatter(md_text)
    body = md_to_html(md_clean)
    # Citação de fontes no fim da matéria: especiais com `referencias`
    # (links da seção "Referências:" da descrição do YouTube + nosso site)
    # viram lista de links; senão, mantém o comportamento anterior.
    refs = ep.get("referencias") or []
    if refs:
        items = []
        for r in refs:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            veic = (r.get("veiculo") or "").strip() or url
            self_tag = '<span class="ref-self">nosso site</span>' if r.get("self") else ""
            items.append(
                '<li><a href="{}" target="_blank" rel="noopener noreferrer">{}</a>{}</li>'
                .format(html.escape(url, quote=True), html.escape(veic, quote=True), self_tag)
            )
        if items:
            sources_html = (
                '<div class="sources"><b>Referências:</b>'
                '<ul class="ref-list">' + "".join(items) + "</ul></div>"
            )
        else:
            sources_html = ""
    else:
        # Prioridade ao "Fonte:" do frontmatter (especiais antigos); senão mapeia ids
        fonte = extract_fonte(md_text)
        if fonte:
            sources_html = (
                '<div class="sources"><b>Fonte:</b> ' + html.escape(fonte, quote=True) + "</div>"
            )
        else:
            src_ids = [s for s in (ep.get("sources") or []) if s in src_names][:8]
            if src_ids:
                sources_html = (
                    '<div class="sources"><b>Fontes desta edição:</b> '
                    + " · ".join(html.escape(src_names[s]) for s in src_ids)
                    + "</div>"
                )
            else:
                sources_html = ""
    page = ARTICLE_TMPL.format(
        title=html.escape(title, quote=True),
        desc=html.escape(desc, quote=True),
        img=html.escape(img, quote=True),
        url=html.escape(url, quote=True),
        base=BASE,
        css=SHARED_CSS,
        kicker=html.escape(kicker, quote=True),
        data=html.escape(date_br(ep.get("date") or ""), quote=True),
        duracao=html.escape(duracao, quote=True),
        editoria=html.escape(ed_label, quote=True),
        player_url=html.escape(player_url, quote=True),
        body=body,
        sources_html=sources_html,
    )
    return slug, page


AD_SLOT_HTML = ('<div class="ad-slot ad-slot-inline"><p class="ad-label">Publicidade</p>'
                '<ins class="adsbygoogle" data-ad-client="" data-ad-slot="" '
                'data-ad-format="auto" data-full-width-responsive="true"></ins></div>')


def write_ads_js() -> None:
    """Gera ads.js com SUPABASE_URL/ANON_KEY embutidos (anon key é pública por design,
    como no index.html do app). Busca monetization_config via REST; se ativo, preenche
    os slots, carrega adsbygoogle e faz push; senão, esconde os slots (kill-switch)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    import os
    supa_url = os.environ.get("SUPABASE_URL", "")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    js = f"""/* Gerado por gen_noticias.py — slots Google AdSense configuráveis via Supabase */
(function(){{
  var URL={json.dumps(supa_url)};
  var KEY={json.dumps(anon_key)};
  var slots=document.querySelectorAll('.adsbygoogle');
  if(!URL||!KEY||!slots.length)return;
  function hide(){{slots.forEach(function(s){{var w=s.closest('.ad-slot');if(w)w.hidden=true;}});}}
  function enable(cfg){{
    slots.forEach(function(s){{
      s.setAttribute('data-ad-client',cfg.adsense_client_id||'');
      if(cfg.feed_slot_id)s.setAttribute('data-ad-slot',cfg.feed_slot_id);
    }});
    var sc=document.createElement('script');
    sc.async=true;
    sc.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+encodeURIComponent(cfg.adsense_client_id||'');
    sc.crossOrigin='anonymous';
    sc.onload=function(){{slots.forEach(function(){{try{{(window.adsbygoogle=window.adsbygoogle||[]).push({{}});}}catch(e){{}}}});}};
    document.head.appendChild(sc);
  }}
  fetch(URL+'/rest/v1/rpc/fn_get_monetization_config',{{
    method:'POST',
    headers:{{'apikey':KEY,'Authorization':'Bearer '+KEY,'Content-Type':'application/json'}},
    body:'{{}}'
  }}).then(function(r){{return r.ok?r.json():null;}})
    .then(function(cfg){{
      cfg=Array.isArray(cfg)?(cfg[0]||null):(cfg||null);
      if(cfg&&cfg.adsense_enabled&&cfg.adsense_client_id)enable(cfg);
      else hide();
    }}).catch(hide);
}})();
"""
    (NOTICIAS_DIR / "ads.js").write_text(js, encoding="utf-8")


MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def build_home(eps: list) -> str:
    hero = eps[0] if eps else None
    rest = eps[1:] if eps else []

    def item_html(ep: dict) -> str:
        title = ep.get("title") or f"Edição {ep.get('date') or ''}"
        slug = slugify(title)
        img = ep.get("cover_url_abs") or GENERIC_IMG
        ed = editoria_of(ep)
        ed_label, _ = EDITORIAS[ed]
        dur = ep.get("duration_min")
        return (
            f'<a class="grade-item" data-ed="{ed}" href="{slug}.html">'
            f'<img class="grade-thumb" src="{html.escape(img, quote=True)}" alt="{html.escape(title, quote=True)}" loading="lazy">'
            f'<div><p class="grade-eyebrow">{html.escape(ed_label, quote=True)}</p>'
            f'<h2 class="grade-title">{html.escape(title, quote=True)}</h2>'
            f'<div class="grade-meta">{html.escape(date_br(ep.get("date") or ""), quote=True)} · {html.escape(str(dur) if dur else "—", quote=True)} min</div>'
            f"</div></a>"
        )

    # Agrupa os itens por mês (chave YYYY-MM da data do episódio)
    meses: dict[str, list] = {}
    for ep in rest:
        chave = str(ep.get("date") or "")[:7]
        if len(chave) != 7:
            chave = "0000-00"
        meses.setdefault(chave, []).append(ep)

    sections = []
    for i, chave in enumerate(sorted(meses.keys(), reverse=True)):
        itens = meses[chave]
        try:
            ano, mes = chave.split("-")
            label = f"{MESES_PT[int(mes) - 1]} {ano}"
        except Exception:
            label = chave
        expandido = i == 0  # mês mais recente (atual) expandido
        itens_html = "\n".join(item_html(e) for e in itens)
        colapsado = "" if expandido else " colapsado"
        ver_mais = ""
        if not expandido and len(itens) > 6:
            extra = len(itens) - 6
            ver_mais = (
                f'<button class="mes-ver-mais" type="button">Ver todos de {html.escape(label, quote=True)} → '
                f'<span class="mes-ver-mais-count">+{extra}</span></button>'
            )
        sections.append(
            f'<section class="grade-mes" data-mes="{chave}">'
            f'<div class="mes-header"><h2 class="mes-titulo">{html.escape(label, quote=True)}</h2>'
            f'<span class="mes-count">{len(itens)} artigos</span></div>'
            f'<div class="mes-itens{colapsado}">\n{itens_html}\n</div>\n{ver_mais}'
            f"</section>"
        )
        # Espaços de publicidade ENTRE as seções mensais (fora das .grade-mes)
        if i in (0, 1):
            sections.append(AD_SLOT_HTML)
    grade_items = "\n".join(sections)
    return HOME_TMPL.format(
        css=SHARED_CSS + HOME_CSS,
        url=f"{BASE}/noticias/",
        base=BASE,
        img=GENERIC_IMG,
        hero_url=f"{slugify(hero.get('title') or '')}.html" if hero else "#",
        hero_img=html.escape(hero.get("cover_url_abs") or GENERIC_IMG, quote=True) if hero else GENERIC_IMG,
        hero_alt=html.escape(hero.get("title") or "", quote=True) if hero else "",
        hero_kicker=html.escape(EDITORIAS[editoria_of(hero)][1], quote=True) if hero else "",
        hero_title=html.escape(hero.get("title") or "", quote=True) if hero else "",
        hero_meta=html.escape(f"{date_br(hero.get('date') or '')} · {hero.get('duration_min') or '—'} min", quote=True) if hero else "",
        hero_desc=html.escape((hero.get("excerpt") or "")[:200], quote=True) if hero else "",
        grade_items=grade_items,
    )


def script_path_for(ep: dict) -> Path | None:
    eid = str(ep.get("id") or "")
    date = str(ep.get("date") or "")
    if ep.get("type") == "especial":
        candidates = [
            EPISODES_DIR / f"{eid}.md",
            PUBLIC / "episodes" / f"{eid}.md",
            ROOT / "output" / "brasil_e_mundo" / "episodes" / f"{eid}.md",
        ]
    else:
        candidates = [EPISODES_DIR / f"{date}.md"]
    for c in candidates:
        if c.exists():
            return c
    return None


def main() -> int:
    catalog = json.loads((PUBLIC / "data" / "episodes.json").read_text(encoding="utf-8"))
    eps = catalog.get("episodes", [])
    eps.sort(key=lambda e: e.get("date") or "", reverse=True)
    src_names = load_sources_map()
    NOTICIAS_DIR.mkdir(parents=True, exist_ok=True)

    # limpa páginas antigas (slugs mudam com o título)
    for old in NOTICIAS_DIR.glob("*.html"):
        old.unlink()

    written = 0
    missing = []
    for ep in eps:
        sp = script_path_for(ep)
        if not sp:
            missing.append(str(ep.get("id")))
            continue
        slug, page = build_article(ep, sp.read_text(encoding="utf-8"), src_names)
        (NOTICIAS_DIR / f"{slug}.html").write_text(page, encoding="utf-8")
        written += 1

    (NOTICIAS_DIR / "index.html").write_text(build_home(eps), encoding="utf-8")
    write_ads_js()
    print(f"Artigos: {written} | Sem roteiro: {len(missing)} | Home: index.html | ads.js")
    if missing:
        print(f"  sem roteiro .md: {missing[:5]}...")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())
