#!/usr/bin/env python3
"""YouTube Data API v3 — auth PKCE + upload (public por padrão) + thumbnail.

Metadados do canal (IA, idioma, data, categoria, playlists) vêm de
youtube_channel_policy.py e valem no insert e no apply-policy.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from youtube_channel_policy import (
    PLAYLIST_IDS,
    TITLE_LANGUAGE,
    AUDIO_LANGUAGE,
    choose_playlists,
    recording_date_iso,
    video_resource_body,
)
import youtube_quota as yq
from youtube_quota import QuotaExhausted

ROOT = Path(__file__).resolve().parent.parent
CRED_DIR = ROOT / "credentials"
CLIENT_SECRET = CRED_DIR / "client_secret.json"
TOKEN_PATH = CRED_DIR / "token.json"
OAUTH_STATE = CRED_DIR / "oauth_state.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    from datetime import timezone, timedelta
    TZ = timezone(timedelta(hours=-3))


def _flow(slot: dict):
    from google_auth_oauthlib.flow import InstalledAppFlow
    secret = yq.client_secret_path(slot)
    if not secret.exists():
        raise SystemExit(f"❌ falta {secret}")
    data = json.loads(secret.read_text(encoding="utf-8"))
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), scopes=SCOPES)
    try:
        flow.redirect_uri = data["installed"]["redirect_uris"][0]
    except Exception:
        flow.redirect_uri = "http://localhost"
    return flow


def _oauth_state_path(slot: dict) -> Path:
    if slot["name"] == "slot1":
        return OAUTH_STATE
    return CRED_DIR / f"oauth_state.{slot['name']}.json"


def cmd_auth(code: str | None, slot_name: str = "slot1") -> int:
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    slot = yq.slot_by_name(slot_name)
    state_path = _oauth_state_path(slot)
    flow = _flow(slot)
    if not code:
        url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        verifier = getattr(flow, "code_verifier", None)
        state_path.write_text(json.dumps({"code_verifier": verifier}), encoding="utf-8")
        state_path.chmod(0o600)
        print(f"slot: {slot['name']}  projeto: {slot.get('project', '?')}")
        print("Abra esta URL na conta DONA do canal (Vale da Liberdade) e autorize:")
        print(url)
        print(f'Depois rode: youtube_uploader.py auth --slot {slot["name"]} --code "<url-ou-codigo>"')
        return 0
    m = re.search(r"[?&]code=([^&]+)", code)
    if m:
        code = m.group(1)
    if state_path.exists():
        flow.code_verifier = json.loads(state_path.read_text(encoding="utf-8")).get("code_verifier")
    flow.fetch_token(code=code)
    token_file = yq.token_path(slot)
    token_file.write_text(flow.credentials.to_json(), encoding="utf-8")
    token_file.chmod(0o600)
    print(f"✅ token salvo em {token_file.name} (slot {slot['name']})")
    return 0


# Slot em uso na chamada corrente. Definido por run_with_slots().
_ACTIVE_SLOT: dict | None = None


def _active_slot() -> dict:
    global _ACTIVE_SLOT
    if _ACTIVE_SLOT is None:
        usable = [s for s in yq.load_slots() if yq.token_path(s).exists()]
        if not usable:
            raise SystemExit("❌ nenhum slot autorizado — rode auth primeiro")
        _ACTIVE_SLOT = usable[0]
    return _ACTIVE_SLOT


def _creds(slot: dict | None = None):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    slot = slot or _active_slot()
    token_file = yq.token_path(slot)
    if not token_file.exists():
        raise SystemExit(f"❌ sem {token_file.name} — rode auth --slot {slot['name']} primeiro")
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _yt(slot: dict | None = None):
    from googleapiclient.discovery import build
    slot = slot or _active_slot()
    service = build("youtube", "v3", credentials=_creds(slot))
    return yq.ChargedResource(service, slot["name"])


def run_with_slots(op: str, fn):
    """Executa fn() no primeiro slot com folga; troca de slot se a quota estourar.

    Gasta um slot até quase o limite diário antes de passar ao seguinte — a
    escolha é por folga estimada (OP_COST) e, no erro 403 quotaExceeded do
    Google, o slot é marcado como esgotado e a operação é repetida no próximo.
    """
    global _ACTIVE_SLOT
    need = yq.OP_COST.get(op, 100)
    candidates = [s for s in yq.pick_slots(need) if yq.token_path(s).exists()]
    if not candidates:
        authed = [s for s in yq.load_slots() if yq.token_path(s).exists()]
        if not authed:
            raise SystemExit("❌ nenhum slot autorizado — rode auth primeiro")
        raise SystemExit("❌ todos os slots autorizados estão sem quota hoje (reset à meia-noite PT)")
    last: Exception | None = None
    for slot in candidates:
        _ACTIVE_SLOT = slot
        if len(candidates) > 1 or slot["name"] != "slot1":
            print(f"[quota] slot={slot['name']} usado={yq.used(slot['name'])}/{yq.DAILY_LIMIT}", file=sys.stderr)
        try:
            return fn()
        except QuotaExhausted as exc:
            last = exc
            print(f"[quota] {exc} — tentando próximo slot", file=sys.stderr)
            continue
    raise SystemExit(f"❌ quota esgotada em todos os slots: {last}")


def cmd_whoami() -> int:
    def _run() -> int:
        yt = _yt()
        resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
        items = resp.get("items") or []
        if not items:
            print("canal vazio — a conta autorizada não é dona de canal")
            return 1
        sn = items[0]["snippet"]
        print(f"slot: {_active_slot()['name']}")
        print(f"{sn.get('title')}  id={items[0]['id']}")
        return 0

    return run_with_slots("whoami", _run)


def cmd_whoami_all() -> int:
    """Mostra o canal de cada slot autorizado — checa que apontam ao mesmo canal."""
    global _ACTIVE_SLOT
    rc = 0
    ids: set[str] = set()
    for slot in yq.load_slots():
        token = yq.token_path(slot)
        if not token.exists():
            print(f"{slot['name']:6s} sem token ({token.name}) — rode auth --slot {slot['name']}")
            rc = 1
            continue
        _ACTIVE_SLOT = slot
        try:
            resp = _yt(slot).channels().list(part="snippet", mine=True).execute()
            items = resp.get("items") or []
            if not items:
                print(f"{slot['name']:6s} conta sem canal")
                rc = 1
                continue
            cid = items[0]["id"]
            ids.add(cid)
            print(f"{slot['name']:6s} {items[0]['snippet'].get('title')}  id={cid}  proj={slot.get('project')}")
        except Exception as exc:  # noqa: BLE001 — diagnóstico
            print(f"{slot['name']:6s} ERRO: {exc}")
            rc = 1
    if len(ids) > 1:
        print("⚠️  slots apontam para canais DIFERENTES:", ", ".join(sorted(ids)))
        rc = 1
    return rc


def cmd_quota() -> int:
    for line in yq.status_lines():
        print(line)
    return 0


def resolve_playlist_ids(yt) -> dict[str, str]:
    ids = dict(PLAYLIST_IDS)
    try:
        resp = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    except Exception:
        return ids
    for it in resp.get("items") or []:
        title = (it.get("snippet") or {}).get("title") or ""
        if title in PLAYLIST_IDS:
            ids[title] = it["id"]
    return ids


def sync_official_playlists(yt, video_id: str, names: tuple[str, ...]) -> list[str]:
    """Alinha o vídeo só nas 5 playlists oficiais. Não cria playlist nova."""
    ids = resolve_playlist_ids(yt)
    wanted = set(names)
    reports: list[str] = []
    for name in PLAYLIST_IDS:
        pid = ids.get(name)
        if not pid:
            if name in wanted:
                reports.append(f"faltou playlist no canal: {name}")
            continue
        existing = (
            yt.playlistItems()
            .list(part="id", playlistId=pid, videoId=video_id, maxResults=1)
            .execute()
            .get("items")
            or []
        )
        present = bool(existing)
        if name in wanted and not present:
            yt.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": pid,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            reports.append(f"+ {name}")
        elif name not in wanted and present:
            yt.playlistItems().delete(id=existing[0]["id"]).execute()
            reports.append(f"- {name}")
    return reports


def _published_date_iso(published_at: str | None) -> str:
    if not published_at:
        return recording_date_iso()
    try:
        raw = published_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw).astimezone(TZ)
        return f"{dt.date().isoformat()}T00:00:00-03:00"
    except ValueError:
        return recording_date_iso()


def apply_channel_policy(
    yt,
    video_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    privacy: str | None = None,
    kind: str = "news",
    category_id: str | None = None,
) -> dict:
    got = yt.videos().list(part="snippet,status,recordingDetails", id=video_id).execute()
    items = got.get("items") or []
    if not items:
        raise RuntimeError(f"vídeo YouTube não encontrado: {video_id}")
    sn = dict(items[0].get("snippet") or {})
    st = dict(items[0].get("status") or {})
    rec = dict(items[0].get("recordingDetails") or {})
    title = title if title is not None else (sn.get("title") or "")
    description = description if description is not None else (sn.get("description") or "")
    tag_list = tags if tags is not None else list(sn.get("tags") or [])
    rec_date = rec.get("recordingDate") or _published_date_iso(sn.get("publishedAt"))
    body = video_resource_body(
        title,
        description,
        tag_list,
        privacy or st.get("privacyStatus") or "public",
        category_id=category_id,
        recording_date=rec_date,
        kind=kind,
    )
    body["id"] = video_id
    yt.videos().update(part="snippet,status,recordingDetails", body=body).execute()
    decision = choose_playlists(title, description)
    pl_report = sync_official_playlists(yt, video_id, decision.names)
    return {
        "id": video_id,
        "playlists": list(decision.names),
        "playlist_reason": decision.reason,
        "playlist_sync": pl_report,
        "categoryId": body["snippet"]["categoryId"],
        "containsSyntheticMedia": True,
        "defaultLanguage": TITLE_LANGUAGE,
        "defaultAudioLanguage": AUDIO_LANGUAGE,
        "recordingDate": rec_date,
    }


def cmd_upload(
    path: str,
    title: str,
    description: str,
    tags: str,
    privacy: str,
    default_lang: str = "pt-BR",
    kind: str = "news",
    publish_at: str | None = None,
    localizations_file: str | None = None,
    localizations_json: str | None = None,
) -> int:
    return run_with_slots(
        "upload",
        lambda: _do_upload(
            path,
            title,
            description,
            tags,
            privacy,
            default_lang,
            kind,
            publish_at,
            localizations_file,
            localizations_json,
        ),
    )


def _do_upload(
    path: str,
    title: str,
    description: str,
    tags: str,
    privacy: str,
    default_lang: str = "pt-BR",
    kind: str = "news",
    publish_at: str | None = None,
    localizations_file: str | None = None,
    localizations_json: str | None = None,
) -> int:
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    yt = _yt()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    # Parse localizations se fornecidas
    localizations: dict[str, dict[str, str]] | None = None
    if localizations_file:
        loc_path = Path(localizations_file)
        if loc_path.exists():
            try:
                localizations = json.loads(loc_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"  ⚠️  falha ao ler localizations-file: {exc}", file=sys.stderr)
    elif localizations_json:
        try:
            localizations = json.loads(localizations_json)
        except Exception as exc:
            print(f"  ⚠️  falha ao decodificar localizations-json: {exc}", file=sys.stderr)

    # Áudio = pt-BR; título/descrição = pt. default_lang só altera o áudio se vier outro valor explícito.
    body = video_resource_body(
        title,
        description,
        tag_list,
        privacy,
        kind=kind,
        publish_at=publish_at,
        localizations=localizations,
    )
    if default_lang and default_lang != AUDIO_LANGUAGE:
        body["snippet"]["defaultAudioLanguage"] = default_lang

    part_items = ["snippet", "status", "recordingDetails"]
    if localizations:
        part_items.append("localizations")
    part_str = ",".join(part_items)

    media = MediaFileUpload(path, chunksize=64 * 1024 * 1024, resumable=True)
    try:
        resp = yt.videos().insert(
            part=part_str,
            body=body,
            media_body=media,
        ).execute()
    except HttpError as exc:
        msg = str(exc).lower()
        if "containssyntheticmedia" in msg.replace("_", "") or "synthetic" in msg:
            body["status"].pop("containsSyntheticMedia", None)
            resp = yt.videos().insert(
                part=part_str,
                body=body,
                media_body=media,
            ).execute()
        else:
            raise
    vid = resp.get("id")
    print(f"ID: {vid}")
    print(f"https://youtu.be/{vid}")
    if publish_at:
        print(f"agendamento (publishAt): {publish_at} (status=private)")
    if localizations:
        print(f"localizations embutidas: {', '.join(sorted(localizations.keys()))}")
    decision = choose_playlists(title, description)
    if decision.names:
        sync = sync_official_playlists(yt, vid, decision.names)
        print("playlists:", " | ".join(decision.names))
        if sync:
            print("playlist_sync:", "; ".join(sync))
    else:
        print(decision.reason)
    print("IA: containsSyntheticMedia=True")
    print(f"idioma: audio={body['snippet']['defaultAudioLanguage']} titulo={TITLE_LANGUAGE}")
    print(f"categoria: {body['snippet']['categoryId']}  rec: {body['recordingDetails']['recordingDate']}")
    print("legendas: certificação Nenhuma")
    return 0


def cmd_apply_policy(video_id: str, kind: str = "news") -> int:
    return run_with_slots("apply-policy", lambda: _do_apply_policy(video_id, kind))


def _do_apply_policy(video_id: str, kind: str = "news") -> int:
    yt = _yt()
    info = apply_channel_policy(yt, video_id, kind=kind)
    print(f"ID: {info['id']}")
    if info["playlists"]:
        print("playlists:", " | ".join(info["playlists"]))
    else:
        print(info["playlist_reason"])
    if info["playlist_sync"]:
        print("playlist_sync:", "; ".join(info["playlist_sync"]))
    print("IA: containsSyntheticMedia=True")
    print(f"idioma: audio={info['defaultAudioLanguage']} titulo={info['defaultLanguage']}")
    print(f"categoria: {info['categoryId']}  rec: {info['recordingDate']}")
    print("legendas: certificação Nenhuma")
    return 0


def cmd_thumbnail(video_id: str, image: str) -> int:
    return run_with_slots("thumbnail", lambda: _do_thumbnail(video_id, image))


def _do_thumbnail(video_id: str, image: str) -> int:
    from googleapiclient.http import MediaFileUpload
    yt = _yt()
    media = MediaFileUpload(image)
    yt.thumbnails().set(videoId=video_id, media_body=media).execute()
    print("thumbnail OK")
    return 0


def upload_caption(video_id: str, srt_path: str, language: str, name: str) -> None:
    from googleapiclient.http import MediaFileUpload

    yt = _yt()
    existing = yt.captions().list(part="snippet", videoId=video_id).execute()
    for item in existing.get("items") or []:
        sn = item.get("snippet") or {}
        if (sn.get("language") or "").lower() == language.lower():
            yt.captions().delete(id=item["id"]).execute()
            break
    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": name,
            "isDraft": False,
        }
    }
    media = MediaFileUpload(srt_path, mimetype="application/octet-stream", resumable=True)
    yt.captions().insert(part="snippet", body=body, media_body=media).execute()


def set_english_localization(video_id: str, title_en: str, description_en: str) -> None:
    yt = _yt()
    got = yt.videos().list(part="snippet,localizations", id=video_id).execute()
    items = got.get("items") or []
    if not items:
        raise RuntimeError(f"vídeo YouTube não encontrado: {video_id}")
    sn = items[0].get("snippet") or {}
    locs = dict(items[0].get("localizations") or {})
    locs["en"] = {"title": title_en[:100], "description": description_en[:4900]}
    body = {
        "id": video_id,
        "snippet": {
            "title": sn.get("title") or title_en[:100],
            "description": sn.get("description") or "",
            "tags": sn.get("tags") or [],
            "categoryId": sn.get("categoryId") or "25",
            "defaultLanguage": TITLE_LANGUAGE,
            "defaultAudioLanguage": sn.get("defaultAudioLanguage") or AUDIO_LANGUAGE,
        },
        "localizations": locs,
    }
    yt.videos().update(part="snippet,localizations", body=body).execute()


def cmd_captions(video_id: str, srt: str, language: str, name: str) -> int:
    def _run() -> int:
        upload_caption(video_id, srt, language, name)
        print(f"caption OK {language}")
        return 0

    return run_with_slots("captions", _run)


def cmd_localize_en(video_id: str, title: str, description: str) -> int:
    def _run() -> int:
        set_english_localization(video_id, title, description)
        print("localization en OK")
        return 0

    return run_with_slots("localize-en", _run)


def post_channel_comment(video_id: str, text: str) -> str:
    """Posta um comentário de nível superior do canal no vídeo.

    Retorna o commentThread id. A API v3 NÃO expõe pin/destaque — isso é
    exclusivo do YouTube Studio; o chamador avisa que o pin é manual.
    """
    yt = _yt()
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": text}},
        }
    }
    resp = yt.commentThreads().insert(part="snippet", body=body).execute()
    return resp.get("id") or ""


def cmd_comment(video_id: str, text: str) -> int:
    if not text.strip():
        print("❌ texto do comentário vazio", file=sys.stderr)
        return 2
    def _run() -> int:
        tid = post_channel_comment(video_id, text)
        print(f"comment OK id={tid}")
        print("ℹ️  fixar/destacar é manual no YouTube Studio (API v3 não suporta pin)")
        return 0

    return run_with_slots("comment", _run)


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube OAuth upload")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth")
    a.add_argument("--code", default=None)
    a.add_argument("--slot", default="slot1", help="slot de credencial (ver credentials/youtube_slots.json)")
    sub.add_parser("whoami")
    sub.add_parser("whoami-all")
    sub.add_parser("quota")
    u = sub.add_parser("upload")
    u.add_argument("--file", required=True)
    u.add_argument("--title", required=True)
    u.add_argument("--description", default="")
    u.add_argument("--tags", default="")
    u.add_argument("--privacy", default="public", choices=["unlisted", "private", "public"])
    u.add_argument("--default-lang", default="pt-BR", help="Idioma do áudio (título/descrição ficam pt)")
    u.add_argument("--kind", default="news", choices=["news", "essay", "behind"])
    u.add_argument("--publish-at", default=None, help="ISO datetime para agendamento (publishAt)")
    u.add_argument("--localizations-file", default=None, help="Arquivo JSON com localizações EN/ES")
    u.add_argument("--localizations-json", default=None, help="String JSON com localizações EN/ES")
    t = sub.add_parser("thumbnail")
    t.add_argument("--video-id", required=True)
    t.add_argument("--image", required=True)
    c = sub.add_parser("captions")
    c.add_argument("--video-id", required=True)
    c.add_argument("--srt", required=True)
    c.add_argument("--language", required=True)
    c.add_argument("--name", default="")
    loc = sub.add_parser("localize-en")
    loc.add_argument("--video-id", required=True)
    loc.add_argument("--title", required=True)
    loc.add_argument("--description", default="")
    p = sub.add_parser("apply-policy")
    p.add_argument("--video-id", required=True)
    p.add_argument("--kind", default="news", choices=["news", "essay", "behind"])
    cm = sub.add_parser("comment")
    cm.add_argument("--video-id", required=True)
    cm.add_argument("--text", required=True)
    args = ap.parse_args()
    if args.cmd == "auth":
        return cmd_auth(args.code, args.slot)
    if args.cmd == "whoami":
        return cmd_whoami()
    if args.cmd == "whoami-all":
        return cmd_whoami_all()
    if args.cmd == "quota":
        return cmd_quota()
    if args.cmd == "upload":
        return cmd_upload(
            args.file,
            args.title,
            args.description,
            args.tags,
            args.privacy,
            args.default_lang,
            args.kind,
            args.publish_at,
            args.localizations_file,
            args.localizations_json,
        )
    if args.cmd == "thumbnail":
        return cmd_thumbnail(args.video_id, args.image)
    if args.cmd == "captions":
        return cmd_captions(args.video_id, args.srt, args.language, args.name or args.language)
    if args.cmd == "localize-en":
        return cmd_localize_en(args.video_id, args.title, args.description)
    if args.cmd == "apply-policy":
        return cmd_apply_policy(args.video_id, args.kind)
    if args.cmd == "comment":
        return cmd_comment(args.video_id, args.text)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
