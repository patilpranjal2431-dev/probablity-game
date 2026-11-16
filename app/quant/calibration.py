"""Server-authoritative probability calibration game and Brier score analytics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.games.card_game import format_card
from app.games.rng import GameRNG
from app.quant.exact import (
    PokerHandRank,
    birthday_collision_probability,
    classify_five_card_hand,
    dice_sum_distribution,
    five_card_poker_probabilities,
    hypergeometric_at_least,
)


@dataclass(frozen=True, slots=True)
class GeneratedCalibrationPrompt:
    """Server-side scenario with realized binary outcome and exact probability."""

    category: str
    question_text: str
    true_probability: float
    actual_outcome: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    """Single point on the player's Brier-score-over-time trajectory."""

    round_number: int
    round_id: int
    category: str
    estimated_prob: float
    true_probability: float
    actual_outcome: bool
    brier_score: float
    cumulative_mean_brier: float


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    """Aggregated forecast reliability bin across [low, high]."""

    bin_label: str
    count: int
    mean_predicted: float
    empirical_rate: float


def compute_brier_score(estimated_prob: float, actual_outcome: bool) -> float:
    """Compute proper Brier score (p_hat - y)^2 in [0, 1] (lower is better)."""
    if not (0.0 <= estimated_prob <= 1.0):
        raise ValueError("estimated_prob must be between 0.0 and 1.0.")
    y = 1.0 if actual_outcome else 0.0
    return (estimated_prob - y) ** 2


def generate_calibration_prompt(rng: GameRNG) -> GeneratedCalibrationPrompt:
    """Generate a quantitative probability scenario and realize its hidden outcome."""
    category = rng.choice(
        (
            "one_card_showdown",
            "dice_sum_at_least",
            "hypergeometric_draw",
            "birthday_collision",
            "poker_pair_or_better",
        )
    )

    if category == "one_card_showdown":
        card_idx = rng.randint(0, 51)
        rank = card_idx % 13
        card_label = format_card(card_idx)
        # Cards beating rank = 4*(12 - rank); cards <= rank = 4*rank + 3 out of 51.
        true_prob = (4 * rank + 3) / 51.0
        remaining = [c for c in range(52) if c != card_idx]
        opp_card = rng.choice(remaining)
        opp_rank = opp_card % 13
        actual_outcome = rank >= opp_rank
        return GeneratedCalibrationPrompt(
            category=category,
            question_text=(
                f"You are dealt {card_label} in 1-Card Poker. One opponent card is dealt "
                "from the remaining 51 cards. Estimate P(your rank >= opponent rank)."
            ),
            true_probability=true_prob,
            actual_outcome=actual_outcome,
            explanation=(
                f"Opponent drew {format_card(opp_card)}. "
                f"Exact probability was {4 * rank + 3}/51 = {true_prob:.3f}."
            ),
        )

    if category == "dice_sum_at_least":
        num_dice = rng.choice((2, 3))
        if num_dice == 2:
            target = rng.randint(5, 10)
        else:
            target = rng.randint(8, 14)
        dist = dice_sum_distribution(num_dice, 6)
        true_prob = sum(p for total, p in dist.items() if total >= target)
        rolls = [rng.randint(1, 6) for _ in range(num_dice)]
        rolled_sum = sum(rolls)
        actual_outcome = rolled_sum >= target
        return GeneratedCalibrationPrompt(
            category=category,
            question_text=(
                f"{num_dice} fair 6-sided dice are rolled on the server. "
                f"Estimate P(sum >= {target})."
            ),
            true_probability=true_prob,
            actual_outcome=actual_outcome,
            explanation=(
                f"Server rolled {rolls} (sum = {rolled_sum}). "
                f"Exact DP probability was {true_prob:.3f}."
            ),
        )

    if category == "hypergeometric_draw":
        variant = rng.choice(("aces", "spades"))
        if variant == "aces":
            draws = rng.choice((4, 5, 7, 10))
            min_hits = rng.choice((1, 2)) if draws >= 5 else 1
            desc = f"{min_hits} or more Aces"
            success_pop = 4
        else:
            draws = rng.choice((4, 5, 6))
            min_hits = rng.choice((1, 2, 3))
            desc = f"{min_hits} or more Spades"
            success_pop = 13

        true_prob = hypergeometric_at_least(52, success_pop, draws, min_hits)
        dealt = rng.sample(range(52), draws)
        hits = (
            sum(1 for c in dealt if c % 13 == 12)
            if variant == "aces"
            else sum(1 for c in dealt if c // 13 == 0)
        )
        actual_outcome = hits >= min_hits
        return GeneratedCalibrationPrompt(
            category=category,
            question_text=(
                f"{draws} cards are drawn without replacement from a 52-card deck. "
                f"Estimate P(drawing {desc})."
            ),
            true_probability=true_prob,
            actual_outcome=actual_outcome,
            explanation=(
                f"Draw contained {hits} matching card(s). "
                f"Exact Hypergeometric(52, {success_pop}, {draws}) tail is {true_prob:.3f}."
            ),
        )

    if category == "birthday_collision":
        num_people = rng.choice((10, 15, 20, 23, 30, 40, 50))
        true_prob = birthday_collision_probability(num_people, 365)
        days = [rng.randint(0, 364) for _ in range(num_people)]
        actual_outcome = len(set(days)) < num_people
        return GeneratedCalibrationPrompt(
            category=category,
            question_text=(
                f"{num_people} people have independent uniform birthdays (365 days). "
                "Estimate P(at least two share a birthday)."
            ),
            true_probability=true_prob,
            actual_outcome=actual_outcome,
            explanation=(
                f"{num_people} random draws had "
                f"{'a collision' if actual_outcome else 'all distinct days'}. "
                f"Exact collision probability is {true_prob:.3f}."
            ),
        )

    # poker_pair_or_better
    probs = five_card_poker_probabilities()
    true_prob = 1.0 - probs[PokerHandRank.HIGH_CARD]
    hand = rng.sample(range(52), 5)
    rank = classify_five_card_hand(hand)
    actual_outcome = rank != PokerHandRank.HIGH_CARD
    labels = [format_card(c) for c in hand]
    return GeneratedCalibrationPrompt(
        category=category,
        question_text=(
            "5 cards are dealt at random from a standard 52-card deck. "
            "Estimate P(hand is One Pair or better — anything above High Card)."
        ),
        true_probability=true_prob,
        actual_outcome=actual_outcome,
        explanation=(
            f"Dealt {labels} ({rank.value}). "
            f"Exact combinatorial probability is {true_prob:.4f}."
        ),
    )


def summarize_calibration_history(
    answered_rounds: Sequence[tuple[int, str, float, float, bool, float]],
) -> tuple[float, float, list[CalibrationPoint], list[CalibrationBin]]:
    """Compute running Brier time-series and 5-bin reliability curve.

    Each tuple in ``answered_rounds`` is:
    ``(round_id, category, estimated_prob, true_probability, actual_outcome, brier_score)``
    ordered chronologically from oldest to newest.
    """
    if not answered_rounds:
        return 0.0, 0.0, [], []

    running_brier_sum = 0.0
    abs_err_sum = 0.0
    points: list[CalibrationPoint] = []

    bin_defs = (
        ("0-20%", 0.0, 0.2),
        ("20-40%", 0.2, 0.4),
        ("40-60%", 0.4, 0.6),
        ("60-80%", 0.6, 0.8),
        ("80-100%", 0.8, 1.01),
    )
    bin_buckets: list[list[tuple[float, bool]]] = [[] for _ in bin_defs]

    for idx, (rid, cat, est_p, true_p, outcome, brier) in enumerate(answered_rounds, start=1):
        running_brier_sum += brier
        abs_err_sum += abs(est_p - true_p)
        points.append(
            CalibrationPoint(
                round_number=idx,
                round_id=rid,
                category=cat,
                estimated_prob=round(est_p, 4),
                true_probability=round(true_p, 4),
                actual_outcome=outcome,
                brier_score=round(brier, 4),
                cumulative_mean_brier=round(running_brier_sum / idx, 4),
            )
        )
        for b_idx, (_label, lo, hi) in enumerate(bin_defs):
            if lo <= est_p < hi:
                bin_buckets[b_idx].append((est_p, outcome))
                break

    n = len(answered_rounds)
    bins: list[CalibrationBin] = []
    for (label, _lo, _hi), items in zip(bin_defs, bin_buckets, strict=True):
        if not items:
            continue
        mean_pred = sum(p for p, _ in items) / len(items)
        emp_rate = sum(1 for _, y in items if y) / len(items)
        bins.append(
            CalibrationBin(
                bin_label=label,
                count=len(items),
                mean_predicted=round(mean_pred, 4),
                empirical_rate=round(emp_rate, 4),
            )
        )

    return round(running_brier_sum / n, 4), round(abs_err_sum / n, 4), points, bins
