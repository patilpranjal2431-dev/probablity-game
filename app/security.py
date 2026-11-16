"""Password hashing (Argon2id) and cryptographic session management."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserSession, utc_now

_password_hasher = PasswordHasher()


def _as_utc(dt: datetime) -> datetime:
    """Normalize naive SQLite datetimes to UTC so comparisons never raise TypeError."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    if not plain_password:
        raise ValueError("Password must not be empty.")
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash."""
    if not plain_password or not password_hash:
        return False
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Return True if the stored Argon2id hash parameters are outdated."""
    return _password_hasher.check_needs_rehash(password_hash)


def generate_session_token() -> str:
    """Generate a cryptographically secure URL-safe session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw session token for safe DB storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_user_session(
    db: Session,
    user_id: int,
    *,
    ttl_seconds: int,
) -> tuple[str, UserSession]:
    """Create and flush a new UserSession, returning (raw_token, session_row)."""
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive.")

    raw_token = generate_session_token()
    now = utc_now()
    session_row = UserSession(
        user_id=user_id,
        token_hash=hash_session_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(session_row)
    db.flush()
    return raw_token, session_row


def get_valid_session(db: Session, raw_token: str | None) -> UserSession | None:
    """Look up an active, non-revoked, non-expired UserSession by raw token."""
    if not raw_token or not raw_token.strip():
        return None

    token_digest = hash_session_token(raw_token)
    session_row = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_digest)
    )
    if session_row is None or session_row.revoked_at is not None:
        return None

    if _as_utc(session_row.expires_at) <= utc_now():
        return None

    return session_row


def revoke_session(db: Session, raw_token: str | None) -> bool:
    """Mark an existing session as revoked so its cookie can no longer be used."""
    if not raw_token or not raw_token.strip():
        return False

    token_digest = hash_session_token(raw_token)
    session_row = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_digest)
    )
    if session_row is None or session_row.revoked_at is not None:
        return False

    session_row.revoked_at = utc_now()
    db.flush()
    return True
