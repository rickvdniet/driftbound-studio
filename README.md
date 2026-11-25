# Driftbound Studio

Local-first, free-first production platform for original long-form ambient YouTube videos
(the **Driftbound Ambience** channel). It covers research, concepts, procedural animation,
sound synthesis, mixing, long-duration rendering, QA, thumbnails, SEO metadata, publishing
packages and analytics. **It needs no paid API.** Paid providers exist only as disabled
interfaces behind a budget guard.

## Quick start

Requirements: Python 3.11+ (3.12 recommended), Node.js 20+, FFmpeg on `PATH`.
Details per OS (Windows, WSL2, macOS, Linux) are in [docs/SETUP.md](docs/SETUP.md).

```bash
./scripts/start.sh          # Linux / macOS / WSL2
```

```powershell
.\scripts\start.ps1         # native Windows
```

Then open http://127.0.0.1:8000. The script creates the venv, builds the dashboard, and starts the API and the worker.

Development mode with hot reload (three terminals):

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1
```

```bash
cd backend && .venv/bin/python -m app.workers.worker
```

```bash
cd frontend && npm run dev     # http://127.0.0.1:5173
```

## Workflow

1. **Settings → Scan this computer.** Checks hardware, tests encoders, and looks for Ollama and ComfyUI.
2. **Keywords & Competitors.** Import a vidIQ, TubeBuddy, Google Trends or Studio CSV, or add keywords by hand. With a free YouTube Data API key you can also collect competitor data. Every score shows its evidence and confidence.
3. **Concepts.** 15 seed concepts plus generation (a local LLM, or templates as fallback). Approve a concept and click "Start production".
4. **Production workspace.** The stages run in this order:
   - Image candidates (procedural painter, ComfyUI or import), then approve the visual direction.
   - Region masks (click polygons on the image).
   - Procedural effects.
   - Soundscape layers.
   - Build a 60 s preview, then approve it.
   - Render 30 s to 8 h.
   - QA report, thumbnail choice and metadata editing.
   - Approve the final video.
   - Export the upload package, upload privately, then publish (each step needs its own confirmation).
5. **Analytics.** Import YouTube Studio CSVs or enter channel snapshots, follow YPP progress, run the business-case calculator.

Run the demo without the UI while the API and worker are running: `backend/.venv/bin/python scripts/demo_saturn.py 600`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

The suite includes a zero-API-cost end-to-end test (concept → 60 s video → QA → mocked private upload → €0 spend) and a 5-minute long-assembly test.

## Documentation

| File | Contents |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phases, status, acceptance criteria, risks |
| [docs/SETUP.md](docs/SETUP.md) | Installation, Windows/WSL2, FFmpeg, hardware acceleration, Ollama, ComfyUI, models |
| [docs/PRODUCTION_GUIDE.md](docs/PRODUCTION_GUIDE.md) | Animation, audio synthesis, mixing, rendering, licensing, SEO, brand |
| [docs/PROVIDERS_AND_COSTS.md](docs/PROVIDERS_AND_COSTS.md) | Providers, model licenses, cost model, budget rules |
| [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md) | Google Cloud project, OAuth, quotas, manual publishing fallback |
| [docs/POLICY_CHECKLIST.md](docs/POLICY_CHECKLIST.md) | Monetization, disclosure and originality checklist |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data model, state machine, job queue |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems, backup and recovery |
