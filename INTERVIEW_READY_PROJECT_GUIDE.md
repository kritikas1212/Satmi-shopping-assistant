# SATMI Interview-Ready Project Guide

## Executive Summary

SATMI is a production-oriented, policy-aware chatbot for Shopify support and shopping flows. The system combines FastAPI, graph-orchestrated action routing, policy grounding, and observability for reliable customer operations.

Interview framing:
- It can answer catalog and support queries from live Shopify data.
- It enforces authentication and policy constraints on sensitive actions.
- It degrades gracefully to fallback data when dependencies fail.
- It offers measurable operational health via metrics, traces, and dependency checks.

## Findings and Action Plan

### Audit Findings

1. Medium: Product-context coverage existed but had brittle assertions.
  - Existing tests validated INR rendering but expected the literal word "stub" in user-facing text.
  - Current response intentionally uses user-friendly fallback wording instead.

2. Low: Synchronous Shopify calls are an explicit concurrency tradeoff.
  - `httpx.Client` + `time.sleep` in retry loops works, but blocks worker threads under high concurrency.
  - FastAPI threadpool behavior mitigates this for moderate load but is not ideal at larger scale.

3. Baseline test risk (environmental): Firebase bootstrap can fail in tests if runtime flags are not controlled.
  - Tests should disable Firebase auth by fixture unless explicitly testing Firebase behavior.

4. Metrics endpoint route mismatch was previously suspected but is no longer a code issue.
  - Route already uses configurable `METRICS_ENDPOINT_PATH`.

### Action Plan Implemented

1. Updated existing product-context tests to assert:
  - INR formatting in response text.
  - Graceful fallback wording for `stub` and `stub_fallback` sources.

2. Kept metrics route implementation unchanged because it is already config-driven.

3. Added test baseline stabilization by forcing Firebase auth flags off in shared test fixture.

4. Rewrote this guide with explicit production/readiness, startup, troubleshooting, and interview material.

## Architecture Overview

### Core Components

- API: FastAPI app exposing `/chat`, health, support, and observability endpoints.
- Orchestration: LangGraph-style state transitions for guardrails, intent, policy retrieval, tool actions, and response composition.
- Tools: Shopify-backed product/order tooling with fallback behavior.
- Persistence: SQLAlchemy-backed conversation, handoff, and async task records.
- Queue worker: cancellation queue processing with Redis support.
- Security: API key + role checks + Firebase verification for sensitive operations.
- Observability: Prometheus metrics, OpenTelemetry tracing, dependency health endpoints.

### Request Lifecycle (`/chat`)

1. Validate auth/rate limits and scrub PII.
2. Optionally hydrate authenticated order context.
3. Run graph nodes: guardrails -> intent -> policy -> action.
4. Call tools (`search_products`, `get_customer_orders`, `place_order`, etc.).
5. Compose a policy-aware final response.
6. Persist events and metadata for support visibility.

## Full Configuration Checklist

## 1) Local Dependencies

Required on macOS:
- Python 3.13+
- pip and venv
- PostgreSQL (local)
- Redis (local)

Optional but recommended:
- `jq` for readable diagnostics output
- `curl` for endpoint verification

## 2) Virtual Environment

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Environment Variables (`.env`)

| Area | Variable | Required | Example | Notes |
|---|---|---|---|---|
| Core | `APP_ENV` | Yes | `dev` | Use `prod` in production deployments. |
| Core | `API_PORT` | Yes | `8000` | Uvicorn bind port. |
| Core | `DATABASE_URL` | Yes | `postgresql+psycopg://user:pass@localhost:5433/satmi_chatbot` | SQLite fallback exists but Postgres is interview-ready default. |
| Core | `REDIS_URL` | Recommended | `redis://localhost:6379/0` | Needed for robust queueing. |
| LLM | `LLM_PROVIDER` | Yes | `gemini` | |
| LLM | `MODEL_NAME` | Yes | `gemini-2.0-flash` | |
| LLM | `GEMINI_API_KEY` | Yes | `<secret>` | |
| Shopify | `SHOPIFY_STORE_DOMAIN` | Yes for live catalog | `store.myshopify.com` | Admin API domain. |
| Shopify | `SHOPIFY_ADMIN_API_TOKEN` | Yes for live catalog | `<secret>` | Needs product/order scopes. |
| Shopify | `SHOPIFY_API_VERSION` | Yes | `2025-01` | |
| Security | `AUTH_REQUIRED` | Yes | `true` | Enable for production. |
| Security | `API_KEY` | Yes if auth required | `<secret>` | Required for protected endpoints. |
| Firebase | `FIREBASE_AUTH_ENABLED` | Yes | `true` or `false` | Enable only when credentials are correctly set. |
| Firebase | `FIREBASE_CREDENTIALS_PATH` | If Firebase enabled | `/absolute/path/key.json` | Must be readable by process user. |
| Firebase | `FIREBASE_PROJECT_ID` | If Firebase enabled | `satmi-xxxxxx` | |
| Firebase | `FIREBASE_REQUIRE_FOR_SENSITIVE_ACTIONS` | Recommended | `true` | Gating for place/cancel/order actions. |
| Behavior | `DISPLAY_CURRENCY_CODE` | Yes | `INR` | Output display preference. |
| Behavior | `USD_TO_INR_RATE` | Yes | `83.0` | Used when source price is USD. |
| Queue | `ASYNC_CANCEL_ENABLED` | Recommended | `true` | Enable async cancellation workflow. |
| Queue | `CANCEL_QUEUE_KEY` | Yes | `satmi:cancel:queue` | |
| Observability | `METRICS_ENDPOINT_ENABLED` | Yes | `true` | |
| Observability | `METRICS_ENDPOINT_PATH` | Yes | `/metrics` | Config-driven route. |

## 4) Shopify Validation Checklist

1. Confirm Admin token has required scopes.
2. Ensure products are active and published.
3. Verify domain format: `*.myshopify.com`.
4. Validate dependency health endpoint reports Shopify reachable.

## 5) Firebase Validation Checklist

1. `firebase-admin` must exist in active virtualenv.
2. Credentials file path must be absolute and readable.
3. Service account must belong to configured project.
4. If running local tests not focused on Firebase, disable Firebase in test fixture/config.

## 6) Postgres and Redis Checklist

1. Postgres reachable at `DATABASE_URL`.
2. Redis reachable at `REDIS_URL`.
3. `/system/healthz/deps` shows both as reachable.

## Bot Product Context (Live, Fallback, INR)

### Live Catalog Behavior

- Product search uses Shopify Admin API when credentials are configured and reachable.
- Response text explicitly notes live-catalog source when Shopify succeeds.

### Fallback Behavior

- If Shopify is unavailable or misconfigured, product responses continue via stub fallback data.
- User-facing response remains graceful and explicit: fallback catalog wording is included.
- This ensures high availability of conversational support even during dependency outages.

### Currency and INR Specifications

- If product currency is INR, response format is `INR <amount with 2 decimals>`.
- If source currency is USD and display currency is INR, conversion uses:

$$
	ext{INR amount} = \text{USD amount} \times \text{USD_TO_INR_RATE}
$$

- Example with default rate:

$$
29.99 \times 83.0 = 2489.17\ \text{INR}
$$

## Exact Startup Guide

## One-Shot Startup (Preferred)

```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
./scripts/start_local_stack.sh
```

What this script should validate:
- `.env` presence and required keys
- Firebase config consistency (if enabled)
- API + worker startup
- health and smoke checks

## Manual Startup (3 terminals)

Terminal 1 (API):
```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python -m uvicorn satmi_agent.main:app --port 8000
```

Terminal 2 (Worker):
```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
export PYTHONPATH=src
python scripts/process_cancellation_queue.py --sleep 1
```

Terminal 3 (Diagnostics):
```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -H "X-API-Key: <api_key>" -H "X-Role: support_agent" http://127.0.0.1:8000/system/healthz/deps
curl -sS -H "X-API-Key: <api_key>" -H "X-Role: support_agent" http://127.0.0.1:8000/system/config
curl -sS -H "X-API-Key: <api_key>" -H "X-Role: support_agent" http://127.0.0.1:8000/metrics
```

If `AUTH_REQUIRED=false`, remove auth headers.

## Troubleshooting Playbook

1. App fails at startup with Firebase error:
  - Install deps in active venv: `pip install -r requirements.txt`
  - Verify `firebase-admin` import works.
  - Set `FIREBASE_AUTH_ENABLED=false` for local non-Firebase runs.

2. Shopify degraded or fallback responses only:
  - Re-check token, domain, API version, network egress.
  - Validate `/system/healthz/deps` Shopify block.

3. Protected endpoint returns 401/403:
  - Confirm `AUTH_REQUIRED`, `API_KEY`, and `X-Role` values.

4. Worker not processing queue:
  - Confirm Redis connectivity and queue key.
  - Check worker logs for retry/error loops.

## Interview Preparation Pack

## Architecture Talking Points

1. Why graph orchestration over single-prompt pipelines.
2. How policy retrieval grounds responses and limits unsafe behavior.
3. Why sensitive actions require authentication interstitial.
4. How fallback + handoff protect customer experience under dependency failure.
5. Why observability and dependency health are first-class APIs.

## Tradeoffs (Be Explicit)

1. Sync Shopify client is simpler but less scalable for massive concurrency.
2. Fallback data improves resilience but can be stale compared with live catalog.
3. Strict auth gating protects users but can add friction for support flows.

## Security Talking Points

1. API key and support-role gates for admin/support endpoints.
2. PII scrubbing before graph invocation and persistence.
3. Firebase token verification for sensitive order operations.

## Demo Script (10-12 minutes)

1. Start stack locally and show health endpoint.
2. Show dependency diagnostics (`/system/healthz/deps`).
3. Ask product query and highlight live/fallback catalog source messaging.
4. Trigger sensitive action without auth and show interstitial.
5. Provide auth token path explanation and replay action.
6. Show cancellation policy redirect behavior.
7. Open metrics endpoint and explain key counters.

## 20 Interview Q and A

1. Q: Why not use a single LLM prompt chain?
  A: Deterministic node transitions are easier to test, observe, and audit.

2. Q: How do you prevent unsafe behavior?
  A: Guardrails + policy retrieval + explicit action routing + auth checks.

3. Q: How do you handle Shopify outages?
  A: Graceful fallback catalog responses and dependency health visibility.

4. Q: Why include handoff support?
  A: It limits blast radius for ambiguous or high-risk customer requests.

5. Q: How is pricing normalized?
  A: INR display formatting and optional USD->INR conversion via configurable rate.

6. Q: How do you enforce secure operations?
  A: Firebase verification for sensitive actions and role-gated support endpoints.

7. Q: What is your observability strategy?
  A: Request metrics, outcome counters, Shopify error counters, and traces.

8. Q: How do you test product-context quality?
  A: Endpoint-level tests for formatting, source behavior, and fallback messaging.

9. Q: How do you avoid PII leakage?
  A: Input scrubbing before graph and persistence.

10. Q: What are key reliability controls?
   A: Health checks, retries, fallback behavior, and async queue workers.

11. Q: Why run local Postgres and Redis?
   A: To mirror production behavior and surface integration issues earlier.

12. Q: How do you validate dependency health?
   A: `/system/healthz/deps` explicitly reports reachability and errors.

13. Q: What are your known scalability constraints?
   A: Synchronous external calls and threadpool pressure at high QPS.

14. Q: How would you scale next?
   A: Move Shopify calls to async client, add caching, autoscale API + worker.

15. Q: How do you validate policy behavior?
   A: Canned prompts for cancellation/auth/order flows and expected action assertions.

16. Q: How do you keep tests stable across environments?
   A: Fixture-level runtime setting resets and deterministic monkeypatching.

17. Q: Why include a worker process?
   A: It isolates long-running tasks and keeps chat latency low.

18. Q: How do you recover from credential failures?
   A: Fail fast on startup for misconfigured auth providers.

19. Q: What is your incident triage path?
   A: Health endpoint checks -> metrics anomalies -> dependency error surfaces -> logs.

20. Q: What makes this interview-ready?
   A: Reproducible startup, explicit tradeoffs, measurable behavior, and clear test coverage.

## Verification Plan

## Automated Tests

Run focused product-context validation:
```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
python -m pytest -q tests/test_product_context.py
```

Run complete suite:
```bash
cd /Users/kritikasingh/Downloads/Satmi-Chatbot
source .venv/bin/activate
python -m pytest -q tests
```

If suite fails due to Firebase bootstrap in local test env:
1. Confirm fixture disables Firebase flags for non-Firebase tests.
2. Or install/verify Firebase dependency in active virtualenv.

## Manual Verification

1. Confirm all startup commands execute on local macOS environment.
2. Verify `/health`, `/system/healthz/deps`, `/system/config`, and metrics endpoint output.
3. Validate product query response in both live and fallback modes.
4. Validate cancellation policy redirect and auth interstitial behaviors.
5. Review this guide for interview flow completeness and command copy/paste accuracy.

## Reference Files

- `README.md`
- `LOCAL_CHATBOT_SETUP_AND_RUN.md`
- `scripts/start_local_stack.sh`
- `scripts/process_cancellation_queue.py`
- `src/satmi_agent/main.py`
- `src/satmi_agent/nodes.py`
- `src/satmi_agent/tools.py`
- `tests/test_api.py`
- `tests/test_product_context.py`
- `tests/test_support_workflows.py`
