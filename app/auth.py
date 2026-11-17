"""Authentication, session cookie helpers, and profile API routes."""

from __future__ import annotations

import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.ledger import audit_wallet_balance, create_user_with_wallet
from app.models import Transaction, User
from app.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    ProfileResponse,
    RegisterRequest,
    TransactionPublic,
    UserPublic,
)
from app.security import (
    create_user_session,
    get_valid_session,
    hash_password,
    password_needs_rehash,
    revoke_session,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])

# Pre-computed dummy Argon2id hash so failed logins for unknown usernames still
# perform a full verification pass (mitigating username enumeration via timing).
_DUMMY_PASSWORD_HASH = hash_password("edge-lab-timing-mitigation-dummy")


def get_app_settings(request: Request) -> Settings:
    """Return Settings attached to app.state or load defaults from environment."""
    return getattr(request.app.state, "settings", None) or get_settings()


def _cookie_policy(request: Request, settings: Settings) -> tuple[bool, Literal["lax", "none"]]:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    is_https = settings.cookie_secure or request.url.scheme == "https" or forwarded_proto == "https"
    if is_https:
        return True, "none"
    return False, "lax"


def _set_session_cookie(
    request: Request,
    response: Response,
    raw_token: str,
    settings: Settings,
) -> None:
    secure, samesite = _cookie_policy(request, settings)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/",
    )


def _clear_session_cookie(
    request: Request,
    response: Response,
    settings: Settings,
) -> None:
    secure, samesite = _cookie_policy(request, settings)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite=samesite,
        secure=secure,
    )


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Return the authenticated human User for the request cookie, or None."""
    settings = get_app_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    user_session = get_valid_session(db, raw_token)
    if user_session is None:
        return None

    user = db.get(User, user_session.user_id)
    if user is None or user.is_bot:
        return None
    return user


def get_current_user(
    current_user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    """Require an authenticated user or raise 401 Unauthorized."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return current_user


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new player account with 1,000 starting virtual coins",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    settings = get_app_settings(request)

    existing_username = db.scalar(
        select(User).where(func.lower(User.username) == payload.username.lower())
    )
    if existing_username is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken.",
        )

    existing_email = db.scalar(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )

    try:
        user = create_user_with_wallet(
            db,
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            is_bot=False,
            starting_balance=settings.initial_wallet_balance,
        )
        raw_token, _ = create_user_session(
            db,
            user.id,
            ttl_seconds=settings.session_ttl_seconds,
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        ) from exc

    _set_session_cookie(request, response, raw_token, settings)
    return AuthResponse(
        user=UserPublic.model_validate(user),
        balance=user.wallet.balance,
        message="Account created successfully.",
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Log in with username and password",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    settings = get_app_settings(request)

    user = db.scalar(
        select(User).where(
            func.lower(User.username) == payload.username.lower(),
            User.is_bot.is_(False),
        )
    )
    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    raw_token, _ = create_user_session(
        db,
        user.id,
        ttl_seconds=settings.session_ttl_seconds,
    )
    db.commit()

    _set_session_cookie(request, response, raw_token, settings)
    return AuthResponse(
        user=UserPublic.model_validate(user),
        balance=user.wallet.balance,
        message="Logged in successfully.",
    )


@router.post(
    "/auth/guest",
    response_model=AuthResponse,
    summary="Initialize or reuse a sandbox virtual-coin session without a login wall",
)
def guest_session(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    existing_user: Annotated[User | None, Depends(get_optional_user)],
) -> AuthResponse:
    if existing_user is not None:
        verified_balance = audit_wallet_balance(db, existing_user.wallet.id)
        return AuthResponse(
            user=UserPublic.model_validate(existing_user),
            balance=verified_balance,
            message="Active session ready.",
        )

    settings = get_app_settings(request)
    suffix = secrets.token_hex(4)
    username = f"desk_{suffix}"
    email = f"{username}@edgelab.local"
    random_secret = secrets.token_urlsafe(24)

    user = create_user_with_wallet(
        db,
        username=username,
        email=email,
        password_hash=hash_password(random_secret),
        is_bot=False,
        starting_balance=settings.initial_wallet_balance,
    )
    raw_token, _ = create_user_session(
        db,
        user.id,
        ttl_seconds=settings.session_ttl_seconds,
    )
    db.commit()
    db.refresh(user)

    _set_session_cookie(request, response, raw_token, settings)
    return AuthResponse(
        user=UserPublic.model_validate(user),
        balance=user.wallet.balance,
        message="Sandbox desk session initialized.",
    )


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="Revoke the active session and clear the session cookie",
)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponse:
    settings = get_app_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if revoke_session(db, raw_token):
        db.commit()

    _clear_session_cookie(request, response, settings)
    return LogoutResponse(message="Logged out successfully.")


@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Get the authenticated user's profile, coin balance, and ledger history",
)
def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileResponse:
    verified_balance = audit_wallet_balance(db, current_user.wallet.id)
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.wallet_id == current_user.wallet.id)
        .order_by(Transaction.id.desc())
    ).all()

    return ProfileResponse(
        user=UserPublic.model_validate(current_user),
        balance=verified_balance,
        transactions=[TransactionPublic.model_validate(tx) for tx in transactions],
    )
