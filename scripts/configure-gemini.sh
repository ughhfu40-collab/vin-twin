#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
read -r -s -p 'Gemini API key (input hidden): ' VIN_GEMINI_KEY
printf '\n'
if [[ ! "$VIN_GEMINI_KEY" =~ ^[A-Za-z0-9_-]+$ ]]; then
  printf 'Invalid API key format.\n' >&2
  exit 1
fi
umask 077
VIN_GEMINI_TEMP=$(mktemp .env-gemini.XXXXXX)
trap 'rm -f "$VIN_GEMINI_TEMP"' EXIT
if [ -f .env ]; then
  sed '/^GEMINI_API_KEY=/d' .env > "$VIN_GEMINI_TEMP"
fi
printf '\nGEMINI_API_KEY=%s\n' "$VIN_GEMINI_KEY" >> "$VIN_GEMINI_TEMP"
mv "$VIN_GEMINI_TEMP" .env
chmod 600 .env
unset VIN_GEMINI_KEY
printf 'Gemini configured in local .env. Restart bash scripts/dev.sh.\n'
