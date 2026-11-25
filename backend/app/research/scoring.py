"""Opportunity scoring (spec 10). Missing inputs are excluded and weights renormalized; confidence drops.
No value is ever invented to complete a score."""
import math
import statistics
from datetime import datetime, timezone

SEED_CLUSTERS = {
    "sleep": ["sleep sounds", "deep sleep sounds", "sounds for sleeping", "relaxing sleep sounds", "sleep ambience",
              "brown noise for sleeping", "rain sounds for sleeping", "ocean sounds for sleeping"],
    "relaxation": ["relaxing sounds", "relaxing ambience", "ambient sounds", "peaceful sounds", "nature sounds",
                   "calming sounds", "fireplace sounds", "water sounds"],
    "focus_study": ["study ambience", "focus sounds", "reading ambience", "library ambience", "fireplace ambience",
                    "cozy study ambience", "background sounds for work"],
    "immersive": ["space ambience", "spaceship ambience", "underwater ambience", "fantasy ambience", "medieval ambience",
                  "cozy cabin ambience", "train ambience", "rainy night ambience", "snowstorm ambience"],
}
# Heuristic evergreen prior per cluster (labeled as heuristic in the breakdown).
EVERGREEN_PRIOR = {"sleep": 0.9, "relaxation": 0.85, "focus_study": 0.8, "immersive": 0.75}
SOURCE_QUALITY = {"verified": 1.0, "third_party_estimate": 0.7, "relative_interest": 0.5, "proxy": 0.4, "heuristic": 0.3, "manual": 0.6}


def _log_norm(v, lo, hi):
    if v is None or v <= 0:
        return None
    return max(0.0, min(1.0, (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))))


def components(k) -> dict:
    """Return {component: (value 0..1, kind, evidence str)} for available inputs only."""
    c = {}
    if k.est_monthly_volume:
        c["demand"] = (_log_norm(k.est_monthly_volume, 100, 1_000_000), k.volume_kind or "third_party_estimate",
                       f"{k.est_monthly_volume:,} monthly searches ({k.volume_source}, {k.volume_kind})")
    elif k.trend_interest is not None:
        c["demand"] = (k.trend_interest / 100, "relative_interest", f"Google Trends (YouTube Search) relative interest {k.trend_interest:.0f}/100")
    elif k.median_views_per_day:
        c["demand"] = (_log_norm(k.median_views_per_day, 10, 100_000), "proxy",
                       f"median {k.median_views_per_day:,.0f} lifetime views/day of sampled videos (proxy: traffic may not be search)")
    if k.median_channel_subs:
        v = 1 - (_log_norm(k.median_channel_subs, 1_000, 10_000_000) or 0)
        c["competition"] = (v, "proxy", f"median subscriber count of ranking channels {k.median_channel_subs:,.0f}")
    if k.small_channel_success is not None:
        c["small_channel"] = (k.small_channel_success, "proxy", f"{k.small_channel_success:.0%} of sampled videos are small-channel outperformers")
    if k.evergreen is not None:
        c["evergreen"] = (k.evergreen, "manual", "manual evergreen rating")
    elif k.cluster in EVERGREEN_PRIOR:
        c["evergreen"] = (EVERGREEN_PRIOR[k.cluster], "heuristic", f"cluster prior for '{k.cluster}'")
    if k.differentiation is not None:
        c["differentiation"] = (k.differentiation, "manual", "manual differentiation rating")
    if k.feasibility is not None:
        c["feasibility"] = (k.feasibility, "manual", "production feasibility rating")
    return c


def score(k, weights: dict) -> dict:
    comps = components(k)
    avail = {n: w for n, w in weights.items() if n in comps and comps[n][0] is not None}
    total_w = sum(weights.values())
    if not avail:
        return {"score": None, "confidence": 0.0, "breakdown": {}, "missing": list(weights), "note": "No data yet"}
    wsum = sum(avail.values())
    s = sum(comps[n][0] * w / wsum for n, w in avail.items())
    conf = sum(w * SOURCE_QUALITY.get(comps[n][1], 0.3) for n, w in avail.items()) / total_w
    return {
        "score": round(100 * s, 1), "confidence": round(conf, 2),
        "breakdown": {n: {"value": round(comps[n][0], 3), "weight_used": round(w / wsum, 3), "kind": comps[n][1],
                          "evidence": comps[n][2]} for n, w in avail.items()},
        "missing": [n for n in weights if n not in avail],
        "note": "Weights renormalized over available inputs." if len(avail) < len(weights) else "",
    }


# ---------------------------------------------------------------- competitor metrics

def age_days(published_at: datetime | None) -> float | None:
    if not published_at:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return max(1.0, (datetime.now(timezone.utc) - published_at).total_seconds() / 86400)


def video_metrics(v, channel, channel_median_views: float | None, snapshots: list) -> dict:
    age = age_days(v.published_at)
    out = {"age_days": round(age, 1) if age else None,
           "lifetime_views_per_day": round(v.views / age, 1) if (v.views is not None and age) else None,
           "views_per_subscriber": round(v.views / channel.subscribers, 2) if (channel and channel.subscribers and v.views is not None) else None,
           "views_vs_channel_median": round(v.views / channel_median_views, 2) if (channel_median_views and v.views is not None) else None,
           "measured_recent_views_per_day": None}
    if len(snapshots) >= 2:
        a, b = snapshots[0], snapshots[-1]
        days = (b.taken_at - a.taken_at).total_seconds() / 86400
        if days >= 0.5:
            out["measured_recent_views_per_day"] = round((b.views - a.views) / days, 1)
    subs = channel.subscribers if channel else None
    out["small_channel"] = subs is not None and subs < 100_000
    out["outperformer"] = bool((out["views_per_subscriber"] or 0) >= 1.0 or (out["views_vs_channel_median"] or 0) >= 3.0)
    return out


def aggregate_keyword(videos_with_metrics: list[tuple]) -> dict:
    """videos_with_metrics: [(video, channel, metrics)] for one query/keyword."""
    if not videos_with_metrics:
        return {}
    views = [v.views for v, _, _ in videos_with_metrics if v.views is not None]
    vpd = [m["lifetime_views_per_day"] for _, _, m in videos_with_metrics if m["lifetime_views_per_day"]]
    ages = [m["age_days"] for _, _, m in videos_with_metrics if m["age_days"]]
    subs = [c.subscribers for _, c, _ in videos_with_metrics if c and c.subscribers]
    small_out = [m for _, _, m in videos_with_metrics if m["small_channel"] and m["outperformer"]]
    return {
        "sampled_videos": len(videos_with_metrics),
        "median_views": statistics.median(views) if views else None,
        "median_views_per_day": statistics.median(vpd) if vpd else None,
        "median_age_days": statistics.median(ages) if ages else None,
        "median_channel_subs": statistics.median(subs) if subs else None,
        "small_channel_success": len(small_out) / len(videos_with_metrics),
    }
