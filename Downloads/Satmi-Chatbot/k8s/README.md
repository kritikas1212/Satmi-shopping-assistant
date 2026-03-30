# SATMI Kubernetes Deployment Pack (Production-On)

## Structure

- `base/`: core resources for namespace, app deployment, worker, Redis, networking, and autoscaling.
- `monitoring/`: overlay that adds Prometheus Operator `ServiceMonitor`.

## Deploy

1. Create a real secret manifest from `base/secret.example.yaml`:

   ```bash
   cp k8s/base/secret.example.yaml k8s/base/secret.yaml
   ```

2. Edit `k8s/base/secret.yaml` and set all production values.

3. Update placeholder image in these files:

   - `ghcr.io/your-org/satmi-chatbot:latest`
   - `k8s/base/deployment.yaml`
   - `k8s/base/worker-deployment.yaml`

4. Update host in `k8s/base/ingress.yaml`:

   - `satmi.example.com`

5. Apply resources:

   ```bash
   kubectl apply -f k8s/base/secret.yaml
   kubectl apply -k k8s/base
   ```

6. Optional Prometheus Operator integration:

   ```bash
   kubectl apply -k k8s/monitoring
   ```

## Verify

```bash
kubectl -n satmi get deploy,po,svc,ingress,hpa,pdb
kubectl -n satmi rollout status deploy/satmi-app
kubectl -n satmi rollout status deploy/satmi-cancel-worker
```
