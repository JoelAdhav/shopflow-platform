# ADR 0003: Base images, and no migration tool yet

**Status:** accepted (Phase 1)

## Base image: python slim (Debian), not Alpine
- `python:3.13.18-slim-trixie`. Debian uses glibc, so prebuilt Python wheels just work.
  Alpine uses musl; some packages then need compiling, which makes builds slow and fragile.
- Cost: bigger images. api is 275MB on disk (about 68MB compressed, which is what gets pushed and pulled).
- Mitigations in place: multi-stage build (no build tools in the final image), pip removed
  from the runtime venv, non-root UID 10001.
- Revisit in Phase 2: Trivy results will show if the base image carries too many CVEs.
  Options then: distroless or Alpine.

## web: nginx-unprivileged, single stage
- Plain HTML/JS has no build step, so a builder stage would be empty. Single stage is the honest choice.
- `nginxinc/nginx-unprivileged` runs as UID 101 on port 8080 out of the box.

## Database schema: `create_all` at startup, no Alembic
- Two tables, no schema changes planned. The api creates missing tables when it starts.
- Limit: `create_all` never alters an existing table. The first schema change needs Alembic migrations.
- Limit: several api replicas starting at once could race on table creation. In Kubernetes
  this should move to a one-off migration Job.
