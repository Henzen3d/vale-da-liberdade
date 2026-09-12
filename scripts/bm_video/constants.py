"""Constantes de layout, caminhos e limites do vídeo BM (sem Playwright)."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts"

MOCKUP_DIR = ROOT / "references" / "youtube" / "mockup-browser"

MOCKUP_HTML = "mockup-browser.html" if (MOCKUP_DIR / "mockup-browser.html").exists() else "mockup-brower.html"

WALLPAPER_DIR = MOCKUP_DIR / "wallpaper"

BROLL_DIR = ROOT / "references" / "youtube" / "broll"

BROLL_INDEX = BROLL_DIR / "_index.json"

AVATAR_LOOP = (
    ROOT / "references" / "youtube" / "Apresentadores"
    / "Peter Albuquerque" / "Peter-Loop-Picsart-BackgroundRemover.mp4"
)

AVATAR_CROP = "910:720:54:0"

AVATAR_SCALE = "546:432"

AVATAR_OVERLAY = "0:H-h+38"

AVATAR_START_DELAY_S = 1.0

APP_URL = "https://news.mob.tec.br"

BLANK_SHOT_STDDEV = float(os.environ.get("BM_BLANK_SHOT_STDDEV", "6.0"))

MIN_SHOT_BYTES = int(os.environ.get("BM_MIN_SHOT_BYTES", "20000"))

EPS_DIR = ROOT / "output" / "brasil_e_mundo" / "episodes"

AUDIO_DIR = ROOT / "output" / "brasil_e_mundo" / "audio"

VIDEOS_OUT = ROOT / "output" / "videos"

STATE_PATH = ROOT / "output" / "brasil_e_mundo" / "videos_published.json"

WORK_ROOT = ROOT / "output" / "brasil_e_mundo" / "mockup_video"

CAPTURE_CACHE_DIR = ROOT / "output" / "brasil_e_mundo" / "capture-cache"

THUMB_DIRS = (ROOT / "thumbnails", ROOT / "public" / "thumbnails")

LAST_VIDEOS_PATH = ROOT / "output" / "brasil_e_mundo" / "last_videos.json"

BRANDING_DIR = ROOT / "branding"

INTRO_AUDIO_DIR = BRANDING_DIR / "audio" / "intro"

OUTRO_CANONICAL = BRANDING_DIR / "outro.mp4"

OUTRO_PRONTOS_DIR = BRANDING_DIR / "encerramento" / "prontos"

GRAVACOES_DIR = BRANDING_DIR / "encerramento" / "gravacoes"

AUDIO_OUTRO_DIR = BRANDING_DIR / "audio" / "outro"

MAX_DURATION_S = 480.0

SOFT_DURATION_S = 330.0

MAX_PER_RUN = 1

WINDOW_DAYS = 2

MAX_SCENES = 8

MAX_PER_HOST = 2

CACHE_MAX_AGE_HOURS = 36.0

CAPTURE_CACHE_VERSION = "handler-v4"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

FIXED_TAGS = ("Brasil e Mundo", "Vale da Liberdade", "notícias", "comentário")

DESC_TEMPLATE = (
    "{summary}\n\n"
    "Ouça no app: {app}\n\n"
    "{assista}"
    "Fontes:\n{refs}\n\n"
    "#BrasilEMundo #{tags}\n"
)

ASSISTA_TAMBEM_N = 2

_X_STATUS_RE = re.compile(r"(?:x|twitter)\.com/[^/]+/status/(\d+)")

_X_EMBED_WRAP = """<!doctype html><html><head><meta charset="utf-8">
<style>
 html,body{margin:0;height:100%;background:#ffffff;
   display:flex;align-items:center;justify-content:center;
   font-family:system-ui,-apple-system,'Segoe UI',sans-serif}
 #box{width:640px;transform:scale(1.3);transform-origin:center center}
 iframe{width:100%;border:0;display:block}
</style></head><body>
<div id="box"><iframe id="tw"
 src="https://platform.twitter.com/embed/Tweet.html?id=__TWEET_ID__&theme=light&dnt=true&lang=pt"
 scrolling="no" allowtransparency="true"></iframe></div>
<script>
 window.addEventListener('message', function(e){
   try{
     var d = JSON.parse(e.data);
     var p = d && d['twttr.embed'] && d['twttr.embed'].params;
     var h = p && p[0] && p[0].height;
     if(h){ document.getElementById('tw').style.height = h + 'px'; }
   }catch(_){}
 });
 setTimeout(function(){
   var f = document.getElementById('tw');
   if(!f.style.height){ f.style.height = '540px'; }
 }, 3000);
</script></body></html>"""

_INSTAGRAM_POST_RE = re.compile(r"instagram\.com/(?:p|reel|reels|tv)/([^/?#&]+)")

_PAYWALL_HINTS_JS = """() => {
  const t = (document.body ? document.body.innerText : '').toLowerCase();
  const hits = [];
  const pats = [
    ['paywall', /continue lendo|assine para continuar|subscribe to (continue|read)|conteúdo exclusivo para assinantes|acesso restrito a assinantes|faça sua assinatura|já é assinante/],
    ['adblock', /desative o adblock|disable your ad ?blocker|whitelist this site|permita os anúncios/],
    ['consent-wall', /escolha seu plano|select your plan|we value your privacy|nós valorizamos sua privacidade/],
    ['ad-interstitial', /publicidade|advertisement/i.test(document.querySelector('[id*="interstitial"], [class*="interstitial"]')?.innerText || '') && !!(document.querySelector('[id*="interstitial"], [class*="interstitial"]')?.offsetParent)],
  ];
  for (const [name, re] of pats) {
    try { if (re.test(t)) hits.push(name); } catch(e) {}
  }
  // paywall estrutural: conteúdo principal menor que o overlay
  try {
    const pay = document.querySelector('[class*="paywall"], [id*="paywall"], [class*="subscription-wall"]');
    if (pay && pay.offsetParent) hits.push('paywall-element');
  } catch(e) {}
  return hits;
}"""

_SCROLL_PAST_ADVERTS_JS = """({maxScrolls}) => {
  let scrolled = 0;
  for (let i = 0; i < maxScrolls; i++) {
    const t = (document.body ? document.body.innerText : '').toLowerCase();
    const blocked =
      t.includes('assine para continuar') || t.includes('subscribe to continue') ||
      t.includes('conteúdo exclusivo para assinantes') || t.includes('desative o adblock') ||
      t.includes('disable your ad blocker');
    if (!blocked) break;
    window.scrollBy(0, window.innerHeight * 0.9);
    scrolled += Math.round(window.innerHeight * 0.9);
  }
  return Promise.resolve({scrolled});
}"""

_DISMISS_BUTTONS = (
    "button:has-text('Agora não')",
    "button:has-text('Agora Nao')",
    "div[role='button']:has-text('Agora não')",
    "div[role='button']:has-text('Not now')",
    "button:has-text('Not now')",
    "button:has-text('Not Now')",
    "div[role='button']:has-text('Not Now')",
    "button:has-text('Decline optional cookies')",
    "button:has-text('Recusar cookies opcionais')",
    "button:has-text('Only allow essential cookies')",
    "button:has-text('Aceitar')",
    "button:has-text('Aceito')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "#onetrust-accept-btn-handler",
    "[aria-label='Close']",
    "[aria-label='Fechar']",
    "[aria-label='Dismiss']",
)

_PREPARE_JS = """({kind}) => {
  const hide = (el) => {
    if (!el) return;
    el.style.setProperty('display', 'none', 'important');
    el.style.setProperty('visibility', 'hidden', 'important');
    el.style.setProperty('pointer-events', 'none', 'important');
  };

  // Placeholders vazios (hero cinza da BBC / branco do G1 quando a imagem não carrega).
  document.querySelectorAll(
    'figure, picture, [data-testid="image"], [data-component="image-block"], .content-media, .content-featured-image, [class*="media-container"]'
  ).forEach(el => {
    const img = el.querySelector('img');
    const r = el.getBoundingClientRect();
    const emptyImg = !img || !img.naturalWidth;
    if (r.height > 80 && emptyImg) hide(el);
  });

  if (kind === 'instagram') {
    document.querySelectorAll('[role="dialog"], [role="presentation"]').forEach(el => {
      const t = (el.innerText || '').toLowerCase();
      if (t.includes('entrar') || t.includes('log in') || t.includes('sign up') || t.includes('inscreva')) {
        hide(el);
      }
    });
  }

  document.documentElement.style.overflow = 'auto';
  if (document.body) document.body.style.overflow = 'auto';

  const h1s = Array.from(document.querySelectorAll('h1')).sort(
    (a, b) => ((b.innerText || '').trim().length) - ((a.innerText || '').trim().length)
  );
  const h1 = h1s[0] || document.querySelector('[role="main"] h1, article h1');

  if (h1) {
    const ty = h1.getBoundingClientRect().top;
    document.querySelectorAll('div, figure, section, aside').forEach(el => {
      if (el.contains(h1) || h1.contains(el)) return;
      const r = el.getBoundingClientRect();
      if (r.height < 100 || r.width < 240) return;
      if (r.bottom <= 8 || r.top >= ty - 4) return;
      const txt = (el.innerText || '').trim();
      if (txt.length > 40) return;
      const img = el.querySelector('img');
      if (img && img.naturalWidth > 10) return;
      hide(el);
    });
  }

  let sticky = 0;
  document.querySelectorAll('header, nav, [class*="header"]').forEach(el => {
    const st = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if ((st.position === 'fixed' || st.position === 'sticky') && r.top < 90 && r.height < 160) {
      sticky = Math.max(sticky, r.bottom);
    }
  });

  if (h1) {
    const y = h1.getBoundingClientRect().top + window.scrollY - sticky - 8;
    window.scrollTo(0, Math.max(0, y));
    return {scrolledTo: 'h1', y: Math.max(0, y), sticky, kind};
  }
  if (kind === 'bbc' || kind === 'g1') {
    const fallback = kind === 'g1' ? 360 : 280;
    window.scrollBy(0, fallback);
    return {scrolledTo: kind + '-fallback', y: fallback};
  }
  return {scrolledTo: 'none', y: 0};
}"""

VAAPI_LOCK_PATH = Path("/tmp/vale-bm-vaapi.lock")

_CTA_RE = re.compile(
    r"(deixe seu like|inscreva-se|compartilhe este v[ií]deo|um abra[cç]o|até a pr[oó]xima)",
    re.I,
)

_OUTLET_PREFIX_RE = re.compile(
    r"^(?:a |o )?(folha(?: de s[ãa]o paulo)?|g1|veja|cnn(?: brasil)?|"
    r"estad[aã]o|bbc|uol|band|jovem pan|reuters|associated press|ap)\b[\s,:—-]*",
    re.I,
)

_BLOCK_TEXT_MARKERS = (
    "access denied",
    "you don't have permission to access",
    "voce nao tem permissao",
    "acesso restrito",
    "errors.edgesuite.net",
    "request blocked",
    "attention required",
    "just a moment",
    "are you a robot",
    "perimeterx",
    "http error 403",
    "403 forbidden",
    "temporarily offline",
)

_WAIT_STYLED_JS = """() => {
  if (document.readyState !== 'complete') return false;
  const sheets = document.styleSheets;
  if (!sheets || sheets.length === 0) return false;
  let cssOk = false;
  for (const s of sheets) {
    try {
      if (s.cssRules && s.cssRules.length > 0) { cssOk = true; break; }
    } catch (e) {
      cssOk = true; // CSS cross-origin já aplicado no layout
      break;
    }
  }
  if (!cssOk) return false;
  const imgs = [...document.images].filter((im) => {
    const r = im.getBoundingClientRect();
    return r.width >= 60 && r.height >= 40 && r.bottom > 0 && r.top < innerHeight + 200;
  });
  if (imgs.length === 0) return true;
  const loaded = imgs.filter((im) => im.complete && im.naturalWidth > 0);
  return loaded.length >= Math.min(imgs.length, 2) || loaded.length >= 1;
}"""

RENDER_NODE = "/dev/dri/renderD128"

INTRO_VOICE_DELAY_S = 1.5

INTRO_DUCK_UNTIL_S = 8.0

INTRO_FADE_END_S = 15.0

INTRO_DUCK_VOL = 0.18

INTRO_MIX_TAG = "v2"

OUTRO_TAIL_S = 20.0

OUTRO_DUCK_VOL = 0.12

OUTRO_PEAK_VOL = 0.75

OUTRO_SWELL_S = 12.0

OUTRO_FADEOUT_S = 4.0

OUTRO_MIX_TAG = "v2"

# Star-imports precisam dos nomes _privados (regex/JS) usados em capture/state.
__all__ = [k for k in list(globals()) if not k.startswith("__")]
