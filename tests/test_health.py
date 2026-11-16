"""Integration tests for the FastAPI application and /health endpoint."""

from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import create_app


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "Edge Lab",
        "version": "0.1.0",
        "database": "ok",
    }


def test_health_endpoint_returns_503_on_database_error() -> None:
    class BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("db down"))

    def broken_db() -> Generator[BrokenSession, None, None]:
        yield BrokenSession()

    app = create_app()
    app.dependency_overrides[get_db] = broken_db

    with TestClient(app) as broken_client:
        response = broken_client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database connectivity check failed."
