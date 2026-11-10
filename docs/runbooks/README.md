# Runbooks

One runbook per alert arrives in Phase 5. Until then, the local debug basics:

| Symptom | First command |
|---|---|
| A container is unhealthy | `docker inspect shopflow-web-1 --format '{{range .State.Health.Log}}{{.Output}}{{end}}'` |
| Orders stay `pending` | `docker compose logs worker --tail 50` |
| api returns 503 on `/readyz` | `curl.exe http://localhost:8000/readyz` (shows which dependency failed) |
| Is the queue backing up? | `curl.exe -s http://localhost:9100/metrics \| Select-String orders_queue_depth` |
