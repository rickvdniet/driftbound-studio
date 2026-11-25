"""Analytics aggregation, YPP progress, profitability and forecasting (spec 33, 34, 37).
Only real imported/API data is aggregated; forecasts are labeled as estimates."""
import csv
import io
import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CostEntry, MetricRecord, Project

# YouTube Studio "Advanced mode" export column aliases (English UI). Unknown columns are ignored.
STUDIO_COLS = {
    "video_id": ["content", "video", "video id"],
    "title": ["video title", "title"],
    "views": ["views"],
    "watch_hours": ["watch time (hours)"],
    "subscribers_gained": ["subscribers", "subscribers gained"],
    "revenue": ["estimated revenue (eur)", "estimated revenue (usd)", "your estimated revenue (eur)", "your estimated revenue (usd)"],
    "impressions": ["impressions"],
    "ctr_pct": ["impressions click-through rate (%)"],
    "avg_view_duration": ["average view duration"],
}


def _f(v):
    if v in (None, ""):
        return None
    v = str(v).replace(",", "").strip()
    m = re.match(r"^(\d+):(\d{2}):(\d{2})$", v)
    if m:
        h, mi, s = map(int, m.groups())
        return h * 3600 + mi * 60 + s
    try:
        return float(v)
    except ValueError:
        return None


def import_studio_csv(db: Session, text: str, period_start: str, period_end: str) -> int:
    rdr = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = {k: next((h for h in rdr.fieldnames or [] if h.lower().strip() in al), None) for k, al in STUDIO_COLS.items()}
    if not cols["views"]:
        raise ValueError("Could not find a 'Views' column; export from YouTube Studio Analytics → Advanced mode")
    projects = {p.data.get("youtube_video_id"): p.id for p in db.scalars(select(Project)) if p.data.get("youtube_video_id")}
    n = 0
    for row in rdr:
        vid = (row.get(cols["video_id"]) or "").strip() if cols["video_id"] else None
        if vid and vid.lower() == "total":
            vid = None
        metrics = {k: _f(row.get(c)) for k, c in cols.items() if c and k not in ("video_id", "title")}
        if cols["revenue"]:
            metrics["revenue_currency"] = "USD" if "usd" in cols["revenue"].lower() else "EUR"
        if cols["title"]:
            metrics["title"] = row.get(cols["title"])
        db.add(MetricRecord(video_id=vid or None, project_id=projects.get(vid), period_start=period_start,
                            period_end=period_end, metrics=metrics, source="studio_csv"))
        n += 1
    return n


def channel_totals(db: Session) -> dict:
    """Latest channel-level manual/API snapshot + sums of per-video records. None when no data exists."""
    recs = list(db.scalars(select(MetricRecord)))
    if not recs:
        return {"has_data": False}
    chan = [r for r in recs if r.video_id is None]
    latest = max(chan, key=lambda r: r.period_end) if chan else None
    vids = [r for r in recs if r.video_id]
    out = {"has_data": True, "sources": sorted({r.source for r in recs})}
    if latest:
        out.update({k: latest.metrics.get(k) for k in ("views", "watch_hours", "subscribers", "subscribers_gained",
                                                         "eligible_public_watch_hours_12m", "revenue")})
        out["as_of"] = latest.period_end
    by = defaultdict(lambda: defaultdict(float))
    for r in vids:
        for k in ("views", "watch_hours", "subscribers_gained", "revenue"):
            if r.metrics.get(k) is not None:
                by[r.video_id][k] += r.metrics[k]
        by[r.video_id]["project_id"] = r.project_id
        by[r.video_id]["title"] = r.metrics.get("title")
    out["videos"] = sorted(({"video_id": k, **v} for k, v in by.items()), key=lambda x: -x.get("views", 0))
    return out


def ypp_progress(db: Session, requirements: dict) -> dict:
    """Uses the most recent manual/API channel snapshot. Eligible public watch hours must come from YouTube
    (Studio → Earn) because they differ from total watch time."""
    t = channel_totals(db)
    subs = t.get("subscribers") if t.get("has_data") else None
    hours = t.get("eligible_public_watch_hours_12m") if t.get("has_data") else None
    tiers = {}
    for name, req in requirements.items():
        tiers[name] = {
            "subscribers": {"current": subs, "target": req["subscribers"], "pct": round(100 * subs / req["subscribers"], 1) if subs is not None else None},
            "watch_hours": {"current": hours, "target": req["watch_hours"], "pct": round(100 * hours / req["watch_hours"], 1) if hours is not None else None},
            "other": req.get("other"),
        }
    return {"as_of": t.get("as_of"), "tiers": tiers, "verified_on": requirements.get("_verified_on"),
            "note": "Eligible public watch hours are not available via the API; enter them from YouTube Studio → Earn."}


YPP_REQUIREMENTS = {
    # As published by YouTube (support.google.com/youtube/answer/72851); verify regularly, regional availability varies.
    "early_access": {"subscribers": 500, "watch_hours": 3000, "other": "3 public uploads in the last 90 days; or 3M Shorts views in 90 days"},
    "full_ads": {"subscribers": 1000, "watch_hours": 4000, "other": "or 10M public Shorts views in 90 days"},
}


def cost_summary(db: Session) -> dict:
    rows = list(db.scalars(select(CostEntry)))
    by_cat, by_prov, by_proj = defaultdict(float), defaultdict(float), defaultdict(float)
    render_s = 0.0
    for r in rows:
        if r.status == "released":
            continue
        v = r.actual_eur if r.actual_eur is not None else r.estimated_eur
        by_cat[r.category] += v
        if r.category == "api":
            by_prov[r.provider or "?"] += v
        by_proj[r.project_id or "-"] += v
        if r.category == "electricity":
            render_s += r.units or 0
    published = len([p for p in db.scalars(select(Project)) if p.state in ("UPLOADED_PRIVATE", "SCHEDULED", "PUBLISHED")])
    produced = len({r.project_id for r in rows if r.category == "electricity" and r.project_id})
    api_total = by_cat.get("api", 0.0)
    return {"api_total_eur": round(api_total, 2), "by_category": dict(by_cat), "api_by_provider": dict(by_prov),
            "by_project": dict(by_proj), "local_render_hours": round(render_s / 3600, 2),
            "api_cost_per_produced_video": round(api_total / produced, 2) if produced else None,
            "api_cost_per_published_video": round(api_total / published, 2) if published else None,
            "electricity_is_estimate": True}


def forecast(inp: dict) -> dict:
    """Business-case calculator. All inputs are assumptions; revenue only after monetization_month."""
    months = int(inp.get("months", 24))
    videos0 = int(inp.get("videos_now", 0))
    per_month = float(inp.get("videos_per_month", 10))
    views_per_video = float(inp.get("monthly_views_per_video", 300))
    growth = float(inp.get("monthly_growth_pct", 0)) / 100
    monet = int(inp.get("monetization_month", 12))
    fixed = float(inp.get("monthly_operating_cost_eur", 0))
    prod = float(inp.get("production_cost_per_video_eur", 0))
    out = {}
    for name, rpm in (inp.get("rpm_scenarios") or {"conservative": 0.5, "base": 2.0, "optimistic": 5.0}).items():
        cum_rev = cum_cost = 0.0
        rows, payback = [], None
        for m in range(1, months + 1):
            vids = videos0 + per_month * m
            views = vids * views_per_video * (1 + growth) ** m
            rev = views / 1000 * rpm if m >= monet else 0.0
            cost = fixed + per_month * prod
            cum_rev += rev
            cum_cost += cost
            if payback is None and cum_cost > 0 and cum_rev >= cum_cost:
                payback = m
            rows.append({"month": m, "videos": vids, "views": round(views), "revenue_eur": round(rev, 2),
                         "cost_eur": round(cost, 2), "surplus_eur": round(rev - cost, 2)})
        monthly_cost = fixed + per_month * prod
        out[name] = {"rpm_eur": rpm, "rows": rows, "annual_revenue_last12_eur": round(sum(r["revenue_eur"] for r in rows[-12:]), 2),
                     "cumulative_surplus_eur": round(cum_rev - cum_cost, 2),
                     "break_even_monthly_views": round(monthly_cost / rpm * 1000) if (rpm > 0 and monthly_cost > 0) else 0,
                     "payback_month": payback if cum_cost > 0 else "no costs to recover"}
    out["_label"] = "Illustrative forecast based on your assumptions; not actual results."
    return out
