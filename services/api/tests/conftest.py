"""Test setup: SQLite in memory + fake Redis, so tests need no containers."""

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.queue import get_queue


@pytest.fixture
def queue():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(queue):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_queue] = lambda: queue
    # No "with": the lifespan (which connects to real Postgres) does not run.
    yield TestClient(app)
    app.dependency_overrides.clear()
