"""FastAPI routes for exact probability calculations and Monte Carlo convergence."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status

from app.quant.bankroll import simulate_bankroll
from app.quant.convergence import (
    QuantProblem,
    run_convergence_analysis,
    run_coverage_test,
)
from app.quant.exact import (
    TOTAL_FIVE_CARD_POKER_HANDS,
    birthday_collision_probability,
    birthday_distinct_probability,
    dice_sum_counts,
    five_card_poker_counts,
    hypergeometric_at_least,
    hypergeometric_distribution,
    hypergeometric_pmf,
)
from app.schemas import (
    BankrollSimRequest,
    BankrollSimResponse,
    BirthdayResponse,
    ConvergenceAndCoverageResponse,
    ConvergencePointSchema,
    ConvergenceRequest,
    CoverageResultSchema,
    DiceOutcomeSchema,
    DiceSumResponse,
    HistogramBinSchema,
    HypergeometricResponse,
    KellyCurvePointSchema,
    PokerDistributionResponse,
    PokerHandEntry,
    TrajectoryPointSchema,
)

router = APIRouter(prefix="/api/quant", tags=["quant"])


@router.get(
    "/exact/dice-sum",
    response_model=DiceSumResponse,
    summary="Compute exact dice sum distribution using dynamic programming",
)
def get_dice_sum_distribution(
    num_dice: int = Query(default=2, ge=1, le=20),
    num_sides: int = Query(default=6, ge=2, le=20),
) -> DiceSumResponse:
    counts = dice_sum_counts(num_dice=num_dice, num_sides=num_sides)
    total_outcomes = num_sides**num_dice
    outcomes = [
        DiceOutcomeSchema(
            total=total,
            count=count,
            probability=count / total_outcomes,
        )
        for total, count in sorted(counts.items())
    ]
    return DiceSumResponse(
        num_dice=num_dice,
        num_sides=num_sides,
        total_outcomes=total_outcomes,
        outcomes=outcomes,
    )


@router.get(
    "/exact/poker",
    response_model=PokerDistributionResponse,
    summary="Return exact combinatorial counts for all 5-card poker hands",
)
def get_five_card_poker_distribution() -> PokerDistributionResponse:
    counts = five_card_poker_counts()
    hands = [
        PokerHandEntry(
            rank=rank.value,
            count=count,
            probability=count / TOTAL_FIVE_CARD_POKER_HANDS,
        )
        for rank, count in counts.items()
    ]
    return PokerDistributionResponse(
        total_hands=TOTAL_FIVE_CARD_POKER_HANDS,
        hands=hands,
    )


@router.get(
    "/exact/hypergeometric",
    response_model=HypergeometricResponse,
    summary="Compute exact Hypergeometric(N, K, n) probabilities",
)
def get_hypergeometric(
    total_pop: int = Query(default=52, alias="N", ge=1, le=1000),
    success_pop: int = Query(default=4, alias="K", ge=0, le=1000),
    draws: int = Query(default=5, alias="n", ge=0, le=1000),
    successes: int = Query(default=1, alias="k", ge=0, le=1000),
) -> HypergeometricResponse:
    try:
        pmf = hypergeometric_pmf(total_pop, success_pop, draws, successes)
        at_least = hypergeometric_at_least(total_pop, success_pop, draws, successes)
        dist = hypergeometric_distribution(total_pop, success_pop, draws)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return HypergeometricResponse(
        total_pop=total_pop,
        success_pop=success_pop,
        draws=draws,
        successes=successes,
        pmf=pmf,
        at_least=at_least,
        distribution=dist,
    )


@router.get(
    "/exact/birthday",
    response_model=BirthdayResponse,
    summary="Compute exact birthday problem collision probability",
)
def get_birthday_probability(
    num_people: int = Query(default=23, ge=0, le=1000),
    num_days: int = Query(default=365, ge=1, le=3660),
) -> BirthdayResponse:
    return BirthdayResponse(
        num_people=num_people,
        num_days=num_days,
        collision_probability=birthday_collision_probability(num_people, num_days),
        distinct_probability=birthday_distinct_probability(num_people, num_days),
    )


@router.post(
    "/convergence",
    response_model=ConvergenceAndCoverageResponse,
    summary="Run seeded Monte Carlo convergence and Wilson 95% CI coverage analysis",
)
def post_convergence_analysis(
    payload: ConvergenceRequest,
) -> ConvergenceAndCoverageResponse:
    try:
        problem = QuantProblem(payload.problem)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported problem {payload.problem!r}.",
        ) from exc

    report = run_convergence_analysis(
        problem,
        payload.sample_sizes,
        seed=payload.seed,
    )
    coverage = run_coverage_test(
        report.exact_probability,
        trials_per_run=payload.trials_per_run,
        num_experiments=payload.num_experiments,
        seed=payload.seed,
    )
    return ConvergenceAndCoverageResponse(
        problem=report.problem,
        label=report.label,
        exact_probability=report.exact_probability,
        seed=report.seed,
        log_log_slope=report.log_log_slope,
        points=[ConvergencePointSchema(**asdict(p)) for p in report.points],
        coverage=CoverageResultSchema(**asdict(coverage)),
    )


@router.post(
    "/bankroll",
    response_model=BankrollSimResponse,
    summary="Run bankroll Kelly & Risk of Ruin simulation",
)
def post_bankroll_simulation(payload: BankrollSimRequest) -> BankrollSimResponse:
    """Compute analytical Kelly sizing, Risk of Ruin, and Monte Carlo distributions."""
    try:
        result = simulate_bankroll(
            initial_bankroll=payload.initial_bankroll,
            win_prob=payload.win_prob,
            payout_odds=payload.payout_odds,
            bet_fraction=payload.bet_fraction,
            sizing_mode=payload.sizing_mode,
            num_bets=payload.num_bets,
            num_paths=payload.num_paths,
            ruin_threshold=payload.ruin_threshold,
            seed=payload.seed,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return BankrollSimResponse(
        initial_bankroll=result.initial_bankroll,
        win_prob=result.win_prob,
        payout_odds=result.payout_odds,
        bet_fraction=result.bet_fraction,
        sizing_mode=result.sizing_mode,
        num_bets=result.num_bets,
        num_paths=result.num_paths,
        ruin_threshold=result.ruin_threshold,
        seed=result.seed,
        full_kelly_fraction=result.full_kelly_fraction,
        half_kelly_fraction=result.half_kelly_fraction,
        expected_edge_per_unit=result.expected_edge_per_unit,
        chosen_log_growth=result.chosen_log_growth,
        optimal_log_growth=result.optimal_log_growth,
        ruined_count=result.ruined_count,
        empirical_risk_of_ruin=result.empirical_risk_of_ruin,
        ruin_ci_lower=result.ruin_ci_lower,
        ruin_ci_upper=result.ruin_ci_upper,
        analytical_risk_of_ruin=result.analytical_risk_of_ruin,
        profit_probability=result.profit_probability,
        mean_terminal=result.mean_terminal,
        median_terminal=result.median_terminal,
        p05_terminal=result.p05_terminal,
        p25_terminal=result.p25_terminal,
        p75_terminal=result.p75_terminal,
        p95_terminal=result.p95_terminal,
        max_terminal=result.max_terminal,
        trajectories=[TrajectoryPointSchema(**asdict(pt)) for pt in result.trajectories],
        histogram=[HistogramBinSchema(**asdict(b)) for b in result.histogram],
        kelly_curve=[KellyCurvePointSchema(**asdict(pt)) for pt in result.kelly_curve],
    )
