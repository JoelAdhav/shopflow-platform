"""shopflow api: products and orders CRUD."""

import logging
import time
from contextlib import asynccontextmanager

import redis
from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import Engine, insert, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import config, metrics, models, schemas
from app.db import Base, engine, get_db
from app.queue import enqueue_order, get_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

SEED_PRODUCTS = [
    {"name": "Mechanical Keyboard", "price_cents": 8900, "stock": 25},
    {"name": "USB-C Hub", "price_cents": 3400, "stock": 40},
    {"name": "Laptop Stand", "price_cents": 4500, "stock": 15},
]


def init_db(bind: Engine, seed_data: bool) -> None:
    """Create tables and (optionally) demo products, in one transaction.

    Fine for two tables; a real project uses migrations (Alembic). See ADR 0003.
    """
    with bind.begin() as conn:
        if conn.dialect.name == "postgresql":
            # In Kubernetes several api replicas start at the same moment. Without
            # a lock they race: duplicate seed rows, or "already exists" crashes.
            # This Postgres lock lets one replica in at a time and is released
            # automatically when the transaction ends.
            conn.execute(text("SELECT pg_advisory_xact_lock(727001)"))
        Base.metadata.create_all(conn)
        if seed_data and conn.scalar(select(models.Product.id).limit(1)) is None:
            conn.execute(insert(models.Product), SEED_PRODUCTS)
            log.info("seeded %d products", len(SEED_PRODUCTS))


def init_db_with_retry(bind: Engine, seed_data: bool, attempts: int = 60, delay: float = 2.0):
    """Wait for the database instead of crashing.

    Kubernetes starts all pods at once, in no order (compose had depends_on).
    Without this the api exits while Postgres is still starting and is
    restarted again and again with growing back-off delays.
    """
    for attempt in range(1, attempts + 1):
        try:
            init_db(bind, seed_data)
            return
        except OperationalError as exc:
            if attempt == attempts:
                raise
            log.warning(
                "database not ready (attempt %d/%d): %s", attempt, attempts, type(exc).__name__
            )
            time.sleep(delay)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db_with_retry(engine, config.SEED_DATA)
    yield


app = FastAPI(title="shopflow-api", lifespan=lifespan)
app.middleware("http")(metrics.metrics_middleware)


# ---------- operations endpoints ----------


@app.get("/healthz")
def healthz():
    """Liveness: the process is up. Never checks dependencies.

    If this checked Postgres, a database outage would make Kubernetes restart
    every api pod, which fixes nothing.
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz(
    response: Response,
    db: Session = Depends(get_db),
    queue: redis.Redis = Depends(get_queue),
):
    """Readiness: can this instance serve traffic right now?"""
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure as not ready
        checks["postgres"] = f"error: {type(exc).__name__}"
    try:
        queue.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"

    ready = all(v == "ok" for v in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "not ready", "checks": checks}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    return metrics.metrics_response()


# ---------- products ----------


def _get_product(db: Session, product_id: int) -> models.Product:
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    return product


@app.get("/products", response_model=list[schemas.ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.scalars(select(models.Product).order_by(models.Product.id)).all()


@app.post("/products", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: schemas.ProductIn, db: Session = Depends(get_db)):
    product = models.Product(**body.model_dump())
    db.add(product)
    db.commit()
    return product


@app.get("/products/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return _get_product(db, product_id)


@app.put("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, body: schemas.ProductIn, db: Session = Depends(get_db)):
    product = _get_product(db, product_id)
    for key, value in body.model_dump().items():
        setattr(product, key, value)
    db.commit()
    return product


@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = _get_product(db, product_id)
    has_orders = db.scalar(
        select(models.Order.id).where(models.Order.product_id == product_id).limit(1)
    )
    if has_orders is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "product has orders")
    db.delete(product)
    db.commit()


# ---------- orders ----------


@app.get("/orders", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.scalars(select(models.Order).order_by(models.Order.id.desc()).limit(50)).all()


@app.get("/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    return order


@app.post("/orders", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: schemas.OrderIn,
    db: Session = Depends(get_db),
    queue: redis.Redis = Depends(get_queue),
):
    # Lock the product row so two orders cannot both take the last item.
    product = db.scalar(
        select(models.Product).where(models.Product.id == body.product_id).with_for_update()
    )
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    if product.stock < body.quantity:
        raise HTTPException(status.HTTP_409_CONFLICT, "not enough stock")

    product.stock -= body.quantity
    order = models.Order(product_id=product.id, quantity=body.quantity, status="pending")
    db.add(order)
    db.commit()
    metrics.ORDERS_CREATED.inc()

    # The order is already safe in Postgres. If Redis is down we still answer
    # 201; the worker's sweep picks up stale pending orders later.
    try:
        enqueue_order(queue, order.id)
    except redis.RedisError:
        metrics.ENQUEUE_FAILURES.inc()
        log.warning("redis unavailable, order %d left pending for sweep", order.id)
    return order
