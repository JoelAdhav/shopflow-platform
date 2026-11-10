from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from worker import main


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(main, "PROCESS_SECONDS", 0)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT, "
                "created_at TIMESTAMP, processed_at TIMESTAMP)"
            )
        )
    return engine


def _insert(engine, order_id, status="pending", age_seconds=0):
    created = datetime.now(UTC) - timedelta(seconds=age_seconds)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO orders (id, status, created_at) VALUES (:id, :s, :c)"),
            {"id": order_id, "s": status, "c": created},
        )


def _status(engine, order_id):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status FROM orders WHERE id = :id"), {"id": order_id}
        ).scalar()


def test_process_order_marks_processed(engine):
    _insert(engine, 1)
    assert main.process_order(engine, 1) is True
    assert _status(engine, 1) == "processed"


def test_process_order_is_idempotent(engine):
    _insert(engine, 1)
    main.process_order(engine, 1)
    assert main.process_order(engine, 1) is False


def test_unknown_order_is_skipped(engine):
    assert main.process_order(engine, 404) is False


def test_handle_message_valid(engine):
    _insert(engine, 7)
    assert main.handle_message(engine, '{"order_id": 7}') is True
    assert _status(engine, 7) == "processed"


@pytest.mark.parametrize("raw", ["not json", "{}", '{"order_id": "abc"}'])
def test_handle_message_invalid_is_dropped(engine, raw):
    assert main.handle_message(engine, raw) is False


def test_sweep_only_takes_stale_pending_orders(engine, monkeypatch):
    monkeypatch.setattr(main, "STALE_SECONDS", 30)
    _insert(engine, 1, age_seconds=120)  # stale: swept
    _insert(engine, 2, age_seconds=1)  # fresh: its queue job is probably on the way
    _insert(engine, 3, status="processed", age_seconds=120)

    assert main.sweep_stale(engine) == 1
    assert _status(engine, 1) == "processed"
    assert _status(engine, 2) == "pending"
