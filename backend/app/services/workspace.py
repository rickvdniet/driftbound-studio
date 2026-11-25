"""Workspace paths, hashing and asset registration."""
import hashlib
import re
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import Asset

PROJECT_DIRS = [
    "research", "images/originals", "images/candidates", "images/approved", "masks", "animations/masters",
    "audio/synthesized", "audio/licensed", "audio/layers", "audio/mixes", "previews", "thumbnails", "metadata",
    "exports", "quality", "manifests", "licenses", "logs",
]


def ws() -> Path:
    return get_settings().workspace


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "project"


def safe_filename(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "file"


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", project_id):
        raise ValueError("invalid project id")
    p = ws() / "projects" / project_id
    for d in PROJECT_DIRS:
        (p / d).mkdir(parents=True, exist_ok=True)
    return p


def resolve(rel: str) -> Path:
    """Resolve a workspace-relative path and refuse traversal outside the workspace."""
    p = (ws() / rel).resolve()
    if not p.is_relative_to(ws().resolve()):
        raise ValueError("path outside workspace")
    return p


def rel(p: Path) -> str:
    return p.resolve().relative_to(ws().resolve()).as_posix()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def phash_image(p: Path) -> str | None:
    """64-bit DCT perceptual hash (hex) for duplicate/similarity checks."""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        small = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
        d = cv2.dct(small)[:8, :8]
        bits = (d > np.median(d[1:].ravel())).ravel()
        return "%016x" % int("".join("1" if b else "0" for b in bits), 2)
    except Exception:
        return None


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def register(db: Session, path: Path, *, kind: str, project_id: str | None, role: str | None = None, **kw) -> Asset:
    a = Asset(project_id=project_id, kind=kind, role=role, path=rel(path), sha256=sha256_file(path),
              size_bytes=path.stat().st_size, **kw)
    if kind in ("image", "thumbnail") and not a.phash:
        a.phash = phash_image(path)
        try:
            from PIL import Image
            with Image.open(path) as im:
                a.width, a.height = im.size
        except Exception:
            pass
    db.add(a)
    db.flush()
    return a


def disk_free_bytes() -> int:
    return shutil.disk_usage(ws()).free


def storage_report() -> dict:
    out = {}
    for sub in ("projects", "assets", "previews", "exports", "research", "cache", "backups"):
        p = ws() / sub
        out[sub] = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
    du = shutil.disk_usage(ws())
    out.update(total_used=sum(out.values()), disk_free=du.free, disk_total=du.total)
    return out
