"""Shared pytest fixtures for database sessions and FastAPI TestClient."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_db_engine, get_db
from app.main import create_app


@pytest.fixture()
def test_engine() -> Generator[Engine, None, None]:
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_db_engine("sqlite:///:memory:", use_static_pool=True)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    """Yield an isolated SQLAlchemy Session bound to the test engine."""
    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_engine: Engine) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient whose get_db dependency uses the test engine."""
    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    app = create_app(session_factory=testing_session_local)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
