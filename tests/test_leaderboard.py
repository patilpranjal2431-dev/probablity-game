"""Integration tests for persisted EV decision grades, leaderboards, and explainer page."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_SESSION_COOKIE_NAME
from app.ledger import create_user_with_wallet, record_transaction
from app.models import (
    DecisionGrade,
    Game,
    GameStatus,
    Hand,
    HandStatus,
    TransactionType,
    User,
    utc_now,
)


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


def test_live_lobby_stores_decision_grades_and_hides_opponent_grades_on_fold(
    client: TestClient,
    db_session: Session,
) -> None:
    c1 = _register_and_get_cookie(client, "grade_p1")
    c2 = _register_and_get_cookie(client, "grade_p2")

    table_id = client.post(
        "/api/lobbies",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"game_type": "one_card_poker", "opponent_type": "human", "ante": 10},
    ).json()["table_id"]

    with client.websocket_connect(
        f"/ws/lobbies/{table_id}",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
    ) as ws1:
        _receive_until(ws1, "table:state")
        with client.websocket_connect(
            f"/ws/lobbies/{table_id}",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c2},
        ) as ws2:
            _receive_until(ws1, "table:state")
            _receive_until(ws2, "table:state")

            # Seat 0 bets 20; Seat 1 folds -> fold keeps private hands/opponent grades hidden!
            ws1.send_json({"type": "action", "action": "bet", "amount": 20})
            _receive_until(ws2, "table:state")
            ws2.send_json({"type": "action", "action": "fold"})

            res1 = _receive_until(ws1, "hand:resolved")
            res2 = _receive_until(ws2, "hand:resolved")

            assert res1["revealed_hands"] is None
            assert res2["revealed_hands"] is None
            assert len(res1["decision_grades"]) == 1
            assert res1["decision_grades"][0]["seat"] == 0
            assert len(res2["decision_grades"]) == 1
            assert res2["decision_grades"][0]["seat"] == 1

    p1 = db_session.scalar(select(User).where(User.username == "grade_p1"))
    p2 = db_session.scalar(select(User).where(User.username == "grade_p2"))
    assert p1 is not None and p2 is not None
    grades = list(db_session.scalars(select(DecisionGrade).order_by(DecisionGrade.id)))
    assert len(grades) == 2
    assert {g.user_id for g in grades} == {p1.id, p2.id}
    assert all(g.regret >= 0.0 and g.best_ev >= g.taken_ev - 1e-6 for g in grades)

    # Personal decision endpoint requires auth and only returns the caller's grades.
    assert client.get("/api/decisions/me").status_code == 401
    me_res = client.get("/api/decisions/me", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert me_res.status_code == 200
    me_body = me_res.json()
    assert me_body["decisions_count"] == 1
    assert me_body["hands_played"] == 1
    assert me_body["decisions"][0]["seat_index"] == 0


def test_skill_leaderboard_and_coins_leaderboard_separate_ev_from_luck(
    client: TestClient,
    db_session: Session,
) -> None:
    skilled_unlucky = create_user_with_wallet(
        db_session,
        username="skilled_unlucky",
        email="skilled@example.com",
        password_hash="hash",
    )
    lucky_fish = create_user_with_wallet(
        db_session,
        username="lucky_fish",
        email="lucky@example.com",
        password_hash="hash",
    )
    bot_user = create_user_with_wallet(
        db_session,
        username="bot_ev_max",
        email="bot@edgelab.local",
        password_hash="hash",
        is_bot=True,
        starting_balance=100_000,
    )
    game = Game(game_type="dice_betting", status=GameStatus.COMPLETED.value)
    db_session.add(game)
    db_session.flush()
    hand = Hand(
        game_id=game.id,
        hand_number=1,
        state_json="{}",
        pot=100,
        status=HandStatus.COMPLETED.value,
        completed_at=utc_now(),
    )
    db_session.add(hand)
    db_session.flush()

    # skilled_unlucky loses 200 coins at showdown despite making a +35 EV, 0-regret call.
    record_transaction(
        db_session,
        skilled_unlucky.wallet,
        amount=-200,
        tx_type=TransactionType.WAGER,
        description="Unlucky runout",
        hand_id=hand.id,
    )
    # lucky_fish wins 200 coins despite making a -25 EV (25 regret) punt.
    record_transaction(
        db_session,
        lucky_fish.wallet,
        amount=200,
        tx_type=TransactionType.PAYOUT,
        description="Lucky showdown",
        hand_id=hand.id,
    )
    db_session.add(
        DecisionGrade(
            hand_id=hand.id,
            game_id=game.id,
            user_id=skilled_unlucky.id,
            seat_index=0,
            decision_index=1,
            game_type="dice_betting",
            private_label="d6:6",
            equity=11 / 12,
            pot_before=40,
            to_call=20,
            taken_action="call",
            taken_amount=0,
            taken_ev=35.0,
            best_action="call",
            best_amount=0,
            best_ev=35.0,
            regret=0.0,
        )
    )
    db_session.add(
        DecisionGrade(
            hand_id=hand.id,
            game_id=game.id,
            user_id=lucky_fish.id,
            seat_index=1,
            decision_index=2,
            game_type="dice_betting",
            private_label="d6:1",
            equity=1 / 12,
            pot_before=40,
            to_call=20,
            taken_action="call",
            taken_amount=0,
            taken_ev=-25.0,
            best_action="fold",
            best_amount=0,
            best_ev=0.0,
            regret=25.0,
        )
    )
    db_session.add(
        DecisionGrade(
            hand_id=hand.id,
            game_id=game.id,
            user_id=bot_user.id,
            seat_index=1,
            decision_index=3,
            game_type="dice_betting",
            private_label="d6:5",
            equity=9 / 12,
            pot_before=20,
            to_call=0,
            taken_action="bet",
            taken_amount=20,
            taken_ev=18.0,
            best_action="bet",
            best_amount=20,
            best_ev=18.0,
            regret=0.0,
        )
    )
    db_session.commit()

    res = client.get("/api/leaderboards")
    assert res.status_code == 200
    body = res.json()
    assert body["include_bots"] is False

    skill_names = [e["username"] for e in body["skill_leaderboard"]]
    coin_names = [e["username"] for e in body["coins_leaderboard"]]
    assert skill_names == ["skilled_unlucky", "lucky_fish"]
    assert coin_names == ["lucky_fish", "skilled_unlucky"]

    assert body["skill_leaderboard"][0]["cumulative_ev"] == 35.0
    assert body["skill_leaderboard"][0]["total_regret"] == 0.0
    assert body["coins_leaderboard"][0]["coin_balance"] == 1200
    assert body["coins_leaderboard"][0]["net_coin_profit"] == 200

    # With include_bots=true, bot_ev_max appears on both leaderboards.
    with_bots = client.get("/api/leaderboards?include_bots=true").json()
    assert len(with_bots["skill_leaderboard"]) == 3
    assert any(e["is_bot"] for e in with_bots["skill_leaderboard"])


def test_leaderboard_and_skill_vs_luck_pages_render(client: TestClient) -> None:
    lb_page = client.get("/leaderboard")
    assert lb_page.status_code == 200
    assert "Skill Leaderboard" in lb_page.text
    assert "Coins Leaderboard" in lb_page.text

    guide_page = client.get("/skill-vs-luck")
    assert guide_page.status_code == 200
    assert "Realized Coin Profit = Decision Expected Value (Skill) + Outcome Variance (Luck)" in (
        guide_page.text
    )
