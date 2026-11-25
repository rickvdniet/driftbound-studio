"""Safe FFmpeg/FFprobe wrappers. Always argument arrays, never shell strings."""
import json
import re
import subprocess
from pathlib import Path

from app.config.settings import get_settings


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    cmd = [get_settings().ffmpeg, "-hide_banner", "-nostdin", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise FFmpegError(p.stderr[-2000:])
    return p


def probe(path: Path) -> dict:
    p = subprocess.run([get_settings().ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise FFmpegError(p.stderr[-1000:])
    return json.loads(p.stdout)


def loudness(path: Path, start: float | None = None, duration: float | None = None) -> dict:
    """Integrated loudness (LUFS), loudness range and true peak (dBTP) via the ebur128 filter."""
    args = []
    if start is not None:
        args += ["-ss", str(start)]
    args += ["-i", str(path)]
    if duration is not None:
        args += ["-t", str(duration)]
    args += ["-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    err = run(args).stderr
    summary = err[err.rfind("Summary:"):]
    def num(label):
        m = re.search(label + r":\s+(-?[\d.]+|-inf)", summary)
        return None if not m or m.group(1) == "-inf" else float(m.group(1))
    return {"integrated_lufs": num("I"), "lra": num("LRA"), "true_peak_db": num("Peak")}


def detect(path: Path, filt: str, start: float = 0, duration: float | None = None) -> list[dict]:
    """Run blackdetect / freezedetect / silencedetect and return detected intervals."""
    args = ["-ss", str(start), "-i", str(path)]
    if duration:
        args += ["-t", str(duration)]
    if filt.startswith("silencedetect"):
        args += ["-vn", "-af", filt]
    else:
        args += ["-an", "-vf", filt]
    err = run(args + ["-f", "null", "-"]).stderr
    out = []
    for m in re.finditer(r"(black_start|freeze_start|silence_start):\s*([\d.]+)", err):
        out.append({"type": m.group(1).split("_")[0], "start": float(m.group(2)) + start})
    return out


def test_encoder(name: str) -> bool:
    """An encoder counts as available only if it actually encodes a short clip."""
    try:
        run(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=0.5", "-c:v", name, "-f", "null", "-"], timeout=30)
        return True
    except Exception:
        return False


def listed_encoders() -> list[str]:
    try:
        out = run(["-encoders"]).stdout
    except Exception:
        return []
    return [m.group(1) for m in re.finditer(r"^\s*V\S*\s+(\S+)", out, re.M)]


def video_encoder_args(encoder: str, crf: int, preset: str, fps: int) -> list[str]:
    g = str(fps * 2)
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-g", g, "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-x264-params", "open-gop=0"]
    if encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", str(crf), "-g", g, "-pix_fmt", "yuv420p"]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(crf), "-g", g, "-pix_fmt", "nv12"]
    if encoder == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-q:v", "65", "-g", g, "-pix_fmt", "yuv420p"]
    if encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-g", g, "-pix_fmt", "yuv420p"]
    raise ValueError(f"unsupported encoder {encoder}")
