"""ComfyUI provider using its documented HTTP API: POST /prompt, GET /history/{id}, GET /view.

You export your workflow in "API format" from ComfyUI and save it in Settings. Placeholders in the JSON are
replaced: "{{prompt}}", "{{negative}}", "{{seed}}", "{{width}}", "{{height}}". Status: implemented, not verified
against a live ComfyUI here (no GPU in the build environment).
"""
import json
import time
import uuid
from pathlib import Path

import httpx

from app.config.settings import get_settings


def _fill(obj, values):
    if isinstance(obj, dict):
        return {k: _fill(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, values) for v in obj]
    if isinstance(obj, str) and obj.startswith("{{") and obj.endswith("}}"):
        return values.get(obj[2:-2], obj)
    return obj


def generate(workflow_json: str, out_dir: Path, *, prompt: str, negative: str, seed: int, width=1920, height=1088,
             timeout_s=900, transport=None) -> list[Path]:
    url = get_settings().comfyui_url
    wf = _fill(json.loads(workflow_json), {"prompt": prompt, "negative": negative, "seed": seed, "width": width, "height": height})
    with httpx.Client(timeout=30, transport=transport) as c:
        r = c.post(f"{url}/prompt", json={"prompt": wf, "client_id": uuid.uuid4().hex})
        r.raise_for_status()
        pid = r.json()["prompt_id"]
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            h = c.get(f"{url}/history/{pid}").json()
            if pid in h:
                outs = []
                for node in h[pid].get("outputs", {}).values():
                    for im in node.get("images", []):
                        data = c.get(f"{url}/view", params={"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                            "type": im.get("type", "output")}).content
                        p = out_dir / f"comfy_{pid[:8]}_{im['filename']}"
                        p.write_bytes(data)
                        outs.append(p)
                return outs
            time.sleep(2)
    raise TimeoutError("ComfyUI did not finish in time")
