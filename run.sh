#!/usr/bin/env bash
# Simple launcher for PaperAtlas

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "Error: OPENROUTER_API_KEY is not set. Get a key from https://openrouter.ai/keys"
  echo 'Then run: export OPENROUTER_API_KEY="your-key"'
  exit 1
fi

if [[ -z "${SKIP_INSTALL:-}" ]]; then
  echo "Installing Python dependencies (set SKIP_INSTALL=1 to skip)..."
  python3 -m pip install --quiet -r requirements.txt
fi

# Always ensure Playwright browser is present
echo "Ensuring Playwright Chromium is installed..."
python3 -m playwright install chromium >/dev/null 2>&1 || python3 -m playwright install chromium

echo "Starting PaperAtlas at http://localhost:5001 ..."
python3 app.py &
APP_PID=$!

sleep 2
if command -v open >/dev/null 2>&1; then
  open "http://localhost:5001"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:5001"
fi

wait $APP_PID
