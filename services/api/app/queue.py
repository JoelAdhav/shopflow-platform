"""Redis job queue. A Redis list is the queue: api LPUSHes, worker BRPOPs."""

import json
from functools import lru_cache

import redis

from app import config


@lru_cache
def _client() -> redis.Redis:
    # Short timeouts: a dead Redis must not hang API requests.
    return redis.Redis.from_url(
        config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1, decode_responses=True
    )


def get_queue() -> redis.Redis:
    """FastAPI dependency. Tests replace it with a fake Redis."""
    return _client()


def enqueue_order(client: redis.Redis, order_id: int) -> None:
    client.lpush(config.QUEUE_NAME, json.dumps({"order_id": order_id}))
