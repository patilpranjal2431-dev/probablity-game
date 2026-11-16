"""Integration tests for /api/games/tournament and /arena page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_tournament_endpoint_dice_and_card_games(client: TestClient) -> None:
    for game_type in ("dice_betting", "one_card_poker"):
        res = client.post(
            "/api/games/tournament",
            json={"game_type": game_type, "hands_per_matchup": 100, "seed": 42},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["game_type"] == game_type
        assert len(data["leaderboard"]) == 4
        assert len(data["matchups"]) == 6
        assert sum(entry["ev_per_game"] for entry in data["leaderboard"]) == pytest.approx(
            0.0, abs=1e-9
        )


def test_tournament_endpoint_validates_inputs(client: TestClient) -> None:
    bad_game = client.post(
        "/api/games/tournament",
        json={"game_type": "roulette", "hands_per_matchup": 100},
    )
    assert bad_game.status_code == 422

    too_many_hands = client.post(
        "/api/games/tournament",
        json={"game_type": "dice_betting", "hands_per_matchup": 50_000},
    )
    assert too_many_hands.status_code == 422


def test_arena_html_page_serves_successfully(client: TestClient) -> None:
    res = client.get("/arena")
    assert res.status_code == 200
    assert "Bot Tournament Arena" in res.text
