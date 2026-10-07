#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  printf 'Run bash scripts/install.sh first.\n' >&2
  exit 1
fi
if ! .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12); import uvicorn, fastapi, pydantic, httpx' >/dev/null 2>&1; then
  printf 'Backend environment is incomplete or uses another Python version. Run bash scripts/install.sh with Python 3.12.\n' >&2
  exit 1
fi
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
VIN_BACKEND_PID=$!
trap 'kill "$VIN_BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
npm run dev --prefix frontend
