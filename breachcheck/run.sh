#!/usr/bin/env bash
# One-step launcher for macOS / Linux.
# Creates a local virtualenv, installs deps, and starts BreachCheck on 127.0.0.1:8787.
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3 not found. Install it from https://python.org and re-run."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo ">> creating virtualenv..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
. .venv/bin/activate
echo ">> installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

URL="http://127.0.0.1:8787"
echo ">> starting BreachCheck at $URL  (Ctrl+C to stop)"

# Try to open the browser once the server is up (best-effort, non-fatal).
( sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi ) >/dev/null 2>&1 &

exec python app.py
