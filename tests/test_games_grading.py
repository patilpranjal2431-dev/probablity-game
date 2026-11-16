"""Unit tests for post-game EV decision grading and regret calculations."""

from __future__ import annotations

import pytest

from app.games.bots import CautiousBot, EVMaximisingBot
from app.games.card_game import OneCardPokerGame
from app.games.dice_game import DiceBettingGame
from app.games.engine import ActionType, PlayerAction, PlayerObservation
from app.games.grading import evaluate_action_ev, grade_decision, grade_hand_decisions
from app.games.rng import SeededRNG


def _obs(
    *,
    game_type: str = "dice_betting",
    private_value: int = 6,
    private_label: str = "d6:6",
    win_prob: float = 5 / 6,
    tie_prob: float = 1 / 6,
    pot: int = 20,
    to_call: int = 0,
    legal: tuple[ActionType, ...] = (ActionType.CHECK, ActionType.BET),
    min_bet: int = 10,
    max_bet: int = 40,
    own_stack: int = 990,
    opponent_stack: int = 990,
) -> PlayerObservation:
    return PlayerObservation(
        game_type=game_type,
        player_index=0,
        private_value=private_value,
        private_label=private_label,
        exact_win_prob=win_prob,
        exact_tie_prob=tie_prob,
        equity=win_prob + 0.5 * tie_prob,
        own_stack=own_stack,
        opponent_stack=opponent_stack,
        pot=pot,
        own_contribution=10,
        opponent_contribution=10 + to_call,
        to_call=to_call,
        ante=10,
        min_bet=min_bet,
        max_bet=max_bet,
        legal_actions=legal,
    )


def test_call_vs_fold_ev_and_regret_against_exact_values() -> None:
    # Pot = 40, to_call = 20 -> calling risks 20 to win 60 (equity = 0.80 -> EV = 0.8*60 - 20 = +28)
    plus_ev_obs = _obs(
        win_prob=0.75,
        tie_prob=0.10,
        pot=40,
        to_call=20,
        legal=(ActionType.FOLD, ActionType.CALL),
    )
    assert evaluate_action_ev(plus_ev_obs, PlayerAction(ActionType.CALL)) == pytest.approx(28.0)
    assert evaluate_action_ev(plus_ev_obs, PlayerAction(ActionType.FOLD)) == pytest.approx(0.0)

    call_grade = grade_decision(plus_ev_obs, PlayerAction(ActionType.CALL))
    assert call_grade.best_action == ActionType.CALL
    assert call_grade.regret == pytest.approx(0.0)

    fold_grade = grade_decision(plus_ev_obs, PlayerAction(ActionType.FOLD))
    assert fold_grade.taken_ev == pytest.approx(0.0)
    assert fold_grade.best_action == ActionType.CALL
    assert fold_grade.best_ev == pytest.approx(28.0)
    assert fold_grade.regret == pytest.approx(28.0)

    # Minus-EV call: equity = 0.25 -> EV(CALL) = 0.25*60 - 20 = -5.0 vs EV(FOLD) = 0.0
    minus_ev_obs = _obs(
        win_prob=0.20,
        tie_prob=0.10,
        pot=40,
        to_call=20,
        legal=(ActionType.FOLD, ActionType.CALL),
    )
    bad_call = grade_decision(minus_ev_obs, PlayerAction(ActionType.CALL))
    assert bad_call.taken_ev == pytest.approx(-5.0)
    assert bad_call.best_action == ActionType.FOLD
    assert bad_call.best_ev == pytest.approx(0.0)
    assert bad_call.regret == pytest.approx(5.0)


def test_dice_open_action_ev_uses_exact_d6_calling_range() -> None:
    # d6:6, pot = 20:
    # CHECK EV = (11/12) * 20 = 18.333333
    # BET 40: opp calls if (y-0.5)/6 >= 40/100=0.40 -> y in {3,4,5,6}.
    # y in {1,2} fold (+20), y in {3,4,5} lose (+60), y=6 ties (+10):
    # EV = (2*20 + 3*60 + 10) / 6 = 230 / 6 = 38.333333
    six_obs = _obs(private_value=6, private_label="d6:6", win_prob=5 / 6, tie_prob=1 / 6)
    assert evaluate_action_ev(six_obs, PlayerAction(ActionType.CHECK)) == pytest.approx(110 / 6)
    assert evaluate_action_ev(six_obs, PlayerAction(ActionType.BET, 40)) == pytest.approx(230 / 6)

    check_six = grade_decision(six_obs, PlayerAction(ActionType.CHECK))
    assert check_six.best_action == ActionType.BET
    assert check_six.best_ev == pytest.approx(230 / 6, abs=1e-4)
    assert check_six.regret == pytest.approx(20.0, abs=1e-4)

    # d6:1, pot = 20:
    # CHECK EV = (1/12) * 20 = 1.666667; bluffing 40 gets called by {3,4,5,6} -> negative EV
    one_obs = _obs(private_value=1, private_label="d6:1", win_prob=0.0, tie_prob=1 / 6)
    bluff_grade = grade_decision(one_obs, PlayerAction(ActionType.BET, 40))
    assert bluff_grade.taken_ev == pytest.approx(-20.0)
    assert bluff_grade.best_action == ActionType.CHECK
    assert bluff_grade.best_ev == pytest.approx(10 / 6, abs=1e-4)
    assert bluff_grade.regret == pytest.approx(10 / 6 + 20.0, abs=1e-4)


def test_one_card_poker_exact_51_card_removal_and_hand_grading() -> None:
    game = OneCardPokerGame(ante=10, min_bet=10, max_bet=40)
    win_p, tie_p = game.exact_showdown_probs(12)  # Ace
    ace_obs = _obs(
        game_type="one_card_poker",
        private_value=12,
        private_label="AS",
        win_prob=win_p,
        tie_prob=tie_p,
    )
    grade = grade_decision(ace_obs, PlayerAction(ActionType.BET, 40))
    assert grade.best_action == ActionType.BET
    assert grade.best_ev >= grade.taken_ev > 30.0
    assert grade.regret >= 0.0

    # Grade all decisions across simulated hands using pure-Python engine.
    dice_game = DiceBettingGame()
    rng = SeededRNG(99)
    bots = (EVMaximisingBot(), CautiousBot())
    for hand_num in range(1, 20):
        outcome = dice_game.play_hand(bots, rng, hand_number=hand_num)
        graded = grade_hand_decisions(outcome)
        assert len(graded) == len(outcome.decisions)
        for _rec, ev in graded:
            assert ev.best_ev >= ev.taken_ev - 1e-6
            assert ev.regret >= 0.0
