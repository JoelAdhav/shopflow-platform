# ADR 0002: A Redis list as the job queue

**Status:** accepted (Phase 1)

## Context
Order processing should not slow down the API response. The api needs to hand work to the worker.

## Decision
The api does `LPUSH orders <json>`. The worker does `BRPOP orders` (blocking pop).
Postgres stays the source of truth: the order row exists before the job is pushed.

## Known weakness, and the fix
`BRPOP` removes the job from Redis. If the worker crashes right after, the job is gone
("at-most-once" delivery). Also, if Redis is down, the push fails.

Fix: the worker **sweeps** Postgres every 30s for orders still `pending` after 30s and
processes them. The update is idempotent (`WHERE status = 'pending'`), so a job handled
twice changes nothing. Result: every order is processed at least once, eventually.

Verified in Phase 1: with Redis stopped, an order returned 201, `orders_enqueue_failures_total`
went to 1, and the sweep processed it after Redis came back.

## Why not the alternatives
- **Celery / RabbitMQ / Kafka:** overkill for one job type. More moving parts to run and explain.
- **Redis Streams with consumer groups:** the right upgrade when multiple workers need
  acknowledgements. Not needed yet.
