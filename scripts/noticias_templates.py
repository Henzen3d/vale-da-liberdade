#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Templates das páginas de notícia — identidade: preto puro / hairline / Inter / âmbar #e8a23d.
Estrutura editorial referência: BBC News / El País América (destaque + grade densa,
hierarquia por peso/tamanho, hairline). Sem prefixos de locutor no corpo (quem lê, lê a notícia).
"""

SHARED_CSS = """
:root{
  --bg:#000000; --panel:#0a0a0a; --panel-2:#101010;
  --text:#f2f2ee; --body:#d6d6d1; --muted:#8a8a86;
  --hairline:rgba(255,255,255,0.12); --hairline-strong:rgba(255,255,255,0.22);
  --accent:#e8a23d; --accent-soft:rgba(232,162,61,0.16);
  --maxw:1080px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit}
img{display:block}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
::selection{background:var(--accent-soft)}

.topbar{position:sticky;top:0;z-index:20;background:rgba(0,0,0,0.92);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--hairline)}
.topbar-inner{max-width:1080px;margin:0 auto;padding:12px 20px;display:flex;
  align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:9px;text-decoration:none;font-weight:800;
  letter-spacing:0.06em;font-size:14px}
.brand-mark{width:11px;height:11px;background:var(--accent);border-radius:3px;flex-shrink:0}
.brand b{font-weight:800}
.brand .sub{color:var(--muted);font-weight:600;font-size:12px;letter-spacing:0.04em}
.back-link{color:var(--muted);text-decoration:none;font-size:13px;font-weight:600;
  display:inline-flex;align-items:center;gap:6px;transition:color .15s ease}
.back-link:hover{color:var(--text)}

.wrap{max-width:var(--maxw);margin:0 auto;padding:28px 20px 80px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
  color:var(--accent);margin:0 0 12px}
h1{font-size:clamp(28px,5.2vw,42px);font-weight:800;line-height:1.14;
  letter-spacing:-0.02em;margin:0 0 14px}
.meta{font-size:13px;color:var(--muted);display:flex;flex-wrap:wrap;gap:6px 14px;
  margin-bottom:22px}
.meta .sep{opacity:.5}
.cover{width:100%;border-radius:12px;border:1px solid var(--hairline);
  max-height:440px;object-fit:cover;margin:0 0 22px}
.listen{display:inline-flex;align-items:center;gap:9px;background:var(--accent);
  color:#000;text-decoration:none;font-weight:800;font-size:15px;padding:13px 22px;
  border-radius:999px;margin:0 0 30px;transition:filter .15s ease,transform .12s ease}
.listen:hover{filter:brightness(1.08)}
.listen:active{transform:scale(.98)}
/* Coluna de leitura: largura do container (mesma da home) */
.article-body{max-width:var(--maxw);margin:0 auto;font-size:17px;line-height:1.78;color:var(--body)}
.article-body p{margin:0 0 18px}
.article-body h2{margin:34px 0 12px}
.article-body .quadro{font-size:12px;font-weight:700;letter-spacing:1.2px;
  text-transform:uppercase;color:var(--accent);border-top:1px solid var(--hairline);
  padding-top:20px}
.article-body ul{margin:0 0 18px;padding-left:22px}
.article-body li{margin:0 0 8px}
.article-body .lead{color:var(--text);font-size:18px;line-height:1.7}
.sources{max-width:var(--maxw);margin:34px auto 0;border-top:1px solid var(--hairline);
  padding-top:18px;font-size:12.5px;color:var(--muted);line-height:1.7}
.sources b{color:#bdbdb8;font-weight:600}
.foot-nav{max-width:var(--maxw);margin:44px auto 0;border-top:1px solid var(--hairline);
  padding-top:20px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}

/* Espaços de publicidade (Google AdSense) */
.ad-slot{margin:26px auto;max-width:var(--maxw);min-height:60px}
.ad-slot .ad-label{font-size:10.5px;font-weight:600;letter-spacing:1.2px;
  text-transform:uppercase;color:var(--muted);margin:0 0 8px;text-align:center}
.ad-slot .adsbygoogle{display:block;min-height:60px;background:var(--panel);
  border:1px solid var(--hairline);border-radius:10px}
.ad-slot.ad-slot-inline{margin:18px 0}
.ad-slot[hidden]{display:none}

@media(max-width:560px){
  .article-body{font-size:16px;line-height:1.72}
  .topbar-inner{padding:10px 16px}
}
@media(prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *{transition:none!important}
}
"""

ARTICLE_TMPL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Vale da Liberdade</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Vale da Liberdade">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="720">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{img}">
<link rel="canonical" href="{url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="{base}/noticias/"><span class="brand-mark"></span><b>VALE DA LIBERDADE</b><span class="sub">NOTÍCIAS</span></a>
    <a class="back-link" href="{base}/noticias/">← Todas as notícias</a>
  </div>
</header>
<main class="wrap">
  <p class="eyebrow">{kicker}</p>
  <h1>{title}</h1>
  <div class="meta">
    <span>{data}</span><span class="sep">·</span><span>{duracao} min de áudio</span><span class="sep">·</span><span>{editoria}</span>
  </div>
  <img class="cover" src="{img}" alt="" loading="eager">
  <a class="listen" href="{player_url}">▶ Ouvir o episódio</a>
  <div class="ad-slot"><p class="ad-label">Publicidade</p><ins class="adsbygoogle" data-ad-client="" data-ad-slot="" data-ad-format="auto" data-full-width-responsive="true"></ins></div>
  <div class="article-body">
{body}
  </div>
  <div class="ad-slot"><p class="ad-label">Publicidade</p><ins class="adsbygoogle" data-ad-client="" data-ad-slot="" data-ad-format="auto" data-full-width-responsive="true"></ins></div>
  {sources_html}
  <nav class="foot-nav">
    <a class="back-link" href="{base}/noticias/">← Todas as notícias</a>
    <a class="back-link" href="{base}/">{base} — ouvir o jornal</a>
  </nav>
</main>
<script src="ads.js" defer></script>
</body>
</html>
"""

HOME_CSS = """
.hero{max-width:1080px;margin:0 auto;padding:30px 20px 0}
.hero-link{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);
  gap:30px;text-decoration:none;align-items:center}
.hero-link:hover .hero-title{color:var(--accent)}
.hero-img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:12px;
  border:1px solid var(--hairline)}
.hero-eyebrow{font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
  color:var(--accent);margin:0 0 10px}
.hero-title{font-size:clamp(26px,4.6vw,40px);font-weight:800;line-height:1.14;
  letter-spacing:-0.02em;margin:0 0 12px;transition:color .15s ease}
.hero-meta{font-size:13px;color:var(--muted)}
.hero-desc{font-size:16px;color:var(--body);line-height:1.6;margin:12px 0 0;max-width:52ch}

.editorias{max-width:1080px;margin:0 auto;padding:18px 20px 0;display:flex;
  flex-wrap:wrap;gap:8px;border-bottom:1px solid var(--hairline)}
.editorias button{appearance:none;background:none;border:1px solid var(--hairline);
  color:var(--muted);font:600 13px 'Inter',sans-serif;padding:7px 14px;border-radius:999px;
  cursor:pointer;transition:color .15s ease,border-color .15s ease,background .15s ease}
.editorias button:hover{color:var(--text);border-color:var(--hairline-strong)}
.editorias button.active{color:#000;background:var(--accent);border-color:var(--accent)}

.grade{max-width:1080px;margin:0 auto;padding:8px 20px 72px}
.grade-item{display:grid;grid-template-columns:140px minmax(0,1fr);gap:18px;
  padding:20px 0;border-bottom:1px solid var(--hairline);text-decoration:none;align-items:start}
.grade-item:last-child{border-bottom:none}
.grade-item:hover .grade-title{color:var(--accent)}
.grade-thumb{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px;
  border:1px solid var(--hairline)}
.grade-eyebrow{font-size:10.5px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;
  color:var(--accent);margin:0 0 6px}
.grade-title{font-size:17px;font-weight:700;line-height:1.35;letter-spacing:-0.01em;
  margin:0 0 8px;transition:color .15s ease}
.grade-meta{font-size:12px;color:var(--muted)}
.grade-note{font-size:12.5px;color:var(--muted);padding:26px 20px 60px;text-align:center}

@media(max-width:680px){
  .hero-link{grid-template-columns:1fr;gap:14px}
  .grade-item{grid-template-columns:96px minmax(0,1fr);gap:12px;padding:16px 0}
  .grade-thumb{width:96px}
  .grade-title{font-size:15.5px}
}
"""

HOME_TMPL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notícias — Vale da Liberdade</title>
<meta name="description" content="Leia as notícias comentadas no Vale da Liberdade — Blumenau, Alto Vale, SC, Brasil e Mundo.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Vale da Liberdade">
<meta property="og:title" content="Notícias — Vale da Liberdade">
<meta property="og:description" content="Leia as notícias comentadas no Vale da Liberdade.">
<meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Notícias — Vale da Liberdade">
<meta name="twitter:description" content="Leia as notícias comentadas no Vale da Liberdade.">
<link rel="canonical" href="{url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="{url}"><span class="brand-mark"></span><b>VALE DA LIBERDADE</b><span class="sub">NOTÍCIAS</span></a>
    <a class="back-link" href="{base}/">Ouvir o jornal</a>
  </div>
</header>

<section class="hero" aria-label="Destaque">
  <a class="hero-link" href="{hero_url}">
    <img class="hero-img" src="{hero_img}" alt="" loading="eager">
    <div>
      <p class="hero-eyebrow">{hero_kicker}</p>
      <h1 class="hero-title">{hero_title}</h1>
      <div class="hero-meta">{hero_meta}</div>
      <p class="hero-desc">{hero_desc}</p>
    </div>
  </a>
</section>

<nav class="editorias" aria-label="Editorias">
  <button type="button" class="active" data-ed="todas" aria-pressed="true">Todas</button>
  <button type="button" data-ed="diario" aria-pressed="false">Diário</button>
  <button type="button" data-ed="bm" aria-pressed="false">Brasil e Mundo</button>
  <button type="button" data-ed="economia" aria-pressed="false">Economia</button>
  <button type="button" data-ed="tecnologia" aria-pressed="false">Tecnologia</button>
</nav>

<div class="ad-slot"><p class="ad-label">Publicidade</p><ins class="adsbygoogle" data-ad-client="" data-ad-slot="" data-ad-format="auto" data-full-width-responsive="true"></ins></div>

<section class="grade" id="grade" aria-label="Todas as notícias">
{grade_items}
</section>
<p class="grade-note" id="gradeNote" hidden>Nenhuma notícia nesta editoria por enquanto.</p>

<script>
(function(){{
  var btns=document.querySelectorAll('.editorias button');
  var items=document.querySelectorAll('.grade-item');
  var note=document.getElementById('gradeNote');
  function apply(ed){{
    var shown=0;
    items.forEach(function(it){{
      var show=(ed==='todas')||it.getAttribute('data-ed')===ed;
      it.hidden=!show;
      if(show)shown++;
    }});
    if(note)note.hidden=shown!==0;
    btns.forEach(function(b){{
      var active=b.getAttribute('data-ed')===ed;
      b.classList.toggle('active',active);
      b.setAttribute('aria-pressed',active?'true':'false');
    }});
  }}
  btns.forEach(function(b){{
    b.addEventListener('click',function(){{apply(b.getAttribute('data-ed'));}});
  }});
}})();
</script>
<script src="ads.js" defer></script>
</body>
</html>
"""
