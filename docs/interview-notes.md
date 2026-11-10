# Interview notes

Per phase: likely questions with short answers, then real problems hit while building.

## Phase 1: local run

### Questions and answers

**Walk me through what happens when a user places an order.**
Browser posts to nginx at `/api/orders`. nginx forwards to the api. The api locks the
product row, checks stock, saves the order as `pending`, commits, then pushes a job to a
Redis list. It returns 201 right away. The worker pops the job and marks the order
`processed`. The page polls every 2s and shows the new status.

**Why a multi-stage Dockerfile?**
Stage 1 installs dependencies. The final stage copies only the finished virtualenv and
the app code. Build tools and caches never reach the final image: smaller, and fewer
things an attacker can use. I also have a `test` stage with pytest and ruff that is
never shipped.

**Why run as non-root?**
If the app is compromised, the attacker has an unprivileged user, not root. I use a
numeric UID (10001) because Kubernetes `runAsNonRoot` can only verify a number.

**Liveness vs readiness?**
`/healthz` (liveness): "is the process alive?" It checks nothing else. Failing it means "restart me".
`/readyz` (readiness): "can I serve traffic now?" It checks Postgres and Redis. Failing it means
"stop sending me traffic", not "restart me". If liveness checked the database, a database
outage would restart every api pod for no benefit.

**What if Redis goes down?**
The order is already committed in Postgres, so the api still returns 201 and counts the
failed push in `orders_enqueue_failures_total`. The worker sweeps Postgres every 30s for
stale `pending` orders and processes them. I tested this by stopping the Redis container.

**What if the same job is delivered twice?**
Nothing bad. The update has `WHERE status = 'pending'`, so the second run changes 0 rows. That is idempotency.

**How do you stop two customers buying the last item?**
`SELECT ... FOR UPDATE` on the product row. The second transaction waits for the first, then sees stock 0 and gets 409.

**Why does `depends_on` need `condition: service_healthy`?**
Plain `depends_on` waits only for the container to start. Postgres needs a few more seconds
before it accepts connections. `service_healthy` waits for the healthcheck to pass.

**Why does nginx proxy `/api` instead of the browser calling the api directly?**
One origin for the browser, so no CORS configuration, and the api does not need to be public.

**Why label metrics with the route template, not the URL?**
`/orders/1`, `/orders/2`... would each create a new time series. That is a cardinality
explosion and can take Prometheus down. `/orders/{order_id}` is one series.

**How do you keep secrets out of git?**
`.env` is gitignored; `.env.example` with fake values is committed. Compose reads `.env`.

### What broke and how I fixed it

1. **web container "unhealthy", but the site worked in the browser.**
   Healthcheck was `wget http://localhost:8080/healthz` and failed with `Connection refused`.
   Inside the Alpine container `localhost` resolved to IPv6 `::1` first, and nginx listened
   on IPv4 only. `wget http://127.0.0.1:8080/healthz` worked. Fix: use `127.0.0.1` in healthchecks.
   Lesson: debug a healthcheck by running its exact command inside the container (`docker exec`).

2. **Worker logged `redis error: TimeoutError` every few seconds while idle.**
   The worker waits on `BRPOP` for 5s. redis-py 8 sets a default socket timeout of 5s, so
   the socket gave up at the same moment the wait ended. Fix: set `socket_timeout` to the
   BRPOP wait plus 5s. Lesson: a client timeout must be longer than any blocking call made through it.
   Found only by reading the logs of a "healthy" container.

3. **`.\tasks.ps1 up` failed with `NativeCommandError` although Docker was fine.**
   Docker prints normal progress to stderr. Windows PowerShell 5.1 with
   `$ErrorActionPreference = "Stop"` turns redirected stderr lines into errors. Fix: do not
   use "Stop"; check `$LASTEXITCODE` after each docker command instead.

4. **Docker commands failed with `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`.**
   The Docker CLI was installed but the Docker Desktop engine was not running. Fix: start Docker Desktop.

5. **First version pins were two years old.**
   I pinned versions from memory, then checked the registries and found much newer releases.
   Old pins mean known CVEs, which the Phase 2 Trivy scan would reject. Fix: look up current
   versions (`pip index versions <pkg>`, Docker Hub tags) before pinning.

6. **Images are 250-275MB on disk, not tiny.**
   Most of it is the Debian slim base plus SQLAlchemy and the Postgres driver. Removing pip
   from the runtime venv saved 13MB. Trade-off is recorded in ADR 0003.
