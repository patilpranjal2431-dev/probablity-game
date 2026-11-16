"""Integration tests for WebSocket lobbies, atomic settlement, timeouts, and disconnects."""

from __future__ import annotations

import time
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.config import DEFAULT_SESSION_COOKIE_NAME, Settings
from app.database import get_db
from app.ledger import audit_wallet_balance
from app.main import create_app
from app.models import User


def _make_client_for_engine(
    test_engine: Engine,
    *,
    turn_timeout_seconds: float = 30.0,
) -> TestClient:
    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    app = create_app(
        settings=Settings(turn_timeout_seconds=turn_timeout_seconds),
        session_factory=testing_session_local,
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _register_and_get_cookie(client: TestClient, username: str) -> str:
    client.cookies.clear()
    res = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "StrongPassword123!",
        },
    )
    assert res.status_code == 201
    cookie = res.cookies.get(DEFAULT_SESSION_COOKIE_NAME)
    assert cookie is not None
    client.cookies.clear()
    return cookie


def _receive_until(ws, expected_type: str, max_msgs: int = 12) -> dict:
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg.get("type") == expected_type:
            return msg
    raise AssertionError(f"Did not receive event {expected_type!r} within {max_msgs} messages.")


def test_lobby_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/lobbies").status_code == 401
    assert client.post("/api/lobbies", json={"game_type": "dice_betting"}).status_code == 401
    assert client.get("/lobby", follow_redirects=False).status_code == 302

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/lobbies/1"):
            pass
    assert exc_info.value.code == 4401


def test_player_vs_bot_game_and_atomic_wallet_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    cookie = _register_and_get_cookie(client, "human_p1")

    create_res = client.post(
        "/api/lobbies",
        cookies={DEFAULT_SESSION_COOKIE_NAME: cookie},
        json={
            "game_type": "one_card_poker",
            "opponent_type": "bot",
            "bot_strategy": "cautious",
            "ante": 10,
            "min_bet": 10,
            "max_bet": 40,
        },
    )
    assert create_res.status_code == 201
    table_id = create_res.json()["table_id"]

    with client.websocket_connect(
        f"/ws/lobbies/{table_id}",
        cookies={DEFAULT_SESSION_COOKIE_NAME: cookie},
    ) as ws:
        state = _receive_until(ws, "table:state")
        assert state["your_seat"] == 0
        assert state["your_private"] is not None
        assert "opponent_private" not in state

        # Human checks on first turn; cautious bot then checks or bets.
        ws.send_json({"type": "action", "action": "check"})
        resolved = None
        for _ in range(8):
            msg = ws.receive_json()
            if msg["type"] == "hand:resolved":
                resolved = msg
                break
            if msg["type"] == "table:state" and msg["current_turn_seat"] == 0:
                ws.send_json({"type": "action", "action": "fold"})

        assert resolved is not None
        assert resolved["hand_number"] == 1

    human = db_session.scalar(select(User).where(User.username == "human_p1"))
    bot = db_session.scalar(select(User).where(User.username == "bot_cautious"))
    assert human is not None and bot is not None
    assert audit_wallet_balance(db_session, human.wallet.id) == human.wallet.balance
    assert audit_wallet_balance(db_session, bot.wallet.id) == bot.wallet.balance
    assert (human.wallet.balance - 1000) + (bot.wallet.balance - 100_000) == 0


def test_pvp_two_clients_betting_hidden_state_and_illegal_moves(
    test_engine: Engine,
    db_session: Session,
) -> None:
    with _make_client_for_engine(test_engine) as client:
        c1_cookie = _register_and_get_cookie(client, "alice_ws")
        c2_cookie = _register_and_get_cookie(client, "bob_ws")
        c3_cookie = _register_and_get_cookie(client, "charlie_ws")

        res = client.post(
            "/api/lobbies",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
            json={"game_type": "dice_betting", "opponent_type": "human", "ante": 10},
        )
        assert res.status_code == 201
        table_id = res.json()["table_id"]

        with client.websocket_connect(
            f"/ws/lobbies/{table_id}",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
        ) as ws1:
            waiting = _receive_until(ws1, "table:state")
            assert waiting["status"] == "waiting"
            assert waiting["your_private"] is None

            with client.websocket_connect(
                f"/ws/lobbies/{table_id}",
                cookies={DEFAULT_SESSION_COOKIE_NAME: c2_cookie},
            ) as ws2:
                s1 = _receive_until(ws1, "table:state")
                s2 = _receive_until(ws2, "table:state")

                assert s1["status"] == "active"
                assert s1["your_seat"] == 0 and s1["current_turn_seat"] == 0
                assert s2["your_seat"] == 1 and s2["current_turn_seat"] == 0
                assert s1["your_private"] is not None
                assert s2["your_private"] is not None

                # Table is full -> 3rd client must be rejected with 4409.
                with pytest.raises(WebSocketDisconnect) as full_exc:
                    with client.websocket_connect(
                        f"/ws/lobbies/{table_id}",
                        cookies={DEFAULT_SESSION_COOKIE_NAME: c3_cookie},
                    ):
                        pass
                assert full_exc.value.code == 4409

                # Illegal move 1: Seat 1 acts out of turn -> rejected without mutating state.
                ws2.send_json({"type": "action", "action": "check"})
                err_turn = _receive_until(ws2, "error")
                assert err_turn["code"] == "not_your_turn"

                # Illegal move 2: Seat 0 sends malformed JSON & illegal bet amount.
                ws1.send_text("{bad-json")
                assert _receive_until(ws1, "error")["code"] == "invalid_json"

                ws1.send_json({"type": "action", "action": "bet", "amount": 9999})
                assert _receive_until(ws1, "error")["code"] == "illegal_move"

                # Now play legally: Seat 0 bets 25, Seat 1 calls 25 -> showdown!
                ws1.send_json({"type": "action", "action": "bet", "amount": 25})
                s2_after_bet = _receive_until(ws2, "table:state")
                assert s2_after_bet["current_turn_seat"] == 1
                assert s2_after_bet["to_call"] == 25

                ws2.send_json({"type": "action", "action": "call"})
                res1 = _receive_until(ws1, "hand:resolved")
                res2 = _receive_until(ws2, "hand:resolved")
                assert res1 == res2
                assert res1["reason"] == "showdown"
                assert res1["pot"] == 70
                assert len(res1["revealed_hands"]) == 2
                assert sum(res1["net_profits"]) == 0

    alice = db_session.scalar(select(User).where(User.username == "alice_ws"))
    bob = db_session.scalar(select(User).where(User.username == "bob_ws"))
    assert alice is not None and bob is not None
    assert audit_wallet_balance(db_session, alice.wallet.id) == alice.wallet.balance
    assert audit_wallet_balance(db_session, bob.wallet.id) == bob.wallet.balance
    assert alice.wallet.balance + bob.wallet.balance == 2000


def test_pvp_disconnect_forfeit_resolves_hand_and_keeps_cards_hidden(
    test_engine: Engine,
    db_session: Session,
) -> None:
    with _make_client_for_engine(test_engine) as client:
        c1_cookie = _register_and_get_cookie(client, "stay_user")
        c2_cookie = _register_and_get_cookie(client, "drop_user")

        table_id = client.post(
            "/api/lobbies",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
            json={"game_type": "one_card_poker", "opponent_type": "human", "ante": 15},
        ).json()["table_id"]

        with client.websocket_connect(
            f"/ws/lobbies/{table_id}",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
        ) as ws1:
            _receive_until(ws1, "table:state")
            with client.websocket_connect(
                f"/ws/lobbies/{table_id}",
                cookies={DEFAULT_SESSION_COOKIE_NAME: c2_cookie},
            ) as ws2:
                _receive_until(ws1, "table:state")
                _receive_until(ws2, "table:state")
                # ws2 exits context -> triggers WebSocketDisconnect during active hand!
            resolved = _receive_until(ws1, "hand:resolved")
            assert resolved["reason"] == "disconnect_forfeit"
            assert resolved["winner_seat"] == 0
            assert resolved["revealed_hands"] is None
            assert resolved["pot"] == 30

    stayer = db_session.scalar(select(User).where(User.username == "stay_user"))
    dropper = db_session.scalar(select(User).where(User.username == "drop_user"))
    assert stayer is not None and dropper is not None
    assert stayer.wallet.balance == 1015
    assert dropper.wallet.balance == 985
    assert audit_wallet_balance(db_session, stayer.wallet.id) == 1015
    assert audit_wallet_balance(db_session, dropper.wallet.id) == 985


def test_turn_timeout_auto_acts_and_resolves_hand(
    test_engine: Engine,
    db_session: Session,
) -> None:
    with _make_client_for_engine(test_engine, turn_timeout_seconds=0.15) as client:
        c1_cookie = _register_and_get_cookie(client, "slow_p1")
        c2_cookie = _register_and_get_cookie(client, "slow_p2")

        table_id = client.post(
            "/api/lobbies",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
            json={"game_type": "dice_betting", "opponent_type": "human", "ante": 10},
        ).json()["table_id"]

        with client.websocket_connect(
            f"/ws/lobbies/{table_id}",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1_cookie},
        ) as ws1:
            _receive_until(ws1, "table:state")
            with client.websocket_connect(
                f"/ws/lobbies/{table_id}",
                cookies={DEFAULT_SESSION_COOKIE_NAME: c2_cookie},
            ) as ws2:
                _receive_until(ws1, "table:state")
                _receive_until(ws2, "table:state")
                # Both players remain silent -> both turns time out via auto-check -> showdown!
                time.sleep(0.45)
                timeout_msg = _receive_until(ws1, "hand:timeout")
                assert timeout_msg["auto_action"] == "check"
                resolved = _receive_until(ws1, "hand:resolved")
                assert resolved["reason"] == "showdown"
                assert resolved["pot"] == 20

    p1 = db_session.scalar(select(User).where(User.username == "slow_p1"))
    p2 = db_session.scalar(select(User).where(User.username == "slow_p2"))
    assert p1 is not None and p2 is not None
    assert audit_wallet_balance(db_session, p1.wallet.id) == p1.wallet.balance
    assert audit_wallet_balance(db_session, p2.wallet.id) == p2.wallet.balance
    assert p1.wallet.balance + p2.wallet.balance == 2000
