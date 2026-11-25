# Setup: installation, hardware and local AI

## 1. Prerequisites
| Tool | Version | Check |
|---|---|---|
| Python | 3.11–3.13 (3.12 recommended) | `python --version` |
| Node.js | 20+ | `node --version` |
| FFmpeg + FFprobe | 6+ (with libx264) | `ffmpeg -version` |

### FFmpeg
- **Windows:** `winget install Gyan.FFmpeg`, then open a new terminal.
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian/WSL2:** `sudo apt install ffmpeg`

## 2. Install & start
Run the start script, as described in the [README](../README.md#quick-start). To install by hand on Linux, macOS or WSL2:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
cd frontend && npm install && npm run build
```

### Native Windows (PowerShell)

```powershell
cd backend; py -3.12 -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
```

```powershell
cd ..\frontend; npm install; npm run build
```

```powershell
cd ..; .\scripts\start.ps1
```

If PowerShell blocks scripts, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Windows with WSL2
1. Install WSL2 and Ubuntu: `wsl --install -d Ubuntu`.
2. Clone the repo **inside** the Linux filesystem (`~/driftbound-studio`, not `/mnt/c/...`). This is much faster for media I/O.
3. Inside Ubuntu: `sudo apt install python3-venv ffmpeg nodejs npm`, then run `./scripts/start.sh`.
4. Open http://127.0.0.1:8000 in your Windows browser (WSL2 forwards localhost).
5. NVIDIA GPU in WSL2: install the normal Windows NVIDIA driver (not a Linux driver). `nvidia-smi` must work inside WSL.
   NVENC in the Ubuntu FFmpeg build may not work; the app tests this and falls back to libx264.

## 3. Hardware assessment
Open **Settings → Scan this computer**. It detects OS, CPU, RAM, GPU/VRAM, disk, Python, Node, FFmpeg, Ollama and
ComfyUI. Each hardware encoder is **tested with a real encode**; being listed by FFmpeg does not count as working.
The scan classifies suitability (good / limited / not recommended) for LLM, image generation, upscaling, AI video,
procedural animation, audio synthesis and long rendering, and gives a recommendation for each.

Rough guide (verify with the scan):
| Machine | LLM | Images | Procedural 1080p master (60 s) |
|---|---|---|---|
| 4-thread CPU, no GPU | 3B model or templates | import / procedural only | ~6 min |
| 8+ core CPU | 3–7B model on CPU | import | ~2–3 min |
| NVIDIA 8–12 GB | 7–8B Q4 | SDXL / FLUX schnell (quantized) | fast |
| NVIDIA 16–24 GB | 7–14B | SDXL / FLUX, local image-to-video experiments | fast |
| Apple Silicon 16 GB+ | 7B Q4 | SDXL via MPS (slow) | ~2–3 min |

## 4. Local language model (optional): Ollama
1. Install from https://ollama.com (Windows/macOS installer; Linux script).
2. Pull a model that fits your hardware and whose license fits commercial use. Check the license yourself before you pull:
   - `ollama pull qwen2.5:7b-instruct` (~4.7 GB; Qwen2.5-7B is Apache-2.0)
   - CPU-only alternative: a 3B model (check its license: some Qwen 3B variants use a research license, and Llama 3.2 uses the Llama Community License).
3. In Settings → Providers, set `"llm": "auto"` and `"llm_model": "qwen2.5:7b-instruct"`.
Without Ollama, every LLM task falls back to deterministic templates or manual entry.
**The app never downloads models itself.** You decide, after checking disk space and license.

## 5. Local image generation (optional): ComfyUI
Needs a GPU for practical speed (NVIDIA ≥ 8 GB VRAM, or Apple Silicon with patience).
1. Install ComfyUI (portable build on Windows, or `git clone` + `pip install -r requirements.txt`). Start it with `--listen 127.0.0.1`.
2. Download **one** model whose license you have checked, for example:
   - SDXL base 1.0 (CreativeML Open RAIL++-M, commercial use allowed with use restrictions, ~6.9 GB)
   - FLUX.1 [schnell] (Apache-2.0, ~23 GB fp16 / smaller quantized). Note: FLUX.1 [dev] has a **non-commercial** model license.
3. Build a 16:9 text-to-image workflow, then "Save (API format)". Replace the prompt text with `{{prompt}}`, the negative with
   `{{negative}}`, the seed with `{{seed}}`, and width/height with `{{width}}`/`{{height}}`.
4. Paste the JSON into Settings → Providers → `comfyui_workflow`, and set `"image": "comfyui"`.
Upscaling: Real-ESRGAN x4plus (BSD-3-Clause) inside the same workflow is the recommended path.

## 6. Relocating the workspace
Set `DRIFTBOUND_WORKSPACE=/big/disk/driftbound` in `.env`, stop the app, move the folder, then start again. Paths in
the database are workspace-relative.

## 7. Hardware acceleration
The render settings default to `"video_encoder": "auto"`, which picks the first *working* of NVENC, Quick Sync, VideoToolbox
or AMF, and otherwise libx264. For long videos the encoder matters less than you might expect: the visual master
(1–5 min) is encoded once and then stream-copied for the full duration.
