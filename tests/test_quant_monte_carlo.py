"""Unit tests for seeded Monte Carlo estimators and Wilson 95% confidence intervals."""

from __future__ import annotations

import pytest

from app.quant.exact import (
    PokerHandRank,
    birthday_collision_probability,
    dice_sum_distribution,
    five_card_poker_probabilities,
    hypergeometric_at_least,
)
from app.quant.monte_carlo import (
    simulate_birthday_collision,
    simulate_dice_sum_probability,
    simulate_five_card_poker_hand,
    simulate_hypergeometric_at_least,
    wilson_confidence_interval,
)


def test_wilson_confidence_interval_properties_and_edge_cases() -> None:
    ci_mid = wilson_confidence_interval(50, 100)
    assert ci_mid.lower < 0.5 < ci_mid.upper
    assert (ci_mid.lower + ci_mid.upper) / 2 == pytest.approx(0.5)
    assert ci_mid.lower == pytest.approx(0.4038315, abs=1e-5)
    assert ci_mid.upper == pytest.approx(0.5961685, abs=1e-5)

    ci_zero = wilson_confidence_interval(0, 100)
    assert ci_zero.lower == 0.0
    assert 0.0 < ci_zero.upper < 0.05

    ci_one = wilson_confidence_interval(100, 100)
    assert ci_one.upper == 1.0
    assert 0.95 < ci_one.lower < 1.0

    with pytest.raises(ValueError):
        wilson_confidence_interval(10, 0)
    with pytest.raises(ValueError):
        wilson_confidence_interval(11, 10)


def test_seeded_monte_carlo_is_reproducible() -> None:
    run1 = simulate_birthday_collision(23, 2_000, seed=12345)
    run2 = simulate_birthday_collision(23, 2_000, seed=12345)
    assert run1 == run2


def test_monte_carlo_estimates_match_exact_probabilities_within_ci() -> None:
    exact_2d6 = dice_sum_distribution(2, 6)[7]
    mc_2d6 = simulate_dice_sum_probability(2, 7, 10_000, seed=42)
    assert mc_2d6.ci_lower <= exact_2d6 <= mc_2d6.ci_upper

    exact_bday = birthday_collision_probability(23, 365)
    mc_bday = simulate_birthday_collision(23, 10_000, seed=42)
    assert mc_bday.ci_lower <= exact_bday <= mc_bday.ci_upper

    exact_hyper = hypergeometric_at_least(52, 4, 5, 1)
    mc_hyper = simulate_hypergeometric_at_least(52, 4, 5, 1, 10_000, seed=42)
    assert mc_hyper.ci_lower <= exact_hyper <= mc_hyper.ci_upper

    exact_pair = five_card_poker_probabilities()[PokerHandRank.ONE_PAIR]
    mc_pair = simulate_five_card_poker_hand(PokerHandRank.ONE_PAIR, 10_000, seed=42)
    assert mc_pair.ci_lower <= exact_pair <= mc_pair.ci_upper
