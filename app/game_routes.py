"""FastAPI routes for running seeded bot-vs-bot tournaments."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from app.games.bots import create_default_bots
from app.games.card_game import OneCardPokerGame
from app.games.dice_game import DiceBettingGame
from app.games.engine import HeadsUpGame
from app.games.tournament import run_round_robin_tournament
from app.schemas import (
    LeaderboardEntrySchema,
    MatchupStatsSchema,
    TournamentRequest,
    TournamentResponse,
)

router = APIRouter(prefix="/api/games", tags=["games"])


def _resolve_game(game_type: str) -> HeadsUpGame:
    if game_type == "dice_betting":
        return DiceBettingGame()
    if game_type == "one_card_poker":
        return OneCardPokerGame()
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported game_type {game_type!r}. Use 'dice_betting' or 'one_card_poker'.",
    )


@router.post(
    "/tournament",
    response_model=TournamentResponse,
    summary="Run a seeded round-robin tournament across all four Edge Lab bots",
)
def post_bot_tournament(payload: TournamentRequest) -> TournamentResponse:
    game = _resolve_game(payload.game_type)
    report = run_round_robin_tournament(
        game,
        create_default_bots(),
        hands_per_matchup=payload.hands_per_matchup,
        seed=payload.seed,
        starting_stack=payload.starting_stack,
    )
    return TournamentResponse(
        game_type=report.game_type,
        hands_per_matchup=report.hands_per_matchup,
        starting_stack=report.starting_stack,
        seed=report.seed,
        leaderboard=[LeaderboardEntrySchema(**asdict(entry)) for entry in report.leaderboard],
        matchups=[MatchupStatsSchema(**asdict(m)) for m in report.matchups],
    )
