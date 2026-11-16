"""Unit and API tests for the Bankroll Simulator (Kelly criterion & Risk of Ruin)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.quant.bankroll import (
    exact_even_money_risk_of_ruin,
    kelly_fraction,
    kelly_log_growth,
    simulate_bankroll,
)


def test_kelly_criterion_exact_values_and_overbetting_decay() -> None:
    # Fair odds b=1.0, p=0.60 -> f* = 0.60 - 0.40 = 0.20
    f_star = kelly_fraction(win_prob=0.60, payout_odds=1.0)
    assert f_star == pytest.approx(0.20)

    # Zero/negative edge -> f* = 0.0
    assert kelly_fraction(win_prob=0.50, payout_odds=1.0) == 0.0
    assert kelly_fraction(win_prob=0.40, payout_odds=1.0) == 0.0

    # At b=2.0, p=0.50 -> f* = (2*0.5 - 0.5)/2 = 0.25
    assert kelly_fraction(win_prob=0.50, payout_odds=2.0) == pytest.approx(0.25)

    # Optimal growth occurs at f*; overbetting beyond ~2f* produces negative log growth.
    g_opt = kelly_log_growth(0.60, 1.0, f_star)
    g_half = kelly_log_growth(0.60, 1.0, 0.5 * f_star)
    g_over = kelly_log_growth(0.60, 1.0, 0.50)
    assert g_opt > g_half > 0.0
    assert g_over < 0.0


def test_exact_gamblers_ruin_matches_known_formulas() -> None:
    # Infinite-horizon even-money RoR = ((1 - p) / p)^N0
    assert exact_even_money_risk_of_ruin(start_units=5, win_prob=0.60) == pytest.approx(
        (0.4 / 0.6) ** 5
    )
    assert exact_even_money_risk_of_ruin(start_units=5, win_prob=0.50) == pytest.approx(1.0)

    # Fair coin finite-target RoR = 1 - N0 / M
    assert exact_even_money_risk_of_ruin(
        start_units=3, win_prob=0.50, target_units=10
    ) == pytest.approx(0.70)


def test_fixed_stake_simulation_matches_analytical_risk_of_ruin() -> None:
    # 10 units starting (1000 initial, bet_fraction=0.10 -> 100 unit stake), p=0.55:
    # Exact infinite-horizon RoR = (0.45/0.55)^10 = 0.13443...
    sim = simulate_bankroll(
        initial_bankroll=1000.0,
        win_prob=0.55,
        payout_odds=1.0,
        bet_fraction=0.10,
        sizing_mode="fixed_stake",
        num_bets=1200,
        num_paths=1500,
        ruin_threshold=0.0,
        seed=42,
    )
    assert sim.analytical_risk_of_ruin == pytest.approx((0.45 / 0.55) ** 10, abs=1e-5)
    assert sim.empirical_risk_of_ruin == pytest.approx(sim.analytical_risk_of_ruin, abs=0.03)
    assert sum(b.count for b in sim.histogram) == 1500
    assert sim.trajectories[0].step == 0
    assert sim.trajectories[-1].step == 1200
    assert sim.p05_terminal <= sim.median_terminal <= sim.p95_terminal

    # Deterministic repeatability with the same seed.
    sim_again = simulate_bankroll(
        initial_bankroll=1000.0,
        win_prob=0.55,
        payout_odds=1.0,
        bet_fraction=0.10,
        sizing_mode="fixed_stake",
        num_bets=1200,
        num_paths=1500,
        ruin_threshold=0.0,
        seed=42,
    )
    assert sim == sim_again


def test_bankroll_endpoint_and_page(client: TestClient) -> None:
    page_res = client.get("/bankroll")
    assert page_res.status_code == 200
    assert "Bankroll &amp; Kelly Simulator" in page_res.text

    res = client.post(
        "/api/quant/bankroll",
        json={
            "initial_bankroll": 1000,
            "win_prob": 0.58,
            "payout_odds": 1.0,
            "bet_fraction": 0.08,
            "sizing_mode": "proportional",
            "num_bets": 150,
            "num_paths": 300,
            "seed": 7,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["full_kelly_fraction"] == pytest.approx(0.16, abs=1e-4)
    assert len(body["histogram"]) == 12
    assert len(body["kelly_curve"]) >= 10
    assert body["chosen_log_growth"] > 0.0

    bad = client.post(
        "/api/quant/bankroll",
        json={"initial_bankroll": 500, "ruin_threshold": 500},
    )
    assert bad.status_code == 422
