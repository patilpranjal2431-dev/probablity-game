"""Integration tests for registration, login, logout, and profile access."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_SESSION_COOKIE_NAME
from app.ledger import record_transaction
from app.models import TransactionType, User, UserSession


def _register_user(
    client: TestClient,
    *,
    username: str = "euler_quant",
    email: str = "euler@example.com",
    password: str = "StrongPass123!",
):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def test_register_creates_user_hashed_password_1000_coins_and_session(
    client: TestClient,
    db_session: Session,
) -> None:
    res = _register_user(client)
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["username"] == "euler_quant"
    assert body["user"]["email"] == "euler@example.com"
    assert body["balance"] == 1000
    assert "password_hash" not in body["user"]
    assert DEFAULT_SESSION_COOKIE_NAME in res.cookies

    user = db_session.scalar(select(User).where(User.username == "euler_quant"))
    assert user is not None
    assert user.password_hash != "StrongPass123!"
    assert user.password_hash.startswith("$argon2")
    assert user.wallet.balance == 1000


def test_duplicate_username_and_email_rejected(client: TestClient) -> None:
    first = _register_user(client, username="gauss", email="gauss@example.com")
    assert first.status_code == 201

    # Exact and case-variant duplicate username must be rejected.
    dup_exact = _register_user(client, username="gauss", email="other@example.com")
    assert dup_exact.status_code == 409
    assert "Username" in dup_exact.json()["detail"]

    dup_case = _register_user(client, username="GAUSS", email="other2@example.com")
    assert dup_case.status_code == 409

    dup_email = _register_user(client, username="gauss_2", email="GAUSS@example.com")
    assert dup_email.status_code == 409
    assert "Email" in dup_email.json()["detail"]


def test_registration_validates_inputs(client: TestClient) -> None:
    bad_username = _register_user(client, username="a!", email="valid@example.com")
    assert bad_username.status_code == 422

    bad_email = _register_user(client, username="valid_user", email="not-an-email")
    assert bad_email.status_code == 422

    short_password = _register_user(
        client, username="valid_user", email="valid@example.com", password="short"
    )
    assert short_password.status_code == 422


def test_login_wrong_password_and_unknown_user_rejected(client: TestClient) -> None:
    reg = _register_user(client, username="kelly", email="kelly@example.com")
    assert reg.status_code == 201
    client.post("/api/auth/logout")
    client.cookies.clear()

    wrong_pw = client.post(
        "/api/auth/login",
        json={"username": "kelly", "password": "WrongPassword999"},
    )
    assert wrong_pw.status_code == 401
    assert DEFAULT_SESSION_COOKIE_NAME not in wrong_pw.cookies

    unknown = client.post(
        "/api/auth/login",
        json={"username": "nobody_here", "password": "StrongPass123!"},
    )
    assert unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


def test_login_logout_and_session_revocation(
    client: TestClient,
    db_session: Session,
) -> None:
    _register_user(client, username="bayes", email="bayes@example.com")
    client.post("/api/auth/logout")
    client.cookies.clear()

    login_res = client.post(
        "/api/auth/login",
        json={"username": "bayes", "password": "StrongPass123!"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["balance"] == 1000
    session_cookie = login_res.cookies.get(DEFAULT_SESSION_COOKIE_NAME)
    assert session_cookie is not None

    profile_res = client.get("/api/profile")
    assert profile_res.status_code == 200

    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    # Even if a client replays the revoked cookie, access must be denied.
    client.cookies.set(DEFAULT_SESSION_COOKIE_NAME, session_cookie)
    after_logout = client.get("/api/profile")
    assert after_logout.status_code == 401

    revoked_rows = db_session.scalars(select(UserSession)).all()
    assert all(row.revoked_at is not None for row in revoked_rows)


def test_unauthenticated_access_rejected(client: TestClient) -> None:
    api_res = client.get("/api/profile")
    assert api_res.status_code == 401

    page_res = client.get("/profile", follow_redirects=False)
    assert page_res.status_code == 302
    assert page_res.headers["location"] == "/"


def test_profile_shows_balance_and_transaction_history_and_html_pages(
    client: TestClient,
    db_session: Session,
) -> None:
    reg = _register_user(client, username="nash", email="nash@example.com")
    assert reg.status_code == 201

    user = db_session.scalar(select(User).where(User.username == "nash"))
    assert user is not None
    record_transaction(
        db_session,
        user.wallet,
        amount=-100,
        tx_type=TransactionType.WAGER,
        description="Test wager",
    )
    record_transaction(
        db_session,
        user.wallet,
        amount=250,
        tx_type=TransactionType.PAYOUT,
        description="Test payout",
    )
    db_session.commit()

    profile_res = client.get("/api/profile")
    assert profile_res.status_code == 200
    data = profile_res.json()
    assert data["user"]["username"] == "nash"
    assert data["balance"] == 1150
    assert [tx["amount"] for tx in data["transactions"]] == [250, -100, 1000]
    assert [tx["balance_after"] for tx in data["transactions"]] == [1150, 900, 1000]

    home_res = client.get("/")
    assert home_res.status_code == 200
    assert "Edge Lab" in home_res.text

    profile_page = client.get("/profile")
    assert profile_page.status_code == 200
    assert "Transaction History" in profile_page.text
