# ADR 0001: Docker Compose for the local run

**Status:** accepted (Phase 1)

## Context
Five containers must start together on a Windows laptop, in the right order, with one command.

## Decision
Use Docker Compose. Every service has a healthcheck, and `depends_on` uses
`condition: service_healthy` so the api starts only after Postgres and Redis answer.

## Why not the alternatives
- **Run everything in kind from day one:** slower feedback loop, and Kubernetes
  concepts would hide basic container problems. Kubernetes arrives in Phase 3.
- **Run Python on the host, only databases in Docker:** "works on my machine" risk;
  the images would not be tested until CI.

## Consequences
- Compose is for local development only. It has no rolling updates or self-healing.
- Compose healthchecks are the same idea as Kubernetes probes, so Phase 3 reuses `/healthz` and `/readyz`.
