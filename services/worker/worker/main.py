"""shopflow worker: takes order jobs from Redis and marks orders processed.

Loop:
  1. BRPOP waits up to BRPOP_SECONDS for a job on the Redis list.
  2. Mark that order processed in Postgres.
  3. Every SWEEP_SECONDS, also process "stale" pending orders straight from
     Postgres. This rescues orders whose job never reached Redis.
"""

import json
import logging
import os
import signal
import time
from datetime import UTC, datetime, timedelta

import redis
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sqlalchemy import Engine, create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://shopflow:shopflow@localhost:5432/shopflow"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "orders")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))
# Fake "work" per order (payment call, email...). Makes queue depth visible.
PROCESS_SECONDS = float(os.getenv("PROCESS_SECONDS", "0.2"))
BRPOP_SECONDS = 5  # how long one blocking wait for a job lasts
SWEEP_SECONDS = float(os.getenv("SWEEP_SECONDS", "30"))
STALE_SECONDS = float(os.getenv("STALE_SECONDS", "30"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

ORDERS_PROCESSED = Counter(
    "orders_processed_total", "Orders handled by the worker", ["result", "source"]
)
PROCESS_DURATION = Histogram("order_processing_seconds", "Time to process one order")
QUEUE_DEPTH = Gauge("orders_queue_depth", "Jobs waiting in the Redis list")
REDIS_UP = Gauge("worker_redis_up", "1 if the worker can reach Redis")

_running = True


def _stop(signum, _frame):
    """SIGTERM is what Docker/Kubernetes send on stop. Finish the job, then exit."""
    global _running
    log.info("signal %s received, finishing current job", signum)
    _running = False


def process_order(engine: Engine, order_id: int, source: str = "queue") -> bool:
    """Mark one order processed. Returns True if a row changed.

    "AND status = 'pending'" makes it idempotent: the same job delivered twice
    changes nothing the second time.
    """
    with PROCESS_DURATION.time():
        time.sleep(PROCESS_SECONDS)
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE orders SET status = 'processed', processed_at = :now "
                    "WHERE id = :id AND status = 'pending'"
                ),
                {"now": datetime.now(UTC), "id": order_id},
            )
    changed = result.rowcount == 1
    ORDERS_PROCESSED.labels("processed" if changed else "skipped", source).inc()
    log.info("order %d %s (%s)", order_id, "processed" if changed else "skipped", source)
    return changed


def sweep_stale(engine: Engine) -> int:
    """Process pending orders older than STALE_SECONDS. Returns how many."""
    cutoff = datetime.now(UTC) - timedelta(seconds=STALE_SECONDS)
    with engine.connect() as conn:
        ids = conn.execute(
            text(
                "SELECT id FROM orders WHERE status = 'pending' AND created_at < :cutoff "
                "ORDER BY id LIMIT 100"
            ),
            {"cutoff": cutoff},
        ).scalars().all()
    return sum(process_order(engine, order_id, source="sweep") for order_id in ids)


def handle_message(engine: Engine, raw: str) -> bool:
    """Parse one queue message. A bad message is counted and dropped, never retried forever."""
    try:
        order_id = int(json.loads(raw)["order_id"])
    except (ValueError, KeyError, TypeError):
        ORDERS_PROCESSED.labels("invalid", "queue").inc()
        log.error("dropping invalid message: %r", raw)
        return False
    return process_order(engine, order_id)


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    start_http_server(METRICS_PORT)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    # socket_timeout must be longer than the BRPOP wait below. redis-py 8 defaults
    # it to 5s, which equals our 5s BRPOP and made every idle wait a TimeoutError.
    client = redis.Redis.from_url(
        REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=BRPOP_SECONDS + 5
    )
    log.info("worker started, queue=%s metrics=:%d", QUEUE_NAME, METRICS_PORT)

    last_sweep = 0.0
    while _running:
        try:
            item = client.brpop(QUEUE_NAME, timeout=BRPOP_SECONDS)
            QUEUE_DEPTH.set(client.llen(QUEUE_NAME))
            REDIS_UP.set(1)
            if item:
                handle_message(engine, item[1])
        except redis.RedisError as exc:
            REDIS_UP.set(0)
            log.warning("redis error: %s; retrying", type(exc).__name__)
            time.sleep(2)
        except Exception:  # noqa: BLE001 - one bad job must not kill the loop
            log.exception("job failed")
            time.sleep(1)

        if time.monotonic() - last_sweep >= SWEEP_SECONDS:
            last_sweep = time.monotonic()
            try:
                sweep_stale(engine)
            except Exception:  # noqa: BLE001
                log.exception("sweep failed")
    log.info("worker stopped cleanly")


if __name__ == "__main__":
    run()
