"""SQLAlchemy database engine, session management, and declarative base."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enforce foreign-key constraints on every SQLite connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine(database_url: str, *, use_static_pool: bool = False) -> Engine:
    """Create a configured SQLAlchemy Engine for SQLite or other SQL backends."""
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict[str, Any] = {"future": True}

    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if use_static_pool or database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool

    db_engine = create_engine(database_url, **kwargs)
    if is_sqlite:
        event.listen(db_engine, "connect", _enable_sqlite_foreign_keys)
    return db_engine


engine: Engine = create_db_engine(get_settings().database_url)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def init_db(target_engine: Engine | None = None) -> None:
    """Create all database tables defined on Base.metadata."""
    # Import models to guarantee all tables are registered before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
