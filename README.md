# SATMI Chatbot (LangGraph + LangChain)

Production-oriented starter for a SATMI customer support + shopping assistant with mandatory human handoff when requests are out of scope.

## Scope of Work (Detailed)

### 1) Discovery & Business Definition
- Define supported intents for V1: order tracking, cancellation, basic shopping suggestions.
- Define out-of-scope categories requiring manual support.
- Define SLA for manual handoff queue and response times.
- Finalize policy rules (e.g., cancellation eligibility windows, refund restrictions).

### 2) Backend Foundation
- Set up FastAPI service with health and chat endpoints.
- Create graph-based orchestration with deterministic control flow.
- Add typed request/response schemas.
- Add structured state object to preserve conversation workflow data.

### 3) LangGraph Workflow
- Intent classification node.
- Policy guard node.
- Action execution node (tool invocation).
- Conditional branch for human handoff.
- Response composition node for final user response.
- Audit logging for traceability.

### 4) Tools & Integrations
- Order APIs: fetch, cancellation, tracking.
- Shopping APIs: search, recommendations, cart/checkout (future step).
- Policy/knowledge retrieval (RAG) for support responses.
- Ticketing API integration for manual agent handoff.

### 5) Handoff & Human-in-the-Loop
- Escalate on: out-of-scope, low confidence, repeated failures, or user asks for human.
- Generate ticket payload with summary, actions attempted, errors, context.
- Return handoff id + ETA to customer.
- Keep thread state as `awaiting_human` until manual agent resumes.

### 6) Data, Security, and Compliance
- Add auth/authz for user identity and API tool access.
- Mask PII in logs and prompts.
- Store audit logs and ticket trails.
- Add rate limiting and abuse protection.

### 7) Observability & QA
- LangSmith traces and OpenTelemetry metrics.
- Unit tests for policy + routing + handoff.
- Integration tests for support/shopping flows.
- Load and failure mode testing.

### 8) Rollout Plan
- V1: track + cancel + product discovery + handoff.
- V2: cart and checkout automation.
- V3: multilingual support and advanced personalization.

## What’s Implemented Right Now
- FastAPI app with `/health` and `/chat`.
- LangGraph workflow with nodes:
  - `input_guardrails`
  - `classify_intent`
  - `policy_guard`
  - `retrieve_policy`
  - `execute_action`
  - `compose_response`
  - `handoff_to_human`
- Shopify-backed order/shopping actions with local fallback stubs.
- Manual handoff with generated handoff id and ETA.
- Phase 2 persistence (conversation event storage + handoff ticket lifecycle).
- Thread-aware LangGraph checkpointer integration (Postgres saver when available, in-memory fallback).
- State channels split for scalability:
  - `message_history` for LLM-facing context
  - `internal_logs` for diagnostics/audit trail
- Phase 3 baseline grounding:
  - Policy retrieval snippets used in response composition
  - Input guardrails for sensitive/toxic patterns
  - Auto-handoff when request is not policy-grounded
- Phase 4 security and reliability baseline:
  - API key auth support (`AUTH_REQUIRED`, `API_KEY`)
  - Role-based access for support operations (`X-Role: support_agent|admin`)
  - PII masking before storage/response metadata
  - In-memory per-user/IP rate limiting for `/chat`
  - Shopify retry/backoff and normalized error messaging
- Phase 5 QA baseline:
  - Automated pytest suite for core API/security behavior
  - Golden query evaluator (`evaluations/golden_queries.json`)
  - GitHub Actions CI workflow running tests + evaluator
  - Phase 5.1 integration tests for support workflows (`/handoffs/*`, `/conversations/*`)
  - Phase 5.2 runtime hardening:
    - FastAPI lifespan-based startup initialization
    - Concurrent smoke load test script (`scripts/load_test_smoke.py`)
    - Phase 5.3 observability baseline:
      - Prometheus-style request counters, latency histograms, and inflight gauge
      - `/metrics` endpoint protected by support-role auth when auth is enabled
      - Phase 5.4 distributed tracing baseline:
        - OpenTelemetry request spans for HTTP middleware
        - OpenTelemetry spans for Shopify API calls and retries
        - OTLP exporter configuration for collector backends
      - Phase 5.5 SRE alerting baseline:
        - Business/reliability metric families for handoffs, auth failures, rate-limit hits, and Shopify error classes
        - Prometheus alert rule pack for error-rate, latency, handoff spikes, and integration failures
        - Grafana dashboard template for operations overview
      - Phase 5.6 local deployment bundle:
        - Dockerized app runtime (`Dockerfile`)
        - One-command observability stack compose file (`docker-compose.observability.yml`)
        - Prometheus scrape config + alert rule mounting
        - Grafana datasource/dashboard provisioning
        - OpenTelemetry Collector service for OTLP traces
      - Phase 5.7 production hardening bundle:
        - Non-root container runtime and image healthcheck
        - Production compose profile with restart policy, read-only fs, tmpfs, and no-new-privileges
        - Resource limit/reservation defaults for app container
        - Deployment checklist and production env template
      - Phase 6 assistant completion layer:
        - External policy knowledge base loaded from JSON file (`data/policy_kb.json`)
        - Native HITL interrupt/resume support (feature-flagged)
        - Async cancellation queue mode with task status API and worker script
- Handoff lifecycle endpoints:
  - `GET /handoffs/{handoff_id}`
  - `POST /handoffs/{handoff_id}/status`
  - `POST /handoffs/{handoff_id}/resume`
  - `GET /conversations/{conversation_id}/events`

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
uvicorn satmi_agent.main:app --reload --port 8000
```

Set database for dev/prod:

```bash
export DATABASE_URL="postgresql+psycopg://username:password@localhost:5432/satmi_chatbot"
```

If `DATABASE_URL` is not set, the app defaults to local SQLite (`satmi_agent.db`) for development.

Security headers when auth is enabled:

```bash
-H "X-API-Key: <your-api-key>"
```

Support-only endpoints additionally require:

```bash
-H "X-Role: support_agent"
```

Install all dependencies (including optional Postgres checkpointer):

```bash
pip install -r requirements.txt
```

## Production Notes from Architecture Review

- **Checkpointer**: enabled in graph compile path. For production thread persistence, use Postgres and install `langgraph-checkpoint-postgres`.
- **State bloat control**: LLM context (`message_history`) is now separated from internal diagnostics (`internal_logs`).
- **HITL interrupts**: lifecycle endpoints are implemented; native `interrupt`/`Command(resume=...)` graph pausing can be added as the next enhancement.
- **Shopify limits**: add Redis caching for product reads and a task queue (Celery/Arq) for cancellation retries to avoid throttle spikes.
- **Evaluation**: add LangSmith golden-set evaluators in CI for regression detection.

## Phase 4 Environment Controls

- `AUTH_REQUIRED`: enforce API key auth (recommended `true` in production).
- `API_KEY`: shared secret for authenticated API access.
- `RATE_LIMIT_ENABLED`: enables `/chat` limiter.
- `RATE_LIMIT_REQUESTS` + `RATE_LIMIT_WINDOW_SECONDS`: limiter thresholds.
- `SHOPIFY_TIMEOUT_SECONDS`: per-request timeout for Shopify calls.
- `SHOPIFY_MAX_RETRIES`: retry count for transient Shopify errors and throttling.
- `GEMINI_INTENT_CLASSIFIER_API_KEY`: optional dedicated Gemini key for conversation intent classification (falls back to `GEMINI_API_KEY` when unset).
- `CONVERSATION_INTENT_ALLOW_HEURISTIC_FALLBACK`: if `true`, falls back to assistant-event heuristics when classifier call fails.
- `CONVERSATION_INTENT_RAW_MODE`: if `true`, runs less constrained full-transcript classification and stores raw model label/output metadata.
- `CONVERSATION_INTENT_RAW_DISABLE_REDACTION`: if `true` with raw mode, transcript sent to classifier is not PII-scrubbed.

## Phase 5 Validation

Run test suite locally:

```bash
PYTHONPATH=src pytest -q
```

Run golden dataset evaluation:

```bash
PYTHONPATH=src python scripts/evaluate_golden_set.py --min-pass-rate 0.80
```

CI pipeline is available at:

- `.github/workflows/ci.yml`

Integration coverage now includes:

- Authenticated handoff lifecycle (`open` → `in_progress` → `resolved`)
- Support-role access checks for conversation and handoff endpoints

Load test smoke profile:

```bash
PYTHONPATH=src python scripts/load_test_smoke.py --base-url http://127.0.0.1:8000 --requests 50 --concurrency 10
```

If auth is enabled:

```bash
PYTHONPATH=src python scripts/load_test_smoke.py --base-url http://127.0.0.1:8000 --requests 50 --concurrency 10 --api-key "<your-api-key>"
```

Metrics endpoint (support role when auth is enabled):

```bash
curl -H "X-API-Key: <your-api-key>" -H "X-Role: support_agent" http://127.0.0.1:8000/metrics
```

Tracing controls (OTLP collector):

```bash
export TRACING_ENABLED=true
export TRACING_EXPORTER=otlp
export TRACING_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

By default, tracing is disabled unless explicitly enabled via `TRACING_ENABLED=true`.

Prometheus alert rules location:

- `monitoring/prometheus/alerts.yml`

Grafana dashboard template location:

- `monitoring/grafana/satmi-overview-dashboard.json`

## Phase 5.6 Local Deployment Stack

Start full local stack (app + Prometheus + Grafana + OTEL collector):

```bash
docker compose -f docker-compose.observability.yml up --build
```

Service URLs:

- API: `http://localhost:8000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (default `admin` / `admin`)

Stack configuration files:

- `Dockerfile`
- `docker-compose.observability.yml`
- `monitoring/prometheus/prometheus.yml`
- `monitoring/prometheus/alerts.yml`
- `monitoring/otel-collector-config.yml`
- `monitoring/grafana/provisioning/datasources/prometheus.yml`
- `monitoring/grafana/provisioning/dashboards/dashboards.yml`

## Phase 5.7 Production Hardening

Production compose profile:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.production.yml up --build -d
```

Hardening artifacts:

- `docker-compose.production.yml`
- `.env.production.example`
- `DEPLOYMENT_CHECKLIST.md`

Key hardening controls now included:

- Non-root app user in container image
- Container healthcheck for `/health`
- `read_only` root filesystem + `tmpfs` for writable temp
- `no-new-privileges` security option
- Resource limits/reservations for production profile

## Phase 5.8 Kubernetes Deployment Pack

Base Kubernetes apply (namespace + app resources):

```bash
kubectl apply -k k8s/base
```

Apply with Prometheus Operator `ServiceMonitor`:

```bash
kubectl apply -k k8s/monitoring
```

Create runtime secret from template:

```bash
cp k8s/base/secret.example.yaml k8s/base/secret.yaml
# Edit secret values before applying
kubectl apply -f k8s/base/secret.yaml
```

Kubernetes resources included:

- Namespace (`satmi`)
- Deployment with readiness/liveness probes and hardened security context
- ClusterIP service (`satmi-app`) on port `8000`
- Ingress template (`satmi.example.com` host placeholder)
- HPA (CPU + memory utilization targets)
- PodDisruptionBudget
- Optional Prometheus Operator `ServiceMonitor`

## Phase 5.9 CI/CD Automation

Automated build + deploy pipeline:

- Workflow file: `.github/workflows/cd.yml`
- Build: Docker image pushed to GHCR (`ghcr.io/<owner>/<repo>:<git-sha>`)
- Deploy: applies `k8s/base` and rolls deployment to the new image tag on `main`/`master`

Required GitHub repository secrets:

- `KUBE_CONFIG_BASE64`: base64-encoded kubeconfig with deploy permissions.
- `SATMI_APP_SECRET_YAML_BASE64`: base64-encoded Kubernetes Secret manifest for `satmi-app-secrets`.

Optional best practice:

- Use GitHub Environment `production` with required reviewers before deploy job execution.

## Phase 6.0 Safe Deploy Controls

Deployment safety controls now added to `.github/workflows/cd.yml`:

- Automatic rollback (`kubectl rollout undo`) if rollout or smoke check fails.
- Optional post-deploy smoke gate via `DEPLOY_SMOKE_URL` secret.
- Optional authenticated smoke request via `DEPLOY_SMOKE_API_KEY` secret.

Recommended smoke URL examples:

- Public health endpoint: `https://satmi.example.com/health`
- Internal probe endpoint routed through trusted gateway.

## Phase 6.1 Assistant Completion Controls

New runtime flags:

- `POLICY_KB_PATH` and `POLICY_RETRIEVAL_MAX_ITEMS`
- `HITL_INTERRUPT_ENABLED`
- `ASYNC_CANCEL_ENABLED`, `REDIS_URL`, and `CANCEL_QUEUE_KEY`

Async cancellation worker:

```bash
PYTHONPATH=src python scripts/process_cancellation_queue.py
```

Task status endpoint:

- `GET /tasks/{task_id}` (support role required)

## Final Production-On Pass

Production defaults are now enabled:

- `HITL_INTERRUPT_ENABLED=true`
- `ASYNC_CANCEL_ENABLED=true`

Production runtime now includes:

- Redis queue backend
- Dedicated cancellation worker process (`satmi-cancel-worker`)
- CD rollout updating both API and worker deployments

## Comprehensive Implementation Summary

### Phase 1 — Commerce Integration
- Added Shopify-backed tool layer for orders, product search, and cancellations.
- Added robust Shopify configuration (`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_API_TOKEN`, `SHOPIFY_API_VERSION`).
- Added fallback local stub behavior when Shopify credentials are not configured.

### Phase 2 — Persistence & Handoff Lifecycle
- Added database persistence for conversation events and handoff tickets.
- Added handoff lifecycle APIs and status flow (`open`, `in_progress`, `resolved`).
- Added thread-aware conversation tracking via `conversation_id`.

### Phase 3 — Grounding & Guardrails
- Added input guardrail checks (sensitive/toxic patterns).
- Added policy retrieval node and policy-grounded response behavior.
- Added escalation when a request is not safely grounded.

### Phase 4 — Security & Reliability
- Added API-key authentication and role-based support endpoint protection.
- Added PII masking for stored events and response metadata.
- Added chat rate limiting and Shopify retry/backoff with normalized error messaging.

### Phase 5 — QA & Delivery
- Added unit and API tests with pytest.
- Added golden query evaluation harness and dataset.
- Added CI workflow to run tests + evaluator on push/PR.
- Added support workflow integration tests for `/handoffs/*` and `/conversations/*`.
- Added Phase 5.2 runtime hardening:
  - migrated startup hook to FastAPI lifespan
  - added concurrent load test smoke script.
- Added Phase 5.3 observability baseline:
  - added Prometheus-style request metrics collection middleware
  - added protected `/metrics` endpoint for scraping.
- Added Phase 5.4 tracing baseline:
  - added OpenTelemetry tracing setup with configurable OTLP/console exporter
  - added HTTP request tracing spans and Shopify tool-call spans.
- Added Phase 5.5 SRE baseline:
  - added business/reliability counters for chat outcomes, handoff volume, auth failures, rate-limit hits, and Shopify error classes
  - added deployable Prometheus alert rules and Grafana dashboard template.
- Added Phase 5.6 deployment bundle:
  - added Dockerfile and `.dockerignore` for containerized API runtime
  - added one-command Docker Compose stack for app + Prometheus + Grafana + OpenTelemetry Collector
  - added Prometheus scrape configuration and Grafana provisioning files for auto-loaded monitoring.
- Added Phase 5.7 production hardening bundle:
  - hardened app image runtime (non-root + healthcheck)
  - added production compose profile with resource/security controls
  - added production env template and deployment checklist.
- Added Phase 5.8 Kubernetes deployment bundle:
  - added Kustomize-ready manifests for namespace, deployment, service, ingress, HPA, and PodDisruptionBudget
  - added ConfigMap and Secret template for production config/credentials
  - added optional Prometheus Operator `ServiceMonitor` overlay.
- Added Phase 5.9 CI/CD automation:
  - added GitHub Actions CD workflow for GHCR image build/push
  - added automated Kubernetes apply + rolling deployment update on default branch.
- Added Phase 6.0 deploy safety controls:
  - added post-deploy smoke gate in CD workflow
  - added automatic rollback when rollout/smoke validation fails.
- Added Phase 6.1 assistant completion controls:
  - moved policy retrieval to external file-backed KB (`data/policy_kb.json`)
  - added feature-flagged native graph interrupt/resume handling for human handoff
  - added async cancellation queue path with persisted task status and worker loop.
- Added final production-on pass:
  - enabled native HITL + async queue defaults for production templates
  - added Redis and `satmi-cancel-worker` runtimes to Kubernetes and production compose
  - extended CD rollout to deploy API and worker image updates together.

### Files Added in QA/Delivery Stages
- `tests/conftest.py`
- `tests/test_api.py`
- `tests/test_support_workflows.py`
- `evaluations/golden_queries.json`
- `scripts/evaluate_golden_set.py`
- `scripts/load_test_smoke.py`
- `src/satmi_agent/observability.py`
- `src/satmi_agent/tracing.py`
- `monitoring/prometheus/alerts.yml`
- `monitoring/grafana/satmi-overview-dashboard.json`
- `monitoring/prometheus/prometheus.yml`
- `monitoring/otel-collector-config.yml`
- `monitoring/grafana/provisioning/datasources/prometheus.yml`
- `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- `Dockerfile`
- `docker-compose.observability.yml`
- `docker-compose.production.yml`
- `.dockerignore`
- `.env.production.example`
- `DEPLOYMENT_CHECKLIST.md`
- `k8s/base/kustomization.yaml`
- `k8s/base/namespace.yaml`
- `k8s/base/configmap.yaml`
- `k8s/base/secret.example.yaml`
- `k8s/base/redis-deployment.yaml`
- `k8s/base/redis-service.yaml`
- `k8s/base/deployment.yaml`
- `k8s/base/worker-deployment.yaml`
- `k8s/base/service.yaml`
- `k8s/base/ingress.yaml`
- `k8s/base/hpa.yaml`
- `k8s/base/pdb.yaml`
- `k8s/base/servicemonitor.yaml`
- `k8s/monitoring/kustomization.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/cd.yml`
- `data/policy_kb.json`
- `scripts/process_cancellation_queue.py`
- `src/satmi_agent/queueing.py`

## Try It

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "cust-123",
    "conversation_id": "thread-1",
    "message": "Please cancel my order"
  }'
```

Out-of-scope test:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "cust-123",
    "conversation_id": "thread-2",
    "message": "I need legal advice about a dispute"
  }'
```

## Next Build Steps (Immediate)
1. Add vector embeddings retrieval for long-form policy docs (hybrid keyword + semantic ranking).
2. Add canary release strategy with weighted traffic and automatic promotion/abort.
3. Add Redis result caching for high-frequency Shopify product reads.
4. Add LangSmith hosted evaluators to CI for model regression governance.
5. Add persistent volume-backed Redis state and backup strategy for queue durability.

## 5-Phase Workflow to Production

### Phase 1 — Commerce Integration (Started)
- Connect order lookup, product search, and cancellation to Shopify Admin APIs.
- Keep safe fallback stubs when credentials are missing.
- Validate end-to-end chat with real store data in development.

### Phase 2 — Persistence & Ticketing
- Store conversations, state transitions, and handoff tickets in a database.
- Add ticket status lifecycle (`open`, `in_progress`, `resolved`).
- Ensure `awaiting_human` sessions can be resumed.

### Phase 3 — Grounded Policy Responses (RAG)
- Add policy/FAQ knowledge base and retrieval pipeline.
- Use retrieved context for guardrails and response composition.
- Add confidence thresholds to auto-handoff low-confidence answers.

### Phase 4 — Security, Access, and Reliability
- Add auth/authz for API and tool operations.
- Add PII masking and structured audit storage.
- Add rate limiting, retries, timeout policy, and error normalization.

### Phase 5 — QA, Release, and Production Ops
- Add unit/integration tests and CI checks.
- Add tracing/metrics dashboards and alerting.
- Run load/failure testing and deploy to production with rollback plan.

## Prerequisites (Your End)

- Shopify store admin access with permission to create a Custom App.
- Shopify Admin API access token from that Custom App.
- Store domain (for example: `your-store.myshopify.com`).
- Gemini API key for model responses.
- A production database (recommended: PostgreSQL) for Phases 2+.
- A ticketing target (Zendesk/Freshdesk/HubSpot/custom queue) for human handoff.
- Deployment target (Render/Railway/AWS/GCP/Azure) and secret management.

## Shopify APIs Needed

This implementation currently uses Shopify Admin REST endpoints:

- `GET /admin/api/{version}/customers/{customer_id}/orders.json` for order history.
- `GET /admin/api/{version}/products.json` for product search suggestions.
- `POST /admin/api/{version}/orders/{order_id}/cancel.json` for cancellation.
- `GET /admin/api/{version}/orders.json` as reference lookup to map order number (for example `#1001`) to Shopify order id.

Required Custom App scopes:

- `read_orders`
- `write_orders`
- `read_products`
