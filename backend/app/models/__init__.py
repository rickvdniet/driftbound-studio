"""SQLAlchemy models. JSON columns hold flexible structures (briefs, configs, evidence)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def now():
    return datetime.now(timezone.utc)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Keyword(Base):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), index=True)
    cluster: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str] = mapped_column(String(16), default="global")
    intent: Mapped[str | None] = mapped_column(String(64))
    related: Mapped[list] = mapped_column(JSON, default=list)
    # Demand: only filled from real sources; kind tells what the number is.
    est_monthly_volume: Mapped[int | None] = mapped_column(Integer)
    volume_source: Mapped[str | None] = mapped_column(String(64))
    volume_kind: Mapped[str | None] = mapped_column(String(32))  # verified|third_party_estimate|relative_interest
    trend_interest: Mapped[float | None] = mapped_column(Float)  # Google Trends 0-100 relative index
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seasonality: Mapped[str | None] = mapped_column(String(64))
    sampled_videos: Mapped[int | None] = mapped_column(Integer)
    median_views: Mapped[float | None] = mapped_column(Float)
    median_age_days: Mapped[float | None] = mapped_column(Float)
    median_views_per_day: Mapped[float | None] = mapped_column(Float)
    median_channel_subs: Mapped[float | None] = mapped_column(Float)
    small_channel_success: Mapped[float | None] = mapped_column(Float)
    evergreen: Mapped[float | None] = mapped_column(Float)
    differentiation: Mapped[float | None] = mapped_column(Float)
    feasibility: Mapped[float | None] = mapped_column(Float)
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitorChannel(Base):
    __tablename__ = "competitor_channels"
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    subscribers: Mapped[int | None] = mapped_column(Integer)  # None when hidden
    total_views: Mapped[int | None] = mapped_column(Integer)
    video_count: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitorVideo(Base):
    __tablename__ = "competitor_videos"
    video_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    cluster: Mapped[str | None] = mapped_column(String(64))
    query: Mapped[str | None] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompetitorSnapshot(Base):
    __tablename__ = "competitor_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[str] = mapped_column(String(32), index=True)
    views: Mapped[int] = mapped_column(Integer)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiUsage(Base):
    """Quota tracking + response cache for free external APIs."""
    __tablename__ = "api_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(String(128))
    cache_key: Mapped[str | None] = mapped_column(String(128), index=True)
    units: Mapped[int] = mapped_column(Integer, default=0)
    response: Mapped[dict | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Concept(Base):
    __tablename__ = "concepts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|approved|rejected|archived|in_production
    mode: Mapped[str] = mapped_column(String(24), default="manual")  # seo|competitor_gap|experimental|manual|seed
    data: Mapped[dict] = mapped_column(JSON)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    concept_id: Mapped[int | None] = mapped_column(ForeignKey("concepts.id"))
    state: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class StateTransition(Base):
    __tablename__ = "state_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(32), default="system")
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))  # concept|image|preview|final|publish
    decision: Mapped[str] = mapped_column(String(16))  # approved|rejected
    config_hash: Mapped[str | None] = mapped_column(String(64))
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # image|mask|visual_master|audio_layer|audio_licensed|audio_mix|preview|final_video|thumbnail|export
    role: Mapped[str | None] = mapped_column(String(32))  # candidate|approved|selected|stem
    path: Mapped[str] = mapped_column(String(500))  # relative to workspace
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(32))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    codec: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None] = mapped_column(Integer)
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    license: Mapped[dict] = mapped_column(JSON, default=dict)
    commercial_ok: Mapped[bool | None] = mapped_column(Boolean)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(48), index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|done|failed|cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    external_id: Mapped[str | None] = mapped_column(String(128))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CostEntry(Base):
    __tablename__ = "cost_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(24))  # api|electricity|storage|subscription|hardware|manual_effort
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    units: Mapped[float | None] = mapped_column(Float)
    estimated_eur: Mapped[float] = mapped_column(Float, default=0.0)
    actual_eur: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    fx_assumption: Mapped[str | None] = mapped_column(String(64))
    pricing_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="committed")  # reserved|committed|released
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    project_id: Mapped[str | None] = mapped_column(String(64), index=True)
    asset_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))  # youtube|mock|manual
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)  # duplicate-upload protection
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    privacy: Mapped[str] = mapped_column(String(16), default="private")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    session_uri: Mapped[str | None] = mapped_column(Text)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    playlist_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MetricRecord(Base):
    """Channel (video_id NULL) or per-video metrics for a period. Only real data (API/CSV/manual)."""
    __tablename__ = "metric_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[str | None] = mapped_column(String(32), index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), index=True)
    period_start: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[str] = mapped_column(String(10))
    metrics: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(24))  # youtube_analytics|studio_csv|manual
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32))  # controlled|youtube_native|before_after|observational
    primary_metric: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MetadataRevision(Base):
    __tablename__ = "metadata_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    thumbnail_asset_id: Mapped[int | None] = mapped_column(Integer)
    observation: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
