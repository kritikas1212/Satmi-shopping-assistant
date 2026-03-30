# SATMI Production Deployment Checklist (Production-On)

## 1) Secrets & Environment
- [ ] Copy `.env.production.example` to `.env.production`.
- [ ] Rotate and set strong values for `API_KEY` and `GF_SECURITY_ADMIN_PASSWORD`.
- [ ] Set valid production keys for `GEMINI_API_KEY` and `SHOPIFY_ADMIN_API_TOKEN`.
- [ ] Set production `DATABASE_URL` to PostgreSQL.
- [ ] Confirm `.env.production` is never committed to source control.

## 2) Security Hardening
- [ ] Verify `AUTH_REQUIRED=true`.
- [ ] Keep support endpoints behind `X-Role: support_agent|admin`.
- [ ] Confirm API runs as non-root user inside container.
- [ ] Verify `no-new-privileges` is enabled in compose services.
- [ ] Restrict network access to Grafana/Prometheus/OTEL ports as needed.

## 3) Reliability & Capacity
- [ ] Review container CPU/memory limits in `docker-compose.production.yml`.
- [ ] Validate healthcheck status for `satmi-app` after startup.
- [ ] Run smoke load profile (`scripts/load_test_smoke.py`) against staging.
- [ ] Verify rate-limit thresholds with expected traffic patterns.

## 4) Observability
- [ ] Confirm Prometheus scrapes `satmi-app:8000/metrics`.
- [ ] Import/provision Grafana dashboard and validate panels.
- [ ] Enable tracing (`TRACING_ENABLED=true`) only when OTEL collector is reachable.
- [ ] Verify alert rules from `monitoring/prometheus/alerts.yml` are loaded.

## 5) Release Gates
- [ ] Run `PYTHONPATH=src pytest -q` and ensure green.
- [ ] Run `PYTHONPATH=src python scripts/evaluate_golden_set.py --min-pass-rate 0.80` and ensure pass rate target.
- [ ] Validate `/health`, `/chat`, `/metrics`, and handoff lifecycle endpoints in staging.
- [ ] Document rollback command and previous image tag.

## 6) Kubernetes Rollout (Phase 5.8)
- [ ] Create `satmi-app-secrets` from `k8s/base/secret.example.yaml` with real values.
- [ ] Replace placeholder image in `k8s/base/deployment.yaml` with release tag.
- [ ] Update ingress host in `k8s/base/ingress.yaml` and configure TLS at ingress controller.
- [ ] Apply base manifests: `kubectl apply -k k8s/base`.
- [ ] If using Prometheus Operator, apply monitoring overlay: `kubectl apply -k k8s/monitoring`.
- [ ] Verify rollout: `kubectl -n satmi get pods,svc,ingress,hpa,pdb`.
- [ ] Validate probes and endpoints via ingress and in-cluster service.
- [ ] Verify Redis and worker are healthy: `kubectl -n satmi get deploy satmi-redis satmi-cancel-worker`.

## 7) CI/CD Rollout (Phase 5.9)
- [ ] Add GitHub secret `KUBE_CONFIG_BASE64` (cluster deploy kubeconfig, base64-encoded).
- [ ] Add GitHub secret `SATMI_APP_SECRET_YAML_BASE64` (base64-encoded Kubernetes Secret YAML).
- [ ] Verify GHCR package publish permission for GitHub Actions.
- [ ] Protect `production` environment with reviewer approval (recommended).
- [ ] Trigger `.github/workflows/cd.yml` on `main` and confirm rollout succeeds.
- [ ] Validate deployed image tag matches commit SHA from workflow output.

## 8) Safe Deploy Controls (Phase 6.0)
- [ ] Set GitHub secret `DEPLOY_SMOKE_URL` to a reliable post-deploy health endpoint.
- [ ] Set optional `DEPLOY_SMOKE_API_KEY` if smoke endpoint requires auth.
- [ ] Confirm failed rollout triggers automatic `kubectl rollout undo` in workflow logs.
- [ ] Verify rollback completes to healthy state (`kubectl rollout status`).

## 9) Assistant Completion Controls (Phase 6.1)
- [ ] Validate `POLICY_KB_PATH` points to a maintained policy file and retrieval snippets are correct.
- [ ] Confirm `HITL_INTERRUPT_ENABLED=true` is set for native pause/resume in production.
- [ ] Confirm `ASYNC_CANCEL_ENABLED=true` and `REDIS_URL` are configured in production env/secret.
- [ ] Ensure cancellation worker process is running (`satmi-cancel-worker` deployment or compose service).
- [ ] Verify `/tasks/{task_id}` support endpoint returns status progression (`queued` → `in_progress` → `completed|failed`).
