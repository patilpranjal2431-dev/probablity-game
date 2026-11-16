"""Authenticated API routes for the market-making Order Book simulation."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.games.order_book import (
    RoundSnapshot,
    SimulatedFill,
    build_book_snapshot,
    compute_post_game_analysis,
    evolve_fair_value,
    generate_initial_market,
    simulate_quote_round,
)
from app.games.rng import LiveRNG
from app.models import OrderBookSession, User, utc_now
from app.schemas import (
    CreateOrderBookRequest,
    OrderBookAnalysisSchema,
    OrderBookFillAnalysis,
    OrderBookFillPublic,
    OrderBookLevelSchema,
    OrderBookRoundAnalysis,
    OrderBookRoundPublic,
    OrderBookSessionResponse,
    OrderBookSessionSummary,
    QuoteRequest,
)

router = APIRouter(prefix="/api/orderbook", tags=["orderbook"])

_LIVE_RNG = LiveRNG()


def _deserialize_rounds(rounds_json: str) -> list[RoundSnapshot]:
    raw_list = json.loads(rounds_json) if rounds_json else []
    rounds: list[RoundSnapshot] = []
    for r in raw_list:
        fills = [SimulatedFill(**f) for f in r.get("fills", [])]
        rounds.append(
            RoundSnapshot(
                round_number=r["round_number"],
                fair_value=r["fair_value"],
                public_signal=r["public_signal"],
                bid_price=r["bid_price"],
                ask_price=r["ask_price"],
                quote_size=r["quote_size"],
                cash_after=r["cash_after"],
                inventory_after=r["inventory_after"],
                mtm_pnl_after=r["mtm_pnl_after"],
                inventory_drift_step=r["inventory_drift_step"],
                fills=fills,
            )
        )
    return rounds


def _serialize_session(row: OrderBookSession) -> OrderBookSessionResponse:
    rounds = _deserialize_rounds(row.rounds_json)
    last_round = rounds[-1] if rounds else None

    book_levels = build_book_snapshot(
        public_signal=row.latest_public_signal,
        bid_price=last_round.bid_price if last_round else None,
        ask_price=last_round.ask_price if last_round else None,
        quote_size=last_round.quote_size if last_round else None,
    )

    public_rounds = [
        OrderBookRoundPublic(
            round_number=r.round_number,
            public_signal=r.public_signal,
            bid_price=r.bid_price,
            ask_price=r.ask_price,
            quote_size=r.quote_size,
            cash_after=r.cash_after,
            inventory_after=r.inventory_after,
            fills=[
                OrderBookFillPublic(
                    round_number=f.round_number,
                    side=f.side,
                    price=f.price,
                    quantity=f.quantity,
                )
                for f in r.fills
            ],
        )
        for r in rounds
    ]

    analysis_schema: OrderBookAnalysisSchema | None = None
    if row.status == "completed":
        analysis = compute_post_game_analysis(
            initial_fair_value=row.initial_fair_value,
            rounds=rounds,
        )
        analysis_schema = OrderBookAnalysisSchema(
            initial_fair_value=analysis.initial_fair_value,
            terminal_fair_value=analysis.terminal_fair_value,
            total_pnl=analysis.total_pnl,
            spread_captured=analysis.spread_captured,
            adverse_selection_cost=analysis.adverse_selection_cost,
            inventory_drift_pnl=analysis.inventory_drift_pnl,
            final_cash=analysis.final_cash,
            final_inventory=analysis.final_inventory,
            max_abs_inventory=analysis.max_abs_inventory,
            total_fills=analysis.total_fills,
            total_volume=analysis.total_volume,
            informed_fills=analysis.informed_fills,
            informed_volume=analysis.informed_volume,
            informed_volume_share=analysis.informed_volume_share,
            avg_quoted_spread=analysis.avg_quoted_spread,
            rounds=[
                OrderBookRoundAnalysis(
                    round_number=r.round_number,
                    fair_value=r.fair_value,
                    public_signal=r.public_signal,
                    bid_price=r.bid_price,
                    ask_price=r.ask_price,
                    quote_size=r.quote_size,
                    cash_after=r.cash_after,
                    inventory_after=r.inventory_after,
                    mtm_pnl_after=r.mtm_pnl_after,
                    inventory_drift_step=r.inventory_drift_step,
                    fills=[
                        OrderBookFillAnalysis(
                            round_number=f.round_number,
                            side=f.side,
                            price=f.price,
                            quantity=f.quantity,
                            bot_kind=f.bot_kind,
                            fair_value=f.fair_value,
                            spread_captured=f.spread_captured,
                            adverse_selection=f.adverse_selection,
                            net_edge=f.net_edge,
                        )
                        for f in r.fills
                    ],
                )
                for r in analysis.rounds
            ],
        )

    return OrderBookSessionResponse(
        id=row.id,
        status="completed" if row.status == "completed" else "active",
        num_rounds=row.num_rounds,
        current_round=row.current_round,
        max_inventory=row.max_inventory,
        fundamental_volatility=row.fundamental_volatility,
        latest_public_signal=row.latest_public_signal,
        cash=round(row.cash, 2),
        inventory=row.inventory,
        book_levels=[OrderBookLevelSchema(**asdict(lvl)) for lvl in book_levels],
        rounds=public_rounds,
        analysis=analysis_schema,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _get_owned_session(db: Session, session_id: int, user_id: int) -> OrderBookSession:
    row = db.get(OrderBookSession, session_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order book session not found.",
        )
    if row.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this order book session.",
        )
    return row


def _finalize_session(row: OrderBookSession, rounds: list[RoundSnapshot]) -> None:
    analysis = compute_post_game_analysis(
        initial_fair_value=row.initial_fair_value,
        rounds=rounds,
    )
    row.status = "completed"
    row.total_pnl = analysis.total_pnl
    row.spread_captured = analysis.spread_captured
    row.adverse_selection_cost = analysis.adverse_selection_cost
    row.inventory_drift_pnl = analysis.inventory_drift_pnl
    row.completed_at = utc_now()


@router.get(
    "/sessions",
    response_model=list[OrderBookSessionSummary],
    summary="List the authenticated user's order book simulation sessions",
)
def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[OrderBookSessionSummary]:
    rows = list(
        db.scalars(
            select(OrderBookSession)
            .where(OrderBookSession.user_id == current_user.id)
            .order_by(OrderBookSession.id.desc())
            .limit(20)
        )
    )
    return [
        OrderBookSessionSummary(
            id=r.id,
            status=r.status,
            num_rounds=r.num_rounds,
            current_round=r.current_round,
            inventory=r.inventory,
            total_pnl=r.total_pnl,
            spread_captured=r.spread_captured,
            adverse_selection_cost=r.adverse_selection_cost,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/sessions",
    response_model=OrderBookSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new market-making order book simulation around a hidden fair value",
)
def create_session(
    payload: CreateOrderBookRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrderBookSessionResponse:
    initial_fair, public_signal = generate_initial_market(_LIVE_RNG)
    row = OrderBookSession(
        user_id=current_user.id,
        status="active",
        num_rounds=payload.num_rounds,
        current_round=0,
        max_inventory=payload.max_inventory,
        fundamental_volatility=payload.fundamental_volatility,
        initial_fair_value=initial_fair,
        current_fair_value=initial_fair,
        latest_public_signal=public_signal,
        cash=0.0,
        inventory=0,
        rounds_json="[]",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_session(row)


@router.get(
    "/sessions/{session_id}",
    response_model=OrderBookSessionResponse,
    summary="Fetch order book session state (post-game analysis revealed only when completed)",
)
def get_session(
    session_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrderBookSessionResponse:
    row = _get_owned_session(db, session_id, current_user.id)
    return _serialize_session(row)


@router.post(
    "/sessions/{session_id}/quote",
    response_model=OrderBookSessionResponse,
    summary="Submit bid/ask quotes for the next round of bot order flow",
)
def submit_quote(
    session_id: int,
    payload: QuoteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrderBookSessionResponse:
    row = _get_owned_session(db, session_id, current_user.id)
    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order book session is already completed.",
        )

    rounds = _deserialize_rounds(row.rounds_json)
    next_round_num = row.current_round + 1
    prev_fair = row.current_fair_value

    if next_round_num == 1:
        curr_fair = prev_fair
        next_signal = row.latest_public_signal
    else:
        curr_fair, next_signal = evolve_fair_value(
            prev_fair,
            _LIVE_RNG,
            volatility=row.fundamental_volatility,
        )

    snapshot = simulate_quote_round(
        round_number=next_round_num,
        prev_fair_value=prev_fair,
        curr_fair_value=curr_fair,
        public_signal=next_signal,
        bid_price=payload.bid_price,
        ask_price=payload.ask_price,
        quote_size=payload.quote_size,
        cash_before=row.cash,
        inventory_before=row.inventory,
        max_inventory=row.max_inventory,
        rng=_LIVE_RNG,
    )
    rounds.append(snapshot)

    row.current_round = next_round_num
    row.current_fair_value = curr_fair
    row.latest_public_signal = next_signal
    row.cash = snapshot.cash_after
    row.inventory = snapshot.inventory_after
    row.rounds_json = json.dumps([asdict(r) for r in rounds])

    if next_round_num >= row.num_rounds:
        _finalize_session(row, rounds)

    db.commit()
    db.refresh(row)
    return _serialize_session(row)


@router.post(
    "/sessions/{session_id}/finish",
    response_model=OrderBookSessionResponse,
    summary="Close the active order book session early and reveal post-game analysis",
)
def finish_session(
    session_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrderBookSessionResponse:
    row = _get_owned_session(db, session_id, current_user.id)
    if row.status != "completed":
        rounds = _deserialize_rounds(row.rounds_json)
        _finalize_session(row, rounds)
        db.commit()
        db.refresh(row)
    return _serialize_session(row)
