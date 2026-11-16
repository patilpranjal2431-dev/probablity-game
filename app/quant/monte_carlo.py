"""Seeded Monte Carlo probability estimators with Wilson confidence intervals."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from app.quant.exact import PokerHandRank, classify_five_card_hand

Z_95 = 1.959963984540054


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    """Confidence interval bounds for a binomial proportion."""

    lower: float
    upper: float
    z: float


@dataclass(frozen=True, slots=True)
class MonteCarloEstimate:
    """Reproducible seeded Monte Carlo probability estimate with Wilson 95% CI."""

    trials: int
    successes: int
    estimate: float
    ci_lower: float
    ci_upper: float
    seed: int


def wilson_confidence_interval(
    successes: int,
    trials: int,
    *,
    z: float = Z_95,
) -> ConfidenceInterval:
    """Compute the Wilson score confidence interval for a binomial proportion."""
    if trials < 1:
        raise ValueError("trials must be >= 1.")
    if successes < 0 or successes > trials:
        raise ValueError("successes must satisfy 0 <= successes <= trials.")
    if z <= 0:
        raise ValueError("z must be positive.")

    p_hat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (p_hat + z2 / (2.0 * trials)) / denom
    margin = (
        z
        * math.sqrt((p_hat * (1.0 - p_hat) / trials) + (z2 / (4.0 * trials * trials)))
        / denom
    )
    return ConfidenceInterval(
        lower=0.0 if successes == 0 else max(0.0, center - margin),
        upper=1.0 if successes == trials else min(1.0, center + margin),
        z=z,
    )


def estimate_bernoulli_probability(
    trial_fn: Callable[[random.Random], bool],
    trials: int,
    *,
    seed: int,
    z: float = Z_95,
) -> MonteCarloEstimate:
    """Run ``trials`` seeded simulations of ``trial_fn`` and return estimate + Wilson CI."""
    if trials < 1:
        raise ValueError("trials must be >= 1.")

    rng = random.Random(seed)
    successes = 0
    for _ in range(trials):
        if trial_fn(rng):
            successes += 1

    ci = wilson_confidence_interval(successes, trials, z=z)
    return MonteCarloEstimate(
        trials=trials,
        successes=successes,
        estimate=successes / trials,
        ci_lower=ci.lower,
        ci_upper=ci.upper,
        seed=seed,
    )


def simulate_dice_sum_probability(
    num_dice: int,
    target_sum: int,
    trials: int,
    *,
    seed: int,
    num_sides: int = 6,
) -> MonteCarloEstimate:
    """Estimate P(sum of num_dice == target_sum) via seeded Monte Carlo."""
    if num_dice < 1 or num_sides < 2:
        raise ValueError("num_dice must be >= 1 and num_sides >= 2.")

    def trial(rng: random.Random) -> bool:
        total = 0
        for _ in range(num_dice):
            total += rng.randint(1, num_sides)
        return total == target_sum

    return estimate_bernoulli_probability(trial, trials, seed=seed)


def simulate_birthday_collision(
    num_people: int,
    trials: int,
    *,
    seed: int,
    num_days: int = 365,
) -> MonteCarloEstimate:
    """Estimate P(at least one shared birthday) via seeded Monte Carlo."""
    if num_people < 0 or num_days < 1:
        raise ValueError("num_people must be >= 0 and num_days >= 1.")

    def trial(rng: random.Random) -> bool:
        seen: set[int] = set()
        for _ in range(num_people):
            day = rng.randrange(num_days)
            if day in seen:
                return True
            seen.add(day)
        return False

    return estimate_bernoulli_probability(trial, trials, seed=seed)


def simulate_hypergeometric_at_least(
    total_pop: int,
    success_pop: int,
    draws: int,
    min_successes: int,
    trials: int,
    *,
    seed: int,
) -> MonteCarloEstimate:
    """Estimate Hypergeometric P(X >= min_successes) via seeded Monte Carlo."""
    if total_pop < 1 or not (0 <= success_pop <= total_pop) or not (0 <= draws <= total_pop):
        raise ValueError("Invalid hypergeometric population/draw parameters.")
    if min_successes < 0 or min_successes > draws:
        raise ValueError("min_successes must satisfy 0 <= min_successes <= draws.")

    population = range(total_pop)

    def trial(rng: random.Random) -> bool:
        sample = rng.sample(population, draws)
        hits = sum(1 for item in sample if item < success_pop)
        return hits >= min_successes

    return estimate_bernoulli_probability(trial, trials, seed=seed)


def simulate_five_card_poker_hand(
    target_hand: PokerHandRank,
    trials: int,
    *,
    seed: int,
) -> MonteCarloEstimate:
    """Estimate 5-card poker hand probability via seeded Monte Carlo."""
    deck = range(52)

    def trial(rng: random.Random) -> bool:
        hand = rng.sample(deck, 5)
        return classify_five_card_hand(hand) == target_hand

    return estimate_bernoulli_probability(trial, trials, seed=seed)
