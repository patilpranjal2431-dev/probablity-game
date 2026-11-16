"""Unit and integration tests for Order Book market-making simulation and adverse selection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_SESSION_COOKIE_NAME
from app.games.order_book import (
    RoundSnapshot,
    compute_post_game_analysis,
    evolve_fair_value,
    generate_initial_market,
    simulate_quote_round,
)
from app.games.rng import SeededRNG


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


def test_order_book_informed_arb_and_pnl_decomposition_identity() -> None:
    rng = SeededRNG(42)
    initial_v, signal = generate_initial_market(rng)
    assert 85.0 <= initial_v <= 115.0

    # Stale ask below hidden fair value -> informed_arb MUST lift ask and cause adverse selection.
    stale_snap = simulate_quote_round(
        round_number=1,
        prev_fair_value=100.0,
        curr_fair_value=100.0,
        public_signal=98.0,
        bid_price=94.0,
        ask_price=98.0,
        quote_size=2,
        cash_before=0.0,
        inventory_before=0,
        max_inventory=10,
        rng=SeededRNG(1),
    )
    informed_fills = [f for f in stale_snap.fills if f.bot_kind == "informed_arb"]
    assert len(informed_fills) == 1
    assert informed_fills[0].side == "sell"
    assert informed_fills[0].quantity == 2
    assert informed_fills[0].adverse_selection == pytest.approx(8.0)

    # Multi-round run with evolving fair value and inventory cap enforcement.
    rounds: list[RoundSnapshot] = []
    curr_v = 100.0
    cash = 0.0
    inv = 0
    max_inv = 4
    sim_rng = SeededRNG(77)
    for rnd in range(1, 13):
        prev_v = curr_v
        if rnd > 1:
            curr_v, sig = evolve_fair_value(prev_v, sim_rng, volatility=1.5)
        else:
            sig = 100.0
        snap = simulate_quote_round(
            round_number=rnd,
            prev_fair_value=prev_v,
            curr_fair_value=curr_v,
            public_signal=sig,
            bid_price=round(sig - 1.5, 2),
            ask_price=round(sig + 1.5, 2),
            quote_size=3,
            cash_before=cash,
            inventory_before=inv,
            max_inventory=max_inv,
            rng=sim_rng,
        )
        assert abs(snap.inventory_after) <= max_inv
        rounds.append(snap)
        cash = snap.cash_after
        inv = snap.inventory_after

    analysis = compute_post_game_analysis(initial_fair_value=100.0, rounds=rounds)
    assert analysis.max_abs_inventory <= max_inv
    assert analysis.total_pnl == pytest.approx(
        analysis.spread_captured - analysis.adverse_selection_cost + analysis.inventory_drift_pnl,
        abs=0.05,
    )


def test_order_book_api_hidden_fair_value_and_post_game_analysis(client: TestClient) -> None:
    assert client.get("/api/orderbook/sessions").status_code == 401
    assert client.post("/api/orderbook/sessions", json={}).status_code == 401
    assert client.get("/orderbook", follow_redirects=False).status_code == 302

    c1 = _register_and_get_cookie(client, "mm_user1")
    c2 = _register_and_get_cookie(client, "mm_user2")

    page_res = client.get("/orderbook", cookies={DEFAULT_SESSION_COOKIE_NAME: c1})
    assert page_res.status_code == 200
    assert "Order Book Simulation" in page_res.text

    create_res = client.post(
        "/api/orderbook/sessions",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"num_rounds": 5, "max_inventory": 8, "fundamental_volatility": 1.0},
    )
    assert create_res.status_code == 201
    session = create_res.json()
    sid = session["id"]
    assert session["status"] == "active"
    assert session["analysis"] is None
    assert "fair_value" not in create_res.text

    # Cross-user access denied
    assert (
        client.get(
            f"/api/orderbook/sessions/{sid}",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c2},
        ).status_code
        == 403
    )

    # Crossed quote rejected
    assert (
        client.post(
            f"/api/orderbook/sessions/{sid}/quote",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
            json={"bid_price": 102.0, "ask_price": 100.0, "quote_size": 2},
        ).status_code
        == 422
    )

    # Play all 5 rounds; verify hidden state stays hidden until round 5 completes.
    latest = session
    for rnd in range(1, 6):
        sig = latest["latest_public_signal"]
        q_res = client.post(
            f"/api/orderbook/sessions/{sid}/quote",
            cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
            json={
                "bid_price": round(max(1.0, sig - 1.5), 2),
                "ask_price": round(sig + 1.5, 2),
                "quote_size": 2,
            },
        )
        assert q_res.status_code == 200
        latest = q_res.json()
        if rnd < 5:
            assert latest["status"] == "active"
            assert latest["analysis"] is None
            assert "adverse_selection" not in q_res.text
            assert "bot_kind" not in q_res.text

    assert latest["status"] == "completed"
    assert latest["current_round"] == 5
    an = latest["analysis"]
    assert an is not None
    assert len(an["rounds"]) == 5
    assert an["total_pnl"] == pytest.approx(
        an["spread_captured"] - an["adverse_selection_cost"] + an["inventory_drift_pnl"],
        abs=0.05,
    )

    # Quoting after completion returns 409
    after = client.post(
        f"/api/orderbook/sessions/{sid}/quote",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"bid_price": 98.0, "ask_price": 102.0, "quote_size": 1},
    )
    assert after.status_code == 409

    # Early finish flow also reveals analysis cleanly
    s2_id = client.post(
        "/api/orderbook/sessions",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
        json={"num_rounds": 10, "max_inventory": 6, "fundamental_volatility": 0.5},
    ).json()["id"]
    fin_res = client.post(
        f"/api/orderbook/sessions/{s2_id}/finish",
        cookies={DEFAULT_SESSION_COOKIE_NAME: c1},
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["status"] == "completed"
    assert fin_res.json()["analysis"] is not None
