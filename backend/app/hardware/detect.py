"""Hardware & environment detection and suitability classification (spec 5).

Cross-platform best effort: Linux, macOS, Windows (native) and WSL2. Every probe is optional and time-boxed.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import psutil

from app.config.settings import get_settings


def _run(cmd: list[str], timeout=8) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def cpu_model() -> str:
    if sys.platform.startswith("linux"):
        m = re.search(r"model name\s*:\s*(.+)", Path("/proc/cpuinfo").read_text(errors="ignore")) if Path("/proc/cpuinfo").exists() else None
        if m:
            return m.group(1).strip()
    if sys.platform == "darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip() or platform.processor()
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"])
        return out.strip() or platform.processor()
    return platform.processor() or "unknown"


def gpus() -> list[dict]:
    found = []
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                found.append({"vendor": "NVIDIA", "name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1),
                              "driver": parts[2] if len(parts) > 2 else None})
    if shutil.which("rocm-smi"):
        out = _run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"])
        try:
            for card, v in json.loads(out).items():
                vram = next((int(x) for k, x in v.items() if "Total Memory" in k), 0)
                found.append({"vendor": "AMD", "name": v.get("Card series", card), "vram_gb": round(vram / 2 ** 30, 1)})
        except Exception:
            pass
    if sys.platform == "darwin":
        out = _run(["system_profiler", "SPDisplaysDataType", "-json"], 15)
        try:
            for g in json.loads(out).get("SPDisplaysDataType", []):
                found.append({"vendor": "Apple" if "Apple" in g.get("sppci_model", "") else g.get("spdisplays_vendor", "?"),
                              "name": g.get("sppci_model"), "vram_gb": None,
                              "note": "Apple Silicon shares system memory (unified memory)"})
        except Exception:
            pass
    if sys.platform == "win32" and not found:
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json"])
        try:
            data = json.loads(out)
            for g in data if isinstance(data, list) else [data]:
                found.append({"vendor": "?", "name": g.get("Name"), "vram_gb": round((g.get("AdapterRAM") or 0) / 2 ** 30, 1),
                              "note": "AdapterRAM is capped at 4 GB by Windows WMI; verify in Task Manager"})
        except Exception:
            pass
    return found


def torch_accel() -> dict:
    """Only reports if PyTorch is already installed; never installs it."""
    try:
        import importlib.util
        if importlib.util.find_spec("torch") is None:
            return {"torch": False}
        import torch
        return {"torch": True, "cuda": torch.cuda.is_available(), "mps": getattr(torch.backends, "mps", None) is not None
                and torch.backends.mps.is_available()}
    except Exception as e:
        return {"torch": False, "error": str(e)[:200]}


def ollama() -> dict:
    s = get_settings()
    info = {"binary": shutil.which("ollama"), "reachable": False, "models": []}
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=2)
        info["reachable"] = r.status_code == 200
        info["models"] = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return info


def comfyui() -> dict:
    s = get_settings()
    info = {"reachable": False, "system": None, "candidate_dirs": []}
    try:
        r = httpx.get(f"{s.comfyui_url}/system_stats", timeout=2)
        info["reachable"] = r.status_code == 200
        info["system"] = r.json()
    except Exception:
        pass
    home = Path.home()
    for d in (home / "ComfyUI", home / "comfyui", home / "Documents" / "ComfyUI", Path("C:/ComfyUI")):
        if d.exists():
            info["candidate_dirs"].append(str(d))
    return info


def encoders() -> dict:
    from app.media.rendering import ffmpeg as ff
    listed = set(ff.listed_encoders())
    out = {}
    for enc in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox", "hevc_nvenc"):
        out[enc] = {"listed": enc in listed, "works": ff.test_encoder(enc) if enc in listed else False}
    return out


def detect(test_encoders=True) -> dict:
    s = get_settings()
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(s.workspace)
    is_wsl = "microsoft" in platform.uname().release.lower()
    info = {
        "os": platform.system(), "os_release": platform.release(), "wsl": is_wsl, "machine": platform.machine(),
        "cpu_model": cpu_model(), "cpu_cores_physical": psutil.cpu_count(logical=False), "cpu_threads": psutil.cpu_count(),
        "ram_total_gb": round(vm.total / 2 ** 30, 1), "ram_available_gb": round(vm.available / 2 ** 30, 1),
        "disk_free_gb": round(du.free / 2 ** 30, 1), "disk_total_gb": round(du.total / 2 ** 30, 1),
        "python": platform.python_version(), "node": _run(["node", "--version"]).strip() or None,
        "ffmpeg": shutil.which(s.ffmpeg), "ffprobe": shutil.which(s.ffprobe),
        "ffmpeg_version": (_run([s.ffmpeg, "-version"]).splitlines() or [None])[0],
        "gpus": gpus(), "accel": torch_accel(), "ollama": ollama(), "comfyui": comfyui(),
        "encoders": encoders() if test_encoders else {},
        "container_hint": Path("/.dockerenv").exists() or bool(os.environ.get("CLAUDE_CODE_REMOTE")),
    }
    info["assessment"] = assess(info)
    return info


def assess(i: dict) -> dict:
    """Rule-based suitability classes: good | limited | not_recommended, with reasons and recommendations."""
    vram = max([g.get("vram_gb") or 0 for g in i["gpus"]] + [0])
    nvidia = any(g["vendor"] == "NVIDIA" for g in i["gpus"])
    apple = any(g.get("vendor") == "Apple" for g in i["gpus"]) or (i["os"] == "Darwin" and i["machine"] == "arm64")
    ram, threads = i["ram_total_gb"], i["cpu_threads"] or 1
    hw_enc = [k for k, v in i.get("encoders", {}).items() if v.get("works") and k != "libx264"]

    def c(level, why, rec=None):
        return {"level": level, "why": why, "recommendation": rec}

    llm = (c("good", f"{vram} GB VRAM", "7–8B instruct model at Q4 (e.g. qwen2.5:7b-instruct, Apache-2.0)") if vram >= 8 else
           c("good", f"Apple unified memory {ram} GB", "qwen2.5:7b-instruct Q4") if apple and ram >= 16 else
           c("limited", f"CPU only, {ram} GB RAM", "3–4B model on CPU (e.g. qwen2.5:3b — check its license; or llama3.2:3b under the Llama license); or use templates") if ram >= 8 else
           c("not_recommended", f"only {ram} GB RAM", "Use deterministic templates + manual/imported text"))
    img = (c("good", f"NVIDIA {vram} GB", "SDXL base 1.0 (CreativeML OpenRAIL++-M) or FLUX.1 [schnell] (Apache-2.0) via ComfyUI") if nvidia and vram >= 10 else
           c("limited", f"NVIDIA {vram} GB", "SDXL with --lowvram / SD 1.5-class models; FLUX quantized (GGUF) builds") if nvidia and vram >= 6 else
           c("limited", "Apple Silicon (MPS)", "SDXL via ComfyUI on MPS: slow but workable (minutes per image)") if apple and ram >= 16 else
           c("not_recommended", "no suitable GPU", "Import artwork (manual or from existing subscriptions) or use the procedural painter for space scenes"))
    up = (c("good", "GPU available", "Real-ESRGAN x4plus (BSD-3-Clause) via ComfyUI") if (nvidia and vram >= 4) or apple else
          c("limited", "CPU only", "OpenCV Lanczos upscale (built in) or Real-ESRGAN ncnn on CPU (slow)"))
    vid = (c("limited", f"NVIDIA {vram} GB", "Wan2.1/2.2 image-to-video (Apache-2.0) via ComfyUI; short clips only, verify license before use") if nvidia and vram >= 16 else
           c("not_recommended", f"{vram} GB VRAM" if vram else "no CUDA GPU", "Use procedural animation (default)"))
    proc = c("good" if threads >= 8 else "limited", f"{threads} CPU threads",
             "1080p masters render at roughly 3–10 fps on CPU; 4K is ~4x slower")
    audio = c("good", f"{threads} threads", "Synthesis runs faster than realtime on most CPUs")
    render = c("good" if hw_enc or threads >= 8 else "limited",
               f"tested hardware encoders: {', '.join(hw_enc) or 'none'}; libx264 fallback",
               "Long videos stream-copy the visual master, so final assembly time is dominated by audio synthesis")
    return {"local_llm": llm, "image_generation": img, "upscaling": up, "ai_video": vid,
            "procedural_animation": proc, "audio_synthesis": audio, "long_rendering": render}
