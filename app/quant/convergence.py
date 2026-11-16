"""Convergence analysis (error vs n with 1/sqrt(n) reference) and CI coverage tests."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

from app.quant.exact import (
    PokerHandRank,
    birthday_collision_probability,
    dice_sum_distribution,
    five_card_poker_probabilities,
    hypergeometric_at_least,
)
from app.quant.monte_carlo import (
    Z_95,
    MonteCarloEstimate,
    simulate_birthday_collision,
    simulate_dice_sum_probability,
    simulate_five_card_poker_hand,
    simulate_hypergeometric_at_least,
    wilson_confidence_interval,
)


class QuantProblem(str, Enum):
    """Supported benchmark problems for convergence and coverage analysis."""

    BIRTHDAY_23 = "birthday_23"
    DICE_2D6_SUM_7 = "dice_2d6_sum_7"
    HYPERGEOMETRIC_ACE = "hypergeometric_ace"
    POKER_ONE_PAIR = "poker_one_pair"


DEFAULT_SAMPLE_SIZES: tuple[int, ...] = (50, 100, 250, 500, 1000, 2500, 5000, 10000)


@dataclass(frozen=True, slots=True)
class ConvergencePoint:
    """Single sample-size observation in a convergence sweep."""

    n: int
    estimate: float
    abs_error: float
    ci_lower: float
    ci_upper: float
    inv_sqrt_n: float
    se_reference: float


@dataclass(frozen=True, slots=True)
class ConvergenceReport:
    """Full convergence sweep comparing Monte Carlo error against 1/sqrt(n)."""

    problem: str
    label: str
    exact_probability: float
    seed: int
    log_log_slope: float | None
    points: list[ConvergencePoint]


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """Empirical coverage rate of repeated Wilson confidence intervals."""

    exact_probability: float
    trials_per_run: int
    num_experiments: int
    covered_count: int
    empirical_coverage: float
    nominal_coverage: float
    mean_ci_width: float
    seed: int


def get_problem_metadata(problem: QuantProblem) -> tuple[str, float]:
    """Return (human_label, exact_probability) for a benchmark problem."""
    if problem == QuantProblem.BIRTHDAY_23:
        return (
            "Birthday Collision (23 people, 365 days)",
            birthday_collision_probability(23, 365),
        )
    if problem == QuantProblem.DICE_2D6_SUM_7:
        return ("2d6 Sum == 7 (DP exact)", dice_sum_distribution(2, 6)[7])
    if problem == QuantProblem.HYPERGEOMETRIC_ACE:
        return (
            "At least 1 Ace in 5-card draw (Hypergeometric)",
            hypergeometric_at_least(52, 4, 5, 1),
        )
    if problem == QuantProblem.POKER_ONE_PAIR:
        return (
            "5-Card Poker: One Pair",
            five_card_poker_probabilities()[PokerHandRank.ONE_PAIR],
        )
    raise ValueError(f"Unsupported problem: {problem!r}")


def _simulate_problem(problem: QuantProblem, n: int, seed: int) -> MonteCarloEstimate:
    if problem == QuantProblem.BIRTHDAY_23:
        return simulate_birthday_collision(23, n, seed=seed, num_days=365)
    if problem == QuantProblem.DICE_2D6_SUM_7:
        return simulate_dice_sum_probability(2, 7, n, seed=seed, num_sides=6)
    if problem == QuantProblem.HYPERGEOMETRIC_ACE:
        return simulate_hypergeometric_at_least(52, 4, 5, 1, n, seed=seed)
    if problem == QuantProblem.POKER_ONE_PAIR:
        return simulate_five_card_poker_hand(PokerHandRank.ONE_PAIR, n, seed=seed)
    raise ValueError(f"Unsupported problem: {problem!r}")


def _estimate_log_log_slope(points: list[ConvergencePoint]) -> float | None:
    """Fit slope of log10(abs_error) ~ beta * log10(n) for non-zero errors."""
    valid = [(math.log10(p.n), math.log10(p.abs_error)) for p in points if p.abs_error > 0]
    if len(valid) < 2:
        return None
    mean_x = sum(x for x, _ in valid) / len(valid)
    mean_y = sum(y for _, y in valid) / len(valid)
    denom = sum((x - mean_x) ** 2 for x, _ in valid)
    if denom == 0:
        return None
    numer = sum((x - mean_x) * (y - mean_y) for x, y in valid)
    return numer / denom


def run_convergence_analysis(
    problem: QuantProblem,
    sample_sizes: list[int] | tuple[int, ...] = DEFAULT_SAMPLE_SIZES,
    *,
    seed: int = 42,
) -> ConvergenceReport:
    """Measure |estimate - exact| across sample sizes alongside a 1/sqrt(n) reference."""
    if not sample_sizes:
        raise ValueError("sample_sizes must not be empty.")
    sorted_sizes = sorted(set(sample_sizes))
    if any(n < 1 for n in sorted_sizes):
        raise ValueError("All sample sizes must be >= 1.")

    label, exact_prob = get_problem_metadata(problem)
    points: list[ConvergencePoint] = []
    for idx, n in enumerate(sorted_sizes):
        sim = _simulate_problem(problem, n, seed + idx)
        abs_error = abs(sim.estimate - exact_prob)
        inv_sqrt_n = 1.0 / math.sqrt(n)
        se_reference = math.sqrt(exact_prob * (1.0 - exact_prob) / n)
        points.append(
            ConvergencePoint(
                n=n,
                estimate=sim.estimate,
                abs_error=abs_error,
                ci_lower=sim.ci_lower,
                ci_upper=sim.ci_upper,
                inv_sqrt_n=inv_sqrt_n,
                se_reference=se_reference,
            )
        )

    return ConvergenceReport(
        problem=problem.value,
        label=label,
        exact_probability=exact_prob,
        seed=seed,
        log_log_slope=_estimate_log_log_slope(points),
        points=points,
    )


def run_coverage_test(
    exact_probability: float,
    *,
    trials_per_run: int = 400,
    num_experiments: int = 200,
    seed: int = 42,
    z: float = Z_95,
    nominal_coverage: float = 0.95,
) -> CoverageResult:
    """Verify empirical coverage of Wilson confidence intervals against a known probability."""
    if not (0.0 <= exact_probability <= 1.0):
        raise ValueError("exact_probability must be in [0, 1].")
    if trials_per_run < 1 or num_experiments < 1:
        raise ValueError("trials_per_run and num_experiments must be >= 1.")

    rng = random.Random(seed)
    covered_count = 0
    total_width = 0.0

    for _ in range(num_experiments):
        # Fast exact Bernoulli sum for binomial(trials_per_run, exact_probability).
        successes = 0
        for _ in range(trials_per_run):
            if rng.random() < exact_probability:
                successes += 1

        ci = wilson_confidence_interval(successes, trials_per_run, z=z)
        if ci.lower <= exact_probability <= ci.upper:
            covered_count += 1
        total_width += ci.upper - ci.lower

    return CoverageResult(
        exact_probability=exact_probability,
        trials_per_run=trials_per_run,
        num_experiments=num_experiments,
        covered_count=covered_count,
        empirical_coverage=covered_count / num_experiments,
        nominal_coverage=nominal_coverage,
        mean_ci_width=total_width / num_experiments,
        seed=seed,
    )
