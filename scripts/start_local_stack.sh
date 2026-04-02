#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/.logs}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT_DEFAULT="8000"
WORKER_SLEEP="${WORKER_SLEEP:-1}"

mkdir -p "$LOG_DIR"

log() {
  printf '[start] %s\n' "$*"
}

fail() {
  printf '[start][error] %s\n' "$*" >&2
  exit 1
}

print_log_tail() {
  local label="$1"
  local path="$2"
  if [[ -f "$path" ]]; then
    printf '\n[start] Last 40 lines of %s (%s):\n' "$label" "$path"
    tail -n 40 "$path" || true
  fi
}

require_cmd() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 || fail "Required command not found: $name"
}

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Env file not found at $ENV_FILE"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  fail "Python virtualenv not found at $VENV_DIR. Create it and run pip install -r requirements.txt first."
fi

require_cmd curl

# Export all values from .env for this process and child processes.
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

PYTHON_BIN="$VENV_DIR/bin/python"
API_PORT="${API_PORT:-$API_PORT_DEFAULT}"
BASE_URL="http://${API_HOST}:${API_PORT}"

log "Preflight: validating required environment keys"
[[ -n "${DATABASE_URL:-}" ]] || fail "DATABASE_URL is required"
[[ -n "${GEMINI_API_KEY:-}" ]] || fail "GEMINI_API_KEY is required"
[[ -n "${SHOPIFY_STORE_DOMAIN:-}" ]] || fail "SHOPIFY_STORE_DOMAIN is required"
[[ -n "${SHOPIFY_ADMIN_API_TOKEN:-}" ]] || fail "SHOPIFY_ADMIN_API_TOKEN is required"

if [[ "${AUTH_REQUIRED:-false}" == "true" ]]; then
  [[ -n "${API_KEY:-}" ]] || fail "AUTH_REQUIRED=true but API_KEY is empty"
fi

if [[ "${FIREBASE_AUTH_ENABLED:-false}" == "true" ]]; then
  FIREBASE_CREDENTIALS_PATH="${FIREBASE_CREDENTIALS_PATH:-}"
  [[ -n "$FIREBASE_CREDENTIALS_PATH" ]] || fail "FIREBASE_AUTH_ENABLED=true but FIREBASE_CREDENTIALS_PATH is empty"
  [[ -r "$FIREBASE_CREDENTIALS_PATH" ]] || fail "Firebase JSON is not readable: $FIREBASE_CREDENTIALS_PATH"

  FIREBASE_JSON_PATH="$FIREBASE_CREDENTIALS_PATH" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys

path = os.environ["FIREBASE_JSON_PATH"]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception as exc:
    print(f"Invalid Firebase JSON at {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)

required = {"type", "project_id", "private_key", "client_email"}
missing = sorted(k for k in required if not data.get(k))
if missing:
    print(f"Firebase JSON missing keys: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(1)
PY

  log "Firebase JSON validated: $FIREBASE_CREDENTIALS_PATH"
else
  log "Firebase auth disabled; skipping Firebase JSON validation"
fi

API_LOG="$LOG_DIR/api.log"
WORKER_LOG="$LOG_DIR/worker.log"

cleanup() {
  local code=$?
  if [[ -n "${WORKER_PID:-}" ]] && kill -0 "$WORKER_PID" >/dev/null 2>&1; then
    kill "$WORKER_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
  wait >/dev/null 2>&1 || true
  if [[ $code -ne 0 ]]; then
    log "Stopped with errors. Check logs: $API_LOG and $WORKER_LOG"
  else
    log "Stopped cleanly"
  fi
}
trap cleanup EXIT INT TERM

log "Starting API on ${BASE_URL}"
PYTHONPATH=src "$PYTHON_BIN" -m uvicorn satmi_agent.main:app --host "$API_HOST" --port "$API_PORT" >"$API_LOG" 2>&1 &
API_PID=$!

log "Starting worker"
PYTHONPATH=src "$PYTHON_BIN" scripts/process_cancellation_queue.py --sleep "$WORKER_SLEEP" >"$WORKER_LOG" 2>&1 &
WORKER_PID=$!

log "Waiting for API readiness"
ready="false"
for _ in $(seq 1 30); do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    ready="true"
    break
  fi
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    print_log_tail "api.log" "$API_LOG"
    fail "API process exited early. See $API_LOG"
  fi
  sleep 1
done

if [[ "$ready" != "true" ]]; then
  fail "API did not become ready in time. See $API_LOG"
fi

log "API is healthy. Running diagnostics"

AUTH_HEADERS=()
if [[ "${AUTH_REQUIRED:-false}" == "true" ]]; then
  AUTH_HEADERS+=( -H "X-API-Key: ${API_KEY}" -H "X-Role: support_agent" )
fi

printf '\n=== /health ===\n'
curl -fsS "$BASE_URL/health"
printf '\n\n=== /system/healthz/deps ===\n'
if [[ ${#AUTH_HEADERS[@]} -gt 0 ]]; then
  curl -fsS "${AUTH_HEADERS[@]}" "$BASE_URL/system/healthz/deps"
else
  curl -fsS "$BASE_URL/system/healthz/deps"
fi
printf '\n\n=== /system/config ===\n'
if [[ ${#AUTH_HEADERS[@]} -gt 0 ]]; then
  curl -fsS "${AUTH_HEADERS[@]}" "$BASE_URL/system/config"
else
  curl -fsS "$BASE_URL/system/config"
fi
printf '\n\n=== /chat smoke ===\n'
if [[ ${#AUTH_HEADERS[@]} -gt 0 ]]; then
  curl -fsS "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" -X POST "$BASE_URL/chat" \
    -d '{"user_id":"startup-smoke-user","conversation_id":"startup-smoke-conv","message":"hello"}'
else
  curl -fsS -H "Content-Type: application/json" -X POST "$BASE_URL/chat" \
    -d '{"user_id":"startup-smoke-user","conversation_id":"startup-smoke-conv","message":"hello"}'
fi
printf '\n\n'

log "Startup complete"
log "API PID: $API_PID"
log "Worker PID: $WORKER_PID"
log "Logs: $API_LOG and $WORKER_LOG"
log "Press Ctrl+C to stop both processes"

while true; do
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    print_log_tail "api.log" "$API_LOG"
    fail "API process exited. See $API_LOG"
  fi
  if ! kill -0 "$WORKER_PID" >/dev/null 2>&1; then
    print_log_tail "worker.log" "$WORKER_LOG"
    fail "Worker process exited. See $WORKER_LOG"
  fi
  sleep 2
done
