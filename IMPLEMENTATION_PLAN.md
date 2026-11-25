# Implementation plan & status

Status legend: ✅ implemented and tested · 🟡 implemented, not verified live (needs credentials/hardware) ·
🔑 needs your credentials · 🖥️ limited by local hardware · ⛔ blocked by platform rules · 🔜 future.

Build environment used for development and tests: Linux container, 4-thread Xeon CPU, 15.7 GB RAM, **no GPU**,
FFmpeg with libx264 (NVENC/QSV listed by FFmpeg but **not functional** there, so they are correctly rejected).
Your own machine's assessment comes from **Settings → Scan this computer**.

## Phase 1: Foundation ✅
| Task | Status | Acceptance |
|---|---|---|
| Hardware detection + suitability classes (Win/macOS/Linux/WSL2) | ✅ | runs without GPU; encoders tested by real encode |
| FastAPI + SQLAlchemy + SQLite WAL + Alembic migrations | ✅ | `migrate()` on start |
| Persistent job queue + separate worker, heartbeat, crash recovery, cancel, retry | ✅ | `test_job_recovery_after_crash` |
| Workspace layout, hashing, path-traversal protection | ✅ | `test_secret_redaction_and_path_traversal` |
| Central brand/app settings (DB, editable) | ✅ | |
| Paid-provider blocking + budget reservation/duplicate protection | ✅ | `test_paid_provider_blocked_by_default`, `test_budget_enforcement_and_duplicates` |
| React/TS/Vite/Tailwind dashboard (10 sections, SSE job stream) | ✅ | `npm run build` passes |

## Phase 2: Research & concepts ✅ (live API 🔑)
| Task | Status |
|---|---|
| Seed keyword clusters (32 keywords) and 15 seed concepts with template briefs | ✅ |
| CSV imports (vidIQ/TubeBuddy/Trends/Studio search terms) with data-kind labels | ✅ |
| Weighted opportunity scoring, renormalized for missing inputs, confidence, evidence | ✅ |
| YouTube Data API research: cache, quota tracking, batching, backoff, retention purge | ✅ with mock transport · 🔑 live |
| Competitor metrics: lifetime vs measured views/day, views/sub, vs channel median, small-channel outperformers | ✅ |
| Ollama structured outputs + bounded retries + template fallback | 🟡 (no Ollama in build env; fallback tested) |

## Phase 3: First complete local production ✅
| Task | Status |
|---|---|
| Image import (license capture), crop/pad without stretching, procedural scene painter | ✅ |
| Procedural effects: rain, snow, embers, dust, bubbles, stars, fog/clouds, fire/candle/ambient glow, caustics, water shimmer / sway, window droplets | ✅ all loop-validated |
| Region masks: polygons, PNG, rect, invert, feather, preview overlay, click-to-draw UI | ✅ |
| Sound generators: white/pink/brown, hum, ventilation, wind, ocean, drone, rain, fire, rhythmic, thunder, underwater | ✅ |
| Mixer: per-layer gain/pan/EQ/variation, mute/solo, seeded, chunked, loudness targeting, limiter, fades | ✅ |
| Visual master + loop-boundary check + preview mux | ✅ |
| Long render: stream-copied master loop + streamed audio | ✅ 5 min test, 1 h and 8 h demo (see bottom) |
| Technical QA (codecs, duration, sync, loudness, peaks, silence, black/freeze) | ✅ |
| Thumbnails (3 variants, size previews), metadata (limits, no medical claims) | ✅ |

## Phase 4: Advanced local production (partial)
| Task | Status |
|---|---|
| ComfyUI image provider (documented /prompt, /history, /view) | 🟡 🖥️ |
| Licensed sound import with provenance + crossfaded loop layer | ✅ |
| Local upscaling (Real-ESRGAN) | 🔜 (OpenCV Lanczos used in fit) |
| Local AI video (Wan via ComfyUI) | 🔜 🖥️ needs ≥16 GB VRAM |
| Layered parallax effect | 🔜 (deliberately skipped: camera stays still) |
| Painted masks in UI / segmentation models | 🔜 (PNG import covers painted masks) |

## Phase 5: Creative & SEO ✅
Briefs, approvals with config hashes and downstream invalidation, thumbnails, metadata revisions, originality checks
(pHash, SHA-256), creative QA, production manifest.

## Phase 6: Publishing 🟡
| Task | Status |
|---|---|
| Manual upload package (MP4 hard link, thumbnail, texts, manifest, checklist) | ✅ |
| Mock publisher, duplicate-upload protection, audience confirmation gate | ✅ |
| OAuth (google-auth-oauthlib) + resumable upload + thumbnail + playlist + scheduling | 🟡 🔑 |

## Phase 7: Analytics & business (partial)
| Task | Status |
|---|---|
| Studio CSV import, manual snapshots, YPP progress, cost dashboard, forecast calculator | ✅ |
| YouTube Analytics API pull | 🔜 🔑 (scope + token flow ready in `scripts/youtube_auth.py analytics`) |
| Experiments: data model + API | ✅ (no dedicated UI yet 🔜) |
| LLM performance recommendations | 🔜 (needs real performance data first) |

## Phase 8: Hardening (ongoing)
21 automated tests pass. Known gaps: no auth on the API (it binds to localhost only), single-user design.

## Phase 9: Paid integrations ⛔ by design
OpenAI / Runway / ElevenLabs exist as interfaces only. Revisit only after the free workflow is validated.

## Known risks
- **YouTube "inauthentic/repetitive content" policy.** Procedural scenes must stay visibly distinct per video. Use the originality checks and keep the catalogue small and varied.
- **Procedural painter quality.** Fine for space skies, too weak for interiors. Cabins, libraries and gardens need ComfyUI (GPU) or imported art.
- **Synthetic fire, birds and streams** sound less real than recordings. Use licensed CC0 recordings for those layers.
- **CPU rendering speed.** About 5–6 fps for 1080p masters on 4 threads (a 60 s master takes ~6 min). Final assembly is fast.
- **API policies and limits** (quota costs, YPP thresholds, upload limits) change. They are marked "verify" in code and docs.

## Long-duration validation log
Run 2026-11-25, build container (4-thread Xeon CPU, no GPU, libx264), project "Sleeping Near Saturn", 1080p30,
60 s procedural master (stars + clouds + ambient glow), 4 synthesized audio layers:

| Duration | Render time | Size | Result |
|---|---|---|---|
| 60 s preview (incl. 1080p master) | 342 s | – | loop seamless (boundary ratio 0.96), −20.4 LUFS |
| 10 min | 47 s | 83 MB | technical + creative QA pass |
| **8 h** | **35.5 min (~13.5× realtime)** | **3.96 GB** | **QA pass**: duration 28800.07 s, A/V aligned, −20.4 LUFS, LRA 2.3, true peak −4.5 dBTP, no silence/black/frozen frames |

Memory stayed flat during the 8 h assembly (worker ≈170 MB RSS, FFmpeg ≈66 MB).
