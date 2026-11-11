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

## Phase 2: CI

### Questions and answers

**Walk me through your pipeline.**
On every pull request: ruff, pytest, build the three images, Trivy scan. On push to main it
does the same and then pushes the images to GHCR tagged with the git SHA. The build job
needs the test job, and the push step comes after the scan, so broken or vulnerable code
cannot produce a published image.

**Why tag with the git SHA and not `latest`?**
A SHA tag is immutable and traceable: I can read the running image tag and know the exact
commit. Rollback means "deploy the previous SHA". `latest` moves, so two nodes can run
different code under the same tag.

**Why fail only on HIGH and CRITICAL, and why `--ignore-unfixed`?**
A gate that is always red gets ignored or disabled. I block on what is serious and fixable.
The cost is that an unfixed critical is not shown, so I would add a scheduled scan later.

**Why pin actions to a commit SHA?**
Tags are mutable. If an action's repo is compromised, an attacker can move `v4` to malicious
code and every pipeline using `@v4` runs it with access to its secrets. A SHA cannot be moved.
Dependabot updates the SHAs.

**How does CI log in to the registry? Where is the password?**
There is none stored. GitHub creates a short-lived `GITHUB_TOKEN` per run. The workflow default
is read-only; only the build job has `packages: write`.

**Trivy found a vulnerability. What do you do?**
Read which package and where it is installed. Options in order: update the package or base
image; remove the package if unused; if no fix exists and it is not reachable, add a
documented, time-limited ignore. I did the first two here.

**How do you know CI and your laptop test the same thing?**
Both run the Dockerfile `test` stage. Same Python, same ruff, same pytest.

**What is the difference between CI and CD here?**
CI builds, tests and publishes an image. Nothing is deployed. CD comes in Phase 4, where
ArgoCD pulls the new tag from git.

### What broke and how I fixed it

1. **First Trivy scan failed on all three images, although every tag was the newest available.**
   - api and worker: `zlib1g` (2 HIGH) in Debian, plus `urllib3`, `msgpack`, `setuptools` (5 HIGH).
   - web: `curl`, `libexpat`, `libxslt`, `musl`, `zlib`, `brotli-libs` (12 HIGH) in Alpine.

   Lesson: a base image is a snapshot. Fixes released after it was built are not in it.
   Fix: `apt-get upgrade` / `apk upgrade` in the runtime stage. After that: 0 findings.

2. **Vulnerable Python packages that were not in my requirements.**
   `urllib3` and `msgpack` were not in my venv. I searched the image filesystem and found them at
   `/usr/local/lib/python3.13/site-packages/pip/_vendor/`. They belong to the pip that ships with
   the base image. The app never runs pip, so I delete it in the runtime stage.
   Lesson: find where a finding lives before deciding how to fix it. Removing unused software beats patching it.

3. **Docker Desktop was stopped again between sessions.**
   Same `failed to connect to the docker API` error as Phase 1. Start Docker Desktop first.

### Design note: patching a non-root image
The nginx image runs as UID 101, and `apk upgrade` needs root. The Dockerfile switches to
`USER root` for that one `RUN`, then back to `USER 101`. The container still runs as UID 101.

### First run on GitHub
- Push to `main` (run 42968863916): all 5 jobs green. Scan passed, then login and push ran for
  api, worker and web. Images are in GHCR tagged with the commit SHA.
- Dependabot opened 4 PRs within a minute of the first push. On those PR runs the login and
  push steps show `skipped`: the `if: github.event_name == 'push'` guard works.

### What broke after the first push

4. **Dependabot PR "Bump python from 3.13.18 to 3.15.0" failed the Trivy step.**
   Lint, tests and build were green; only the scan failed. My Dockerfile deleted the bundled pip
   with a hardcoded path, `/usr/local/lib/python3.13/site-packages/pip*`. On a 3.15 image that
   path does not exist, `rm -rf` silently did nothing, pip stayed in the image, and Trivy found
   its vulnerable vendored packages again.
   Fix: version-independent glob, `/usr/local/lib/python3*/site-packages/pip*`.
   Reproduced locally by building the api image on Python 3.15: 6 HIGH findings with the old
   path, 0 with the glob.
   Lessons: `rm -rf` on a missing path succeeds silently, so a cleanup step can stop working
   without any error. The scan gate caught a real regression on a real PR, with nobody reviewing it.

5. **Dependabot proposed major-version jumps (Postgres 17 to 18, Redis 7 to 8, Python 3.13 to 3.15).**
   Green CI on a major database bump proves little here: the tests use SQLite and a fake Redis.
   A Postgres major upgrade also needs a data migration (`pg_upgrade` or dump and restore); the
   existing volume would not start on 18. These PRs need a human decision, not auto-merge.
