#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python scripts/export_reference.py --check
.venv/bin/python -m pytest backend/tests -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
