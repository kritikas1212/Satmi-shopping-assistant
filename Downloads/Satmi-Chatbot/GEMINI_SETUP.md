# SATMI Gemini Setup Guide (End-to-End)

This guide gives every required setup step to run SATMI with Gemini API in local and production environments.

## 1) What You Need Before Starting

- A Google AI Studio or Google Cloud account with Gemini API access.
- A Shopify store admin account.
- A PostgreSQL database (local or managed).
- A Redis instance (local or managed).
- Python 3.13 and `pip`.
- (For production) Docker and/or a Kubernetes cluster.
- (For CI/CD) GitHub repository admin access.

## 2) Create All Required Keys / Secrets

### 2.1 Gemini API Key

1. Open Google AI Studio and create an API key.
2. Save it as:

   - `GEMINI_API_KEY`

3. Use model name:

   - `MODEL_NAME=gemini-2.0-flash`

### 2.2 SATMI API Key (your app auth secret)

Generate a strong secret:

```bash
python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Save output as:

- `API_KEY`

### 2.3 Shopify Credentials

Create a Shopify Custom App and grant scopes:

- `read_orders`
- `write_orders`
- `read_products`

Collect:

- `SHOPIFY_STORE_DOMAIN` (example: `your-store.myshopify.com`)
- `SHOPIFY_ADMIN_API_TOKEN`

### 2.4 Database and Queue URLs

- `DATABASE_URL` (PostgreSQL)
- `REDIS_URL`

Examples:

- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/satmi_chatbot`
- `REDIS_URL=redis://localhost:6379/0`

## 3) Local Development Setup

### 3.1 Start Postgres + Redis locally (quick Docker option)

```bash
docker run -d --name satmi-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=satmi_chatbot -p 5432:5432 postgres:16
docker run -d --name satmi-redis -p 6379:6379 redis:7.4-alpine
```

### 3.2 Create local environment file

```bash
cp .env.example .env
```

Set these in `.env`:

- `LLM_PROVIDER=gemini`
- `MODEL_NAME=gemini-2.0-flash`
- `GEMINI_API_KEY=<your_key>`
- `LLM_RESPONSE_REFINEMENT_ENABLED=false` (recommended for stable local testing)
- `DATABASE_URL=<your_postgres_url>`
- `REDIS_URL=<your_redis_url>`
- `API_KEY=<generated_secret>`
- `SHOPIFY_STORE_DOMAIN=<your_store_domain>`
- `SHOPIFY_ADMIN_API_TOKEN=<your_shopify_token>`

### 3.3 Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.4 Start app and queue worker

Terminal 1 (API):

```bash
source .venv/bin/activate
export PYTHONPATH=src
uvicorn satmi_agent.main:app --reload --port 8000
```

Terminal 2 (worker):

```bash
source .venv/bin/activate
PYTHONPATH=src python scripts/process_cancellation_queue.py --sleep 1
```

### 3.5 Verify locally

Health:

```bash
curl http://127.0.0.1:8000/health
```

Chat example:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","conversation_id":"c1","message":"cancel my order #1001"}'
```

If `AUTH_REQUIRED=true`, include:

```bash
-H "X-API-Key: <API_KEY>"
```

Run tests and golden eval:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/evaluate_golden_set.py --min-pass-rate 0.80
```

## 4) Production Docker Setup

1. Copy production env:

```bash
cp .env.production.example .env.production
```

2. Fill all placeholders in `.env.production` (especially `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `API_KEY`).

3. Start stack:

```bash
docker compose -f docker-compose.production.yml up --build -d
```

This starts:

- `satmi-app`
- `satmi-cancel-worker`
- `redis`
- `prometheus`
- `grafana`
- `otel-collector`

## 5) Production Kubernetes Setup

### 5.1 Prepare secret manifest

```bash
cp k8s/base/secret.example.yaml k8s/base/secret.yaml
```

Set real values in `k8s/base/secret.yaml` for:

- `API_KEY`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `SHOPIFY_STORE_DOMAIN`
- `SHOPIFY_ADMIN_API_TOKEN`
- `REDIS_URL`

### 5.2 Update image tags

Replace image placeholder in:

- `k8s/base/deployment.yaml`
- `k8s/base/worker-deployment.yaml`

### 5.3 Apply manifests

```bash
kubectl apply -f k8s/base/secret.yaml
kubectl apply -k k8s/base
```

Optional monitoring overlay:

```bash
kubectl apply -k k8s/monitoring
```

### 5.4 Verify rollout

```bash
kubectl -n satmi get deploy,po,svc,ingress,hpa,pdb
kubectl -n satmi rollout status deploy/satmi-app
kubectl -n satmi rollout status deploy/satmi-cancel-worker
kubectl -n satmi get deploy satmi-redis
```

## 6) GitHub Actions CI/CD Secrets (Required)

Workflow file: `.github/workflows/cd.yml`.

Set repository secrets:

- `KUBE_CONFIG_BASE64`
- `SATMI_APP_SECRET_YAML_BASE64`

Generate values:

```bash
base64 -i ~/.kube/config | tr -d '\n'
base64 -i k8s/base/secret.yaml | tr -d '\n'
```

Optional secrets:

- `DEPLOY_SMOKE_URL`
- `DEPLOY_SMOKE_API_KEY`

## 7) Recommended Production Values

- `LLM_PROVIDER=gemini`
- `MODEL_NAME=gemini-2.0-flash`
- `LLM_RESPONSE_REFINEMENT_ENABLED=true`
- `HITL_INTERRUPT_ENABLED=true`
- `ASYNC_CANCEL_ENABLED=true`

## 8) Common Failures and Fixes

- **401/403 from API**: verify `API_KEY` and request headers.
- **Gemini not being used**: check `GEMINI_API_KEY`, `LLM_PROVIDER=gemini`, and `LLM_RESPONSE_REFINEMENT_ENABLED=true`.
- **Queue not processing**: ensure Redis is reachable and worker is running.
- **Shopify failures**: verify token scopes and store domain.
- **K8s deploy fails in GitHub Actions**: verify `KUBE_CONFIG_BASE64` and `SATMI_APP_SECRET_YAML_BASE64` are valid base64 and not wrapped.

## 9) Final Readiness Checklist

- [ ] Gemini key configured and validated.
- [ ] Shopify credentials and scopes validated.
- [ ] PostgreSQL reachable by app.
- [ ] Redis reachable by app and worker.
- [ ] App, worker, and health checks all green.
- [ ] `pytest` and golden evaluation pass.
- [ ] CI/CD deploy + smoke check + rollback path validated.
