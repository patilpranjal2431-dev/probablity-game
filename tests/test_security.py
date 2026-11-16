"""Unit tests for password hashing and session token security helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.ledger import create_user_with_wallet
from app.models import utc_now
from app.security import (
    create_user_session,
    generate_session_token,
    get_valid_session,
    hash_password,
    hash_session_token,
    revoke_session,
    verify_password,
)


def test_argon2_password_hashing_and_verification() -> None:
    pw_hash = hash_password("correct-horse-battery-staple")
    assert pw_hash.startswith("$argon2")
    assert verify_password("correct-horse-battery-staple", pw_hash) is True
    assert verify_password("wrong-password", pw_hash) is False
    assert verify_password("", pw_hash) is False
    assert verify_password("anything", "not-a-valid-hash") is False

    with pytest.raises(ValueError, match="empty"):
        hash_password("")


def test_session_token_is_hashed_in_database(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="sec_user",
        email="sec@example.com",
        password_hash=hash_password("strongpass123"),
    )
    db_session.commit()

    raw_token, session_row = create_user_session(db_session, user.id, ttl_seconds=3600)
    db_session.commit()

    assert len(raw_token) >= 32
    assert session_row.token_hash != raw_token
    assert session_row.token_hash == hash_session_token(raw_token)
    assert get_valid_session(db_session, raw_token) is not None
    assert get_valid_session(db_session, None) is None
    assert get_valid_session(db_session, "tampered-token") is None


def test_expired_and_revoked_sessions_are_rejected(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="exp_user",
        email="exp@example.com",
        password_hash=hash_password("strongpass123"),
    )
    db_session.commit()

    raw_token, session_row = create_user_session(db_session, user.id, ttl_seconds=60)
    session_row.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert get_valid_session(db_session, raw_token) is None

    active_token, _ = create_user_session(db_session, user.id, ttl_seconds=3600)
    db_session.commit()
    assert revoke_session(db_session, active_token) is True
    db_session.commit()
    assert get_valid_session(db_session, active_token) is None
    assert revoke_session(db_session, active_token) is False


def test_generate_session_token_produces_distinct_tokens() -> None:
    tokens = {generate_session_token() for _ in range(50)}
    assert len(tokens) == 50
