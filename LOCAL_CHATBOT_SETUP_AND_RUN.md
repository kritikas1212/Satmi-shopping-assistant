# SATMI Chatbot Local Run Guide (No Docker, End-to-End)

This guide is the full start-to-finish flow to run the SATMI chatbot locally on macOS without containers.

It includes:
- One-time machine setup
- Project setup
- Required `.env` configuration
- Running API + worker
- Sending chat messages
- Tracking async cancellation tasks
- Troubleshooting common errors

---

## 1) What You Are Running

This project has 2 long-running Python processes:

1. API server (FastAPI)
- Endpoint base: `http://127.0.0.1:8000`
- Main chat endpoint: `POST /chat`

2. Cancellation worker
- Consumes queue jobs from Redis
- Processes async cancellation tasks created by `/chat`

For full functionality, you need both processes running.

---

## 2) Prerequisites (One-Time)

Install on macOS:
- Homebrew
- Python 3.13
- PostgreSQL (Homebrew)
- Redis (Homebrew)

Check versions:

```bash
brew --version
python3 --version
psql --version
redis-server --version
```

---

## 3) Start Local Services (Postgres + Redis)

Start services:

```bash
brew services start postgresql@14
brew services start redis
```

Verify:

```bash
brew services list | grep -E "postgresql@14|redis"
```

Expected: both should show `started`.

Note about port conflicts:
- If you also run Postgres.app on 5432, keep Homebrew Postgres on 5433 and use that in `.env`.

---

## 4) Project Setup (One-Time)

From project root:

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create local env file:

```bash
cp .env.example .env
```

---

## 5) Required `.env` Values

Set these in `.env`.

### Core local runtime

```env
APP_ENV=dev
API_PORT=8000
DATABASE_URL=postgresql+psycopg://kritikasingh@localhost:5433/satmi_chatbot
REDIS_URL=redis://localhost:6379/0
ASYNC_CANCEL_ENABLED=true
TRACING_ENABLED=false
AUTH_REQUIRED=false
```

### Gemini

```env
LLM_PROVIDER=gemini
MODEL_NAME=gemini-2.0-flash
GEMINI_API_KEY=<your_real_gemini_key>
GEMINI_INTENT_CLASSIFIER_API_KEY=<separate_classifier_key_optional>
```

Optional conversation-intent classifier controls:

```env
CONVERSATION_INTENT_CLASSIFIER_ENABLED=true
CONVERSATION_INTENT_SHADOW_MODE=false
CONVERSATION_INTENT_USE_LLM_PRIMARY=true
CONVERSATION_INTENT_ALLOW_HEURISTIC_FALLBACK=false
CONVERSATION_INTENT_RAW_MODE=true
CONVERSATION_INTENT_RAW_DISABLE_REDACTION=false
```

### Shopify (required for real Shopify operations)

```env
SHOPIFY_STORE_DOMAIN=<your-store.myshopify.com>
SHOPIFY_ADMIN_API_TOKEN=<your_real_shopify_token>
SHOPIFY_API_VERSION=2025-01
```

If Shopify values are wrong, cancellation tasks can still be created but may fail during processing.

---

## 6) Create Database (If Needed)

If DB does not exist yet:

```bash
createdb -p 5433 satmi_chatbot
```

Quick check:

```bash
psql -p 5433 -d postgres -c "\\l" | grep satmi_chatbot
```

---

## 7) Run the App (Every Time)

Open 3 terminals.

### Terminal 1: API

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python -m uvicorn satmi_agent.main:app --reload --port 8000
```

Keep this running.

### Terminal 2: Worker

Important: the worker script is in `scripts/`, not project root.

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python scripts/process_cancellation_queue.py --sleep 1
```

Keep this running.

### Terminal 3: Requests / Testing

Use this terminal for `curl` commands.

---

## 8) Verify Health

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

---

## 9) Start Chatting

### Option A: API docs UI (easy)

Open in browser:
- `http://127.0.0.1:8000/docs`

Use `POST /chat` with JSON body.

### Option B: Terminal `curl`

First message:

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","conversation_id":"c1","message":"Hi, where is my order #1001?"}'
```

Continue same conversation (same `conversation_id`):

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","conversation_id":"c1","message":"Please cancel order #1001"}'
```

---

## 10) Track Async Cancellation Tasks

When cancellation is queued, `/chat` response metadata contains:
- `async_task_id`

Query task status:

```bash
curl -sS http://127.0.0.1:8000/tasks/<REAL_TASK_ID>
```

Status values you may see:
- `queued`
- `in_progress`
- `completed`
- `failed`

---

## 11) What Your Previous Errors Mean

### Error A
`can't open file ... process_cancellation_queue.py: [Errno 2] No such file or directory`

Cause:
- Wrong script path.

Fix:

```bash
python scripts/process_cancellation_queue.py --sleep 1
```

### Error B
`ls: process_cancellation_queue.py: No such file or directory`

Cause:
- You checked root path.

Fix:

```bash
ls scripts/process_cancellation_queue.py
```

### Error C
Worker exits with `KeyboardInterrupt` and code `130`

Cause:
- Worker was manually interrupted with `Ctrl+C`.

Fix:
- Restart worker and keep it running.

### Error D
`{"detail":"Async task not found"}`

Cause:
- Placeholder ID used (example: `PASTE_TASK_ID`).

Fix:
- Use real `metadata.async_task_id` from `/chat` response.

### Error E
Task status is `failed` with Shopify error

Cause:
- Queue and worker are working, but Shopify call failed.
- Usually invalid token/domain, missing scopes, or order not found.

Fix checklist:
- Verify `SHOPIFY_STORE_DOMAIN`
- Verify `SHOPIFY_ADMIN_API_TOKEN`
- Verify app scopes: `read_orders`, `write_orders`, `read_products`
- Verify order reference exists

---

## 12) Minimal Daily Startup Checklist

Run in order:

1. Start services

```bash
brew services start postgresql@14
brew services start redis
```

2. Start API (Terminal 1)

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python -m uvicorn satmi_agent.main:app --reload --port 8000
```

3. Start worker (Terminal 2)

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python scripts/process_cancellation_queue.py --sleep 1
```

4. Send chat (Terminal 3)

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","conversation_id":"c1","message":"Hello"}'
```

---

## 13) Optional: If Auth Is Enabled

If `AUTH_REQUIRED=true`, include API key header in requests:

```bash
-H "X-API-Key: <your_api_key>"
```

Support endpoints may also require role header:

```bash
-H "X-Role: support_agent"
```

---

## 14) Stop Everything

- In API terminal: `Ctrl+C`
- In worker terminal: `Ctrl+C`

Services can remain running in background, or stop them:

```bash
brew services stop postgresql@14
brew services stop redis
```

---

## 15) Quick Reality Check

If these are true, your chatbot is running correctly:
- `/health` returns `{"status":"ok"}`
- `POST /chat` returns response JSON
- Worker stays running in terminal
- `/tasks/<real_task_id>` returns task record

If task is `failed` but record exists, app/queue path is healthy and the failure is integration-specific (usually Shopify config/data).
