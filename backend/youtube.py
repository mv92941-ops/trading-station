"""
YouTube Data API v3 — OAuth 2.0 串接
Google Cloud Console 設定：
  1. 建立 OAuth 2.0 憑證 → 類型選「網頁應用程式」
  2. 授權重新導向 URI 加入：http://localhost:8000/youtube/callback
  3. 將 client_id / client_secret 填入 config.json
"""

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

TOKEN_FILE = Path(__file__).parent / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Render 自動注入 RENDER_EXTERNAL_URL；本機用 localhost
_base = (
    os.environ.get("RENDER_EXTERNAL_URL")          # Render 雲端
    or os.environ.get("YOUTUBE_REDIRECT_URI", "").replace("/youtube/callback", "")  # 手動覆蓋
    or "http://localhost:8000"                       # 本機預設
)
REDIRECT_URI = _base.rstrip("/") + "/youtube/callback"


class YouTubeAuth:
    def __init__(self, config: dict):
        self.client_id = config["youtube"]["client_id"]
        self.client_secret = config["youtube"]["client_secret"]
        self.playlist_id = config["youtube"]["playlist_id"]
        self._creds: Credentials | None = self._load_token()

    # ── OAuth 流程 ────────────────────────────────────────────────

    def get_auth_url(self) -> str:
        flow = self._make_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
        )
        return auth_url

    def exchange_code(self, code: str):
        flow = self._make_flow()
        flow.fetch_token(code=code)
        self._creds = flow.credentials
        self._save_token()

    def is_authorized(self) -> bool:
        if not self._creds:
            return False
        if self._creds.expired and self._creds.refresh_token:
            self._creds.refresh(Request())
            self._save_token()
        return self._creds and self._creds.valid

    # ── 播放清單 ──────────────────────────────────────────────────

    def get_playlist_items(self) -> list:
        if not self.is_authorized():
            return []
        yt = build("youtube", "v3", credentials=self._creds)
        items = []
        page_token = None
        while True:
            resp = (
                yt.playlistItems()
                .list(
                    part="snippet",
                    playlistId=self.playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
            for item in resp.get("items", []):
                snip = item["snippet"]
                vid_id = snip["resourceId"]["videoId"]
                items.append(
                    {
                        "videoId": vid_id,
                        "title": snip["title"],
                        "thumbnail": snip["thumbnails"].get("default", {}).get("url", ""),
                    }
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return items

    # ── 內部工具 ──────────────────────────────────────────────────

    def _make_flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        }
        return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)

    def _load_token(self) -> Credentials | None:
        if TOKEN_FILE.exists():
            return Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        return None

    def _save_token(self):
        TOKEN_FILE.write_text(self._creds.to_json(), encoding="utf-8")
