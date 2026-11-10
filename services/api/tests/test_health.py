import redis

from app.main import app
from app.queue import get_queue


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_ok(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["checks"] == {"postgres": "ok", "redis": "ok"}


def test_readyz_503_when_redis_down(client):
    class DeadRedis:
        def ping(self):
            raise redis.ConnectionError("down")

    app.dependency_overrides[get_queue] = lambda: DeadRedis()
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["checks"]["redis"].startswith("error")


def test_metrics_exposes_request_counter(client):
    client.get("/products")
    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",path="/products",status="200"}' in body
