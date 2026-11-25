"""YouTube Data API v3 research provider (free quota, API key). Read-only public data.

Quota costs used for tracking (per Google's quota table; verify in the Cloud console): search.list = 100 units,
videos.list = 1, channels.list = 1. Default project quota is 10,000 units/day.
Responses are cached in api_usage for `cache_hours` to avoid repeated requests.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApiUsage

BASE = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100, "videos": 1, "channels": 1}


class QuotaExceeded(Exception):
    pass


def units_today(db: Session) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(select(func.coalesce(func.sum(ApiUsage.units), 0)).where(
        ApiUsage.provider == "youtube_data_api", ApiUsage.at >= start)) or 0)


class YouTubeResearch:
    def __init__(self, db: Session, api_key: str, daily_limit=8000, cache_hours=24, transport=None):
        if not api_key:
            raise ValueError("No YouTube Data API key configured (DRIFTBOUND_YOUTUBE_API_KEY)")
        self.db, self.key, self.limit, self.cache_h = db, api_key, daily_limit, cache_hours
        self.client = httpx.Client(timeout=20, transport=transport)

    def _get(self, endpoint: str, params: dict) -> dict:
        ck = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()[:40]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.cache_h)
        hit = self.db.scalars(select(ApiUsage).where(ApiUsage.cache_key == ck, ApiUsage.at >= cutoff)).first()
        if hit and hit.response is not None:
            return hit.response
        cost = COST[endpoint]
        if units_today(self.db) + cost > self.limit:
            raise QuotaExceeded(f"Daily research quota limit ({self.limit} units) reached")
        for attempt in range(3):
            r = self.client.get(f"{BASE}/{endpoint}", params={**params, "key": self.key})
            if r.status_code in (429, 500, 503) and attempt < 2:
                import random
                import time
                time.sleep((2 ** attempt) + random.random())
                continue
            break
        self.db.add(ApiUsage(provider="youtube_data_api", endpoint=endpoint, cache_key=ck, units=cost,
                             response=r.json() if r.status_code == 200 else None))
        self.db.flush()
        if r.status_code == 403 and "quota" in r.text.lower():
            raise QuotaExceeded("YouTube reports the daily quota is exhausted")
        r.raise_for_status()
        return r.json()

    def search_videos(self, query: str, max_results=25, region: str | None = None) -> list[str]:
        p = {"part": "id", "q": query, "type": "video", "maxResults": min(50, max_results), "order": "relevance",
             "videoDuration": "long", "relevanceLanguage": "en"}
        if region:
            p["regionCode"] = region
        return [i["id"]["videoId"] for i in self._get("search", p).get("items", [])]

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):  # batching: 50 ids per call
            out += self._get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])}).get("items", [])
        return out

    def channels(self, ids: list[str]) -> list[dict]:
        out = []
        ids = sorted(set(ids))
        for i in range(0, len(ids), 50):
            out += self._get("channels", {"part": "snippet,statistics", "id": ",".join(ids[i:i + 50])}).get("items", [])
        return out
