# CLAUDE.md

Driftbound Studio: local, free-first production platform for long ambient YouTube videos.
Read this first; details live in `docs/` and `IMPLEMENTATION_PLAN.md`.

## Non-negotiables
- **No paid API calls, ever, without the budget guard** (`backend/app/services/budget.py::reserve`).
  Paid usage is off by default, budgets are €0, and there is no automatic paid fallback.
- **Never fabricate data.** Search volume, analytics and competitor metrics come only from imports/APIs and are
  labeled by kind (verified / third_party_estimate / relative_interest / proxy / heuristic). Missing stays missing.
- **Human gates:** concept, image, preview, final and publish approvals are human-only states (`state_machine.HUMAN_ONLY`).
  Uploads are always private first. No full render without a valid preview approval for the current config hash.
- Branding comes from settings (`settings_store.DEFAULTS["brand"]`), never hardcoded in UI or templates.
- Credentials only via env/`secrets/` (git-ignored); never sent to the frontend or logged (`logging_setup.redact`).
- FFmpeg via argument arrays only (`media/rendering/ffmpeg.py`).

## Layout
- `backend/app/media/` animation effects (seamless by construction), synthesis generators, mixer, rendering.
- `backend/app/services/pipeline.py` stage logic + job handlers; `workers/` DB-backed queue + worker process.
- `backend/app/research/` scoring + competitor metrics; `providers/` LLM, image, YouTube, research, paid stubs.
- `frontend/src/pages/ProjectWorkspace.tsx` main production UI.

## Commands
```
cd backend && .venv/bin/python -m pytest -q          # all tests (~1 min)
cd backend && .venv/bin/alembic revision --autogenerate -m "msg"   # after model changes
cd frontend && npm run build                          # type-check + build
./scripts/start.sh                                    # run everything on 127.0.0.1:8000
```

## Conventions
- Determinism: audio renders in fixed 1 s chunks with seeded layers. The final's first 60 s equal the approved preview.
- Any time-varying visual must be periodic in the loop length (integer cycles or two-phase flow). Check with `loop_check`.
- Config changes after an approval must call `state_machine.invalidate_from`.
