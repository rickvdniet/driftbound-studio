#!/usr/bin/env bash
# One-command start (Linux / macOS / WSL2): API + worker + built dashboard on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/.."
command -v ffmpeg >/dev/null || { echo "FFmpeg not found. See docs/SETUP.md"; exit 1; }
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -e "backend[dev]"
fi
if [ ! -d frontend/dist ]; then (cd frontend && npm install --no-audit --no-fund && npm run build); fi
cd backend
.venv/bin/python -m app.workers.worker & WORKER=$!
trap 'kill $WORKER 2>/dev/null' EXIT
echo "Driftbound Studio: http://127.0.0.1:${DRIFTBOUND_PORT:-8000}"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${DRIFTBOUND_PORT:-8000}"
