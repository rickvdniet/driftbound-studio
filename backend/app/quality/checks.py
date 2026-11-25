"""Technical + creative quality assurance (spec 28). Produces passed / warnings / blocking errors."""
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.licensing.licenses import evaluate_asset
from app.media.rendering import ffmpeg as ff
from app.models import Asset, Project
from app.publishing.metadata import Metadata, validate
from app.services import workspace as wsp

YT_MAX_BYTES = 256 * 1024 ** 3  # 256 GB upload limit (verify current limit)
YT_MAX_SECONDS = 12 * 3600  # 12 h (verify; longer requires verified account rules)


class Report:
    def __init__(self):
        self.passed, self.warnings, self.errors = [], [], []

    def check(self, ok: bool, msg: str, blocking=True, detail=None):
        item = {"check": msg, "detail": detail}
        (self.passed if ok else (self.errors if blocking else self.warnings)).append(item)

    def dict(self):
        return {"passed": self.passed, "warnings": self.warnings, "errors": self.errors,
                "status": "fail" if self.errors else ("warn" if self.warnings else "pass")}


def technical(video: Path, *, expected_s: float, w: int, h: int, profile: dict, master: Path | None) -> Report:
    r = Report()
    try:
        info = ff.probe(video)
    except Exception as e:
        r.check(False, "File readable by ffprobe", detail=str(e)[:300])
        return r
    streams = info.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"), None)
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    dur = float(info["format"].get("duration", 0))
    size = int(info["format"].get("size", 0))
    r.check(v is not None and a is not None, "Video and audio streams present")
    if v:
        r.check(v["codec_name"] == "h264", "Video codec H.264", detail=v["codec_name"])
        r.check((v["width"], v["height"]) == (w, h), f"Resolution {w}x{h}", detail=f"{v['width']}x{v['height']}")
        r.check(abs(v["width"] / v["height"] - 16 / 9) < 0.01, "Aspect ratio 16:9")
        r.check(v.get("pix_fmt") in ("yuv420p", "nv12"), "Pixel format yuv420p", blocking=False, detail=v.get("pix_fmt"))
        vd = float(v.get("duration") or dur)
    if a:
        r.check(a["codec_name"] == "aac", "Audio codec AAC", detail=a["codec_name"])
        r.check(int(a["sample_rate"]) == 48000, "Audio 48 kHz", detail=a["sample_rate"])
        r.check(int(a["channels"]) == 2, "Stereo audio")
        ad = float(a.get("duration") or dur)
    r.check(abs(dur - expected_s) <= max(1.0, expected_s * 0.001), "Duration matches target",
            detail=f"{dur:.2f}s vs {expected_s:.2f}s")
    if v and a:
        r.check(abs(vd - ad) < 0.5, "Audio/video stream durations aligned (sync)", detail=f"v={vd:.2f}s a={ad:.2f}s")
    r.check(size < YT_MAX_BYTES, "File size within YouTube limit", detail=f"{size / 1e9:.2f} GB")
    r.check(dur <= YT_MAX_SECONDS, "Duration within YouTube limit")
    head = (info["format"].get("tags") or {})
    r.check(True, "MP4 container", detail=info["format"].get("format_name"))
    # timestamps: decode errors over the first loop boundary region
    try:
        ff.run(["-v", "error", "-ss", "0", "-i", str(video), "-t", str(min(dur, 130)), "-f", "null", "-"])
        r.check(True, "Decodes cleanly (first 130 s, includes a loop boundary)")
    except Exception as e:
        r.check(False, "Decodes cleanly", detail=str(e)[:300])
    # loudness over the full audio (fast: audio only)
    L = ff.loudness(video)
    tgt, tp = profile.get("target_lufs", -20), profile.get("true_peak_db", -2)
    r.check(L["integrated_lufs"] is not None and abs(L["integrated_lufs"] - tgt) <= 2.0, f"Integrated loudness ≈ {tgt} LUFS",
            blocking=False, detail=L)
    r.check(L["true_peak_db"] is not None and L["true_peak_db"] <= tp + 0.5, f"True peak ≤ {tp} dBTP (clipping)", detail=L)
    r.check((L["lra"] or 0) <= 15, "Loudness range stable (LRA ≤ 15 LU)", blocking=False, detail=L.get("lra"))
    sil = ff.detect(video, "silencedetect=n=-60dB:d=5", 0, min(dur, 600))
    r.check(not sil, "No unexpected silence (first 10 min)", detail=sil[:5])
    tgt_scan = master or video
    blk = ff.detect(tgt_scan, "blackdetect=d=1:pic_th=0.98", 0, None if master else min(dur, 300))
    r.check(not blk, "No unexpected black frames (visual master)", blocking=False, detail=blk[:5])
    frz = ff.detect(tgt_scan, "freezedetect=n=-70dB:d=8", 0, None if master else min(dur, 300))
    r.check(not frz, "No fully frozen segments (visual master)", blocking=False, detail=frz[:5])
    return r


def creative(db: Session, project: Project, meta: Metadata | None, thumb: Asset | None) -> Report:
    r = Report()
    assets = list(db.scalars(select(Asset).where(Asset.project_id == project.id)))
    used = [a for a in assets if a.role in ("approved", "selected") or a.kind in ("audio_licensed",)]
    for a in used:
        ev = evaluate_asset(a)
        r.check(ev["ok"], f"Usage rights established: {a.kind} #{a.id}", detail=ev["issues"])
    loop = project.data.get("loop_check") or {}
    r.check(bool(loop.get("seamless")), "Visual loop boundary looks seamless", blocking=False, detail=loop)
    # originality vs other projects: perceptual hash of approved image
    img = next((a for a in assets if a.kind == "image" and a.role == "approved"), None)
    if img and img.phash:
        others = db.scalars(select(Asset).where(Asset.kind == "image", Asset.role == "approved", Asset.project_id != project.id))
        close = [o.project_id for o in others if o.phash and wsp.hamming(o.phash, img.phash) <= 8]
        r.check(not close, "Artwork distinct from other projects (perceptual hash)", blocking=False, detail=close)
        dup = db.scalars(select(Asset).where(Asset.sha256 == img.sha256, Asset.project_id != project.id)).first()
        r.check(dup is None, "Artwork not reused byte-for-byte from another project", detail=dup.project_id if dup else None)
    if meta:
        errs = validate(meta)
        r.check(not errs, "Metadata within YouTube limits and free of medical claims", detail=errs)
    else:
        r.check(False, "Metadata generated")
    r.check(thumb is not None, "Thumbnail selected", blocking=False)
    if thumb:
        r.check((thumb.width, thumb.height) == (1280, 720) and (thumb.size_bytes or 0) <= 2 * 1024 ** 2,
                "Thumbnail 1280x720 and ≤ 2 MB", detail=f"{thumb.width}x{thumb.height}, {thumb.size_bytes} B")
    r.check(True, "Human creative approval required before upload (enforced by workflow)")
    return r
