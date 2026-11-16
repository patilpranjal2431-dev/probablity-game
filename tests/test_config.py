"""Unit tests for app.config."""

from __future__ import annotations

import pytest

from app.config import (
    DEFAULT_DATABASE_URL,
    DEFAULT_INITIAL_WALLET_BALANCE,
    DEFAULT_SESSION_COOKIE_NAME,
    DEFAULT_SESSION_TTL_SECONDS,
    Settings,
    get_settings,
)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "EDGE_LAB_APP_NAME",
        "EDGE_LAB_APP_VERSION",
        "EDGE_LAB_DATABASE_URL",
        "EDGE_LAB_INITIAL_WALLET_BALANCE",
        "EDGE_LAB_SESSION_COOKIE_NAME",
        "EDGE_LAB_SESSION_TTL_SECONDS",
        "EDGE_LAB_COOKIE_SECURE",
        "EDGE_LAB_TURN_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = get_settings()
    assert settings.app_name == "Edge Lab"
    assert settings.app_version == "0.1.0"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.initial_wallet_balance == DEFAULT_INITIAL_WALLET_BALANCE
    assert settings.initial_wallet_balance == 1000
    assert settings.session_cookie_name == DEFAULT_SESSION_COOKIE_NAME
    assert settings.session_ttl_seconds == DEFAULT_SESSION_TTL_SECONDS
    assert settings.cookie_secure is False
    assert settings.turn_timeout_seconds == 30.0


def test_settings_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDGE_LAB_APP_NAME", "Edge Lab Test")
    monkeypatch.setenv("EDGE_LAB_APP_VERSION", "0.2.0")
    monkeypatch.setenv("EDGE_LAB_DATABASE_URL", "sqlite:///./custom.db")
    monkeypatch.setenv("EDGE_LAB_INITIAL_WALLET_BALANCE", "2500")
    monkeypatch.setenv("EDGE_LAB_SESSION_COOKIE_NAME", "custom_sess")
    monkeypatch.setenv("EDGE_LAB_SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("EDGE_LAB_COOKIE_SECURE", "true")
    monkeypatch.setenv("EDGE_LAB_TURN_TIMEOUT_SECONDS", "12.5")

    settings = get_settings()
    assert settings.app_name == "Edge Lab Test"
    assert settings.app_version == "0.2.0"
    assert settings.database_url == "sqlite:///./custom.db"
    assert settings.initial_wallet_balance == 2500
    assert settings.session_cookie_name == "custom_sess"
    assert settings.session_ttl_seconds == 3600
    assert settings.cookie_secure is True
    assert settings.turn_timeout_seconds == 12.5


def test_settings_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="initial_wallet_balance"):
        Settings(initial_wallet_balance=0)

    with pytest.raises(ValueError, match="database_url"):
        Settings(database_url="   ")

    with pytest.raises(ValueError, match="session_cookie_name"):
        Settings(session_cookie_name="  ")

    with pytest.raises(ValueError, match="session_ttl_seconds"):
        Settings(session_ttl_seconds=-5)

    with pytest.raises(ValueError, match="turn_timeout_seconds"):
        Settings(turn_timeout_seconds=0)

    monkeypatch.setenv("EDGE_LAB_INITIAL_WALLET_BALANCE", "not-an-int")
    with pytest.raises(ValueError, match="must be an integer"):
        get_settings()
