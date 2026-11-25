"""Three local thumbnail candidates from the project artwork (spec 25). Pillow only; font = Pillow's bundled
default (Aileron, CC0) so no font licensing issue."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1280, 720
MAX_BYTES = 2 * 1024 * 1024  # YouTube custom thumbnail limit (2 MB); verify current limit


def _cover(img: Image.Image, w, h, cx=0.5, cy=0.5, zoom=1.0):
    s = max(w / img.width, h / img.height) * zoom
    r = img.resize((max(w, int(img.width * s)), max(h, int(img.height * s))), Image.LANCZOS)
    x = int((r.width - w) * cx)
    y = int((r.height - h) * cy)
    return r.crop((x, y, x + w, y + h))


def _focus(img: Image.Image):
    """Brightest smooth region as a simple saliency proxy (planet, window, fire)."""
    g = np.asarray(img.convert("L").resize((64, 36)).filter(ImageFilter.GaussianBlur(4)), np.float32)
    y, x = np.unravel_index(np.argmax(g), g.shape)
    return x / 63, y / 35


def _vignette(img: Image.Image, strength=0.45):
    a = np.asarray(img, np.float32)
    yy, xx = np.mgrid[0:img.height, 0:img.width]
    d = np.sqrt(((xx - img.width / 2) / (img.width / 2)) ** 2 + ((yy - img.height / 2) / (img.height / 2)) ** 2)
    a *= (1 - strength * np.clip(d - 0.4, 0, 1))[..., None]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def _save(img: Image.Image, out: Path):
    for q in (92, 85, 78, 70):
        img.save(out, "JPEG", quality=q, optimize=True, progressive=True)
        if out.stat().st_size <= MAX_BYTES:
            return out
    return out


def generate(src: Path, out_dir: Path, *, text: str | None, palette: dict, exposure=1.08, contrast=1.12) -> list[dict]:
    img = Image.open(src).convert("RGB")
    fx, fy = _focus(img)
    gold = palette.get("muted_gold", "#D9C9A0")
    variants = []
    # A: full scene, cinematic grade
    a = _vignette(ImageEnhance.Contrast(ImageEnhance.Brightness(_cover(img, W, H)).enhance(exposure)).enhance(contrast))
    variants.append(("full_scene", a, "Full composition, gentle vignette, no text"))
    # B: tighter crop on the focal element
    b = _cover(img, W, H, cx=min(max(fx, 0), 1), cy=min(max(fy, 0), 1), zoom=1.35)
    b = _vignette(ImageEnhance.Color(ImageEnhance.Contrast(b).enhance(contrast + 0.08)).enhance(1.1), 0.55)
    variants.append(("focal_crop", b, "Zoomed on the brightest focal element"))
    # C: full scene + minimal brand-styled text (e.g. duration)
    c = a.copy()
    if text:
        d = ImageDraw.Draw(c)
        font = ImageFont.load_default(size=86)
        tw = d.textlength(text, font=font)
        x, y = W - tw - 60, H - 150
        d.text((x + 3, y + 3), text, font=font, fill=(12, 21, 40))
        d.text((x, y), text, font=font, fill=gold)
    variants.append(("text_overlay", c, f"Minimal text overlay: '{text}'" if text else "Same as A (no text configured)"))
    out = []
    for name, im, note in variants:
        p = _save(im, out_dir / f"thumb_{name}.jpg")
        im.resize((320, 180), Image.LANCZOS).save(out_dir / f"thumb_{name}_small.jpg", quality=85)
        out.append({"path": p, "variant": name, "note": note, "bytes": p.stat().st_size})
    return out
