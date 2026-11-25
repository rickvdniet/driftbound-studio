"""Research workflows: seeding, CSV imports, competitor collection and keyword scoring."""
import csv
import io
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CompetitorChannel, CompetitorSnapshot, CompetitorVideo, Keyword
from app.research import scoring
from app.services import settings_store


def seed_keywords(db: Session) -> int:
    n = 0
    for cluster, kws in scoring.SEED_CLUSTERS.items():
        for kw in kws:
            if not db.scalar(select(Keyword).where(Keyword.keyword == kw)):
                db.add(Keyword(keyword=kw, cluster=cluster, intent=cluster, evidence=[], related=[]))
                n += 1
    db.flush()
    return n


def rescore_all(db: Session):
    weights = settings_store.get(db, "scoring_weights")
    for k in db.scalars(select(Keyword)):
        r = scoring.score(k, weights)
        k.opportunity_score, k.confidence, k.score_breakdown = r["score"], r["confidence"], r


# Column aliases from common exports (vidIQ, TubeBuddy, Google Trends, generic). Unknown columns are ignored.
ALIASES = {
    "keyword": ["keyword", "keywords", "query", "search term", "term", "top queries"],
    "volume": ["search volume", "volume", "monthly searches", "est. monthly searches", "search_volume"],
    "competition": ["competition", "competition score"],
    "trend": ["interest", "trend", "relative interest"],
    "cluster": ["cluster", "category", "group"],
}


def _col(headers, key):
    low = {h.lower().strip(): h for h in headers}
    for a in ALIASES[key]:
        if a in low:
            return low[a]
    return None


def _num(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([kKmM]?)", s)
    if not m:
        return None
    v = float(m.group(1)) * {"k": 1e3, "m": 1e6, "": 1}[m.group(2).lower()]
    return v


def import_keywords_csv(db: Session, text: str, source: str, kind: str, default_cluster="imported") -> dict:
    """source e.g. 'vidiq', 'tubebuddy', 'google_trends_youtube', 'manual'.
    kind: third_party_estimate | relative_interest | verified (authorized YouTube Analytics search terms)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    kc, vc, tc, cc = (_col(reader.fieldnames, k) for k in ("keyword", "volume", "trend", "cluster"))
    if not kc:
        raise ValueError(f"No keyword column found in {reader.fieldnames}")
    created = updated = 0
    now = datetime.now(timezone.utc)
    for row in reader:
        kw = (row.get(kc) or "").strip().lower()
        if not kw or len(kw) > 200:
            continue
        k = db.scalar(select(Keyword).where(Keyword.keyword == kw))
        if not k:
            k = Keyword(keyword=kw, cluster=(row.get(cc) or default_cluster).strip() if cc else default_cluster, evidence=[], related=[])
            db.add(k)
            created += 1
        else:
            updated += 1
        vol, tr = _num(row.get(vc)) if vc else None, _num(row.get(tc)) if tc else None
        if vol is not None and kind != "relative_interest":
            k.est_monthly_volume, k.volume_source, k.volume_kind, k.verified_at = int(vol), source, kind, now
        if tr is not None or (vol is not None and kind == "relative_interest"):
            k.trend_interest = min(100.0, tr if tr is not None else vol)
        k.evidence = (k.evidence or []) + [{"source": source, "kind": kind, "imported_at": now.isoformat(),
                                            "row": {kk: vv for kk, vv in row.items() if kk}}]
    db.flush()
    rescore_all(db)
    return {"created": created, "updated": updated}


def _parse_duration(iso: str | None) -> int | None:
    if not iso:
        return None
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def ingest_api_items(db: Session, query: str, cluster: str, video_items: list[dict], channel_items: list[dict]):
    """Store public API data (untrusted text: stored as data only, never interpreted)."""
    for c in channel_items:
        st = c.get("statistics", {})
        ch = db.get(CompetitorChannel, c["id"]) or CompetitorChannel(channel_id=c["id"], title="")
        ch.title = c["snippet"]["title"][:300]
        ch.subscribers = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
        ch.total_views, ch.video_count = int(st.get("viewCount", 0)), int(st.get("videoCount", 0))
        ch.fetched_at = datetime.now(timezone.utc)
        db.merge(ch)
    for v in video_items:
        sn, st = v["snippet"], v.get("statistics", {})
        cv = db.get(CompetitorVideo, v["id"]) or CompetitorVideo(video_id=v["id"], channel_id=sn["channelId"], title="")
        cv.title, cv.description = sn["title"][:300], (sn.get("description") or "")[:5000]
        cv.thumbnail_url = (sn.get("thumbnails", {}).get("high") or {}).get("url")
        cv.published_at = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        cv.duration_s = _parse_duration(v.get("contentDetails", {}).get("duration"))
        cv.views = int(st["viewCount"]) if "viewCount" in st else None
        cv.likes = int(st["likeCount"]) if "likeCount" in st else None
        cv.comments = int(st["commentCount"]) if "commentCount" in st else None
        cv.cluster, cv.query, cv.fetched_at = cluster, query, datetime.now(timezone.utc)
        db.merge(cv)
        if cv.views is not None:
            db.add(CompetitorSnapshot(video_id=v["id"], views=cv.views))
    db.flush()


def video_table(db: Session, query: str | None = None) -> list[dict]:
    q = select(CompetitorVideo)
    if query:
        q = q.where(CompetitorVideo.query == query)
    vids = list(db.scalars(q))
    chans = {c.channel_id: c for c in db.scalars(select(CompetitorChannel))}
    by_ch: dict[str, list[int]] = {}
    for v in db.scalars(select(CompetitorVideo)):
        if v.views is not None:
            by_ch.setdefault(v.channel_id, []).append(v.views)
    import statistics
    rows = []
    for v in vids:
        snaps = list(db.scalars(select(CompetitorSnapshot).where(CompetitorSnapshot.video_id == v.video_id).order_by(CompetitorSnapshot.taken_at)))
        med = statistics.median(by_ch[v.channel_id]) if len(by_ch.get(v.channel_id, [])) >= 3 else None
        ch = chans.get(v.channel_id)
        m = scoring.video_metrics(v, ch, med, snaps)
        rows.append({"video_id": v.video_id, "title": v.title, "channel": ch.title if ch else v.channel_id,
                     "channel_id": v.channel_id, "subscribers": ch.subscribers if ch else None,
                     "views": v.views, "published_at": v.published_at.isoformat() if v.published_at else None,
                     "duration_s": v.duration_s, "cluster": v.cluster, "query": v.query, "thumbnail_url": v.thumbnail_url,
                     "snapshots": len(snaps), **m, "_v": v, "_c": ch})
    return rows


def update_keyword_from_competitors(db: Session, keyword: Keyword):
    rows = video_table(db, keyword.keyword)
    agg = scoring.aggregate_keyword([(r["_v"], r["_c"], r) for r in rows])
    for k, v in agg.items():
        setattr(keyword, k, v)
    rescore_all(db)


def purge_expired(db: Session, retention_days: int):
    """YouTube API Services policy: don't keep API data beyond the retention window without refreshing it."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stale = [v.video_id for v in db.scalars(select(CompetitorVideo).where(CompetitorVideo.fetched_at < cutoff))]
    if stale:
        db.execute(delete(CompetitorSnapshot).where(CompetitorSnapshot.video_id.in_(stale)))
        db.execute(delete(CompetitorVideo).where(CompetitorVideo.video_id.in_(stale)))
    db.execute(delete(CompetitorChannel).where(CompetitorChannel.fetched_at < cutoff))
    return len(stale)
