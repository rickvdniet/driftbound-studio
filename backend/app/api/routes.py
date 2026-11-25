"""REST API. All business rules live in services; routes validate input and translate errors."""
import asyncio
import json
import shutil
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import business
from app.config.settings import get_settings
from app.db import get_db, session
from app.models import (Approval, Asset, CompetitorChannel, Concept, Experiment, Job, Keyword, MetricRecord, Project,
                        StateTransition, Upload)
from app.providers import registry
from app.research import service as research
from app.services import budget, pipeline, settings_store
from app.services import state_machine as sm
from app.services import workspace as wsp
from app.services.concepts import SEED, ConceptData, heuristic_scores, template_concept
from app.workers.queue import enqueue

api = APIRouter(prefix="/api")
# scope="function": commit happens before the response is sent (no read-after-write races)
DB = Depends(get_db, scope="function")


def err(e: Exception, code=400):
    raise HTTPException(code, str(e))


def project_or_404(db, pid) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def ser(obj, exclude=()):
    d = {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in exclude}
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}


# ---------------------------------------------------------------- overview, settings, hardware

@api.get("/health")
def health():
    return {"ok": True}


@api.get("/overview")
def overview(db: Session = DB):
    states = dict(db.execute(select(Project.state, func.count()).group_by(Project.state)).all())
    in_prod = sum(v for k, v in states.items() if k in sm.ORDER and sm.idx("CONCEPT_APPROVED") <= sm.idx(k) < sm.idx("FINAL_REVIEW"))
    awaiting = sum(states.get(s, 0) for s in ("IMAGE_REVIEW", "PREVIEW_READY", "FINAL_REVIEW", "UPLOADED_PRIVATE"))
    hw = settings_store.get(db, "hardware_cache")
    top_kw = db.scalars(select(Keyword).where(Keyword.opportunity_score.is_not(None)).order_by(Keyword.opportunity_score.desc()).limit(5))
    return {
        "projects": sum(states.values()), "states": states, "in_production": in_prod, "awaiting_approval": awaiting,
        "published": states.get("PUBLISHED", 0), "scheduled": states.get("SCHEDULED", 0),
        "failed_jobs": db.scalar(select(func.count(Job.id)).where(Job.status == "failed")),
        "running_jobs": db.scalar(select(func.count(Job.id)).where(Job.status.in_(["queued", "running"]))),
        "api_spend_month_eur": budget.api_spend(db), "api_reserved_eur": budget.api_spend(db, statuses=("reserved",)),
        "budget": settings_store.get(db, "budget"), "storage": wsp.storage_report(),
        "hardware": {k: hw.get(k) for k in ("cpu_model", "cpu_threads", "ram_total_gb", "gpus", "scanned_at")} if hw else None,
        "analytics": business.channel_totals(db),
        "recent": [ser(t) for t in db.scalars(select(StateTransition).order_by(StateTransition.id.desc()).limit(12))],
        "opportunities": [{"keyword": k.keyword, "score": k.opportunity_score, "confidence": k.confidence} for k in top_kw],
    }


@api.get("/settings")
def get_settings_all(db: Session = DB):
    return settings_store.all_settings(db)


@api.put("/settings/{key}")
def put_setting(key: str, value: dict, db: Session = DB):
    if key not in settings_store.DEFAULTS:
        raise HTTPException(404, "unknown settings group")
    if key == "budget" and value.get("paid_api_enabled") and not value.get("confirm_paid"):
        raise HTTPException(400, "Enabling paid APIs requires confirm_paid=true (explicit opt-in)")
    value.pop("confirm_paid", None)
    if key == "scoring_weights":
        research.rescore_all(db)
    return settings_store.put(db, key, value)


@api.get("/hardware")
def hardware(db: Session = DB):
    return settings_store.get(db, "hardware_cache") or {}


@api.post("/hardware/scan")
def hardware_scan(db: Session = DB):
    from app.hardware.detect import detect
    info = detect(test_encoders=True)
    info["scanned_at"] = datetime.now(timezone.utc).isoformat()
    settings_store.put(db, "hardware_cache", info)
    return info


@api.get("/providers")
def providers():
    return registry.catalogue()


# ---------------------------------------------------------------- keywords & competitors

class KeywordIn(BaseModel):
    keyword: str
    cluster: str = "manual"
    intent: str | None = None
    est_monthly_volume: int | None = None
    volume_source: str | None = None
    volume_kind: str | None = None
    trend_interest: float | None = None
    evergreen: float | None = None
    differentiation: float | None = None
    feasibility: float | None = None
    notes: str | None = None


@api.get("/keywords")
def keywords(db: Session = DB):
    return [ser(k) for k in db.scalars(select(Keyword).order_by(Keyword.cluster, Keyword.keyword))]


@api.post("/keywords")
def add_keyword(k: KeywordIn, db: Session = DB):
    kw = Keyword(**k.model_dump(), evidence=[{"source": "manual", "at": datetime.now(timezone.utc).isoformat()}], related=[])
    if kw.est_monthly_volume and not kw.volume_kind:
        kw.volume_kind = "third_party_estimate"
    db.add(kw)
    db.flush()
    research.rescore_all(db)
    return ser(kw)


@api.patch("/keywords/{kid}")
def patch_keyword(kid: int, body: dict, db: Session = DB):
    k = db.get(Keyword, kid) or err(KeyError("not found"), 404)
    for f in KeywordIn.model_fields:
        if f in body:
            setattr(k, f, body[f])
    research.rescore_all(db)
    return ser(k)


@api.delete("/keywords/{kid}")
def del_keyword(kid: int, db: Session = DB):
    k = db.get(Keyword, kid)
    if k:
        db.delete(k)
    return {"deleted": kid}


@api.post("/keywords/import")
async def import_keywords(file: UploadFile = File(...), source: str = Form("manual"), kind: str = Form("third_party_estimate"),
                          cluster: str = Form("imported"), db: Session = DB):
    if kind not in ("third_party_estimate", "relative_interest", "verified"):
        raise HTTPException(400, "kind must be third_party_estimate, relative_interest or verified")
    text = (await file.read(5_000_001)).decode("utf-8", "replace")
    try:
        return research.import_keywords_csv(db, text, source, kind, cluster)
    except ValueError as e:
        err(e)


class CollectIn(BaseModel):
    keyword_id: int
    max_results: int = 25


@api.post("/research/collect")
def collect(body: CollectIn, db: Session = DB):
    """Fetch public competitor data for one keyword via the free YouTube Data API (~102 quota units)."""
    from app.providers.keyword_research.youtube_data_api import QuotaExceeded, YouTubeResearch
    k = db.get(Keyword, body.keyword_id) or err(KeyError("keyword not found"), 404)
    rs = settings_store.get(db, "research")
    try:
        yt = YouTubeResearch(db, get_settings().youtube_api_key, rs["daily_quota_limit"], rs["cache_hours"])
        ids = yt.search_videos(k.keyword, body.max_results)
        vids = yt.videos(ids)
        chans = yt.channels([v["snippet"]["channelId"] for v in vids])
    except (ValueError, QuotaExceeded) as e:
        err(e)
    research.ingest_api_items(db, k.keyword, k.cluster, vids, chans)
    research.update_keyword_from_competitors(db, k)
    return {"videos": len(vids), "channels": len(chans), "keyword": ser(k)}


@api.get("/research/quota")
def quota(db: Session = DB):
    from app.providers.keyword_research.youtube_data_api import units_today
    return {"units_today": units_today(db), "limit": settings_store.get(db, "research")["daily_quota_limit"],
            "api_key_configured": bool(get_settings().youtube_api_key)}


@api.get("/competitors/videos")
def competitor_videos(query: str | None = None, db: Session = DB):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in research.video_table(db, query)]


@api.get("/competitors/channels")
def competitor_channels(db: Session = DB):
    return [ser(c) for c in db.scalars(select(CompetitorChannel))]


@api.post("/research/purge")
def purge(db: Session = DB):
    return {"purged_videos": research.purge_expired(db, settings_store.get(db, "research")["retention_days"])}


# ---------------------------------------------------------------- concepts

@api.get("/concepts")
def concepts(db: Session = DB):
    return [ser(c) for c in db.scalars(select(Concept).order_by(Concept.id))]


@api.post("/concepts")
def create_concept(data: ConceptData, db: Session = DB):
    names = [c.name for c in db.scalars(select(Concept))]
    c = Concept(name=data.name, mode="manual", data=data.model_dump(), generated_by="manual", scores=heuristic_scores(data, None, names))
    db.add(c)
    db.flush()
    return ser(c)


@api.put("/concepts/{cid}")
def update_concept(cid: int, data: ConceptData, db: Session = DB):
    c = db.get(Concept, cid) or err(KeyError("not found"), 404)
    kw = db.scalar(select(Keyword).where(Keyword.keyword == data.primary_keyword))
    c.name, c.data = data.name, data.model_dump()
    c.scores = heuristic_scores(data, (kw.opportunity_score or 0) / 100 if kw and kw.opportunity_score else None,
                                [x.name for x in db.scalars(select(Concept))])
    return ser(c)


@api.post("/concepts/{cid}/status")
def concept_status(cid: int, body: dict, db: Session = DB):
    c = db.get(Concept, cid) or err(KeyError("not found"), 404)
    if body.get("status") not in ("draft", "approved", "rejected", "archived"):
        raise HTTPException(400, "invalid status")
    c.status = body["status"]
    return ser(c)


class GenerateIn(BaseModel):
    mode: str = "seo"  # seo | competitor_gap | experimental
    keyword_id: int | None = None
    idea: str | None = None


@api.post("/concepts/generate")
def generate_concept(body: GenerateIn, db: Session = DB):
    """Local LLM when available (Ollama), otherwise a deterministic template. Never a paid API."""
    from app.providers.llm.provider import LLMUnavailable, get_llm
    kw = db.get(Keyword, body.keyword_id) if body.keyword_id else None
    existing = [c.name for c in db.scalars(select(Concept))]
    evidence = [{"keyword": kw.keyword, "score": kw.opportunity_score, "confidence": kw.confidence,
                 "breakdown": kw.score_breakdown.get("breakdown")}] if kw else []
    llm = get_llm(settings_store.get(db, "providers"))
    data, by = None, "template"
    if llm:
        prompt = (f"Create ONE original ambient YouTube video concept for the Driftbound channel (premium immersive environments). "
                  f"Mode: {body.mode}. Target keyword: {kw.keyword if kw else 'free choice'}. Idea: {body.idea or '-'}. "
                  f"Avoid these existing concepts: {', '.join(existing)}. Category must be one of sleep, study, focus, relaxation. "
                  f"scene.audio must be a subset of [space, rain_interior, fireplace, underwater, train, ocean, wind, storm, water]; "
                  f"scene.fx a subset of [stars, space_clouds, rain, droplets, snow, fire_glow, candles, embers, fog, caustics, "
                  f"particles_uw, bubbles, water_shimmer, sway, clouds, ambient]. No health claims. estimated_api_cost_eur = 0.")
        try:
            data = llm.structured("You are a careful creative director. Output JSON only.", prompt, ConceptData)
            by = f"ollama:{llm.model}"
        except LLMUnavailable:
            data = None
    if data is None:
        # Template: pick the seed environment closest to the keyword, then retarget it.
        words = set((kw.keyword if kw else body.idea or "").lower().split())
        row = max(SEED, key=lambda r: len(words & set(" ".join([r[0], r[3], *r[6]]).lower().split())))
        data = template_concept(row)
        if kw:
            data.primary_keyword = kw.keyword
            data.name = f"{data.name} ({kw.keyword})"
        data.originality_notes = "Template draft. Edit the environment to make it distinct before approving."
    data.research_evidence = evidence or data.research_evidence
    c = Concept(name=data.name, mode=body.mode, data=data.model_dump(), generated_by=by,
                scores=heuristic_scores(data, (kw.opportunity_score or 0) / 100 if kw and kw.opportunity_score else None, existing))
    db.add(c)
    db.flush()
    return ser(c)


@api.post("/concepts/{cid}/to-project")
def concept_to_project(cid: int, db: Session = DB):
    c = db.get(Concept, cid) or err(KeyError("not found"), 404)
    if c.status != "approved":
        raise HTTPException(400, "Approve the concept first")
    return ser(pipeline.create_project(db, c))


# ---------------------------------------------------------------- projects

@api.get("/projects")
def projects(db: Session = DB):
    return [ser(p, exclude=("data",)) | {"duration_hours": p.data.get("render", {}).get("duration_hours"),
                                         "category": p.data.get("brief", {}).get("category"),
                                         "youtube_video_id": p.data.get("youtube_video_id")}
            for p in db.scalars(select(Project).order_by(Project.updated_at.desc()))]


@api.get("/projects/{pid}")
def project(pid: str, db: Session = DB):
    p = project_or_404(db, pid)
    rs = settings_store.get(db, "render")
    master = wsp.project_dir(pid) / "animations" / "masters" / "master.mp4"
    dur = p.data["render"]["duration_hours"] * 3600
    est = (int(master.stat().st_size * dur / p.data["render"]["loop_seconds"] + dur * rs["audio_bitrate_kbps"] * 125)
           if master.exists() else None)
    return {**ser(p), "assets": [ser(a) for a in db.scalars(select(Asset).where(Asset.project_id == pid).order_by(Asset.id))],
            "approvals": [ser(a) for a in db.scalars(select(Approval).where(Approval.project_id == pid).order_by(Approval.id))],
            "transitions": [ser(t) for t in db.scalars(select(StateTransition).where(StateTransition.project_id == pid).order_by(StateTransition.id))],
            "jobs": [ser(j) for j in db.scalars(select(Job).where(Job.project_id == pid).order_by(Job.id.desc()).limit(20))],
            "uploads": [ser(u) for u in db.scalars(select(Upload).where(Upload.project_id == pid))],
            "preview_approved": bool(sm.valid_approval(db, p, "preview", sm.preview_hash(p))),
            "estimated_output_bytes": est, "disk_free_bytes": wsp.disk_free_bytes(),
            "api_cost_eur": budget.api_spend(db, pid)}


class ConfigIn(BaseModel):
    animation: dict | None = None
    audio: dict | None = None
    render: dict | None = None


@api.put("/projects/{pid}/config")
def project_config(pid: str, body: ConfigIn, db: Session = DB):
    p = project_or_404(db, pid)
    pipeline.update_config(db, p, body.animation, body.audio, body.render)
    return ser(p)


def _job(db, typ, pid, payload):
    running = db.scalar(select(Job).where(Job.project_id == pid, Job.type == typ, Job.status.in_(["queued", "running"])))
    if running:
        raise HTTPException(409, f"A {typ} job is already queued/running (#{running.id})")
    return ser(enqueue(db, typ, pid, payload))


@api.post("/projects/{pid}/images/generate")
def gen_images(pid: str, body: dict, db: Session = DB):
    project_or_404(db, pid)
    return _job(db, "generate_images", pid, body)


@api.post("/projects/{pid}/images/import")
async def import_image(pid: str, file: UploadFile = File(...), license: str = Form("{}"), prompt: str = Form(""),
                       db: Session = DB):
    p = project_or_404(db, pid)
    data = await file.read(60_000_001)
    if len(data) > 60_000_000:
        raise HTTPException(413, "image too large")
    lic = json.loads(license or "{}")
    lic.setdefault("name", "user-owned")
    try:
        return ser(pipeline.import_image(db, p, file.filename or "image.png", data, lic,
                                         provider="import_ai" if lic.get("ai_generated") else "import", prompt=prompt or None))
    except pipeline.StageError as e:
        err(e)


@api.post("/projects/{pid}/audio/import")
async def import_audio(pid: str, file: UploadFile = File(...), license: str = Form(...), layer_id: str = Form("recording"),
                       gain_db: float = Form(-12), db: Session = DB):
    """Licensed recording → asset with provenance + a looping 'file' layer in the soundscape."""
    from app.licensing.licenses import evaluate
    p = project_or_404(db, pid)
    lic = json.loads(license)
    ev = evaluate(lic)
    out = wsp.project_dir(pid) / "audio" / "licensed" / wsp.safe_filename(file.filename or "audio.wav")
    out.write_bytes(await file.read(500_000_001))
    try:
        from app.media.rendering import ffmpeg as ff
        info = ff.probe(out)
        dur = float(info["format"]["duration"])
    except Exception:
        out.unlink(missing_ok=True)
        raise HTTPException(400, "Not a readable audio file")
    a = wsp.register(db, out, kind="audio_licensed", project_id=pid, provider="licensed_import", duration_s=dur,
                     license={**lic, "imported_at": datetime.now(timezone.utc).isoformat()}, commercial_ok=ev["commercial"],
                     meta={"evaluation": ev})
    audio = dict(p.data["audio"])
    audio["layers"] = audio.get("layers", []) + [{"id": wsp.safe_filename(layer_id), "type": "file", "gain_db": gain_db, "seed": a.id,
                                                  "params": {"path": str(out), "crossfade_s": 3.0}, "asset_id": a.id}]
    pipeline.update_config(db, p, audio=audio)
    return {"asset": ser(a), "evaluation": ev}


@api.post("/projects/{pid}/images/{aid}/approve")
def approve_image(pid: str, aid: int, db: Session = DB):
    p = project_or_404(db, pid)
    try:
        pipeline.approve_image(db, p, aid)
    except (pipeline.StageError, sm.TransitionError) as e:
        err(e)
    return ser(p)


@api.post("/projects/{pid}/preview")
def build_preview(pid: str, body: dict, db: Session = DB):
    p = project_or_404(db, pid)
    if not sm.valid_approval(db, p, "image"):
        raise HTTPException(400, "Approve an image first")
    return _job(db, "build_preview", pid, {"parts": body.get("parts", ["visual", "audio"]), "seconds": body.get("seconds", 60)})


@api.post("/projects/{pid}/preview/approve")
def approve_preview(pid: str, db: Session = DB):
    p = project_or_404(db, pid)
    try:
        pipeline.approve_preview(db, p)
    except (pipeline.StageError, sm.TransitionError) as e:
        err(e)
    return ser(p)


@api.post("/projects/{pid}/render")
def render(pid: str, body: dict, db: Session = DB):
    p = project_or_404(db, pid)
    if not sm.valid_approval(db, p, "preview", sm.preview_hash(p)):
        raise HTTPException(400, "Approve the current preview before a full render")
    return _job(db, "render_final", pid, {"duration_s": body.get("duration_s")})


@api.post("/projects/{pid}/thumbnails/{aid}/select")
def select_thumb(pid: str, aid: int, db: Session = DB):
    p = project_or_404(db, pid)
    try:
        pipeline.select_thumbnail(db, p, aid)
    except pipeline.StageError as e:
        err(e)
    return ser(p)


@api.put("/projects/{pid}/metadata")
def put_metadata(pid: str, body: dict, db: Session = DB):
    p = project_or_404(db, pid)
    return {"errors": pipeline.save_metadata(db, p, body), "metadata": p.data["metadata"]}


@api.post("/projects/{pid}/approve-final")
def approve_final(pid: str, db: Session = DB):
    p = project_or_404(db, pid)
    try:
        pipeline.approve_final(db, p)
    except (pipeline.StageError, sm.TransitionError) as e:
        err(e)
    return ser(p)


@api.post("/projects/{pid}/export")
def export(pid: str, db: Session = DB):
    p = project_or_404(db, pid)
    try:
        return {"export_dir": wsp.rel(pipeline.export_package(db, p))}
    except pipeline.StageError as e:
        err(e)


@api.post("/projects/{pid}/upload")
def upload(pid: str, db: Session = DB):
    project_or_404(db, pid)
    return _job(db, "upload_private", pid, {})


@api.post("/projects/{pid}/publish")
def publish(pid: str, body: dict, db: Session = DB):
    p = project_or_404(db, pid)
    if body.get("confirm") is not True:
        raise HTTPException(400, "Publishing requires confirm=true")
    try:
        pipeline.approve_publication(db, p, body.get("mode", "public"), body.get("publish_at"))
    except (pipeline.StageError, sm.TransitionError) as e:
        err(e)
    return ser(p)


@api.post("/projects/{pid}/state")
def side_state(pid: str, body: dict, db: Session = DB):
    p = project_or_404(db, pid)
    to = body.get("state")
    if to not in ("PAUSED", "ARCHIVED", "CANCELLED") and not (to and p.state in ("PAUSED", "ARCHIVED", "CANCELLED")):
        raise HTTPException(400, "Only PAUSED/ARCHIVED/CANCELLED, or restoring from them")
    try:
        sm.transition(db, p, to, "user", body.get("note"))
    except sm.TransitionError as e:
        err(e)
    return ser(p)


@api.get("/projects/{pid}/manifest")
def get_manifest(pid: str, db: Session = DB):
    return pipeline.manifest(db, project_or_404(db, pid))


@api.get("/projects/{pid}/mask-preview")
def mask_preview(pid: str, name: str, db: Session = DB):
    import cv2
    from app.media.animation.masks import build_mask, preview_overlay
    p = project_or_404(db, pid)
    img = cv2.imread(str(pipeline._image_path(db, p)))
    img = cv2.resize(img, (960, int(960 * img.shape[0] / img.shape[1])))
    spec = p.data["animation"].get("masks", {}).get(name)
    m = build_mask(spec, img.shape[1], img.shape[0], wsp.ws())
    out = wsp.project_dir(pid) / "masks" / f"preview_{wsp.safe_filename(name)}.jpg"
    cv2.imwrite(str(out), preview_overlay(img, m))
    return FileResponse(out, headers={"Cache-Control": "no-store"})


@api.get("/projects/{pid}/frame-preview")
def frame_preview(pid: str, t: float = 0.0, db: Session = DB):
    """One animated frame at reduced size, for quick effect tuning without building the master."""
    import cv2
    from app.media.rendering.render import frame_iter
    p = project_or_404(db, pid)
    r = p.data["render"]
    fr = next(frame_iter(pipeline._image_path(db, p), p.data["animation"], 960, 540, r["fps"], r["loop_seconds"], wsp.ws(),
                         frames=[int(t * r["fps"])]))
    out = wsp.project_dir(pid) / "previews" / "frame.jpg"
    cv2.imwrite(str(out), fr)
    return FileResponse(out, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- assets & files

@api.get("/assets")
def assets(kind: str | None = None, project_id: str | None = None, q: str | None = None, db: Session = DB):
    s = select(Asset).order_by(Asset.id.desc()).limit(500)
    if kind:
        s = s.where(Asset.kind == kind)
    if project_id:
        s = s.where(Asset.project_id == project_id)
    rows = [ser(a) for a in db.scalars(s)]
    if q:
        rows = [r for r in rows if q.lower() in json.dumps(r).lower()]
    dup = dict(db.execute(select(Asset.sha256, func.count()).group_by(Asset.sha256).having(func.count() > 1)).all())
    for r in rows:
        r["duplicate_count"] = dup.get(r["sha256"], 1)
    return rows


@api.get("/files/{path:path}")
def files(path: str):
    try:
        p = wsp.resolve(path)
    except ValueError:
        raise HTTPException(403, "forbidden")
    if not p.is_file() or p.suffix.lower() in (".db", ".json") and "secrets" in p.parts:
        raise HTTPException(404, "not found")
    return FileResponse(p)


# ---------------------------------------------------------------- jobs

@api.get("/jobs")
def jobs(db: Session = DB):
    return [ser(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(100))]


@api.post("/jobs/{jid}/cancel")
def cancel(jid: int, db: Session = DB):
    j = db.get(Job, jid) or err(KeyError("not found"), 404)
    if j.status == "queued":
        j.status = "cancelled"
    else:
        j.cancel_requested = True
    return ser(j)


@api.post("/jobs/{jid}/retry")
def retry(jid: int, db: Session = DB):
    j = db.get(Job, jid) or err(KeyError("not found"), 404)
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(400, "only failed/cancelled jobs can be retried")
    return ser(enqueue(db, j.type, j.project_id, j.payload))


@api.get("/jobs/stream")
async def job_stream():
    async def gen():
        last = None
        for _ in range(3600):
            with session() as db:
                rows = [ser(j, exclude=("payload", "result")) for j in db.scalars(
                    select(Job).where(Job.status.in_(["queued", "running"])).order_by(Job.id))]
            data = json.dumps(rows)
            if data != last:
                yield f"data: {data}\n\n"
                last = data
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------- analytics, costs, experiments, backup

@api.get("/analytics")
def analytics(db: Session = DB):
    return {"totals": business.channel_totals(db), "ypp": business.ypp_progress(db, business.YPP_REQUIREMENTS),
            "records": [ser(r) for r in db.scalars(select(MetricRecord).order_by(MetricRecord.id.desc()).limit(200))]}


@api.post("/analytics/import")
async def analytics_import(file: UploadFile = File(...), period_start: str = Form(...), period_end: str = Form(...),
                           db: Session = DB):
    try:
        return {"rows": business.import_studio_csv(db, (await file.read(20_000_001)).decode("utf-8", "replace"), period_start, period_end)}
    except ValueError as e:
        err(e)


@api.post("/analytics/manual")
def analytics_manual(body: dict, db: Session = DB):
    """Channel snapshot typed in from YouTube Studio (subscribers, eligible public watch hours, ...)."""
    allowed = {"views", "watch_hours", "subscribers", "subscribers_gained", "eligible_public_watch_hours_12m", "revenue"}
    m = {k: float(v) for k, v in body.get("metrics", {}).items() if k in allowed and v not in (None, "")}
    d = body.get("as_of") or datetime.now(timezone.utc).date().isoformat()
    db.add(MetricRecord(video_id=body.get("video_id"), period_start=d, period_end=d, metrics=m, source="manual"))
    return {"ok": True}


@api.post("/analytics/forecast")
def forecast(body: dict):
    return business.forecast(body)


@api.get("/costs")
def costs(db: Session = DB):
    return {**business.cost_summary(db), "budget": settings_store.get(db, "budget"),
            "month_api_spend_eur": budget.api_spend(db)}


@api.get("/experiments")
def experiments(db: Session = DB):
    return [ser(e) for e in db.scalars(select(Experiment).order_by(Experiment.id.desc()))]


@api.post("/experiments")
def add_experiment(body: dict, db: Session = DB):
    if body.get("type") not in ("controlled", "youtube_native", "before_after", "observational"):
        raise HTTPException(400, "invalid experiment type")
    e = Experiment(hypothesis=body["hypothesis"], type=body["type"], primary_metric=body.get("primary_metric", "views"),
                   data={k: v for k, v in body.items() if k not in ("hypothesis", "type", "primary_metric")})
    db.add(e)
    db.flush()
    return ser(e)


@api.post("/backup")
def backup():
    s = get_settings()
    dst = s.workspace / "backups" / f"driftbound_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    src = sqlite3.connect(s.db_url.removeprefix("sqlite:///"))
    out = sqlite3.connect(dst)
    src.backup(out)
    out.close()
    src.close()
    return {"backup": wsp.rel(dst), "bytes": dst.stat().st_size}
