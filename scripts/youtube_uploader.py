#!/usr/bin/env python3
"""YouTube Data API v3 — auth PKCE + upload (public por padrão) + thumbnail."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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


def cmd_upload(path: str, title: str, description: str, tags: str, privacy: str) -> int:
    from googleapiclient.http import MediaFileUpload
    yt = _yt()
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    body = {
        "snippet": {"title": title, "description": description, "tags": tag_list},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, chunksize=64 * 1024 * 1024, resumable=True)
    resp = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    vid = resp.get("id")
    print(f"ID: {vid}")
    print(f"https://youtu.be/{vid}")
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
            "defaultLanguage": "pt",
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
    args = ap.parse_args()
    if args.cmd == "auth":
        return cmd_auth(args.code)
    if args.cmd == "whoami":
        return cmd_whoami()
    if args.cmd == "upload":
        return cmd_upload(args.file, args.title, args.description, args.tags, args.privacy)
    if args.cmd == "thumbnail":
        return cmd_thumbnail(args.video_id, args.image)
    if args.cmd == "captions":
        return cmd_captions(args.video_id, args.srt, args.language, args.name or args.language)
    if args.cmd == "localize-en":
        return cmd_localize_en(args.video_id, args.title, args.description)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
