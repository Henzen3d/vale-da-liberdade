#!/usr/bin/env python3
"""Gera o episódio BM completo (10 quadros) como SUB-COMPOSIÇÕES HyperFrames.

Estrutura (recomendação do check — evita 40 overlays pesados num único HTML):
- compositions/qNN.html — 1 sub-composição por quadro (timeline própria, offsets
  relativos ao quadro, ~4 overlays pesados cada, como o q02 validado)
- index.html — raiz: um ÚNICO <audio> com o episódio completo + 10 mounts
  data-composition-src em sequência (sem overlap de áudio)

Padrão visual = preset vale-newsroom (2026-08-11): navegador com screenshot real
da matéria, pill de região (ABERTURA/PESQUISA/ANÁLISE), fonte + data, barra de
progresso global, avatar PiP placeholder, karaoke palavra a palavra, crossfade.

Uso (parametrizado p/ qualquer episódio):
    python3 build_episode_composition.py --video-id <ID> [--date DD/MM/AAAA]
    # quadros: references/youtube/prototype/quadros-<ID>.json
    # assets:  output/brasil_e_mundo/assets/<ID>/
    # áudio:   output/brasil_e_mundo/audio/<ID>_<data>.mp3
    # karaoke: references/youtube/prototype/generated/<qid>_words.json
"""
import argparse
import json
import os
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "project"
ROOT = HERE.parent.parent.parent.parent

ap = argparse.ArgumentParser(description="Gera composição HyperFrames de um episódio BM")
ap.add_argument("--video-id", default="EwZxO3DKHoQ",
                help="ID do episódio (default: EwZxO3DKHoQ)")
ap.add_argument("--date", default=None,
                help="Data do episódio DD/MM/AAAA (default: extraída do quadros.json ou nome do áudio)")
ap.add_argument("--project-dir", default=None,
                help="Diretório de saída da composição (default: project/ — use project-<ID> p/ manter episódios)")
ap.add_argument("--width", type=int, default=1920,
                help="Largura de captura da composição (default: 1920 → 1080p)")
ap.add_argument("--height", type=int, default=1080,
                help="Altura de captura da composição (default: 1080 → 1080p)")
ap.add_argument("--legenda-mode", default="destaques", choices=["destaques", "karaoke", "none"],
                help="Estilo de legenda (default: destaques — frase de impacto dinâmica estilo YC, "
                     "sem karaoke contínuo; karaoke = palavra a palavra antigo; none = sem legenda)")
args = ap.parse_args()

# Modo de legenda (decisão 2026-08-12): usuário achou o karaoke palavra a
# palavra "poluído". "destaques" mostra UMA frase-chave grande que entra e sai
# em ponto estratégico de cada quadro (estilo Y Combinator). "karaoke" preserva
# o comportamento antigo. "none" remove qualquer legenda.
LEGENDA_MODE = args.legenda_mode

# Design interno é 1920×1080 (vale-newsroom); o viewport de captura pode ser
# menor (ex.: 1280×720 via --width 1280 --height 720) — o body escala o design
# inteiro via CSS transform. PADRÃO = 1080p nativo (decisão 2026-08-12: 720p
# via scale deixava o texto com aspecto "estêncil"; 1080p não escala nada).
VIEW_W, VIEW_H = args.width, args.height
SCALE = VIEW_W / 1920.0

if args.project_dir:
    PROJECT = HERE / args.project_dir
COMPOSITIONS = PROJECT / "compositions"

VIDEO_ID = args.video_id
QUADROS_PATH = HERE.parent / f"quadros-{VIDEO_ID}.json"
if not QUADROS_PATH.exists():
    print(f"❌ quadros não encontrado: {QUADROS_PATH}")
    print("   Rode antes: bm_pipeline.py roteiro/audio/assets --video-id <ID>")
    raise SystemExit(1)
QUADROS = json.load(open(QUADROS_PATH))
ASSETS_EP = ROOT / "output/brasil_e_mundo/assets" / VIDEO_ID
GEN = HERE.parent / "generated"
OUT = PROJECT / "index.html"
A = PROJECT / "assets"
A.mkdir(parents=True, exist_ok=True)
COMPOSITIONS.mkdir(parents=True, exist_ok=True)

# áudio completo: procura <ID>_*.mp3 no diretório de áudio
AUDIO_DIR = ROOT / "output/brasil_e_mundo/audio"
_AUDIO_CANDIDATES = sorted(AUDIO_DIR.glob(f"{VIDEO_ID}_*.mp3"))
if not _AUDIO_CANDIDATES:
    print(f"❌ áudio não encontrado: {AUDIO_DIR}/{VIDEO_ID}_*.mp3")
    raise SystemExit(1)
AUDIO_FULL = _AUDIO_CANDIDATES[0]

# ---- 1. copia assets ----
for q in QUADROS["quadros"]:
    qid = q["id"]
    for kind, ext in (("image.jpg", "bg.jpg"), ("screenshot.png", "shot.png")):
        src = ASSETS_EP / qid / kind
        if src.exists():
            shutil.copy(src, A / f"{qid}_{ext}")
    seg = Path("/tmp/bm_karaoke") / f"{qid}.mp3"
    if seg.exists():
        shutil.copy(seg, A / f"{qid}_audio.mp3")
if not (A / "episodio.mp3").exists():
    shutil.copy(AUDIO_FULL, A / "episodio.mp3")

HAS_AVATAR = (A / "avatar_loop.mp4").exists()
TOTAL_S = QUADROS["total_duration_ms"] / 1000.0
furl = (QUADROS.get("fonte_principal") or {}).get("fonte_url") or ""
FONTE_NOME = (QUADROS.get("fonte_principal") or {}).get("fonte_veiculo") or "Gazeta do Povo"
# nome curto do veículo derivado do domínio (ex.: gazetadopovo.com.br → GAZETA DO POVO)
import re as _re
_DOMAIN_NAMES = {
    "gazetadopovo": "GAZETA DO POVO", "estadao": "ESTADÃO", "folha": "FOLHA DE S.PAULO",
    "cnnbrasil": "CNN BRASIL", "globo": "GLOBO", "g1": "G1", "uol": "UOL",
    "r7": "R7", "veja": "VEJA", "exame": "EXAME", "infomoney": "INFOMONEY",
    "valor": "VALOR ECONÔMICO", "correiodobrasil": "CORREIO DO BRASIL",
    "brasil247": "BRASIL 247", "metropoles": "METRÓPOLES", "poder360": "PODER360",
    "jornaldacidade": "JORNAL DA CIDADE", "diariodocentro": "DIÁRIO DO CENTRO",
}
_dom = _re.search(r"https?://([^/]+)", furl or "")
if _dom:
    _host = _dom.group(1).replace("www.", "").split(".")[0].lower()
    FONTE_NOME = _DOMAIN_NAMES.get(_host, _host.upper())
FONTE_URL = furl.replace("https://", "").replace("http://", "")[:46] + ("…" if len(furl) > 46 else "")

# Vale Newsroom — pill de região por quadro (blockframe): ABERTURA / PESQUISA / ANÁLISE / EXCLUSIVO
def _pill_for(q: dict) -> str:
    section = (q.get("section") or "").lower()
    if section in ("abertura",):
        return "ABERTURA"
    if section in ("fechamento",):
        return "ENCERRAMENTO"
    # quadros com dado numérico central = PESQUISA; comentário de opinião = ANÁLISE
    txt = (q.get("script_text") or "").lower()
    if any(w in txt for w in ("pesquisa", "levantamento", "gerp", "votos válidos", "percentual")):
        return "PESQUISA"
    if any(w in txt for w in ("institutos", "viés", "tse", "datafolha", "quaest")):
        return "ANÁLISE"
    return "ANÁLISE"

# data do episódio: --date > nome do áudio (<ID>_YYYY-MM-DD.mp3) > data do quadros.json
def _episode_date() -> str:
    if args.date:
        return args.date
    import re as _re2
    m = _re2.search(r"(\d{4})-(\d{2})-(\d{2})", AUDIO_FULL.name)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    for key in ("data", "date", "publicado_em", "episode_date"):
        v = QUADROS.get(key)
        if v:
            return str(v)[:10].replace("-", "/")
    return ""

EPISODE_DATE = _episode_date()

KEYWORDS = set()

# KEYWORDS DINÂMICOS POR EPISÓDIO (fix 2026-08-12): antes era um set
# hardcoded do GERP (flávio, lula, 38%, gerp, pesquisa…) que destacava
# palavras de outro episódio no karaoke de TODOS os vídeos. Agora deriva
# do script real do episódio: números/percentuais SEMPRE + os termos mais
# frequentes do roteiro (excluindo stopwords comuns).
_STOP = {"de", "da", "do", "das", "dos", "um", "uma", "o", "a", "os", "as", "que",
         "com", "em", "para", "por", "no", "na", "nos", "nas", "e", "é", "como",
         "mais", "mas", "foi", "ser", "ter", "sobre", "não", "não", "se", "sua",
         "seu", "suas", "seus", "ele", "ela", "eles", "elas", "isso", "isto", "até"}
_WORD_RE = _re.compile(r"[a-zA-Zà-úÀ-Ú0-9%]+")
for _q in QUADROS["quadros"]:
    for _w in _WORD_RE.findall((_q.get("script_text") or "").lower()):
        if len(_w) > 2 and _w not in _STOP:
            KEYWORDS.add(_w)
# termos numéricos e percentuais entram sempre
KEYWORDS.update(w for w in list(KEYWORDS) if "%" in w or w.isdigit())

def is_keyword(w: str) -> bool:
    wl = w.strip(".,;:!?()\"'").lower()
    return wl in KEYWORDS or "%" in wl or wl.isdigit()

def _destaque_for(q: dict) -> str:
    """Frase de impacto para o modo 'destaques' (estilo YC): procura a frase
    com número/percentual/dado forte no script; senão, a primeira frase curta.
    Retorna '' quando não há material (abertura/fechamento sem texto útil)."""
    txt = (q.get("script_text") or "").strip()
    if not txt:
        return ""
    # frase com dado numérico/percentual tem prioridade
    import re as _re_d
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", txt) if len(f.strip()) > 14]
    if not frases:
        return ""
    for f in frases:
        if _re_d.search(r"\d[\d.,]*\s*%|\d+ (?:ponto|pontos|milh|bilh|trilh|voto|votos|anos|reais)", f):
            return f[:110]
    # senão a primeira frase que não seja genérica de transição
    _GEN = ("vamos", "agora", "então", "olha", "veja", "aqui", "hoje", "nesse", "nessa", "neste", "nesta")
    for f in frases[:3]:
        if not f.lower().startswith(_GEN):
            return f[:110]
    return frases[0][:110]


def _destaque_html(qid: str, d: float, frase: str) -> tuple[str, str]:
    """HTML + JS do destaque estilo YC: texto grande, entra ~48% do quadro,
    fica ~3s, sai. Retorna ('', '') se frase vazia."""
    if not frase:
        return "", ""
    t_in = max(d * 0.48, 2.0)
    t_out = min(t_in + 3.4, d - 1.0)
    html = f"""
      <div id="destaque-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="4">
        <div class="destaque" data-layout-allow-occlusion data-layout-allow-overlap>
          <div class="destaque-rule" id="destaque-rule"></div>
          <span class="destaque-text" id="destaque-text">{frase}</span>
        </div>
      </div>"""
    js = f"""
      tl.fromTo("#destaque-text", {{ y: 44, opacity: 0, scale: 0.96 }}, {{ y: 0, opacity: 1, scale: 1, duration: 0.6, ease: "power3.out" }}, {t_in:.3f});
      tl.fromTo("#destaque-rule", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.5, ease: "power3.out" }}, {t_in + 0.15:.3f});
      tl.to("#destaque-text", {{ y: -30, opacity: 0, duration: 0.5, ease: "power2.in" }}, {t_out:.3f});
      tl.to("#destaque-rule", {{ scaleX: 0, duration: 0.4, ease: "power2.in" }}, {t_out + 0.05:.3f});"""
    return html, js


def words_for(qid: str) -> list[dict]:
    # ISOLAMENTO POR EPISÓDIO (fix 2026-08-12): words.json vivem em
    # generated/<video_id>/<qid>_words.json — antes eram compartilhados
    # (generated/q01_words.json sem ID) e a legenda de um episódio vazava
    # para o vídeo seguinte. Fallback para o caminho antigo por segurança.
    p = GEN / VIDEO_ID / f"{qid}_words.json"
    if not p.exists():
        p = GEN / f"{qid}_words.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

def split_lines(words: list[dict], max_chars: int = 78) -> list[list[tuple[int, dict]]]:
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append((i, w))
        if sum(len(x[1]["word"]) for x in cur) >= max_chars or i == len(words) - 1:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines

# ---- 2. CSS compartilhado (uma cópia por sub-composição) ----
CSS = """
      /* ===== Vale Newsroom — fundo #3B82F6 + Floating Lines (2026-08-13) ===== */
      html, body { margin: 0; width: __VIEW_W__px; height: __VIEW_H__px; overflow: hidden;
        background: #3B82F6; } /* Canvas BG azul Tailwind como no playground */
      body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: #f2f2ee;
        transform: scale(__SCALE__); transform-origin: 0 0; }
      /* Canvas overlay animado (Floating Lines estilo playground) */
      .floating-lines { position: absolute; inset: 0; width: 100%; height: 100%;
        pointer-events: none; z-index: 1; }
      /* Sobreposição de contraste sobre o azul pra manter legibilidade */
      .bg { position: absolute; inset: 0;
        background: radial-gradient(ellipse at 50% 42%, rgba(59,130,246,0.85) 0%, rgba(10,14,20,0.94) 70%); }
      .clip { position: absolute; inset: 0; width: 1920px; height: 1080px; }

      .bg-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0.28; }
      .bg-shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(10,14,20,0.55) 0%, rgba(10,14,20,0.30) 40%, rgba(10,14,20,0.78) 100%); }
      .glow { position: absolute; width: 1500px; height: 1500px; right: -260px; top: -300px; border-radius: 50%;
        background: radial-gradient(circle, rgba(232,162,61,0.20) 0%, rgba(232,162,61,0.05) 45%, transparent 72%); }
      .grid { position: absolute; inset: 0; opacity: 0.5;
        background-image: linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
                          linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
        background-size: 90px 90px; }
      .rings { position: absolute; right: -300px; top: -280px; width: 1060px; height: 1060px; }
      .rings i { position: absolute; border-radius: 50%; border: 3px solid rgba(232,162,61,0.14); }
      .rings .r1 { inset: 0; }
      .rings .r2 { inset: 150px; border-width: 2px; border-color: rgba(232,162,61,0.10); }
      .rings .r3 { inset: 300px; width: 40px; height: 40px; border-width: 4px; border-color: rgba(232,162,61,0.28); }
      .vignette { position: absolute; inset: 0;
        background: radial-gradient(ellipse at 50% 42%, transparent 50%, rgba(2,5,9,0.62) 100%); }
      .grain { position: absolute; inset: 0; opacity: 0.045; pointer-events: none;
        background-image: repeating-linear-gradient(0deg, rgba(255,255,255,0.6) 0 1px, transparent 1px 3px); }

      .browser { position: absolute; left: 220px; top: 96px; width: 1560px; height: 844px;
        border-radius: 16px; border: 1px solid rgba(255,255,255,0.10); background: #0e141b;
        box-shadow: 0 40px 120px rgba(0,0,0,0.55); overflow: hidden;
        transform-origin: 50% 50%; }
      .chrome { height: 64px; display: flex; align-items: center; gap: 16px; padding: 0 20px;
        background: #111820; border-bottom: 1px solid rgba(255,255,255,0.07); }
      .traffic { display: flex; gap: 9px; }
      .traffic i { width: 14px; height: 14px; border-radius: 50%; display: block; }
      .t-red { background: #ff5f57; } .t-yel { background: #febc2e; } .t-grn { background: #28c840; }
      .tab { display: flex; align-items: center; gap: 10px; height: 40px; padding: 0 18px;
        background: #0e141b; border: 1px solid rgba(255,255,255,0.08); border-bottom: none;
        border-radius: 10px 10px 0 0; max-width: 560px; }
      .fav { width: 16px; height: 16px; border-radius: 4px; flex: none;
        background: linear-gradient(135deg, #e8a23d, #9c6213); }
      .tab-title { font-size: 15px; color: #c7d0da; font-weight: 500; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; }
      .ghost-tab { width: 36px; height: 40px; display: flex; align-items: center; justify-content: center;
        color: #9fb0c1; font-size: 22px; font-weight: 300; border-radius: 10px 10px 0 0; }
      .addr { flex: 1; display: flex; align-items: center; gap: 10px; height: 38px; padding: 0 18px;
        max-width: 660px; margin-left: auto; background: #0a0f15;
        border: 1px solid rgba(255,255,255,0.08); border-radius: 19px; }
      .addr svg { flex: none; }
      .url { font-size: 15px; color: #93a1b0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .progress { position: absolute; left: 0; top: 64px; width: 100%; height: 3px;
        background: linear-gradient(90deg, #e8a23d, #f5c476); transform-origin: 0 50%; z-index: 3; }
      .viewport { position: absolute; left: 0; right: 0; top: 64px; bottom: 0; overflow: hidden; background: #10161d; }
      .viewport img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
      .win-flash { position: absolute; inset: 0; border-radius: 16px; border: 3px solid rgba(232,162,61,0);
        opacity: 0; pointer-events: none; z-index: 4; }

      .avatar { position: absolute; left: 72px; bottom: 92px; width: 284px; height: 284px; z-index: 5; }
      .avatar-glow { position: absolute; inset: -34px; border-radius: 50%;
        background: radial-gradient(circle, rgba(232,162,61,0.32) 0%, transparent 62%); }
      .clip.avatar-video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
        border-radius: 50%; border: 5px solid #e8a23d;
        box-shadow: 0 0 0 3px rgba(232,162,61,0.22), 0 24px 70px rgba(0,0,0,0.55); }
      .avatar-disc { position: absolute; inset: 0; border-radius: 50%; border: 5px solid #e8a23d;
        overflow: hidden; background: radial-gradient(circle at 50% 28%, #3d4f61 0%, #24313f 52%, #131c26 100%);
        box-shadow: 0 0 0 3px rgba(232,162,61,0.22), 0 24px 70px rgba(0,0,0,0.55); }
      .avatar-disc .ph { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
        color: #e8a23d; font-size: 32px; font-weight: 700; letter-spacing: 5px; text-transform: uppercase; }
      .avatar-tag { position: absolute; left: 50%; bottom: -46px; transform: translateX(-50%);
        font-size: 19px; font-weight: 600; letter-spacing: 3px; text-transform: uppercase;
        color: #93a1b0; white-space: nowrap; }

      .legend-pill { position: absolute; left: 430px; right: 110px; bottom: 44px; height: 132px;
        background: linear-gradient(180deg, rgba(10,15,22,0.94), rgba(10,15,22,0.88));
        border: 1px solid rgba(232,162,61,0.30); border-left: 6px solid #e8a23d;
        border-radius: 12px; padding: 18px 34px 16px;
        box-shadow: 0 18px 50px rgba(0,0,0,0.45); overflow: hidden; }
      .legend-pill:empty { display: none; }
      .kline { position: absolute; left: 34px; right: 34px; top: 18px; font-size: 36px; line-height: 1.32;
        font-weight: 600; color: rgba(255,255,255,0.40); }
      .kline .kw { display: inline-block; }

      /* Destaque estilo YC (legenda-mode: destaques) — frase de impacto grande */
      .destaque { position: absolute; left: 240px; right: 240px; bottom: 170px; z-index: 5;
        display: flex; flex-direction: column; align-items: flex-start; gap: 18px; }
      .destaque-rule { display: block; width: 110px; height: 6px; border-radius: 3px; background: #e8a23d; }
      .destaque-text { font-size: 54px; line-height: 1.18; font-weight: 800; color: #ffffff;
        background: linear-gradient(90deg, rgba(8,12,18,0.92) 0%, rgba(8,12,18,0.78) 60%, rgba(8,12,18,0.55) 100%);
        padding: 18px 30px; border-radius: 14px; border-left: 8px solid #e8a23d;
        box-shadow: 0 14px 44px rgba(0,0,0,0.55); max-width: 1240px; }

      .kicker { position: absolute; left: 72px; top: 52px; display: flex; align-items: center; gap: 16px; }
      .kicker-rule { display: block; width: 64px; height: 4px; border-radius: 2px; background: #e8a23d; }
      .kicker-text { font-size: 22px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase;
        color: #f2f2ee; padding: 6px 14px 8px; border-radius: 8px;
        background: rgba(18,16,14,0.94); text-shadow: 0 2px 12px rgba(0,0,0,0.85); }
      .kicker-text em { font-style: normal; color: #e8a23d; font-weight: 600; }

      /* Vale Newsroom — label-pill de região (blockframe) + meta de veículo/data (editorial-forest) */
      .pill { display: inline-flex; align-items: center; height: 34px; padding: 0 16px; margin-left: 8px;
        border: 1px solid rgba(232,162,61,0.75); border-radius: 999px;
        font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace;
        font-size: 16px; font-weight: 600; letter-spacing: 2.2px; text-transform: uppercase;
        color: #e8a23d; background: rgba(18,16,14,0.92); white-space: nowrap;
        box-shadow: 0 2px 14px rgba(0,0,0,0.5); }
      .kicker-text { text-shadow: 0 2px 12px rgba(0,0,0,0.85); }

      .fonte { position: absolute; right: 72px; top: 52px; display: flex; align-items: center; gap: 12px;
        padding: 11px 18px; background: rgba(10,15,22,0.80); border: 1px solid rgba(255,255,255,0.10);
        border-radius: 8px; font-size: 17px; max-width: 980px; overflow: hidden; }
      .fonte-nome { color: #e8a23d; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase;
        white-space: nowrap; max-width: 380px; }
      .fonte-url { color: #93a1b0; font-weight: 500; white-space: nowrap; max-width: 460px; }
      .fonte-meta { color: #93a1b0; font-weight: 500; font-size: 15px; letter-spacing: 1px;
        padding-left: 12px; border-left: 1px solid rgba(255,255,255,0.14); flex: none;
        font-family: 'JetBrains Mono', 'DejaVu Sans Mono', monospace; }

      /* Vale Newsroom — barra de progresso permanente no rodapé do frame (bold-poster/cobalt-grid) */
      .frame-progress { position: absolute; left: 0; right: 0; bottom: 0; height: 4px;
        background: rgba(232,162,61,0.16); z-index: 9; pointer-events: none; }
      .frame-progress > i { display: block; height: 100%; width: 100%;
        background: #e8a23d; transform-origin: 0 50%; }

      .stamp { position: absolute; right: 150px; top: 150px; width: 300px; z-index: 6;
        transform: rotate(-6deg); }
      .stamp-core { background: rgba(10,15,22,0.92); border: 3px solid #e8a23d; border-radius: 16px;
        padding: 16px 10px 14px; text-align: center; box-shadow: 0 24px 60px rgba(0,0,0,0.5); }
      .stamp-num { display: block; font-size: 108px; font-weight: 900; line-height: 1; color: #e8a23d; }
      .stamp-label { display: block; font-size: 18px; font-weight: 600; color: #dfe5ea;
        margin-top: 10px; letter-spacing: 0.3px; }
      .stamp-label small { display: block; font-size: 13px; font-weight: 500; color: #93a1b0;
        letter-spacing: 1.5px; text-transform: uppercase; margin-top: 4px; }

      .outro { position: absolute; inset: 0; background: #0a0e14; opacity: 0; }
"""
# Substitui marcadores de viewport/escala (design interno segue 1920×1080)
CSS = (CSS.replace("__VIEW_W__", str(VIEW_W))
          .replace("__VIEW_H__", str(VIEW_H))
          .replace("__SCALE__", f"{SCALE:.6f}"))

STAMPS = {}

# STAMPS DINÂMICOS POR EPISÓDIO (fix 2026-08-12): antes os stamps eram
# hardcoded do episódio GERP ("38% / empate técnico / 1º turno") e apareciam
# em TODOS os vídeos. Agora são derivados do roteiro real do episódio:
# procura o percentual mais citado no script de cada quadro e usa só quando
# o quadro realmente fala de número/pesquisa/percentual.
import re as _re_stamp
_PCT_RE = _re_stamp.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")
for _q in QUADROS["quadros"]:
    _qid = _q["id"]
    _txt = (_q.get("script_text") or "") + " " + (_q.get("titulo") or "")
    _txt_l = _txt.lower()
    if not any(w in _txt_l for w in ("%", "percentual", "pesquisa", "levantamento",
                                     "votos", "pontos", "número", "número")):
        continue
    _pcts = _PCT_RE.findall(_txt)
    if _pcts:
        _top = max(set(_pcts), key=lambda p: _pcts.count(p))
        _num = _top.replace(".", ",")
        STAMPS[_qid] = (_num + "%", _txt.strip()[:38] or "destaque", "dado do episódio")

# ---- 3. gera UMA sub-composição por quadro ----
def build_quadro_html(q: dict) -> str:
    qid = q["id"]
    d = q["duration_ms"] / 1000.0
    is_comment = q.get("type") == "comentario_materia"
    shot = A / f"{qid}_shot.png"
    has_shot = shot.exists()
    img_src = f"assets/{qid}_shot.png" if (is_comment and has_shot) else f"assets/{qid}_bg.jpg"
    alt = f"Matéria — {FONTE_NOME}" if (is_comment and has_shot) else "Imagem do tópico"
    stamp = STAMPS.get(qid)
    pill = _pill_for(q)
    words = words_for(qid)
    lines = split_lines(words)

    if HAS_AVATAR:
        avatar = f"""
      <div class="avatar" id="avatar">
        <div class="avatar-glow" id="avatar-glow"></div>
        <video id="avatar-video" class="clip avatar-video" data-start="0" data-duration="{d:.3f}"
          data-track-index="3" src="assets/avatar_loop.mp4" muted playsinline loop
          data-layout-allow-occlusion data-layout-allow-overlap></video>
        <div class="avatar-tag" data-layout-allow-occlusion data-layout-allow-overlap>apresentação</div>
      </div>"""
    else:
        avatar = f"""
      <div id="avatar-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="3">
        <div class="avatar" id="avatar">
          <div class="avatar-glow" id="avatar-glow"></div>
          <div class="avatar-disc" data-layout-allow-occlusion data-layout-allow-overlap>
            <span class="ph">Peter</span>
          </div>
          <div class="avatar-tag" data-layout-allow-occlusion data-layout-allow-overlap>apresentação</div>
        </div>
      </div>"""

    kline_html = "\n".join(
        f'        <div class="kline" id="L{li+1}">' + " ".join(
            f'<span id="L{li+1}-w{gi}" class="kw" data-t="{max(w["start"], 0.3):.3f}">{w["word"]}</span>'
            for gi, (_, w) in enumerate(line)
        ) + "</div>"
        for li, line in enumerate(lines)
    )

    # ---- legenda: karaoke (palavra a palavra) OU destaque estilo YC ----
    destaque_html, destaque_js = "", ""
    legend_html = ""
    legend_js_in, legend_js_out = "", ""
    if LEGENDA_MODE == "karaoke":
        legend_html = f"""
      <div id="legend-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="4">
        <div class="legend-pill" id="legend-pill" data-layout-allow-occlusion data-layout-allow-overlap>
{kline_html}
        </div>
      </div>"""
        legend_js_in = ('      tl.fromTo("#legend-pill", {{ y: 52, opacity: 0 }}, '
                        '{{ y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }}, 0.3);')
        legend_js_out = ('      tl.to("#legend-pill", {{ opacity: 0, y: 26, duration: 0.5, ease: "power2.in" }}, fade - 0.4);')
    elif LEGENDA_MODE == "destaques":
        frase = _destaque_for(q)
        destaque_html, destaque_js = _destaque_html(qid, d, frase)
        kline_html = ""  # sem karaoke contínuo; só a frase de impacto
    else:  # none
        kline_html = ""

    stamp_html = ""
    if stamp:
        stamp_html = f"""
      <div id="stamp-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="7">
        <div class="stamp" data-layout-allow-occlusion data-layout-allow-overlap>
          <div class="stamp-core" id="stamp-core">
            <span class="stamp-num">{stamp[0]}</span>
            <span class="stamp-label">{stamp[1]}
              <small>{stamp[2]}</small>
            </span>
          </div>
        </div>
      </div>"""

    # karaoke JS (offsets relativos ao quadro) — só no modo karaoke
    kjs = ""
    if LEGENDA_MODE == "karaoke":
        kjs_lines = []
        for li, line in enumerate(lines):
            lid = f"L{li+1}"
            first_t = max(line[0][1]["start"], 0.3)
            t0 = 0.25 if li == 0 else first_t - 0.28
            if li < len(lines) - 1:
                t1 = max(lines[li+1][0][1]["start"], 0.3)
            else:
                t1 = (words[-1]["end"] or words[-1]["start"]) + 0.9
            wjs = ", ".join(
                f'["#{lid}-w{gi}", {max(w["start"], 0.3):.3f}, {1 if is_keyword(w["word"]) else 0}]'
                for gi, (_, w) in enumerate(line)
            )
            kjs_lines.append(f'{{id:"{lid}", t0:{t0:.3f}, t1:{t1:.3f}, words:[{wjs}]}}')
        kjs = ",\n      ".join(kjs_lines)

    stamp_js = ""
    if stamp:
        hit = d * 0.55
        out = min(hit + 3.2, d - 0.8)
        stamp_js = f"""
      tl.fromTo("#stamp-core", {{ scale: 0.2, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.55, ease: "back.out(2.2)" }}, {hit:.3f});
      tl.to("#stamp-core", {{ scale: 0.88, opacity: 0, duration: 0.45, ease: "power2.in" }}, {out:.3f});"""

    return f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={VIEW_W}, height={VIEW_H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
    <style>
{CSS}    </style>
  </head>
  <body>
    <div id="root" data-composition-id="{qid}" data-start="0" data-duration="{d:.3f}"
      data-width="{VIEW_W}" data-height="{VIEW_H}">

      <div id="bg-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="1">
        <div class="bg">
          <img class="bg-img" id="bg-img" src="{img_src}" alt="" data-layout-allow-overflow />
          <div class="bg-shade"></div>
          <div class="glow" id="glow"></div>
          <div class="grid" id="grid"></div>
          <div class="vignette" id="vignette"></div>
          <div class="rings" id="rings" data-layout-allow-overflow aria-hidden="true">
            <i class="r1"></i><i class="r2"></i><i class="r3"></i>
          </div>
          <div class="grain"></div>
        </div>
      </div>

      <div id="browser-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="2">
        <div class="browser" id="browser">
          <div class="chrome">
            <div class="traffic">
              <i class="t-red" id="t-red"></i><i class="t-yel" id="t-yel"></i><i class="t-grn" id="t-grn"></i>
            </div>
            <div class="tab" id="tab">
              <span class="fav"></span><span class="tab-title">{FONTE_NOME}</span>
            </div>
            <div class="ghost-tab">+</div>
            <div class="addr" id="addr">
              <svg width="13" height="15" viewBox="0 0 13 15" fill="none" aria-hidden="true">
                <rect x="1" y="6.5" width="11" height="8" rx="2" fill="#3f7f52"/>
                <path d="M3.5 6.5V4.5a3 3 0 0 1 6 0v2" stroke="#3f7f52" stroke-width="2" fill="none"/>
              </svg>
              <span class="url">{FONTE_URL}</span>
            </div>
          </div>
          <div class="progress" id="progress"></div>
          <div class="viewport">
            <img id="shot" src="{img_src}" alt="{alt}" data-layout-allow-overflow />
          </div>
          <div class="win-flash" id="win-flash"></div>
        </div>
      </div>
{avatar}
{destaque_html}
{legend_html}

      <div id="kicker-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="5">
        <div class="kicker" data-layout-allow-occlusion data-layout-allow-overlap>
          <span class="kicker-rule" id="kicker-rule"></span>
          <span class="kicker-text" id="kicker-text">Brasil &amp; Mundo <em>· Comentário</em></span>
          <span class="pill" id="pill">{pill}</span>
        </div>
      </div>

      <div id="fonte-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="6">
        <div class="fonte" id="fonte" data-layout-allow-occlusion data-layout-allow-overlap>
          <span class="fonte-nome">{FONTE_NOME}</span>
          <span class="fonte-url">{FONTE_URL}</span>
          <span class="fonte-meta">{EPISODE_DATE}</span>
        </div>
      </div>
      <div id="progress-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="9">
        <div class="frame-progress" data-layout-allow-occlusion data-layout-allow-overlap>
          <i id="frame-progress-bar"></i>
        </div>
      </div>
{stamp_html}
      <div id="outro-zone" class="clip" data-start="0" data-duration="{d:.3f}" data-track-index="8">
        <div class="outro" id="outro"></div>
      </div>
    </div>

    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});

      tl.fromTo("#bg-img", {{ scale: 1.12, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 2.2, ease: "power2.out" }}, 0);
      tl.fromTo("#glow", {{ opacity: 0 }}, {{ opacity: 1, duration: 1.1, ease: "power2.out" }}, 0);
      tl.fromTo("#rings", {{ rotation: 0 }}, {{ rotation: 14, duration: {d:.1f}, ease: "none" }}, 0);
      tl.fromTo("#rings", {{ opacity: 0 }}, {{ opacity: 1, duration: 1.6, ease: "power2.out" }}, 0.15);
      tl.fromTo("#kicker-rule", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.5, ease: "power3.out" }}, 0.35);
      tl.fromTo("#kicker-text", {{ x: -20, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.55, ease: "power2.out" }}, 0.45);
      tl.fromTo("#pill", {{ scale: 0.6, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.45, ease: "back.out(2.2)" }}, 0.6);
      tl.fromTo("#fonte", {{ x: 22, opacity: 0 }}, {{ x: 0, opacity: 1, duration: 0.55, ease: "power2.out" }}, 0.5);
      tl.fromTo("#browser", {{ scale: 0.9, y: 70, opacity: 0 }},
        {{ scale: 1, y: 0, opacity: 1, duration: 0.95, ease: "power3.out" }}, 0.7);
      tl.fromTo("#t-red", {{ scale: 0 }}, {{ scale: 1, duration: 0.25, ease: "back.out(2.5)" }}, 1.7);
      tl.fromTo("#t-yel", {{ scale: 0 }}, {{ scale: 1, duration: 0.25, ease: "back.out(2.5)" }}, 1.78);
      tl.fromTo("#t-grn", {{ scale: 0 }}, {{ scale: 1, duration: 0.25, ease: "back.out(2.5)" }}, 1.86);
      tl.fromTo("#tab", {{ opacity: 0, y: -8 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power2.out" }}, 1.8);
      tl.fromTo("#addr", {{ opacity: 0, x: 10 }}, {{ opacity: 1, x: 0, duration: 0.45, ease: "power2.out" }}, 1.9);
      tl.fromTo("#avatar", {{ scale: 0.55, y: 90, opacity: 0 }},
        {{ scale: 1, y: 0, opacity: 1, duration: 0.75, ease: "back.out(1.7)" }}, 1.05);
      tl.fromTo("#avatar-glow", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.9, ease: "power2.out" }}, 1.3);
{legend_js_in}

      tl.fromTo("#glow", {{ opacity: 0.85 }}, {{ opacity: 1.15, scale: 1.07, duration: 8, ease: "sine.inOut", yoyo: true, repeat: 3 }}, 1.6);
      tl.fromTo("#avatar", {{ y: 0 }}, {{ y: -12, duration: 3.9, ease: "sine.inOut", yoyo: true, repeat: 6 }}, 1.9);
      tl.fromTo("#shot", {{ scale: 1 }}, {{ scale: 1.09, duration: {d - 1:.1f}, ease: "none" }}, 0.6);
      tl.fromTo("#progress", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {d - 1:.1f}, ease: "none" }}, 0.6);
      tl.fromTo("#frame-progress-bar", {{ scaleX: 0 }}, {{ scaleX: 1, duration: {d:.1f}, ease: "none" }}, 0);

      const LINES = [
      {kjs}
      ];
      LINES.forEach(function (L) {{
        tl.fromTo("#" + L.id, {{ opacity: 0, y: 16 }}, {{ opacity: 1, y: 0, duration: 0.34, ease: "power2.out" }}, L.t0);
        L.words.forEach(function (w) {{
          if (w[2]) {{ tl.to(w[0], {{ color: "#e8a23d", scale: 1.1, duration: 0.18, ease: "power1.out" }}, w[1]); }}
          else {{ tl.to(w[0], {{ color: "#ffffff", duration: 0.14, ease: "none" }}, w[1]); }}
        }});
        tl.to("#" + L.id, {{ opacity: 0, y: -14, duration: 0.3, ease: "power2.in" }}, L.t1);
      }});
{destaque_js}
{stamp_js}
      const fade = Math.max({d:.3f} - 1.3, 0.5);
{legend_js_out}
      tl.to("#outro", {{ opacity: 1, duration: 0.95, ease: "power2.in" }}, fade);

      window.__timelines["{qid}"] = tl;
    </script>
  </body>
</html>
"""

# ---- 4. index.html raiz: áudio único + mounts sequenciais ----
mounts = []
for q in QUADROS["quadros"]:
    s = q["start_ms"] / 1000.0
    d = q["duration_ms"] / 1000.0
    mounts.append(
        f'      <div data-composition-id="{q["id"]}" data-composition-src="compositions/{q["id"]}.html" '
        f'data-start="{s:.3f}" data-duration="{d:.3f}"></div>'
    )

INDEX = f"""<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={VIEW_W}, height={VIEW_H}" />
    <title>{QUADROS.get("titulo", "Brasil e Mundo")}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  </head>
  <body style="margin:0; background:#0a0e14;">
    <div id="root" data-composition-id="main" data-start="0"
      data-duration="{TOTAL_S:.3f}" data-width="{VIEW_W}" data-height="{VIEW_H}">
      <audio id="episodio-audio" class="clip" data-start="0" data-duration="{TOTAL_S:.3f}"
        data-track-index="0" src="assets/episodio.mp3"></audio>
{chr(10).join(mounts)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""

for q in QUADROS["quadros"]:
    (COMPOSITIONS / f"{q['id']}.html").write_text(build_quadro_html(q), encoding="utf-8")
OUT.write_text(INDEX, encoding="utf-8")
print(f"OK — {len(QUADROS['quadros'])} sub-composições + index raiz ({TOTAL_S:.1f}s)")
