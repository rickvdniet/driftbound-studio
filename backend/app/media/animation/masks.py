"""Region masks: normalized polygons, imported PNGs, invert, feathered edges (spec 16)."""
from pathlib import Path

import cv2
import numpy as np


def build_mask(spec: dict | None, w: int, h: int, workspace: Path | None = None) -> np.ndarray:
    """Return float32 (h, w) in [0, 1]. spec=None means the whole frame.

    spec = {"polygons": [[[x, y], ...], ...]  # normalized 0..1 coordinates
            "png": "projects/<id>/masks/sky.png",  # white = effect
            "invert": false, "feather": 0.01}      # feather as fraction of frame width
    """
    if not spec:
        return np.ones((h, w), np.float32)
    m = np.zeros((h, w), np.float32)
    for poly in spec.get("polygons", []):
        pts = np.array([[x * w, y * h] for x, y in poly], np.float32).round().astype(np.int32)
        if len(pts) >= 3:
            cv2.fillPoly(m, [pts], 1.0, lineType=cv2.LINE_AA)
    if spec.get("png"):
        p = Path(spec["png"]) if workspace is None else workspace / spec["png"]
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"mask image not readable: {spec['png']}")
        if img.ndim == 3:
            img = img[..., 3] if img.shape[2] == 4 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        m = np.maximum(m, img)
    if spec.get("rect"):
        x0, y0, x1, y1 = spec["rect"]
        m[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1.0
    if spec.get("invert"):
        m = 1.0 - m
    feather = spec.get("feather", 0.01)
    if feather:
        k = max(1, int(feather * w))
        m = cv2.GaussianBlur(m, (0, 0), sigmaX=k)
    return np.clip(m, 0, 1)


def preview_overlay(image_bgr: np.ndarray, mask: np.ndarray, color=(80, 200, 255)) -> np.ndarray:
    """Tint the masked area for visual inspection in the dashboard."""
    tint = np.zeros_like(image_bgr, np.float32)
    tint[:] = color
    m = mask[..., None] * 0.45
    return (image_bgr.astype(np.float32) * (1 - m) + tint * m).clip(0, 255).astype(np.uint8)
