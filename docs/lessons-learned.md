# Lessons learned

A running log of real problems hit while building this project, how I found the cause,
and how I fixed it. One section per phase.

## Phase 1: local run

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

### Not verified yet
The workflow file passes `actionlint`, and every command in it was run locally with the same
result. The workflow itself has not run on GitHub yet: that needs the first push.
