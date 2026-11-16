"""Application configuration for Edge Lab."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATABASE_URL = "sqlite:///./edge_lab.db"
DEFAULT_INITIAL_WALLET_BALANCE = 1000
DEFAULT_SESSION_COOKIE_NAME = "edge_lab_session"
DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
DEFAULT_TURN_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime configuration loaded from environment variables."""

    app_name: str = "Edge Lab"
    app_version: str = "0.1.0"
    database_url: str = DEFAULT_DATABASE_URL
    initial_wallet_balance: int = DEFAULT_INITIAL_WALLET_BALANCE
    session_cookie_name: str = DEFAULT_SESSION_COOKIE_NAME
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    cookie_secure: bool = False
    turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.initial_wallet_balance <= 0:
            raise ValueError("initial_wallet_balance must be a positive integer.")
        if not self.database_url.strip():
            raise ValueError("database_url must not be empty.")
        if not self.session_cookie_name.strip():
            raise ValueError("session_cookie_name must not be empty.")
        if self.session_ttl_seconds <= 0:
            raise ValueError("session_ttl_seconds must be a positive integer.")
        if self.turn_timeout_seconds <= 0:
            raise ValueError("turn_timeout_seconds must be positive.")


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}.") from exc


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float, got {raw_value!r}.") from exc


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    """Build a Settings instance from the current process environment."""
    return Settings(
        app_name=os.getenv("EDGE_LAB_APP_NAME", "Edge Lab"),
        app_version=os.getenv("EDGE_LAB_APP_VERSION", "0.1.0"),
        database_url=os.getenv("EDGE_LAB_DATABASE_URL", DEFAULT_DATABASE_URL),
        initial_wallet_balance=_parse_int_env(
            "EDGE_LAB_INITIAL_WALLET_BALANCE",
            DEFAULT_INITIAL_WALLET_BALANCE,
        ),
        session_cookie_name=os.getenv(
            "EDGE_LAB_SESSION_COOKIE_NAME",
            DEFAULT_SESSION_COOKIE_NAME,
        ),
        session_ttl_seconds=_parse_int_env(
            "EDGE_LAB_SESSION_TTL_SECONDS",
            DEFAULT_SESSION_TTL_SECONDS,
        ),
        cookie_secure=_parse_bool_env("EDGE_LAB_COOKIE_SECURE", False),
        turn_timeout_seconds=_parse_float_env(
            "EDGE_LAB_TURN_TIMEOUT_SECONDS",
            DEFAULT_TURN_TIMEOUT_SECONDS,
        ),
    )
