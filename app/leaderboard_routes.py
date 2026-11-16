"""API routes for Skill (Cumulative EV) vs Coins leaderboards and personal decision grades."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import DecisionGrade, Transaction, TransactionType, User, Wallet
from app.schemas import (
    CoinsLeaderboardEntry,
    DecisionGradePublic,
    DecisionHistoryResponse,
    LeaderboardsResponse,
    SkillLeaderboardEntry,
)

router = APIRouter(prefix="/api", tags=["leaderboard"])

OPTIMAL_REGRET_EPS = 1e-6


@router.get(
    "/leaderboards",
    response_model=LeaderboardsResponse,
    summary="Fetch separate Skill (Cumulative EV) and Coins (Luck + Skill) leaderboards",
)
def get_leaderboards(
    db: Annotated[Session, Depends(get_db)],
    include_bots: Annotated[bool, Query()] = False,
) -> LeaderboardsResponse:
    """Return dual leaderboards ranking players by Cumulative EV vs Coin Balance."""
    user_stmt = select(User, Wallet).join(Wallet, Wallet.user_id == User.id)
    if not include_bots:
        user_stmt = user_stmt.where(User.is_bot.is_(False))
    user_rows = db.execute(user_stmt).all()

    grade_rows = db.execute(
        select(
            DecisionGrade.user_id,
            func.coalesce(func.sum(DecisionGrade.taken_ev), 0.0).label("cumulative_ev"),
            func.coalesce(func.sum(DecisionGrade.best_ev), 0.0).label("total_best_ev"),
            func.coalesce(func.sum(DecisionGrade.regret), 0.0).label("total_regret"),
            func.count(DecisionGrade.id).label("decisions_count"),
            func.count(func.distinct(DecisionGrade.hand_id)).label("hands_played"),
            func.coalesce(
                func.sum(case((DecisionGrade.regret <= OPTIMAL_REGRET_EPS, 1), else_=0)),
                0,
            ).label("optimal_count"),
        ).group_by(DecisionGrade.user_id)
    ).all()
    grades_by_user = {row.user_id: row for row in grade_rows}

    game_tx_types = (
        TransactionType.WAGER.value,
        TransactionType.PAYOUT.value,
        TransactionType.REFUND.value,
    )
    profit_rows = db.execute(
        select(
            Wallet.user_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("net_profit"),
        )
        .join(Transaction, Transaction.wallet_id == Wallet.id)
        .where(Transaction.tx_type.in_(game_tx_types))
        .group_by(Wallet.user_id)
    ).all()
    profit_by_user = {row.user_id: int(row.net_profit) for row in profit_rows}

    player_stats: list[dict] = []
    for user, wallet in user_rows:
        g = grades_by_user.get(user.id)
        decisions_count = int(g.decisions_count) if g is not None else 0
        hands_played = int(g.hands_played) if g is not None else 0
        cumulative_ev = round(float(g.cumulative_ev), 4) if g is not None else 0.0
        total_best_ev = round(float(g.total_best_ev), 4) if g is not None else 0.0
        total_regret = round(float(g.total_regret), 4) if g is not None else 0.0
        optimal_count = int(g.optimal_count) if g is not None else 0
        mean_regret = round(total_regret / decisions_count, 4) if decisions_count > 0 else 0.0
        optimal_rate = round(optimal_count / decisions_count, 4) if decisions_count > 0 else 0.0

        player_stats.append(
            {
                "user_id": user.id,
                "username": user.username,
                "is_bot": user.is_bot,
                "cumulative_ev": cumulative_ev,
                "total_best_ev": total_best_ev,
                "total_regret": total_regret,
                "mean_regret": mean_regret,
                "optimal_rate": optimal_rate,
                "decisions_count": decisions_count,
                "hands_played": hands_played,
                "coin_balance": wallet.balance,
                "net_coin_profit": profit_by_user.get(user.id, 0),
            }
        )

    skill_sorted = sorted(
        player_stats,
        key=lambda item: (
            item["decisions_count"] == 0,
            -item["cumulative_ev"],
            item["total_regret"],
            item["username"].lower(),
        ),
    )
    skill_leaderboard = [
        SkillLeaderboardEntry(rank=idx, **item)
        for idx, item in enumerate(skill_sorted, start=1)
    ]

    coins_sorted = sorted(
        player_stats,
        key=lambda item: (
            -item["coin_balance"],
            -item["net_coin_profit"],
            item["username"].lower(),
        ),
    )
    coins_leaderboard = [
        CoinsLeaderboardEntry(
            rank=idx,
            user_id=item["user_id"],
            username=item["username"],
            is_bot=item["is_bot"],
            coin_balance=item["coin_balance"],
            net_coin_profit=item["net_coin_profit"],
            cumulative_ev=item["cumulative_ev"],
            total_regret=item["total_regret"],
            hands_played=item["hands_played"],
        )
        for idx, item in enumerate(coins_sorted, start=1)
    ]

    return LeaderboardsResponse(
        include_bots=include_bots,
        skill_leaderboard=skill_leaderboard,
        coins_leaderboard=coins_leaderboard,
    )


@router.get(
    "/decisions/me",
    response_model=DecisionHistoryResponse,
    summary="Fetch the authenticated player's EV decision grades and regret summary",
)
def get_my_decisions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DecisionHistoryResponse:
    """Return cumulative EV/regret stats and recent graded decisions for ``current_user``."""
    agg = db.execute(
        select(
            func.coalesce(func.sum(DecisionGrade.taken_ev), 0.0).label("cumulative_ev"),
            func.coalesce(func.sum(DecisionGrade.best_ev), 0.0).label("total_best_ev"),
            func.coalesce(func.sum(DecisionGrade.regret), 0.0).label("total_regret"),
            func.count(DecisionGrade.id).label("decisions_count"),
            func.count(func.distinct(DecisionGrade.hand_id)).label("hands_played"),
            func.coalesce(
                func.sum(case((DecisionGrade.regret <= OPTIMAL_REGRET_EPS, 1), else_=0)),
                0,
            ).label("optimal_count"),
        ).where(DecisionGrade.user_id == current_user.id)
    ).one()

    decisions_count = int(agg.decisions_count)
    optimal_rate = (
        round(int(agg.optimal_count) / decisions_count, 4) if decisions_count > 0 else 0.0
    )

    rows = list(
        db.scalars(
            select(DecisionGrade)
            .where(DecisionGrade.user_id == current_user.id)
            .order_by(DecisionGrade.id.desc())
            .limit(limit)
        )
    )

    return DecisionHistoryResponse(
        cumulative_ev=round(float(agg.cumulative_ev), 4),
        total_best_ev=round(float(agg.total_best_ev), 4),
        total_regret=round(float(agg.total_regret), 4),
        optimal_rate=optimal_rate,
        decisions_count=decisions_count,
        hands_played=int(agg.hands_played),
        decisions=[DecisionGradePublic.model_validate(row) for row in rows],
    )
