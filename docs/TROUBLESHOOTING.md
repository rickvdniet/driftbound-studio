# Troubleshooting

| Problem | Fix |
|---|---|
| Jobs stay "queued" | The worker isn't running. Start `python -m app.workers.worker` in `backend/` (the start scripts do this). |
| A job was interrupted (crash, reboot) | Restart the worker. It requeues interrupted jobs (max 2 attempts). Otherwise use "Retry that stage". |
| "Approve the current preview before a full render" | The animation or audio config changed after approval. Rebuild the preview and approve it again. |
| "Audio gain is stale" | Same cause: rebuild the preview. |
| Hardware encoder listed but not used | The scan found it doesn't actually encode (driver, WSL or build). libx264 is used instead. |
| `ffmpeg` not found | Install it (see SETUP.md) or set `DRIFTBOUND_FFMPEG` to the full path. |
| Upload blocked "Confirm the audience" | Settings → Publishing → `made_for_kids_confirmed: true/false`. |
| Upload stays private | Expected. Unverified API projects can only upload privately. Publish in YouTube Studio or pass the API audit. |
| Not enough disk space | Free space or move the workspace (`DRIFTBOUND_WORKSPACE`). Final videos are hard-linked into exports, not copied. |
| Research "quota limit reached" | Wait for the daily reset (Pacific time) or lower `max_results_per_query`. Cached results stay usable. |

## Backup & recovery
- Settings → Backup (or `POST /api/backup`) makes a consistent SQLite copy in `workspace/backups/`.
- Media lives in `workspace/projects/`. Back up the whole `workspace/` folder with your usual tool.
- The app never deletes approved originals. Re-rendering marks the old final as `superseded` and leaves the file in place.

## Known limitations
See IMPLEMENTATION_PLAN.md (status legend and risks).
