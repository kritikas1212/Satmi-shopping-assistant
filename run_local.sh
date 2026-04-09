#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pushd satmi-frontend >/dev/null
npm install
popd >/dev/null

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

PYTHONPATH=src uvicorn satmi_agent.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

(
  cd satmi-frontend
  npm run dev -- --port 3000
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
