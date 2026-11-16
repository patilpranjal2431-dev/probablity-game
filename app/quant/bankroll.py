"""Bankroll simulator: Kelly criterion, risk of ruin, and outcome distributions."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

from app.quant.monte_carlo import Z_95, wilson_confidence_interval

SizingMode = Literal["proportional", "fixed_stake"]


@dataclass(frozen=True, slots=True)
class KellyCurvePoint:
    """Expected log-growth rate and ruin estimate at a candidate bet fraction."""

    fraction: float
    log_growth: float
    ruin_rate: float


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    """Bankroll percentiles across simulation paths at bet step ``step``."""

    step: int
    p10: float
    median: float
    p90: float
    mean: float


@dataclass(frozen=True, slots=True)
class HistogramBin:
    """Single bin in the terminal bankroll outcome distribution."""

    bin_start: float
    bin_end: float
    count: int
    frequency: float


@dataclass(frozen=True, slots=True)
class BankrollSimulationResult:
    """Complete analytical + seeded Monte Carlo bankroll report."""

    initial_bankroll: float
    win_prob: float
    payout_odds: float
    bet_fraction: float
    sizing_mode: SizingMode
    num_bets: int
    num_paths: int
    ruin_threshold: float
    seed: int
    full_kelly_fraction: float
    half_kelly_fraction: float
    expected_edge_per_unit: float
    chosen_log_growth: float
    optimal_log_growth: float
    ruined_count: int
    empirical_risk_of_ruin: float
    ruin_ci_lower: float
    ruin_ci_upper: float
    analytical_risk_of_ruin: float | None
    profit_probability: float
    mean_terminal: float
    median_terminal: float
    p05_terminal: float
    p25_terminal: float
    p75_terminal: float
    p95_terminal: float
    max_terminal: float
    trajectories: list[TrajectoryPoint]
    histogram: list[HistogramBin]
    kelly_curve: list[KellyCurvePoint]


def kelly_fraction(win_prob: float, payout_odds: float) -> float:
    """Return optimal full-Kelly wager fraction f* = max(0, p - (1 - p) / b)."""
    if not (0.0 < win_prob < 1.0):
        raise ValueError("win_prob must be strictly between 0 and 1.")
    if payout_odds <= 0.0:
        raise ValueError("payout_odds must be > 0.")
    loss_prob = 1.0 - win_prob
    return max(0.0, (payout_odds * win_prob - loss_prob) / payout_odds)


def kelly_log_growth(win_prob: float, payout_odds: float, fraction: float) -> float:
    """Compute exact expected log-wealth growth rate g(f) = E[ln(B_{t+1} / B_t)]."""
    if not (0.0 < win_prob < 1.0):
        raise ValueError("win_prob must be strictly between 0 and 1.")
    if payout_odds <= 0.0:
        raise ValueError("payout_odds must be > 0.")
    if not (0.0 <= fraction < 1.0):
        raise ValueError("fraction must satisfy 0 <= fraction < 1.")
    if fraction == 0.0:
        return 0.0
    loss_prob = 1.0 - win_prob
    return win_prob * math.log1p(payout_odds * fraction) + loss_prob * math.log1p(-fraction)


def exact_even_money_risk_of_ruin(
    start_units: int,
    win_prob: float,
    *,
    target_units: int | None = None,
) -> float:
    """Compute exact closed-form Gambler's Ruin probability for even-money (+1/-1) wagers.

    If ``target_units`` is None, returns infinite-horizon P(ever hitting 0).
    Otherwise returns P(hitting 0 before ``target_units``).
    """
    if start_units < 0:
        raise ValueError("start_units must be >= 0.")
    if not (0.0 < win_prob < 1.0):
        raise ValueError("win_prob must be strictly between 0 and 1.")
    if start_units == 0:
        return 1.0

    loss_prob = 1.0 - win_prob
    if target_units is None:
        if win_prob <= 0.5:
            return 1.0
        return (loss_prob / win_prob) ** start_units

    if target_units <= start_units:
        raise ValueError("target_units must be > start_units.")
    if math.isclose(win_prob, 0.5, rel_tol=0.0, abs_tol=1e-12):
        return 1.0 - (start_units / target_units)

    ratio = loss_prob / win_prob
    num = (ratio**start_units) - (ratio**target_units)
    den = 1.0 - (ratio**target_units)
    return max(0.0, min(1.0, num / den))


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile for sorted_vals (q in [0, 1])."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _build_histogram(values: list[float], num_bins: int = 12) -> list[HistogramBin]:
    """Bin terminal bankroll outcomes into ``num_bins`` uniform intervals."""
    if not values:
        return []
    v_min = min(values)
    v_max = max(values)
    if math.isclose(v_min, v_max):
        return [
            HistogramBin(
                bin_start=round(v_min, 2),
                bin_end=round(v_max, 2),
                count=len(values),
                frequency=1.0,
            )
        ]

    width = (v_max - v_min) / num_bins
    counts = [0] * num_bins
    for val in values:
        idx = int((val - v_min) / width)
        if idx >= num_bins:
            idx = num_bins - 1
        counts[idx] += 1

    total = len(values)
    return [
        HistogramBin(
            bin_start=round(v_min + i * width, 2),
            bin_end=round(v_min + (i + 1) * width, 2),
            count=counts[i],
            frequency=counts[i] / total,
        )
        for i in range(num_bins)
    ]


def simulate_bankroll(
    *,
    initial_bankroll: float = 1000.0,
    win_prob: float = 0.55,
    payout_odds: float = 1.0,
    bet_fraction: float = 0.10,
    sizing_mode: SizingMode = "proportional",
    num_bets: int = 200,
    num_paths: int = 1000,
    ruin_threshold: float | None = None,
    seed: int = 42,
) -> BankrollSimulationResult:
    """Run seeded Monte Carlo bankroll trajectories alongside exact Kelly metrics."""
    if initial_bankroll <= 0.0:
        raise ValueError("initial_bankroll must be > 0.")
    if not (0.0 < win_prob < 1.0):
        raise ValueError("win_prob must be strictly between 0 and 1.")
    if payout_odds <= 0.0:
        raise ValueError("payout_odds must be > 0.")
    if not (0.0 < bet_fraction < 1.0):
        raise ValueError("bet_fraction must be strictly between 0 and 1.")
    if num_bets < 1:
        raise ValueError("num_bets must be >= 1.")
    if num_paths < 1:
        raise ValueError("num_paths must be >= 1.")

    resolved_ruin = (
        0.10 * initial_bankroll
        if (ruin_threshold is None and sizing_mode == "proportional")
        else (0.0 if ruin_threshold is None else ruin_threshold)
    )
    if resolved_ruin < 0.0 or resolved_ruin >= initial_bankroll:
        raise ValueError("ruin_threshold must satisfy 0 <= ruin_threshold < initial_bankroll.")

    rng = random.Random(seed)
    fixed_unit = initial_bankroll * bet_fraction

    # Sample ~20 evenly spaced steps for trajectory chart (always includes 0 and num_bets).
    step_stride = max(1, num_bets // 25)
    recorded_steps = sorted(set(range(0, num_bets + 1, step_stride)) | {num_bets})
    step_samples: dict[int, list[float]] = {step: [] for step in recorded_steps}

    terminal_values: list[float] = []
    ruined_count = 0

    for _ in range(num_paths):
        bankroll = float(initial_bankroll)
        ruined = False
        if 0 in step_samples:
            step_samples[0].append(bankroll)

        for step in range(1, num_bets + 1):
            if not ruined:
                wager = (
                    bankroll * bet_fraction
                    if sizing_mode == "proportional"
                    else fixed_unit
                )
                if sizing_mode == "fixed_stake" and bankroll < wager - 1e-9:
                    ruined = True
                    bankroll = 0.0
                else:
                    if rng.random() < win_prob:
                        bankroll += payout_odds * wager
                    else:
                        bankroll -= wager
                    if bankroll <= resolved_ruin + 1e-9:
                        ruined = True
                        if sizing_mode == "fixed_stake" and resolved_ruin == 0.0:
                            bankroll = 0.0

            if step in step_samples:
                step_samples[step].append(bankroll)

        if ruined:
            ruined_count += 1
        terminal_values.append(bankroll)

    ci = wilson_confidence_interval(ruined_count, num_paths, z=Z_95)
    sorted_term = sorted(terminal_values)

    full_k = kelly_fraction(win_prob, payout_odds)
    half_k = 0.5 * full_k
    chosen_g = kelly_log_growth(win_prob, payout_odds, bet_fraction)
    optimal_g = kelly_log_growth(win_prob, payout_odds, min(0.999, full_k))

    analytical_ror: float | None = None
    if sizing_mode == "fixed_stake" and math.isclose(payout_odds, 1.0, rel_tol=0.0, abs_tol=1e-9):
        if math.isclose(resolved_ruin, 0.0, abs_tol=1e-9):
            units = max(1, round((initial_bankroll - resolved_ruin) / fixed_unit))
            analytical_ror = exact_even_money_risk_of_ruin(units, win_prob)

    trajectories: list[TrajectoryPoint] = []
    for step in recorded_steps:
        vals = sorted(step_samples[step])
        trajectories.append(
            TrajectoryPoint(
                step=step,
                p10=round(_percentile(vals, 0.10), 2),
                median=round(_percentile(vals, 0.50), 2),
                p90=round(_percentile(vals, 0.90), 2),
                mean=round(sum(vals) / len(vals), 2),
            )
        )

    # Kelly growth curve across candidate bet fractions using quick lightweight Monte Carlo for RoR.
    max_curve_f = min(0.90, max(0.45, 2.5 * full_k, bet_fraction * 1.2))
    grid = {round(0.02 + i * (max_curve_f - 0.02) / 14, 4) for i in range(15)}
    grid.add(round(bet_fraction, 4))
    if 0.005 <= full_k < 0.95:
        grid.add(round(full_k, 4))
    if 0.005 <= half_k < 0.95:
        grid.add(round(half_k, 4))

    kelly_curve: list[KellyCurvePoint] = []
    curve_paths = min(250, num_paths)
    curve_steps = min(150, num_bets)
    for f_idx, frac in enumerate(sorted(grid)):
        if frac <= 0.0 or frac >= 1.0:
            continue
        c_rng = random.Random(seed + 10_000 + f_idx)
        c_ruin = 0
        c_unit = initial_bankroll * frac
        for _ in range(curve_paths):
            b = float(initial_bankroll)
            for _s in range(curve_steps):
                w = b * frac if sizing_mode == "proportional" else c_unit
                if sizing_mode == "fixed_stake" and b < w - 1e-9:
                    c_ruin += 1
                    break
                b += payout_odds * w if c_rng.random() < win_prob else -w
                if b <= resolved_ruin + 1e-9:
                    c_ruin += 1
                    break
        kelly_curve.append(
            KellyCurvePoint(
                fraction=frac,
                log_growth=round(kelly_log_growth(win_prob, payout_odds, frac), 6),
                ruin_rate=round(c_ruin / curve_paths, 4),
            )
        )

    return BankrollSimulationResult(
        initial_bankroll=initial_bankroll,
        win_prob=win_prob,
        payout_odds=payout_odds,
        bet_fraction=bet_fraction,
        sizing_mode=sizing_mode,
        num_bets=num_bets,
        num_paths=num_paths,
        ruin_threshold=round(resolved_ruin, 2),
        seed=seed,
        full_kelly_fraction=round(full_k, 6),
        half_kelly_fraction=round(half_k, 6),
        expected_edge_per_unit=round(win_prob * payout_odds - (1.0 - win_prob), 6),
        chosen_log_growth=round(chosen_g, 6),
        optimal_log_growth=round(optimal_g, 6),
        ruined_count=ruined_count,
        empirical_risk_of_ruin=round(ruined_count / num_paths, 6),
        ruin_ci_lower=round(ci.lower, 6),
        ruin_ci_upper=round(ci.upper, 6),
        analytical_risk_of_ruin=round(analytical_ror, 6) if analytical_ror is not None else None,
        profit_probability=round(
            sum(1 for v in terminal_values if v > initial_bankroll) / num_paths, 6
        ),
        mean_terminal=round(sum(terminal_values) / num_paths, 2),
        median_terminal=round(_percentile(sorted_term, 0.50), 2),
        p05_terminal=round(_percentile(sorted_term, 0.05), 2),
        p25_terminal=round(_percentile(sorted_term, 0.25), 2),
        p75_terminal=round(_percentile(sorted_term, 0.75), 2),
        p95_terminal=round(_percentile(sorted_term, 0.95), 2),
        max_terminal=round(sorted_term[-1], 2),
        trajectories=trajectories,
        histogram=_build_histogram(terminal_values, num_bins=12),
        kelly_curve=kelly_curve,
    )
