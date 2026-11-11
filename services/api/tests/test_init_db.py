from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from app import models
from app.main import SEED_PRODUCTS, init_db


def _engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def _count(engine):
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(models.Product))


def test_init_db_seeds_once_even_when_run_twice():
    engine = _engine()
    init_db(engine, seed_data=True)
    init_db(engine, seed_data=True)  # second replica / restart
    assert _count(engine) == len(SEED_PRODUCTS)


def test_init_db_without_seed_creates_empty_tables():
    engine = _engine()
    init_db(engine, seed_data=False)
    assert _count(engine) == 0


def test_init_db_retries_until_database_is_up(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app import main

    calls = []

    def flaky_init(bind, seed_data):
        calls.append(1)
        if len(calls) < 3:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main, "init_db", flaky_init)
    main.init_db_with_retry(_engine(), seed_data=False, attempts=5, delay=0)
    assert len(calls) == 3


def test_init_db_gives_up_after_last_attempt(monkeypatch):
    import pytest
    from sqlalchemy.exc import OperationalError

    from app import main

    def always_down(bind, seed_data):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main, "init_db", always_down)
    with pytest.raises(OperationalError):
        main.init_db_with_retry(_engine(), seed_data=False, attempts=2, delay=0)
