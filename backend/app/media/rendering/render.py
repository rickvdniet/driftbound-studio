"""Visual masters, previews and long-duration final assembly (spec 19 + 24)."""
import subprocess
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.config.settings import get_settings
from app.media.animation.effects import EFFECTS
from app.media.animation.masks import build_mask
from app.media.mixing.mixer import safety_limit, stream
from app.media.rendering import ffmpeg as ff

Progress = Callable[[float, str], None]


def fit_image(path: Path, w: int, h: int, mode: str = "cover", focus=(0.5, 0.5)) -> np.ndarray:
    """Fit artwork to the frame without stretching: crop ('cover') or pad ('pad'). Returns float32 BGR 0..1."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot read image {path}")
    ih, iw = img.shape[:2]
    if mode == "pad":
        s = min(w / iw, h / ih)
        nw, nh = int(round(iw * s)), int(round(ih * s))
        r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LANCZOS4)
        out = np.zeros((h, w, 3), np.uint8)
        y, x = (h - nh) // 2, (w - nw) // 2
        out[y:y + nh, x:x + nw] = r
    else:
        s = max(w / iw, h / ih)
        nw, nh = int(np.ceil(iw * s)), int(np.ceil(ih * s))
        r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LANCZOS4)
        x = int((nw - w) * focus[0])
        y = int((nh - h) * focus[1])
        out = r[y:y + h, x:x + w]
    return out.astype(np.float32) / 255.0


def build_effects(base, anim: dict, w, h, T, fps, workspace: Path):
    effects = []
    for i, e in enumerate(anim.get("effects", [])):
        if not e.get("enabled", True):
            continue
        spec = e.get("mask")
        if isinstance(spec, str):  # named mask defined on the project
            spec = anim.get("masks", {}).get(spec)
        mask = build_mask(spec, w, h, workspace)
        effects.append(EFFECTS[e["type"]](w, h, T, fps, e.get("params", {}), mask, int(e.get("seed", i + 1)), base))
    return effects


def frame_iter(image_path: Path, anim: dict, w: int, h: int, fps: int, loop_s: float, workspace: Path, frames=None):
    base = fit_image(image_path, w, h, anim.get("fit", "cover"), tuple(anim.get("focus", (0.5, 0.5))))
    T = int(round(loop_s * fps))
    effects = build_effects(base, anim, w, h, T, fps, workspace)
    for f in (frames if frames is not None else range(T)):
        fr = base.copy()
        for e in effects:
            fr = e(fr, f % T)
        yield np.clip(fr * 255 + 0.5, 0, 255).astype(np.uint8)


def pick_encoder(preferred: str = "auto") -> str:
    if preferred not in ("auto", "", None):
        return preferred
    for enc in ("h264_nvenc", "h264_qsv", "h264_videotoolbox", "h264_amf"):
        if enc in ff.listed_encoders() and ff.test_encoder(enc):
            return enc
    return "libx264"


def render_master(image_path: Path, anim: dict, out: Path, *, w: int, h: int, fps: int, loop_s: float,
                  workspace: Path, encoder="libx264", crf=18, preset="medium", progress: Progress | None = None) -> dict:
    """Render one seamless loop (T frames) as an H.264 master with closed GOPs (safe for stream-copy looping)."""
    T = int(round(loop_s * fps))
    cmd = [get_settings().ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", *ff.video_encoder_args(encoder, crf, preset, fps),
           "-movflags", "+faststart", "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = time.time()
    try:
        for i, fr in enumerate(frame_iter(image_path, anim, w, h, fps, loop_s, workspace)):
            proc.stdin.write(fr.tobytes())
            if progress and i % max(1, fps) == 0:
                el = time.time() - t0
                eta = el / (i + 1) * (T - i - 1)
                progress((i + 1) / T, f"visual master frame {i + 1}/{T}, ~{eta:.0f}s left")
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise ff.FFmpegError(err[-1500:])
    except BaseException:
        proc.kill()
        out.unlink(missing_ok=True)
        raise
    return {"frames": T, "seconds": time.time() - t0, "encoder": encoder}


def loop_check(master: Path, image_path: Path, anim: dict, w: int, h: int, fps: int, loop_s: float, workspace: Path) -> dict:
    """Compare the jump across the loop boundary (last->first frame) with ordinary frame-to-frame change.
    Uses the exact generated frames (pre-encode) so the measurement reflects the animation itself."""
    T = int(round(loop_s * fps))
    idx = [T - 2, T - 1, 0, 1, T // 2, T // 2 + 1]
    fr = [f.astype(np.float32) for f in frame_iter(image_path, anim, w, h, fps, loop_s, workspace, frames=idx)]
    d = lambda a, b: float(np.mean(np.abs(a - b)))
    normal = np.mean([d(fr[0], fr[1]), d(fr[2], fr[3]), d(fr[4], fr[5])]) + 1e-6
    boundary = d(fr[1], fr[2])
    m = lambda a: float(a.mean())
    bright = abs(m(fr[1]) - m(fr[2]))
    typical_bright = np.mean([abs(m(fr[0]) - m(fr[1])), abs(m(fr[2]) - m(fr[3])), abs(m(fr[4]) - m(fr[5]))])
    ratio = boundary / normal
    bratio = bright / (typical_bright + 0.05)
    return {"boundary_diff": round(boundary, 4), "typical_diff": round(float(normal), 4), "ratio": round(float(ratio), 2),
            "brightness_jump": round(bright, 4), "brightness_ratio": round(float(bratio), 2),
            "seamless": bool(ratio < 2.5 and bratio < 4.0)}


def audio_to_wav(audio_cfg, duration_s, out: Path, sr, profile, ceiling_db):
    from scipy.io import wavfile
    data = np.concatenate(list(stream(audio_cfg, duration_s, sr, profile=profile)))
    wavfile.write(out, sr, safety_limit(data, ceiling_db))
    return out


def mux_preview(master: Path, audio_wav: Path, out: Path, duration_s: float, audio_kbps=192):
    ff.run(["-y", "-stream_loop", "-1", "-i", str(master), "-i", str(audio_wav), "-t", str(duration_s),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", f"{audio_kbps}k",
            "-movflags", "+faststart", "-shortest", str(out)])
    return out


def estimate_size_bytes(duration_s: float, video_kbps: float, audio_kbps: float) -> int:
    return int(duration_s * (video_kbps + audio_kbps) * 1000 / 8 * 1.02)


def render_final(master: Path, audio_cfg: dict, duration_s: float, out: Path, *, sr=48000, profile=None,
                 ceiling_db=-2.0, audio_kbps=192, progress: Progress | None = None) -> dict:
    """Long-duration assembly: the approved visual master is looped by stream copy (no re-encode),
    audio is synthesized chunk-by-chunk and piped straight into the AAC encoder (constant memory)."""
    tmp = out.with_suffix(".partial.mp4")
    cmd = [get_settings().ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-stream_loop", "-1", "-i", str(master),
           "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-",
           "-map", "0:v", "-map", "1:a", "-t", f"{duration_s:.3f}", "-c:v", "copy",
           "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ar", str(sr), "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0, done = time.time(), 0.0
    try:
        for chunk in stream(audio_cfg, duration_s, sr, profile=profile):
            proc.stdin.write(safety_limit(chunk, ceiling_db).astype(np.float32).tobytes())
            done += len(chunk) / sr
            if progress and int(done) % 30 == 0:
                el = time.time() - t0
                rate = done / max(el, 1e-6)
                progress(done / duration_s, f"assembled {done / 3600:.2f}/{duration_s / 3600:.2f} h, "
                                            f"{rate:.0f}x realtime, ~{(duration_s - done) / max(rate, 1e-6) / 60:.0f} min left")
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise ff.FFmpegError(err[-1500:])
        tmp.replace(out)
    except BaseException:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    return {"seconds": time.time() - t0}
