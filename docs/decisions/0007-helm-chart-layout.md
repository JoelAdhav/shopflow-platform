# ADR 0007: One Helm chart, two values files

**Status:** accepted (Phase 3)

## Decision
- One chart, `charts/shopflow`, contains api, worker, web, Postgres and Redis.
- Environments differ only by values: `values-dev.yaml` (1 replica each) and
  `values-prod.yaml` (2 replicas of api, worker, web).
- Each environment is a separate namespace: `shopflow-dev`, `shopflow-prod`.

## Why one chart, not one per service or an umbrella chart
The three services are released together from one repo and one commit. One chart means one
version, one `helm upgrade`, one rollback. Separate charts or an umbrella with subcharts pay
off when teams release services independently. That is not the case here.

## Secrets
The chart contains no secret values. It references a Secret named `shopflow-db` that must
already exist. `tasks.ps1` creates it from a gitignored file (`k8s/secrets/<env>.env`) with a
generated password. Dev and prod have different passwords.

Limit: a Kubernetes Secret is only base64-encoded, not encrypted, and anyone with read access
to the namespace can read it. Real clusters add encryption at rest and an external secret
store (External Secrets, Vault, or sealed secrets).

## Security settings in the chart
- Every pod: `runAsNonRoot`, fixed UID, `seccompProfile: RuntimeDefault`,
  `allowPrivilegeEscalation: false`, all Linux capabilities dropped.
- api, worker, web, redis: read-only root filesystem (web gets two `emptyDir` volumes for nginx).
- Namespaces enforce the Kubernetes "restricted" Pod Security Standard, so a pod that breaks
  these rules is rejected by the API server.

## Postgres and Redis inside the chart
Simple and free, and enough to demonstrate StatefulSets and PersistentVolumeClaims.
Known gaps, on purpose: single Postgres pod (no replica, no backups), Redis without persistence.
Production would use a managed database or an operator. Redis loss is tolerated by design
(the worker sweep recovers jobs, ADR 0002).

## Requests and limits
Every container sets both. Requests are what the scheduler reserves; limits are the cap.
Values are small first guesses for a laptop. Phase 5 metrics will show real usage to tune them.
