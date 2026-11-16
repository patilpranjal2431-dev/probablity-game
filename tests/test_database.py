"""Unit tests for app.database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import create_db_engine, get_db, init_db


def test_sqlite_foreign_keys_enabled(test_engine) -> None:
    with test_engine.connect() as conn:
        pragma_value = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert pragma_value == 1


def test_init_db_creates_expected_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "phase1.db"
    file_engine = create_db_engine(f"sqlite:///{db_file}")
    try:
        init_db(file_engine)
        table_names = set(inspect(file_engine).get_table_names())
        assert table_names == {
            "users",
            "wallets",
            "games",
            "hands",
            "transactions",
            "user_sessions",
            "decision_grades",
            "calibration_rounds",
            "order_book_sessions",
        }
    finally:
        file_engine.dispose()


def test_get_db_yields_and_closes_session() -> None:
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    # Closing the generator triggers the finally block without error.
    gen.close()
