"""Unit tests for pure-Python heads-up dice and 1-card poker engines."""

from __future__ import annotations

import pytest

from app.games.bots import CautiousBot, EVMaximisingBot
from app.games.card_game import OneCardPokerGame, format_card
from app.games.dice_game import DiceBettingGame
from app.games.engine import ActionType, PlayerAction, PlayerObservation, validate_player_action
from app.games.rng import GameRNG, SeededRNG


class _SpyBot:
    """Captures observations to verify opponent private state is never leaked."""

    def __init__(self) -> None:
        self.observations: list[PlayerObservation] = []

    @property
    def name(self) -> str:
        return "Spy"

    @property
    def strategy_id(self) -> str:
        return "spy"

    def decide(self, observation: PlayerObservation, _rng: GameRNG) -> PlayerAction:
        self.observations.append(observation)
        if ActionType.CALL in observation.legal_actions:
            return PlayerAction(ActionType.CALL)
        return PlayerAction(ActionType.CHECK)


def test_dice_betting_exact_showdown_probs_and_zero_sum() -> None:
    game = DiceBettingGame()
    assert game.exact_showdown_probs(1) == pytest.approx((0.0, 1 / 6))
    assert game.exact_showdown_probs(6) == pytest.approx((5 / 6, 1 / 6))

    spy = _SpyBot()
    ev_bot = EVMaximisingBot()
    for i in range(40):
        outcome = game.play_hand((spy, ev_bot), SeededRNG(100 + i), hand_number=i + 1)
        assert sum(outcome.net_profits) == 0

    # PlayerObservation must never include any opponent private card/roll field.
    assert spy.observations
    sample_obs = spy.observations[0]
    assert not hasattr(sample_obs, "opponent_value")
    assert not hasattr(sample_obs, "opponent_private_value")


def test_one_card_poker_exact_card_removal_and_format() -> None:
    assert format_card(0) == "2S"
    assert format_card(51) == "AC"

    game = OneCardPokerGame()
    # Deuce (rank 0): 0 lower cards, 3 equal cards out of 51
    assert game.exact_showdown_probs(0) == pytest.approx((0.0, 3 / 51))
    # Ace (rank 12): 48 lower cards, 3 equal cards out of 51
    assert game.exact_showdown_probs(12) == pytest.approx((48 / 51, 3 / 51))

    outcome = game.play_hand(
        (CautiousBot(), EVMaximisingBot()),
        SeededRNG(55),
        stacks=(500, 500),
    )
    assert sum(outcome.net_profits) == 0
    assert outcome.private_labels[0] != outcome.private_labels[1]


def test_validate_player_action_rejects_illegal_actions_and_overbets() -> None:
    obs = PlayerObservation(
        game_type="dice_betting",
        player_index=0,
        private_value=5,
        private_label="d6:5",
        exact_win_prob=4 / 6,
        exact_tie_prob=1 / 6,
        equity=4.5 / 6,
        own_stack=100,
        opponent_stack=30,
        pot=20,
        own_contribution=10,
        opponent_contribution=10,
        to_call=0,
        ante=10,
        min_bet=10,
        max_bet=30,
        legal_actions=(ActionType.CHECK, ActionType.BET),
    )

    with pytest.raises(ValueError, match="Illegal action"):
        validate_player_action(obs, PlayerAction(ActionType.CALL))

    with pytest.raises(ValueError, match="out of bounds"):
        validate_player_action(obs, PlayerAction(ActionType.BET, amount=35))

    with pytest.raises(ValueError, match="amount=0"):
        validate_player_action(obs, PlayerAction(ActionType.CHECK, amount=10))
