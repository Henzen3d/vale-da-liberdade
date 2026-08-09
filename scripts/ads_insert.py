#!/usr/bin/env python3
"""ads_insert.py — Inserção manual de patrocínio Tipo 1 no diário Peter+Ricardo.

Fluxo:
  1. Lê ads/schedule.json (rotação de anúncios, histórico por data).
  2. Escolhe o anúncio do dia (rotação cíclica, nunca repete até esgotar).
  3. Acha o melhor ponto de inserção: silêncio longo (~pausa entre quadros)
     mais próximo do MEIO do episódio, dentro da janela 40-60% da duração,
     evitando vizinhança de conteúdo sensível (morte/assassinato/violência).
  4. Faz splice via ffmpeg (re-encode único, MP3 192k mono 44.1kHz).
  5. Registra no Supabase (Tipo 1): upsert do patrocinador + link_episode_sponsor.
  6. Atualiza histórico no schedule.json.

Uso:
  python3 scripts/ads_insert.py --date 2026-08-04 [--dry-run] [--force-ad ID]
  python3 scripts/ads_insert.py --date 2026-08-04 --no-republish

Integração futura: será chamado pelo cmd_full do pipeline.py após cmd_audio.
Quando o dashboard admin estiver pronto, a seleção sai do schedule.json e
vem do backend (ad_campaigns/sponsors). Por enquanto, fonte = schedule.json.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADS_DIR = ROOT / "ads"
SCHEDULE = ADS_DIR / "schedule.json"
AUDIO_DIR = ROOT / "audio"
EPISODES_DIR = ROOT / "episodes"

HERMES_PY = "/home/osmar/.hermes/hermes-agent/venv/bin/python3"

# Janela de inserção: entre 40% e 60% da duração do episódio
WINDOW_LO = 0.40
WINDOW_HI = 0.60

# Palavras que indicam conteúdo sensível perto do ponto de inserção
SENSITIVE = [
    "morte", "morto", "morta", "mortes", "assassinato", "assassinada",
    "assassinado", "matou", "matar", "homicídio", "homicidio", "feminicídio",
    "feminicidio", "vítima", "vitima", "vítimas", "vitimas", "tragédia",
    "tragédia familiar", "fatal", "óbito", "obito", "suicídio", "suicidio",
    "chacina", "execução", "execucao", "baleado", "baleada", "esfaqueado",
    "esfaqueada", "estupro", "estuprada", "corpo encontrado", "encontrada morta",
    "encontrado morto", "colisão frontal", "colisão fatal", "acidente fatal",
]

# Raio de contexto (em palavras no texto) considerado "vizinhança" do corte
CONTEXT_WORDS = 90


def load_env():
    env = {}
    for f in [ROOT / ".env"]:
        if f.exists():
            for line in f.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def find_silences(mp3: Path, min_dur: float = 1.2) -> list[float]:
    """Retorna pontos médios dos silêncios longos (pausas entre blocos)."""
    r = subprocess.run(
        ["ffmpeg", "-nostats", "-i", str(mp3),
         "-af", f"silencedetect=noise=-35dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end: ([\d.]+)", r.stderr)]
    pts = []
    for s, e in zip(starts, ends):
        pts.append((s + e) / 2.0)
    return pts


def spoken_words(date: str) -> list[str]:
    """Palavras faladas do episódio (arquivo -tts.txt, sem marcadores)."""
    tts = EPISODES_DIR / f"{date}-tts.txt"
    if not tts.exists():
        return []
    text = tts.read_text(encoding="utf-8")
    text = re.sub(r"\[PAUSA\]|\[QUADRO:[^\]]*\]", " ", text)
    return text.split()


def context_is_safe(words: list[str], t_frac: float, duration: float) -> tuple[bool, str]:
    """Verifica se o texto em torno do ponto t_frac está livre de tema sensível."""
    if not words:
        return True, "(sem texto para checar)"
    n = len(words)
    center = int(t_frac * n)
    lo = max(0, center - CONTEXT_WORDS)
    hi = min(n, center + CONTEXT_WORDS)
    window = " ".join(words[lo:hi]).lower()
    hits = [k for k in SENSITIVE if k in window]
    return (len(hits) == 0), (", ".join(hits[:4]) if hits else "")


def pick_insert_point(mp3: Path, date: str) -> tuple[float, str] | None:
    """Escolhe o melhor silêncio: mais perto do meio, janela 40-60%, contexto seguro."""
    duration = ffprobe_duration(mp3)
    mid = duration / 2.0
    silences = find_silences(mp3)
    words = spoken_words(date)

    candidates = []
    for t in silences:
        frac = t / duration
        if not (WINDOW_LO <= frac <= WINDOW_HI):
            continue
        safe, hits = context_is_safe(words, frac, duration)
        candidates.append({
            "t": t, "frac": frac, "safe": safe, "hits": hits,
            "dist": abs(t - mid),
        })

    if not candidates:
        # relaxa janela para 30-70% se não houver silêncio na faixa central
        for t in silences:
            frac = t / duration
            if not (0.30 <= frac <= 0.70):
                continue
            safe, hits = context_is_safe(words, frac, duration)
            candidates.append({"t": t, "frac": frac, "safe": safe,
                               "hits": hits, "dist": abs(t - mid)})
    if not candidates:
        return None

    safe_c = [c for c in candidates if c["safe"]]
    pool = safe_c if safe_c else candidates
    best = min(pool, key=lambda c: c["dist"])
    if not safe_c:
        print(f"⚠️  Nenhum candidato livre de tema sensível; usando o menos ruim.")
    return best["t"], f"{best['frac']*100:.1f}% do episódio ({best['t']:.1f}s), seguro={bool(safe_c)}"


def pick_ad(schedule: dict, date: str, force_ad: str | None) -> tuple[str, dict] | None:
    order = schedule["rotation_order"]
    history = schedule.get("history", [])
    by_date = {h["date"]: h for h in history}

    if force_ad:
        if force_ad not in schedule["ads"]:
            return None
        return force_ad, schedule["ads"][force_ad]

    done_ads = [h["ad_id"] for h in history if h.get("status") == "done"]
    last_idx = order.index(done_ads[-1]) if done_ads else -1
    idx = (last_idx + 1) % len(order)
    ad_id = order[idx]
    return ad_id, schedule["ads"][ad_id]


def record_history(schedule: dict, date: str, ad_id: str, insert_at_s: float | None,
                   status: str) -> dict:
    history = schedule.setdefault("history", [])
    for h in history:
        if h["date"] == date:
            h.update({"ad_id": ad_id, "insert_at_s": insert_at_s, "status": status})
            return h
    entry = {"date": date, "ad_id": ad_id, "insert_at_s": insert_at_s, "status": status}
    history.append(entry)
    return entry


def register_supabase(date: str, ad: dict, schedule: dict) -> None:
    """Tipo 1: garante patrocinador + vínculo com o episódio."""
    env = load_env()
    key = env.get("SUPABASE_ANON_KEY", "")
    if not key:
        print("⚠️  Supabase não configurado; pulando registro.")
        return
    # Preferir rota local (Kong no host, porta 8080) — o túnel público pode
    # bloquear User-Agent não-browser (CF error 1010). Fallback = .env URL.
    urls = ["http://127.0.0.1:8080", env.get("SUPABASE_URL", "")]

    def rpc(fn, payload):
        last_err = None
        for base in urls:
            if not base:
                continue
            req = urllib.request.Request(
                f"{base}/rest/v1/rpc/{fn}",
                data=json.dumps(payload).encode(),
                headers={"apikey": key, "Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except Exception as e:
                last_err = e
        raise RuntimeError(f"todas as rotas Supabase falharam: {last_err}")

    slug = ad["sponsor_slug"]
    sponsor_id = schedule.get("sponsor_ids", {}).get(slug)

    try:
        if not sponsor_id:
            resp = rpc("upsert_sponsor_admin", {
                "p_name": ad["sponsor"],
                "p_website_url": ad.get("website_url"),
            })
            sponsor_id = resp.get("sponsor_id")
            schedule.setdefault("sponsor_ids", {})[slug] = sponsor_id
            SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2))
            print(f"  ✅ Patrocinador criado: {ad['sponsor']} ({sponsor_id})")

        resp = rpc("link_episode_sponsor", {
            "p_episode_date": date,
            "p_sponsor_id": sponsor_id,
            "p_placement": "mid-roll",
            "p_notes": f"inserido por ads_insert.py — take {ad.get('_id', slug)}",
        })
        if resp.get("ok"):
            print(f"  ✅ episode_sponsors vinculado: {date} ← {ad['sponsor']}")
        else:
            print(f"  ⚠️ link_episode_sponsor: {resp}")
    except Exception as e:
        print(f"  ⚠️ Registro Supabase falhou (não aborta): {e}")


def splice(mp3: Path, ad_mp3: Path, t: float, out: Path) -> bool:
    fc = (
        f"[0:a]atrim=0:{t:.3f},asetpts=PTS-STARTPTS[a0];"
        f"[0:a]atrim={t:.3f},asetpts=PTS-STARTPTS[a1];"
        f"[a0][1:a][a1]concat=n=3:v=0:a=1[out]"
    )
    r = subprocess.run(
        ["ffmpeg", "-y", "-nostats", "-v", "error",
         "-i", str(mp3), "-i", str(ad_mp3),
         "-filter_complex", fc, "-map", "[out]",
         "-ar", "44100", "-ac", "1", "-b:a", "192k", str(out)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"❌ ffmpeg falhou: {r.stderr[-800:]}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None, help="Data YYYY-MM-DD (default: hoje)")
    ap.add_argument("--dry-run", action="store_true", help="Mostra escolha sem alterar nada")
    ap.add_argument("--force-ad", default=None, help="Força um ad_id específico")
    ap.add_argument("--no-republish", action="store_true",
                    help="Não republica (hardlink public + R2 + publish_site)")
    args = ap.parse_args()

    import datetime
    date = args.date or datetime.date.today().isoformat()

    schedule = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    mp3 = AUDIO_DIR / f"{date}.mp3"
    if not mp3.exists():
        print(f"❌ Episódio não encontrado: {mp3}")
        sys.exit(1)

    # Idempotência: já inseriu hoje? (mas se o áudio foi regenerado sem o
    # anúncio — mesma duração do backup — reinserir)
    for h in schedule.get("history", []):
        if h["date"] == date and h.get("status") == "done" and not args.force_ad:
            backup = AUDIO_DIR / f"{date}-sem-ad.mp3"
            if backup.exists():
                try:
                    ad_file_chk = ROOT / schedule["ads"][h["ad_id"]]["file"]
                    d_ep = ffprobe_duration(mp3)
                    d_bk = ffprobe_duration(backup)
                    d_ad = ffprobe_duration(ad_file_chk)
                    if abs(d_ep - (d_bk + d_ad)) < 2.0:
                        print(f"ℹ️  Anúncio já inserido em {date} (ad={h['ad_id']}). Nada a fazer.")
                        sys.exit(0)
                    print(f"🔁 Áudio regenerado sem anúncio ({d_ep:.0f}s ≈ backup {d_bk:.0f}s); reinserindo.")
                except Exception:
                    print(f"ℹ️  Anúncio já inserido em {date} (ad={h['ad_id']}). Nada a fazer.")
                    sys.exit(0)
            else:
                print(f"ℹ️  Anúncio já inserido em {date} (ad={h['ad_id']}). Nada a fazer.")
                sys.exit(0)

    picked = pick_ad(schedule, date, args.force_ad)
    if not picked:
        print(f"❌ Anúncio não encontrado: {args.force_ad}")
        sys.exit(1)
    ad_id, ad = picked
    ad["_id"] = ad_id
    ad_file = ROOT / ad["file"]
    if not ad_file.exists():
        print(f"❌ Clipe não encontrado: {ad_file}")
        sys.exit(1)

    dur_ep = ffprobe_duration(mp3)
    dur_ad = ffprobe_duration(ad_file)
    point = pick_insert_point(mp3, date)
    if point is None:
        print("❌ Nenhum silêncio candidato encontrado no episódio.")
        sys.exit(2)
    t, desc = point

    print(f"📻 Episódio: {date} ({dur_ep/60:.1f} min)")
    print(f"📢 Anúncio: {ad_id} — {ad['sponsor']} ({dur_ad:.1f}s)")
    print(f"🎯 Inserção: {desc} @ {t:.1f}s")

    if args.dry_run:
        print("🧪 DRY-RUN: nada alterado.")
        sys.exit(0)

    record_history(schedule, date, ad_id, None, "in_progress")
    SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2))

    # Backup + splice (backup sempre = versão atual sem anúncio)
    backup = AUDIO_DIR / f"{date}-sem-ad.mp3"
    shutil.copy2(mp3, backup)
    print(f"💾 Backup original: {backup.name}")

    tmp = AUDIO_DIR / f"{date}-com-ad.tmp.mp3"
    if not splice(mp3, ad_file, t, tmp):
        record_history(schedule, date, ad_id, None, "error")
        SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2))
        sys.exit(3)

    new_dur = ffprobe_duration(tmp)
    expected = dur_ep + dur_ad
    if abs(new_dur - expected) > 1.5:
        print(f"❌ Duração inesperada: {new_dur:.1f}s (esperado ~{expected:.1f}s)")
        tmp.unlink(missing_ok=True)
        sys.exit(3)

    # Substitui entrega (mp3 + nomeado, que são hardlinks do mesmo inode)
    shutil.move(str(tmp), str(mp3))
    named = AUDIO_DIR / f"{date}-vale-da-liberdade.mp3"
    if named.exists():
        named.unlink()
    os.link(mp3, named)
    print(f"✅ Áudio atualizado: {mp3.name} ({new_dur/60:.1f} min, +{dur_ad:.0f}s de anúncio)")

    # Registro backend Tipo 1
    register_supabase(date, ad, schedule)

    record_history(schedule, date, ad_id, round(t, 1), "done")
    SCHEDULE.write_text(json.dumps(schedule, ensure_ascii=False, indent=2))
    print(f"🗂️  Histórico atualizado: {date} ← {ad_id}")

    if args.no_republish:
        print("⏭️  Publicação pulada (--no-republish).")
        return

    # Republicação: hardlink público + R2 + catálogo
    pub = ROOT / "public" / "audio" / f"{date}.mp3"
    if pub.exists() or pub.is_symlink():
        pub.unlink()
    os.link(mp3, pub)
    print(f"🔗 public/audio/{date}.mp3 atualizado")

    env = os.environ.copy()
    r2 = ROOT / "scripts" / "upload_r2.py"
    if r2.exists():
        subprocess.run([sys.executable, str(r2), "--date", date, "--file", str(mp3)],
                       cwd=str(ROOT), env=env)

    pub_script = ROOT / "scripts" / "publish_site.py"
    if pub_script.exists():
        r = subprocess.run([sys.executable, str(pub_script), "--date", date],
                           cwd=str(ROOT), env=env, capture_output=True, text=True)
        print(r.stdout[-800:] if r.stdout else "")
        if r.returncode != 0:
            print(f"⚠️ publish_site exit {r.returncode}: {r.stderr[-400:]}")

    print(f"\n🎉 Concluído: {ad['sponsor']} inserido no episódio de {date}.")


if __name__ == "__main__":
    main()
