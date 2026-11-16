"""Unit tests for Random, Cautious, EV-Maximising, and Kelly-Sizing bots."""

from __future__ import annotations

import pytest

from app.games.bots import (
    CautiousBot,
    EVMaximisingBot,
    KellySizingBot,
    RandomBot,
    create_default_bots,
)
from app.games.engine import ActionType, PlayerObservation, validate_player_action
from app.games.rng import SeededRNG


def _obs(
    *,
    equity: float,
    legal: tuple[ActionType, ...],
    pot: int = 20,
    to_call: int = 0,
    own_stack: int = 1000,
    min_bet: int = 10,
    max_bet: int = 40,
) -> PlayerObservation:
    return PlayerObservation(
        game_type="dice_betting",
        player_index=0,
        private_value=4,
        private_label="d6:4",
        exact_win_prob=max(0.0, equity - 1 / 12),
        exact_tie_prob=1 / 6,
        equity=equity,
        own_stack=own_stack,
        opponent_stack=1000,
        pot=pot,
        own_contribution=10,
        opponent_contribution=10 + to_call,
        to_call=to_call,
        ante=10,
        min_bet=min_bet,
        max_bet=max_bet,
        legal_actions=legal,
    )


def test_random_bot_always_produces_legal_actions() -> None:
    bot = RandomBot()
    rng = SeededRNG(123)
    for legal in (
        (ActionType.CHECK, ActionType.BET),
        (ActionType.FOLD, ActionType.CALL),
    ):
        obs = _obs(equity=0.5, legal=legal, to_call=20 if ActionType.CALL in legal else 0)
        for _ in range(30):
            action = bot.decide(obs, rng)
            validate_player_action(obs, action)


def test_cautious_bot_folds_marginal_pot_odds_and_only_bets_nuts() -> None:
    bot = CautiousBot()
    rng = SeededRNG(1)

    # Pot odds = 20 / 60 = 0.333; equity = 0.40 is +EV, yet Cautious folds (< 0.333 + 0.15)
    marginal_call = _obs(equity=0.40, legal=(ActionType.FOLD, ActionType.CALL), pot=40, to_call=20)
    assert bot.decide(marginal_call, rng).action == ActionType.FOLD

    # Strong hand facing bet calls
    strong_call = _obs(equity=0.80, legal=(ActionType.FOLD, ActionType.CALL), pot=40, to_call=20)
    assert bot.decide(strong_call, rng).action == ActionType.CALL

    # Checks medium hand, min-bets nut hand
    med_open = _obs(equity=0.65, legal=(ActionType.CHECK, ActionType.BET))
    assert bot.decide(med_open, rng).action == ActionType.CHECK

    nut_open = _obs(equity=0.90, legal=(ActionType.CHECK, ActionType.BET))
    nut_act = bot.decide(nut_open, rng)
    assert nut_act.action == ActionType.BET and nut_act.amount == 10


def test_ev_maximising_bot_respects_exact_pot_odds() -> None:
    bot = EVMaximisingBot()
    rng = SeededRNG(1)

    # Pot = 40, to_call = 20 -> breakeven equity = 20/60 = 0.3333
    plus_ev = _obs(equity=0.35, legal=(ActionType.FOLD, ActionType.CALL), pot=40, to_call=20)
    assert bot.decide(plus_ev, rng).action == ActionType.CALL

    minus_ev = _obs(equity=0.30, legal=(ActionType.FOLD, ActionType.CALL), pot=40, to_call=20)
    assert bot.decide(minus_ev, rng).action == ActionType.FOLD

    strong_open = _obs(equity=0.90, legal=(ActionType.CHECK, ActionType.BET))
    assert bot.decide(strong_open, rng).action == ActionType.BET


def test_kelly_bot_sizes_wagers_by_edge_and_bankroll() -> None:
    bot = KellySizingBot(kelly_fraction=0.5)
    rng = SeededRNG(1)

    # Negative edge -> check
    weak_open = _obs(equity=0.40, legal=(ActionType.CHECK, ActionType.BET), own_stack=200)
    assert bot.decide(weak_open, rng).action == ActionType.CHECK

    # equity=0.70 -> edge=0.40 -> half-Kelly = 0.20 * 100 = 20
    med_open = _obs(equity=0.70, legal=(ActionType.CHECK, ActionType.BET), own_stack=100)
    act = bot.decide(med_open, rng)
    assert act.action == ActionType.BET and act.amount == 20

    # Oversized call relative to tiny stack and thin edge -> folds to protect bankroll
    thin_giant_call = _obs(
        equity=0.40,
        legal=(ActionType.FOLD, ActionType.CALL),
        pot=60,
        to_call=30,
        own_stack=40,
        min_bet=10,
    )
    assert bot.decide(thin_giant_call, rng).action == ActionType.FOLD

    with pytest.raises(ValueError, match="kelly_fraction"):
        KellySizingBot(kelly_fraction=0.0)

    assert len(create_default_bots()) == 4
