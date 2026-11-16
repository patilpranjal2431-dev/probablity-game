"""Unit tests for the bot-vs-bot tournament runner and confidence intervals."""

from __future__ import annotations

import pytest

from app.games.bots import EVMaximisingBot, KellySizingBot, RandomBot, create_default_bots
from app.games.card_game import OneCardPokerGame
from app.games.dice_game import DiceBettingGame
from app.games.tournament import run_head_to_head, run_round_robin_tournament


def test_head_to_head_is_reproducible_and_reports_valid_cis() -> None:
    game = DiceBettingGame()
    s1 = run_head_to_head(game, KellySizingBot(), RandomBot(), num_hands=400, seed=42)
    s2 = run_head_to_head(game, KellySizingBot(), RandomBot(), num_hands=400, seed=42)
    assert s1 == s2

    assert s1.wins + s1.losses + s1.ties == 400
    assert s1.win_rate_ci_lower <= s1.win_rate <= s1.win_rate_ci_upper
    assert s1.ev_ci_lower <= s1.ev_per_game <= s1.ev_ci_upper
    assert s1.ev_per_game > 0.0


def test_round_robin_tournaments_zero_sum_and_quant_bots_beat_random() -> None:
    for game in (DiceBettingGame(), OneCardPokerGame()):
        report = run_round_robin_tournament(
            game,
            create_default_bots(),
            hands_per_matchup=500,
            seed=42,
        )
        assert len(report.leaderboard) == 4
        assert len(report.matchups) == 6  # C(4, 2) = 6 pairs

        # Two-player zero-sum invariant: average EV across all bots must equal 0.
        total_ev = sum(entry.ev_per_game for entry in report.leaderboard)
        assert total_ev == pytest.approx(0.0, abs=1e-9)

        by_id = {entry.strategy_id: entry for entry in report.leaderboard}
        assert by_id["kelly"].ev_per_game > by_id["random"].ev_per_game
        assert by_id["ev_max"].ev_per_game > by_id["random"].ev_per_game

    # Sanity check EV-Max directly vs Random
    h2h = run_head_to_head(
        OneCardPokerGame(), EVMaximisingBot(), RandomBot(), num_hands=500, seed=7
    )
    assert h2h.ev_per_game > 0.0
