#!/usr/bin/env sh
# TG Agent launcher for macOS / Linux: creates a virtual environment on first run, then starts the service.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if [ ! -x ".venv/bin/python" ]; then
  echo "[TG Agent] Creating virtual environment..."
  "$PY" -m venv .venv
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "[TG Agent] Installing dependencies..."
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
exec .venv/bin/python -m tgagent "$@"
