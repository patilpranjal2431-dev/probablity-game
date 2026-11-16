"""Unit tests for Monte Carlo convergence analysis and Wilson CI coverage."""

from __future__ import annotations

import math

import pytest

from app.quant.convergence import (
    QuantProblem,
    run_convergence_analysis,
    run_coverage_test,
)
from app.quant.exact import birthday_collision_probability, dice_sum_distribution


def test_convergence_analysis_error_scaling_and_reference_line() -> None:
    report = run_convergence_analysis(
        QuantProblem.BIRTHDAY_23,
        sample_sizes=[50, 200, 1000, 5000, 20000],
        seed=7,
    )
    assert report.exact_probability == pytest.approx(birthday_collision_probability(23, 365))
    assert [p.n for p in report.points] == [50, 200, 1000, 5000, 20000]

    for pt in report.points:
        assert pt.inv_sqrt_n == pytest.approx(1.0 / math.sqrt(pt.n))
        expected_se = math.sqrt(report.exact_probability * (1.0 - report.exact_probability) / pt.n)
        assert pt.se_reference == pytest.approx(expected_se)
        assert pt.abs_error == pytest.approx(abs(pt.estimate - report.exact_probability))

    assert report.log_log_slope is not None
    assert -0.9 <= report.log_log_slope <= -0.15


def test_convergence_analysis_reproducible_and_validates_input() -> None:
    r1 = run_convergence_analysis(QuantProblem.DICE_2D6_SUM_7, [100, 500, 2000], seed=99)
    r2 = run_convergence_analysis(QuantProblem.DICE_2D6_SUM_7, [100, 500, 2000], seed=99)
    assert r1 == r2

    with pytest.raises(ValueError, match="empty"):
        run_convergence_analysis(QuantProblem.DICE_2D6_SUM_7, [], seed=1)
    with pytest.raises(ValueError, match=">= 1"):
        run_convergence_analysis(QuantProblem.DICE_2D6_SUM_7, [0, 100], seed=1)


def test_wilson_ci_empirical_coverage_near_95_percent() -> None:
    p_bday = birthday_collision_probability(23, 365)
    cov_bday = run_coverage_test(p_bday, trials_per_run=300, num_experiments=300, seed=42)
    assert cov_bday.nominal_coverage == pytest.approx(0.95)
    assert 0.90 <= cov_bday.empirical_coverage <= 0.99
    assert cov_bday.covered_count == round(cov_bday.empirical_coverage * 300)

    p_2d6 = dice_sum_distribution(2, 6)[7]
    cov_2d6 = run_coverage_test(p_2d6, trials_per_run=400, num_experiments=300, seed=101)
    assert 0.90 <= cov_2d6.empirical_coverage <= 0.99
