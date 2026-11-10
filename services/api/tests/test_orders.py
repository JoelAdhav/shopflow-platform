import json

import redis

from app.main import app
from app.queue import get_queue


def _product(client, stock=5):
    return client.post(
        "/products", json={"name": "Mouse", "price_cents": 1999, "stock": stock}
    ).json()["id"]


def test_create_order_enqueues_job_and_reduces_stock(client, queue):
    pid = _product(client)
    res = client.post("/orders", json={"product_id": pid, "quantity": 2})

    assert res.status_code == 201
    order = res.json()
    assert order["status"] == "pending"
    assert json.loads(queue.rpop("orders")) == {"order_id": order["id"]}
    assert client.get(f"/products/{pid}").json()["stock"] == 3


def test_order_rejected_when_stock_too_low(client, queue):
    pid = _product(client, stock=1)
    res = client.post("/orders", json={"product_id": pid, "quantity": 2})
    assert res.status_code == 409
    assert queue.llen("orders") == 0


def test_order_unknown_product(client):
    assert client.post("/orders", json={"product_id": 999, "quantity": 1}).status_code == 404


def test_order_still_accepted_when_redis_down(client):
    class DeadRedis:
        def lpush(self, *_):
            raise redis.ConnectionError("down")

    pid = _product(client)
    app.dependency_overrides[get_queue] = lambda: DeadRedis()
    res = client.post("/orders", json={"product_id": pid, "quantity": 1})
    assert res.status_code == 201
    assert res.json()["status"] == "pending"


def test_product_with_orders_cannot_be_deleted(client):
    pid = _product(client)
    client.post("/orders", json={"product_id": pid, "quantity": 1})
    assert client.delete(f"/products/{pid}").status_code == 409
