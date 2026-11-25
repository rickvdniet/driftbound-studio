"""End-to-end production pipeline: stage functions (sync, for API calls) and job handlers (worker)."""
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session
from app.licensing.licenses import evaluate_asset
from app.media.mixing.mixer import render_wav
from app.media.rendering import ffmpeg as ff
from app.media.rendering import render as rnd
from app.models import Approval, Asset, Concept, CostEntry, MetadataRevision, Project, StateTransition, Upload
from app.publishing import metadata as md
from app.publishing import thumbnails as th
from app.quality import checks
from app.services import budget, settings_store
from app.services import state_machine as sm
from app.services import workspace as wsp
from app.services.concepts import ConceptData, default_project_config


class StageError(Exception):
    pass


def _set(project: Project, **kw):
    d = dict(project.data)
    d.update(kw)
    project.data = d


# ---------------------------------------------------------------- creation / images

def create_project(db: Session, concept: Concept, actor="user") -> Project:
    c = ConceptData(**concept.data)
    base = wsp.slugify(c.name)
    pid, i = base, 2
    while db.get(Project, pid):
        pid, i = f"{base}-{i}", i + 1
    cfg = default_project_config(c)
    r = settings_store.get(db, "render")
    p = Project(id=pid, name=c.name, concept_id=concept.id, state="DRAFT", data={
        "brief": c.model_dump(), "animation": cfg["animation"], "audio": cfg["audio"],
        "render": {"duration_hours": c.duration_hours, "width": r["width"], "height": r["height"], "fps": r["fps"],
                   "loop_seconds": r["loop_seconds"]},
        "estimated_api_cost_eur": 0.0,
    })
    db.add(p)
    db.flush()
    wsp.project_dir(pid)
    for st in ("CONCEPT_READY",):
        sm.transition(db, p, st, "system")
    sm.approve(db, p, "concept", "approved", "Concept approved for production", None)
    sm.transition(db, p, "CONCEPT_APPROVED", actor, "Concept converted to project")
    concept.status = "in_production"
    return p


def import_image(db: Session, project: Project, filename: str, data: bytes, license: dict, provider="import", prompt=None) -> Asset:
    from PIL import Image
    d = wsp.project_dir(project.id)
    out = d / "images" / "originals" / wsp.safe_filename(filename)
    out.write_bytes(data)
    try:
        with Image.open(out) as im:
            im.verify()
    except Exception:
        out.unlink(missing_ok=True)
        raise StageError("Not a valid image file")
    a = wsp.register(db, out, kind="image", project_id=project.id, role="candidate", provider=provider,
                     model=license.get("model"), prompt=prompt, license=license,
                     commercial_ok=license.get("commercial_use"), meta={"realistic": bool(license.get("realistic"))})
    if sm.idx(project.state) < sm.idx("IMAGE_REVIEW"):
        sm.transition(db, project, "IMAGE_REVIEW", "user", "Image imported")
    return a


def approve_image(db: Session, project: Project, asset_id: int, note=None):
    a = db.get(Asset, asset_id)
    if not a or a.project_id != project.id or a.kind != "image":
        raise StageError("Image not found in this project")
    if project.data.get("approved_image_asset_id") not in (None, asset_id):
        sm.invalidate_from(db, project, "preview", "approved image changed")
    for other in db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind == "image", Asset.role == "approved")):
        other.role = "candidate"
    a.role = "approved"
    anim = dict(project.data["animation"])
    if not anim.get("masks") and (a.meta or {}).get("suggested_masks"):
        anim["masks"] = a.meta["suggested_masks"]
    _set(project, approved_image_asset_id=asset_id, animation=anim)
    sm.approve(db, project, "image", "approved", note, str(asset_id))
    sm.transition(db, project, "IMAGE_APPROVED", "user", f"Visual direction approved (asset {asset_id})")


def update_config(db: Session, project: Project, animation: dict | None = None, audio: dict | None = None,
                  render: dict | None = None):
    if animation is not None:
        _set(project, animation=animation)
    if audio is not None:
        _set(project, audio=audio)
    if render is not None:
        _set(project, render={**project.data["render"], **render})
    if (animation is not None or audio is not None) and sm.valid_approval(db, project, "preview"):
        if not sm.valid_approval(db, project, "preview", sm.preview_hash(project)):
            sm.invalidate_from(db, project, "preview", "animation/audio configuration changed")


# ---------------------------------------------------------------- job handlers

def _image_path(db, project) -> Path:
    aid = project.data.get("approved_image_asset_id")
    a = db.get(Asset, aid) if aid else None
    if not a:
        raise StageError("Approve an image first")
    return wsp.resolve(a.path)


def job_generate_images(ctx, project_id: str, payload: dict):
    from app.providers.image import comfyui, procedural
    with session() as db:
        p = db.get(Project, project_id)
        prov = payload.get("provider") or settings_store.get(db, "providers")["image"]
        brief = p.data["brief"]
        if sm.idx(p.state) < sm.idx("GENERATING_OR_IMPORTING_IMAGES"):
            sm.transition(db, p, "SELECTING_PROVIDERS")
            sm.transition(db, p, "GENERATING_OR_IMPORTING_IMAGES", note=f"provider={prov}")
        workflow = settings_store.get(db, "providers").get("comfyui_workflow")
    d = wsp.project_dir(project_id) / "images" / "candidates"
    count, seed0 = int(payload.get("count", 3)), int(payload.get("seed", 1))
    made = []
    for i in range(count):
        ctx.progress(i / count, f"generating candidate {i + 1}/{count} with {prov}")
        seed = seed0 + i
        if prov == "procedural":
            theme = payload.get("theme") or ("saturn" if "saturn" in brief["name"].lower() or "space" in brief["primary_keyword"] else "space")
            out = d / f"procedural_{seed}.png"
            info = procedural.generate(out, theme=theme, seed=seed)
            made.append((out, info))
        elif prov == "comfyui":
            if not workflow:
                raise StageError("No ComfyUI workflow configured (Settings → Providers)")
            for out in comfyui.generate(workflow, d, prompt=brief["image_prompt"], negative=brief["negative_prompt"], seed=seed):
                made.append((out, {"provider": "comfyui", "model": "see workflow", "seed": seed}))
        else:
            raise StageError(f"Unknown image provider {prov}")
    with session() as db:
        p = db.get(Project, project_id)
        ids = []
        for out, info in made:
            lic = {"name": "generated-local", "commercial_use": True, "source": info["provider"]}
            a = wsp.register(db, out, kind="image", project_id=project_id, role="candidate", provider=info["provider"],
                             model=info.get("model"), prompt=brief["image_prompt"], seed=info.get("seed"), license=lic,
                             commercial_ok=True, meta={k: v for k, v in info.items() if k in ("suggested_masks", "quality_note")})
            ids.append(a.id)
        sm.transition(db, p, "IMAGE_REVIEW", note=f"{len(ids)} candidates")
    return {"assets": ids}


def _audio_gain(db, project: Project, sr: int, profile: dict, tmp: Path) -> float:
    """Measure the raw mix once (60 s, gain 0) and derive the master gain for the target loudness.
    Cached per audio-config hash so the approved preview and the final render use the same gain."""
    h = sm.config_hash(project.data["audio"])
    cache = project.data.get("audio_gain") or {}
    if cache.get("hash") == h:
        return cache["gain_db"]
    cfg = dict(project.data["audio"], master_gain_db=0.0, fade_in_s=0, fade_out_s=0)
    render_wav(cfg, 60, tmp, sr, profile=profile)
    L = ff.loudness(tmp)
    tmp.unlink(missing_ok=True)
    if L["integrated_lufs"] is None:
        raise StageError("Mix is silent; enable at least one audible layer")
    gain = round(profile["target_lufs"] - L["integrated_lufs"], 2)
    _set(project, audio_gain={"hash": h, "gain_db": gain, "measured_raw": L})
    return gain


def job_build_preview(ctx, project_id: str, payload: dict):
    """Build (or rebuild only the requested parts of) the visual master and audio preview, then mux a preview."""
    parts = set(payload.get("parts", ["visual", "audio"]))
    seconds = float(payload.get("seconds", 60))
    with session() as db:
        p = db.get(Project, project_id)
        if not sm.valid_approval(db, p, "image"):
            raise StageError("Approve the visual direction (image) first")
        img = _image_path(db, p)
        r, rs = p.data["render"], settings_store.get(db, "render")
        profile = settings_store.get(db, "audio_profiles")[p.data["audio"].get("profile", "sleep")]
        sm.transition(db, p, "BUILDING_MASTERS", note=f"parts={sorted(parts)}")
        anim, audio_cfg = p.data["animation"], p.data["audio"]
        gain = _audio_gain(db, p, rs["sample_rate"], profile, wsp.project_dir(project_id) / "audio" / "mixes" / "_measure.wav") if "audio" in parts else None
        encoder = rnd.pick_encoder(rs["video_encoder"])
    d = wsp.project_dir(project_id)
    w, h, fps, loop_s = r["width"], r["height"], r["fps"], r["loop_seconds"]
    result, t0 = {}, time.time()
    if "visual" in parts:
        master = d / "animations" / "masters" / "master.mp4"
        info = rnd.render_master(img, anim, master, w=w, h=h, fps=fps, loop_s=loop_s, workspace=wsp.ws(), encoder=encoder,
                                 crf=rs["crf"] - 2, preset=rs["preset"], progress=lambda f, m: ctx.progress(f * 0.7, m))
        ctx.progress(0.72, "checking loop boundary")
        loop = rnd.loop_check(master, img, anim, w // 2, h // 2, fps, loop_s, wsp.ws())
        result.update(master=info, loop_check=loop)
    if "audio" in parts:
        ctx.progress(0.75, "rendering audio stems and preview mix")
        cfg = dict(audio_cfg, master_gain_db=gain)
        stems = []
        for layer in cfg.get("layers", []):
            out = d / "audio" / "layers" / f"stem_{wsp.safe_filename(layer['id'])}.wav"
            render_wav(cfg, seconds, out, only_layer=layer["id"])
            stems.append((layer["id"], out))
        mix = rnd.audio_to_wav(cfg, seconds, d / "audio" / "mixes" / "preview_mix.wav", 48000, profile, profile["true_peak_db"])
        result["audio_loudness"] = ff.loudness(mix)
    ctx.progress(0.92, "muxing preview")
    master = d / "animations" / "masters" / "master.mp4"
    mix = d / "audio" / "mixes" / "preview_mix.wav"
    if not master.exists() or not mix.exists():
        raise StageError("Both a visual master and an audio mix are needed; build the missing part")
    preview = rnd.mux_preview(master, mix, d / "previews" / "preview.mp4", seconds)
    with session() as db:
        p = db.get(Project, project_id)
        for kind, role in (("visual_master", None), ("audio_mix", "preview"), ("audio_layer", "stem"), ("preview", None)):
            if (kind == "visual_master" and "visual" not in parts) or (kind in ("audio_mix", "audio_layer") and "audio" not in parts):
                continue
            for old in db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.kind == kind)):
                db.delete(old)
        if "visual" in parts:
            wsp.register(db, master, kind="visual_master", project_id=project_id, provider="procedural", model="driftbound-fx",
                         duration_s=loop_s, width=w, height=h, codec="h264", meta={"animation": anim, "loop_check": result["loop_check"]})
            _set(p, loop_check=result["loop_check"])
        if "audio" in parts:
            for lid, path in stems:
                wsp.register(db, path, kind="audio_layer", project_id=project_id, role="stem", provider="synth",
                             model=lid, duration_s=seconds, meta={"layer_id": lid})
            wsp.register(db, mix, kind="audio_mix", project_id=project_id, role="preview", provider="synth",
                         duration_s=seconds, meta={"loudness": result["audio_loudness"], "gain_db": gain, "seed": audio_cfg.get("seed")})
        wsp.register(db, preview, kind="preview", project_id=project_id, provider="driftbound", duration_s=seconds)
        _set(p, preview_hash=sm.preview_hash(p), preview_built_at=datetime.now(timezone.utc).isoformat())
        budget.record_local_render(db, project_id, time.time() - t0, "preview build")
        sm.transition(db, p, "PREVIEW_READY", note="Representative 60 s preview ready")
    return {k: v for k, v in result.items() if k != "master"} | {"seconds": round(time.time() - t0, 1)}


def approve_preview(db: Session, project: Project, note=None):
    if project.state != "PREVIEW_READY":
        raise StageError(f"Preview not ready (state {project.state})")
    h = sm.preview_hash(project)
    if project.data.get("preview_hash") != h:
        raise StageError("Configuration changed since the preview was built; rebuild the preview")
    sm.approve(db, project, "preview", "approved", note, h)
    sm.transition(db, project, "PREVIEW_APPROVED", "user", "Preview approved")


def job_render_final(ctx, project_id: str, payload: dict):
    with session() as db:
        p = db.get(Project, project_id)
        h = sm.preview_hash(p)
        if not sm.valid_approval(db, p, "preview", h):
            raise StageError("Full renders require an approved preview of the current configuration")
        r, rs = p.data["render"], settings_store.get(db, "render")
        duration = float(payload.get("duration_s") or r["duration_hours"] * 3600)
        if duration > checks.YT_MAX_SECONDS:
            raise StageError("Duration exceeds the YouTube limit")
        profile = settings_store.get(db, "audio_profiles")[p.data["audio"].get("profile", "sleep")]
        gain = (p.data.get("audio_gain") or {}).get("gain_db")
        if (p.data.get("audio_gain") or {}).get("hash") != sm.config_hash(p.data["audio"]):
            raise StageError("Audio gain is stale; rebuild the preview")
        audio_cfg = dict(p.data["audio"], master_gain_db=gain)
        master = wsp.project_dir(project_id) / "animations" / "masters" / "master.mp4"
        mbytes = master.stat().st_size
        est = int(mbytes * duration / r["loop_seconds"] + duration * rs["audio_bitrate_kbps"] * 125)
        if wsp.disk_free_bytes() < est * 1.2 + 2 * 1024 ** 3:
            raise StageError(f"Not enough disk space: need ~{est / 1e9:.1f} GB + margin")
        sm.transition(db, p, "RENDERING", note=f"{duration / 3600:.2f} h, est. {est / 1e9:.2f} GB")
        brand = settings_store.get(db, "brand")
    d = wsp.project_dir(project_id)
    out = d / "exports" / f"{project_id}_{int(duration)}s.mp4"
    t0 = time.time()
    rnd.render_final(master, audio_cfg, duration, out, profile=profile, ceiling_db=profile["true_peak_db"],
                     audio_kbps=rs["audio_bitrate_kbps"], progress=lambda f, m: ctx.progress(f * 0.8, m))
    render_s = time.time() - t0
    with session() as db:
        p = db.get(Project, project_id)
        for old in db.scalars(select(Asset).where(Asset.project_id == project_id, Asset.kind == "final_video")):
            old.role = "superseded"
        fa = wsp.register(db, out, kind="final_video", project_id=project_id, role="selected", provider="driftbound",
                          duration_s=duration, width=r["width"], height=r["height"], codec="h264",
                          meta={"preview_hash": h, "audio_gain_db": gain, "render_seconds": round(render_s, 1)})
        budget.record_local_render(db, project_id, render_s, "final render")
        sm.transition(db, p, "QUALITY_CHECK")
        fid = fa.id
    ctx.progress(0.82, "technical quality checks")
    tech = checks.technical(out, expected_s=duration, w=r["width"], h=r["height"], profile=profile, master=master)
    ctx.progress(0.92, "thumbnails and metadata")
    with session() as db:
        p = db.get(Project, project_id)
        _set(p, qa_technical=tech.dict(), final_asset_id=fid)
        generate_thumbnails(db, p, brand)
        generate_metadata(db, p)
        run_creative_qa(db, p)
        sm.transition(db, p, "FINAL_REVIEW", note=f"QA: {tech.dict()['status']}")
    return {"final_asset_id": fid, "qa": tech.dict()["status"], "render_seconds": round(render_s, 1)}


def _final_hours(db: Session, p: Project) -> float:
    """Duration of the actual final render (falls back to the target duration)."""
    fa = db.get(Asset, p.data["final_asset_id"]) if p.data.get("final_asset_id") else None
    return (fa.duration_s / 3600) if fa and fa.duration_s else p.data["render"]["duration_hours"]


def generate_thumbnails(db: Session, p: Project, brand: dict):
    d = wsp.project_dir(p.id)
    img = _image_path(db, p)
    hours = _final_hours(db, p)
    text = f"{int(hours)} HOURS" if float(hours).is_integer() and hours >= 1 else None
    for old in db.scalars(select(Asset).where(Asset.project_id == p.id, Asset.kind == "thumbnail")):
        old.role = "history" if old.role == "selected" else old.role
    first = None
    for v in th.generate(img, d / "thumbnails", text=text, palette=brand["palette"]):
        a = wsp.register(db, v["path"], kind="thumbnail", project_id=p.id, role="candidate", provider="driftbound",
                         meta={"variant": v["variant"], "note": v["note"]})
        first = first or a
    if first and not p.data.get("thumbnail_asset_id"):
        first.role = "selected"
        _set(p, thumbnail_asset_id=first.id)


def generate_metadata(db: Session, p: Project, use_llm=True):
    brand = settings_store.get(db, "brand")
    assets = list(db.scalars(select(Asset).where(Asset.project_id == p.id)))
    attributions = [t for t in (evaluate_asset(a).get("attribution_text") for a in assets if a.kind == "audio_licensed") if t]
    disc = md.disclosure_recommendation([a for a in assets if a.kind == "image" and a.role == "approved"])
    m = md.template_metadata(p.data["brief"], _final_hours(db, p), brand, attributions, disc)
    m.category_id = settings_store.get(db, "publishing")["default_category_id"]
    _set(p, metadata=m.model_dump(), metadata_errors=md.validate(m))
    db.add(MetadataRevision(project_id=p.id, title=m.title, description=m.description, tags=m.tags,
                            thumbnail_asset_id=p.data.get("thumbnail_asset_id"), observation="generated (template)"))


def save_metadata(db: Session, p: Project, meta: dict):
    m = md.Metadata(**{**p.data.get("metadata", {}), **meta})
    m.tags = md.fit_tags(m.tags)
    errs = md.validate(m)
    _set(p, metadata=m.model_dump(), metadata_errors=errs)
    db.add(MetadataRevision(project_id=p.id, title=m.title, description=m.description, tags=m.tags,
                            thumbnail_asset_id=p.data.get("thumbnail_asset_id"), observation="edited by user"))
    if sm.valid_approval(db, p, "final"):
        sm.invalidate_from(db, p, "final", "metadata changed")
        if p.state in ("APPROVED", "READY_FOR_UPLOAD"):
            sm.transition(db, p, "FINAL_REVIEW", note="metadata changed after approval")
    run_creative_qa(db, p)
    return errs


def select_thumbnail(db: Session, p: Project, asset_id: int):
    a = db.get(Asset, asset_id)
    if not a or a.project_id != p.id or a.kind != "thumbnail":
        raise StageError("Thumbnail not found")
    for t in db.scalars(select(Asset).where(Asset.project_id == p.id, Asset.kind == "thumbnail", Asset.role == "selected")):
        t.role = "candidate"
    a.role = "selected"
    _set(p, thumbnail_asset_id=asset_id)
    run_creative_qa(db, p)


def run_creative_qa(db: Session, p: Project):
    thumb = db.get(Asset, p.data.get("thumbnail_asset_id")) if p.data.get("thumbnail_asset_id") else None
    meta = md.Metadata(**p.data["metadata"]) if p.data.get("metadata") else None
    _set(p, qa_creative=checks.creative(db, p, meta, thumb).dict())


def approve_final(db: Session, p: Project, note=None):
    if p.state != "FINAL_REVIEW":
        raise StageError(f"Not in final review (state {p.state})")
    errs = (p.data.get("qa_technical") or {}).get("errors", []) + (p.data.get("qa_creative") or {}).get("errors", [])
    if errs:
        raise StageError(f"{len(errs)} blocking QA errors: " + "; ".join(e["check"] for e in errs))
    sm.approve(db, p, "final", "approved", note, sm.config_hash(p.data.get("final_asset_id"), p.data.get("metadata"),
                                                                 p.data.get("thumbnail_asset_id")))
    sm.transition(db, p, "APPROVED", "user", "Final content approved")


def manifest(db: Session, p: Project) -> dict:
    assets = list(db.scalars(select(Asset).where(Asset.project_id == p.id)))
    return {
        "project": p.id, "name": p.name, "generated_at": datetime.now(timezone.utc).isoformat(),
        "creative_brief": p.data["brief"], "image_prompt": p.data["brief"].get("image_prompt"),
        "animation": p.data["animation"], "audio": p.data["audio"], "audio_gain": p.data.get("audio_gain"),
        "render": p.data["render"], "loop_check": p.data.get("loop_check"),
        "assets": [{"id": a.id, "kind": a.kind, "role": a.role, "path": a.path, "sha256": a.sha256, "provider": a.provider,
                    "model": a.model, "seed": a.seed, "license": a.license, "cost_eur": a.cost_eur} for a in assets],
        "quality": {"technical": p.data.get("qa_technical"), "creative": p.data.get("qa_creative")},
        "approvals": [{"stage": a.stage, "decision": a.decision, "valid": a.valid, "at": a.at.isoformat(), "note": a.note}
                      for a in db.scalars(select(Approval).where(Approval.project_id == p.id))],
        "transitions": [{"from": t.from_state, "to": t.to_state, "actor": t.actor, "at": t.at.isoformat()}
                        for t in db.scalars(select(StateTransition).where(StateTransition.project_id == p.id))],
        "api_cost_eur": budget.api_spend(db, p.id),
        "note": "Internal production documentation. Not a guarantee of YouTube Partner Program approval.",
    }


CHECKLIST = """# Publishing checklist: {name}

- [ ] Watched the preview and spot-checked the final video (start, a loop boundary, the end)
- [ ] Title, description and tags reviewed (no health claims)
- [ ] Thumbnail represents the video accurately
- [ ] Audience: "made for kids" answered explicitly in YouTube Studio ({kids})
- [ ] Altered/synthetic content disclosure set as recommended: {disclosure}
- [ ] Sound credits present for every attribution-required asset
- [ ] Upload as **Private** first; check processing, HD availability and copyright checks
- [ ] Add to playlist: {playlist}
- [ ] Publish or schedule only after the private upload looks right
- [ ] Monetization settings are configured manually in YouTube Studio (not available via the API)
"""


def export_package(db: Session, p: Project) -> Path:
    if p.state not in ("APPROVED", "READY_FOR_UPLOAD", "UPLOADED_PRIVATE", "PUBLISH_APPROVED", "SCHEDULED", "PUBLISHED"):
        raise StageError("Approve the final content first")
    d = wsp.ws() / "exports" / p.id
    d.mkdir(parents=True, exist_ok=True)
    video = db.get(Asset, p.data["final_asset_id"])
    thumb = db.get(Asset, p.data["thumbnail_asset_id"]) if p.data.get("thumbnail_asset_id") else None
    src = wsp.resolve(video.path)
    dst = d / src.name
    if not dst.exists():
        try:
            dst.hardlink_to(src)  # no media duplication
        except OSError:
            shutil.copy2(src, dst)
    if thumb:
        shutil.copy2(wsp.resolve(thumb.path), d / "thumbnail.jpg")
    m = p.data["metadata"]
    (d / "title.txt").write_text(m["title"])
    (d / "description.txt").write_text(m["description"])
    (d / "tags.txt").write_text(", ".join(m["tags"]))
    (d / "metadata.json").write_text(json.dumps(m, indent=2))
    (d / "manifest.json").write_text(json.dumps(manifest(db, p), indent=2, default=str))
    (d / "CHECKLIST.md").write_text(CHECKLIST.format(
        name=p.name, kids=settings_store.get(db, "publishing").get("made_for_kids_confirmed"),
        disclosure=m.get("synthetic_disclosure", {}).get("reason"), playlist=m.get("playlist")))
    if p.state == "APPROVED":
        sm.transition(db, p, "READY_FOR_UPLOAD", note="Upload package exported")
    _set(p, export_dir=wsp.rel(d))
    return d


def job_upload_private(ctx, project_id: str, payload: dict):
    from app.providers.youtube.publisher import get_publisher
    with session() as db:
        p = db.get(Project, project_id)
        if p.state not in ("READY_FOR_UPLOAD", "UPLOADING_PRIVATE"):
            raise StageError("Export the approved package first")
        pub_s = settings_store.get(db, "publishing")
        if pub_s.get("made_for_kids_confirmed") is None:
            raise StageError("Confirm the audience ('made for kids' yes/no) in Settings → Publishing first")
        video = db.get(Asset, p.data["final_asset_id"])
        dup = db.scalars(select(Upload).where(Upload.file_sha256 == video.sha256, Upload.status == "uploaded")).first()
        if dup:
            raise StageError(f"This exact file was already uploaded (video {dup.youtube_id}); duplicate upload blocked")
        name = settings_store.get(db, "providers")["youtube_publisher"]
        up = Upload(project_id=project_id, provider=name, file_sha256=video.sha256, status="uploading")
        db.add(up)
        db.flush()
        upload_id = up.id
        meta = dict(p.data["metadata"], made_for_kids=pub_s["made_for_kids_confirmed"],
                    contains_synthetic_media=p.data["metadata"].get("synthetic_disclosure", {}).get("contains_synthetic_media_flag", False))
        vpath = wsp.resolve(video.path)
        tpath = wsp.resolve(db.get(Asset, p.data["thumbnail_asset_id"]).path) if p.data.get("thumbnail_asset_id") else None
        sm.transition(db, p, "UPLOADING_PRIVATE", note=f"provider={name}")
    publisher = get_publisher(name)
    res = publisher.upload(vpath, meta, tpath, progress=lambda f: ctx.progress(f, "uploading (private)"))
    with session() as db:
        p = db.get(Project, project_id)
        up = db.get(Upload, upload_id)
        up.status, up.youtube_id, up.privacy, up.progress = "uploaded", res["video_id"], "private", 1.0
        _set(p, youtube_video_id=res["video_id"])
        sm.transition(db, p, "UPLOADED_PRIVATE", note=f"video {res['video_id']} (private)")
    return res


def approve_publication(db: Session, p: Project, mode: str, publish_at: str | None = None, note=None):
    from app.providers.youtube.publisher import get_publisher
    if p.state != "UPLOADED_PRIVATE":
        raise StageError("Only private uploads can be published")
    if mode not in ("public", "unlisted", "schedule"):
        raise StageError("mode must be public, unlisted or schedule")
    sm.approve(db, p, "publish", "approved", note, f"{mode}:{publish_at}")
    sm.transition(db, p, "PUBLISH_APPROVED", "user", f"Publication approved: {mode} {publish_at or ''}")
    pub = get_publisher(settings_store.get(db, "providers")["youtube_publisher"])
    pub.set_publication(p.data["youtube_video_id"], "private" if mode == "schedule" else mode, publish_at)
    up = db.scalars(select(Upload).where(Upload.project_id == p.id).order_by(Upload.id.desc())).first()
    if up:
        up.privacy = "private" if mode == "schedule" else mode
        up.publish_at = datetime.fromisoformat(publish_at) if publish_at else None
    sm.transition(db, p, "SCHEDULED" if mode == "schedule" else "PUBLISHED", note=mode)


TASKS = {"generate_images": job_generate_images, "build_preview": job_build_preview,
         "render_final": job_render_final, "upload_private": job_upload_private}
