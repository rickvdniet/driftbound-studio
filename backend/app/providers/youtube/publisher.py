"""YouTube publishing providers. Every upload is private; making public/scheduling needs a separate approval.

- MockPublisher: used by tests and when no credentials exist. Never touches the network.
- YouTubePublisher: OAuth 2.0 (google-auth-oauthlib) + resumable videos.insert (google-api-python-client).
  Implemented against the documented API but NOT verified live (needs your credentials). Install extras:
  `pip install -e .[youtube]`. Note: uploads from unverified API projects are locked to private by YouTube.
"""
import hashlib
from pathlib import Path

from app.config.settings import get_settings

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"  # requested separately
MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube"  # needed for thumbnails.set / playlists / status updates


class MockPublisher:
    name = "mock"

    def channel(self):
        return {"id": "UC_MOCK_CHANNEL", "title": "Mock channel (no network)"}

    def upload(self, video: Path, meta: dict, thumbnail: Path | None, progress=None, session_uri=None) -> dict:
        for i in range(1, 5):
            progress and progress(i / 4)
        vid = "mock_" + hashlib.sha1(video.name.encode()).hexdigest()[:8]
        return {"video_id": vid, "privacy": "private", "processing": "succeeded", "session_uri": None}

    def set_publication(self, video_id: str, privacy: str, publish_at: str | None):
        return {"video_id": video_id, "privacy": privacy, "publish_at": publish_at}


class YouTubePublisher:
    name = "youtube"

    def __init__(self, scopes=(UPLOAD_SCOPE, READ_SCOPE, MANAGE_SCOPE)):
        self.scopes = list(scopes)
        self._svc = None

    def _creds(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        s = get_settings()
        if not s.youtube_token_file.exists():
            raise RuntimeError("YouTube is not connected. Run: python -m scripts.youtube_auth (see docs/YOUTUBE_SETUP.md)")
        c = Credentials.from_authorized_user_file(str(s.youtube_token_file), self.scopes)
        if c.expired and c.refresh_token:
            c.refresh(Request())
            s.youtube_token_file.write_text(c.to_json())
            s.youtube_token_file.chmod(0o600)
        return c

    def svc(self):
        if self._svc is None:
            from googleapiclient.discovery import build
            self._svc = build("youtube", "v3", credentials=self._creds(), cache_discovery=False)
        return self._svc

    def channel(self):
        r = self.svc().channels().list(part="snippet", mine=True).execute()
        it = r["items"][0]
        return {"id": it["id"], "title": it["snippet"]["title"]}

    def upload(self, video: Path, meta: dict, thumbnail: Path | None, progress=None, session_uri=None) -> dict:
        from googleapiclient.http import MediaFileUpload
        body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                            "categoryId": meta.get("category_id", "10"), "defaultLanguage": meta.get("language", "en")},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(meta["made_for_kids"]),
                           "containsSyntheticMedia": bool(meta.get("contains_synthetic_media", False))}}
        media = MediaFileUpload(str(video), chunksize=16 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        req = self.svc().videos().insert(part="snippet,status", body=body, media_body=media)
        resp, retries = None, 0
        while resp is None:
            try:
                status, resp = req.next_chunk()
                if status and progress:
                    progress(status.progress())
            except Exception:
                retries += 1
                if retries > 5:
                    raise
                import random
                import time
                time.sleep(min(60, 2 ** retries + random.random()))
        vid = resp["id"]
        if thumbnail:
            from googleapiclient.http import MediaFileUpload as M
            self.svc().thumbnails().set(videoId=vid, media_body=M(str(thumbnail), mimetype="image/jpeg")).execute()
        if meta.get("playlist_id"):
            self.svc().playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": meta["playlist_id"], "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        return {"video_id": vid, "privacy": "private", "processing": resp.get("processingDetails", {}).get("processingStatus")}

    def set_publication(self, video_id: str, privacy: str, publish_at: str | None):
        status = {"privacyStatus": "private" if publish_at else privacy}
        if publish_at:
            status["publishAt"] = publish_at  # scheduled publishing requires privacyStatus=private
        return self.svc().videos().update(part="status", body={"id": video_id, "status": status}).execute()


def get_publisher(name: str):
    return YouTubePublisher() if name == "youtube" else MockPublisher()
