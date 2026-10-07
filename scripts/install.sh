#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VIN_PYTHON="${VIN_PYTHON:-python3.12}"
if ! command -v "$VIN_PYTHON" >/dev/null 2>&1; then
  printf 'Python 3.12 is required. On macOS with Homebrew: brew install python@3.12\n' >&2
  printf 'Then run: bash scripts/install.sh\n' >&2
  exit 1
fi
if [ "$("$VIN_PYTHON" -c 'import sys; print("%s.%s" % sys.version_info[:2])')" != "3.12" ]; then
  printf 'Python 3.12 is required; the selected interpreter has another version.\n' >&2
  printf 'Run: VIN_PYTHON=python3.12 bash scripts/install.sh\n' >&2
  exit 1
fi
if [ -d .venv ]; then
  VIN_EXISTING_VERSION="$(.venv/bin/python -c 'import sys; print("%s.%s" % sys.version_info[:2])' 2>/dev/null || true)"
  if [ "$VIN_EXISTING_VERSION" != "3.12" ]; then
    VIN_BACKUP="$(mktemp -d .venv-backup.XXXXXX)"
    mv .venv "$VIN_BACKUP/environment"
    printf 'Previous environment preserved in %s/environment\n' "$VIN_BACKUP"
  fi
fi
"$VIN_PYTHON" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend --cache "$PWD/.npm-cache" --no-audit --no-fund
printf '\nInstallation complete. Run: bash scripts/dev.sh\n'
