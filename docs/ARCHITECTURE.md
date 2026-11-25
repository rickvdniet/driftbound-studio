# Architecture

```
browser (React/TS/Vite/Tailwind, hash routes) ──HTTP/SSE──▶ FastAPI (127.0.0.1:8000)
                                                            │  routes → services (pipeline, research, budget, state machine)
                                                            ▼
                                       SQLite (WAL) ◀──── worker process(es): claim job → handler → progress/heartbeat
                                                            │
                                    media engine: effects + masks → visual master (FFmpeg pipe)
                                                  generators + mixer → streamed PCM → FFmpeg (AAC)
                                    providers: LLM (Ollama/template) · image (procedural/ComfyUI/import)
                                               YouTube (mock/OAuth) · research (YouTube Data API) · paid stubs
```

- **No microservices.** One API process and one or more worker processes share the SQLite database. A job is claimed
  atomically (`UPDATE … WHERE status='queued'`). Workers send heartbeats. On start, `recover_stale()` requeues interrupted
  jobs (bounded attempts). Users can cancel at progress checkpoints.
- **Data model** (`backend/app/models`): settings, keywords, competitor channels/videos/snapshots, api_usage (cache +
  quota), concepts, projects (JSON config: brief, animation, audio, render, metadata, QA), state_transitions, approvals
  (config hash + valid flag), assets (hash, pHash, provider, model, prompt, seed, license, cost), jobs, cost_entries,
  uploads, metric_records, experiments, metadata_revisions.
- **Migrations**: Alembic, run automatically on API and worker start.
- **Workspace**: `workspace/projects/<id>/{images,masks,animations,audio,previews,thumbnails,exports,...}`. Paths in the DB
  are workspace-relative, so the folder can be relocated. File serving rejects paths outside the workspace.
- **Security**: binds to localhost only, no credentials in the frontend, log redaction, FFmpeg via argument arrays,
  upload size limits, filename sanitization, external text stored as data only.
