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
TZ = ZoneInfo("America/Sao_Paulo")


def _flow():
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not CLIENT_SECRET.exists():
        raise SystemExit(f"❌ falta {CLIENT_SECRET}")
    data = json.loads(CLIENT_SECRET.read_text(encoding="utf-8"))
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), scopes=SCOPES)
    try:
        flow.redirect_uri = data["installed"]["redirect_uris"][0]
    except Exception:
        flow.redirect_uri = "http://localhost"
    return flow


def cmd_auth(code: str | None) -> int:
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    flow = _flow()
    if not code:
        url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        verifier = getattr(flow, "code_verifier", None)
        OAUTH_STATE.write_text(json.dumps({"code_verifier": verifier}), encoding="utf-8")
        OAUTH_STATE.chmod(0o600)
        print("Abra esta URL na conta DONA do canal e autorize:")
        print(url)
        print("Depois rode: youtube_uploader.py auth --code \"<url-ou-codigo>\"")
        return 0
    m = re.search(r"[?&]code=([^&]+)", code)
    if m:
        code = m.group(1)
    if OAUTH_STATE.exists():
        flow.code_verifier = json.loads(OAUTH_STATE.read_text(encoding="utf-8")).get("code_verifier")
    flow.fetch_token(code=code)
    TOKEN_PATH.write_text(flow.credentials.to_json(), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    print("✅ token salvo")
    return 0


def _creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not TOKEN_PATH.exists():
        raise SystemExit("❌ sem token.json — rode auth primeiro")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _yt():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_creds())


def cmd_whoami() -> int:
    yt = _yt()
    resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        print("canal vazio — a conta autorizada não é dona de canal")
        return 1
    sn = items[0]["snippet"]
    print(f"{sn.get('title')}  id={items[0]['id']}")
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
) -> int:
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    yt = _yt()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    # Áudio = pt-BR; título/descrição = pt. default_lang só altera o áudio se vier outro valor explícito.
    body = video_resource_body(title, description, tag_list, privacy, kind=kind)
    if default_lang and default_lang != AUDIO_LANGUAGE:
        body["snippet"]["defaultAudioLanguage"] = default_lang
    media = MediaFileUpload(path, chunksize=64 * 1024 * 1024, resumable=True)
    try:
        resp = yt.videos().insert(
            part="snippet,status,recordingDetails",
            body=body,
            media_body=media,
        ).execute()
    except HttpError as exc:
        msg = str(exc).lower()
        if "containssyntheticmedia" in msg.replace("_", "") or "synthetic" in msg:
            body["status"].pop("containsSyntheticMedia", None)
            resp = yt.videos().insert(
                part="snippet,status,recordingDetails",
                body=body,
                media_body=media,
            ).execute()
        else:
            raise
    vid = resp.get("id")
    print(f"ID: {vid}")
    print(f"https://youtu.be/{vid}")
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
    upload_caption(video_id, srt, language, name)
    print(f"caption OK {language}")
    return 0


def cmd_localize_en(video_id: str, title: str, description: str) -> int:
    set_english_localization(video_id, title, description)
    print("localization en OK")
    return 0


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
    tid = post_channel_comment(video_id, text)
    print(f"comment OK id={tid}")
    print("ℹ️  fixar/destacar é manual no YouTube Studio (API v3 não suporta pin)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube OAuth upload")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth")
    a.add_argument("--code", default=None)
    sub.add_parser("whoami")
    u = sub.add_parser("upload")
    u.add_argument("--file", required=True)
    u.add_argument("--title", required=True)
    u.add_argument("--description", default="")
    u.add_argument("--tags", default="")
    u.add_argument("--privacy", default="public", choices=["unlisted", "private", "public"])
    u.add_argument("--default-lang", default="pt-BR", help="Idioma do áudio (título/descrição ficam pt)")
    u.add_argument("--kind", default="news", choices=["news", "essay", "behind"])
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
        return cmd_auth(args.code)
    if args.cmd == "whoami":
        return cmd_whoami()
    if args.cmd == "upload":
        return cmd_upload(
            args.file, args.title, args.description, args.tags, args.privacy, args.default_lang, args.kind
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
