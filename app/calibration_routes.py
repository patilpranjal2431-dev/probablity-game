"""Authenticated API routes for the probability calibration game and Brier score tracking."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.games.rng import LiveRNG
from app.models import CalibrationRound, User, utc_now
from app.quant.calibration import (
    compute_brier_score,
    generate_calibration_prompt,
    summarize_calibration_history,
)
from app.schemas import (
    CalibrationBinSchema,
    CalibrationGuessRequest,
    CalibrationHistoryResponse,
    CalibrationPointSchema,
    CalibrationPromptPublic,
    CalibrationRoundResult,
)

router = APIRouter(prefix="/api/calibration", tags=["calibration"])

_LIVE_RNG = LiveRNG()


def _to_public_prompt(row: CalibrationRound) -> CalibrationPromptPublic:
    return CalibrationPromptPublic(
        id=row.id,
        category=row.category,
        question_text=row.question_text,
        created_at=row.created_at,
    )


def _to_round_result(row: CalibrationRound) -> CalibrationRoundResult:
    if row.estimated_prob is None or row.brier_score is None or row.answered_at is None:
        raise ValueError("Cannot serialize unanswered CalibrationRound as result.")
    return CalibrationRoundResult(
        id=row.id,
        category=row.category,
        question_text=row.question_text,
        estimated_prob=row.estimated_prob,
        true_probability=row.true_probability,
        actual_outcome=row.actual_outcome,
        brier_score=row.brier_score,
        explanation=row.explanation,
        answered_at=row.answered_at,
    )


@router.post(
    "/prompts",
    response_model=CalibrationPromptPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Fetch or generate the current unanswered calibration prompt",
)
def create_or_get_prompt(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CalibrationPromptPublic:
    """Return an active unanswered prompt or deal a fresh server-generated scenario."""
    existing = db.scalar(
        select(CalibrationRound)
        .where(
            CalibrationRound.user_id == current_user.id,
            CalibrationRound.answered_at.is_(None),
        )
        .order_by(CalibrationRound.id.desc())
    )
    if existing is not None:
        return _to_public_prompt(existing)

    generated = generate_calibration_prompt(_LIVE_RNG)
    row = CalibrationRound(
        user_id=current_user.id,
        category=generated.category,
        question_text=generated.question_text,
        true_probability=generated.true_probability,
        actual_outcome=generated.actual_outcome,
        explanation=generated.explanation,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_public_prompt(row)


@router.post(
    "/prompts/{prompt_id}/guess",
    response_model=CalibrationRoundResult,
    summary="Submit a probability estimate in [0, 1] and score Brier error",
)
def submit_calibration_guess(
    prompt_id: int,
    payload: CalibrationGuessRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CalibrationRoundResult:
    """Grade ``payload.estimated_prob`` against the hidden server outcome."""
    row = db.get(CalibrationRound, prompt_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calibration prompt not found.",
        )
    if row.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot answer another user's calibration prompt.",
        )
    if row.answered_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This calibration prompt has already been answered.",
        )

    brier = compute_brier_score(payload.estimated_prob, row.actual_outcome)
    row.estimated_prob = payload.estimated_prob
    row.brier_score = round(brier, 6)
    row.answered_at = utc_now()
    db.commit()
    db.refresh(row)
    return _to_round_result(row)


@router.get(
    "/history",
    response_model=CalibrationHistoryResponse,
    summary="Fetch cumulative Brier scores over time and reliability curve",
)
def get_calibration_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
) -> CalibrationHistoryResponse:
    """Return pending prompt, chronological Brier series, and calibration bins."""
    pending = db.scalar(
        select(CalibrationRound)
        .where(
            CalibrationRound.user_id == current_user.id,
            CalibrationRound.answered_at.is_(None),
        )
        .order_by(CalibrationRound.id.desc())
    )

    answered = list(
        db.scalars(
            select(CalibrationRound)
            .where(
                CalibrationRound.user_id == current_user.id,
                CalibrationRound.answered_at.is_not(None),
            )
            .order_by(CalibrationRound.id.asc())
        )
    )

    tuples = [
        (
            r.id,
            r.category,
            float(r.estimated_prob or 0.0),
            r.true_probability,
            r.actual_outcome,
            float(r.brier_score or 0.0),
        )
        for r in answered
    ]
    mean_brier, mean_abs_err, points, bins = summarize_calibration_history(tuples)
    recent_rows = list(reversed(answered[-limit:]))

    return CalibrationHistoryResponse(
        pending_prompt=_to_public_prompt(pending) if pending is not None else None,
        rounds_answered=len(answered),
        mean_brier_score=mean_brier,
        mean_abs_prob_error=mean_abs_err,
        points=[CalibrationPointSchema(**asdict(p)) for p in points],
        bins=[CalibrationBinSchema(**asdict(b)) for b in bins],
        recent_rounds=[_to_round_result(r) for r in recent_rows],
    )
