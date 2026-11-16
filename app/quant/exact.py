"""Exact probability calculations via dynamic programming and combinatorics."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from enum import Enum

TOTAL_FIVE_CARD_POKER_HANDS = math.comb(52, 5)  # 2,598,960


class PokerHandRank(str, Enum):
    """Standard 10-tier five-card poker hand classification."""

    ROYAL_FLUSH = "royal_flush"
    STRAIGHT_FLUSH = "straight_flush"
    FOUR_OF_A_KIND = "four_of_a_kind"
    FULL_HOUSE = "full_house"
    FLUSH = "flush"
    STRAIGHT = "straight"
    THREE_OF_A_KIND = "three_of_a_kind"
    TWO_PAIR = "two_pair"
    ONE_PAIR = "one_pair"
    HIGH_CARD = "high_card"


def dice_sum_counts(num_dice: int, num_sides: int = 6) -> dict[int, int]:
    """Compute exact outcome counts for every sum of ``num_dice`` fair dice via DP."""
    if isinstance(num_dice, bool) or not isinstance(num_dice, int) or num_dice < 1:
        raise ValueError("num_dice must be an integer >= 1.")
    if isinstance(num_sides, bool) or not isinstance(num_sides, int) or num_sides < 2:
        raise ValueError("num_sides must be an integer >= 2.")

    dp: dict[int, int] = {0: 1}
    for _ in range(num_dice):
        next_dp: dict[int, int] = {}
        for running_sum, ways in dp.items():
            for face in range(1, num_sides + 1):
                new_sum = running_sum + face
                next_dp[new_sum] = next_dp.get(new_sum, 0) + ways
        dp = next_dp
    return dp


def dice_sum_distribution(num_dice: int, num_sides: int = 6) -> dict[int, float]:
    """Compute exact probability distribution for the sum of ``num_dice`` fair dice."""
    counts = dice_sum_counts(num_dice, num_sides)
    total_outcomes = num_sides**num_dice
    return {total: count / total_outcomes for total, count in counts.items()}


def five_card_poker_counts() -> dict[PokerHandRank, int]:
    """Return exact combinatorial counts for all 5-card poker hands (sum = 2,598,960)."""
    # 10 possible high cards for a straight (5-high wheel through Ace-high royal).
    num_straight_ranks = 10
    num_suits = 4

    royal_flush = num_suits
    straight_flush = num_straight_ranks * num_suits - royal_flush
    four_of_a_kind = math.comb(13, 1) * math.comb(4, 4) * math.comb(12, 1) * math.comb(4, 1)
    full_house = math.comb(13, 1) * math.comb(4, 3) * math.comb(12, 1) * math.comb(4, 2)
    flush = num_suits * math.comb(13, 5) - (royal_flush + straight_flush)
    straight = num_straight_ranks * (num_suits**5) - (royal_flush + straight_flush)
    three_of_a_kind = (
        math.comb(13, 1) * math.comb(4, 3) * math.comb(12, 2) * (math.comb(4, 1) ** 2)
    )
    two_pair = (
        math.comb(13, 2) * (math.comb(4, 2) ** 2) * math.comb(11, 1) * math.comb(4, 1)
    )
    one_pair = (
        math.comb(13, 1) * math.comb(4, 2) * math.comb(12, 3) * (math.comb(4, 1) ** 3)
    )
    high_card = (math.comb(13, 5) - num_straight_ranks) * ((num_suits**5) - num_suits)

    counts = {
        PokerHandRank.ROYAL_FLUSH: royal_flush,
        PokerHandRank.STRAIGHT_FLUSH: straight_flush,
        PokerHandRank.FOUR_OF_A_KIND: four_of_a_kind,
        PokerHandRank.FULL_HOUSE: full_house,
        PokerHandRank.FLUSH: flush,
        PokerHandRank.STRAIGHT: straight,
        PokerHandRank.THREE_OF_A_KIND: three_of_a_kind,
        PokerHandRank.TWO_PAIR: two_pair,
        PokerHandRank.ONE_PAIR: one_pair,
        PokerHandRank.HIGH_CARD: high_card,
    }
    if sum(counts.values()) != TOTAL_FIVE_CARD_POKER_HANDS:
        raise AssertionError("Poker hand counts failed to sum to C(52, 5).")
    return counts


def five_card_poker_probabilities() -> dict[PokerHandRank, float]:
    """Return exact probabilities for all 10 five-card poker hand categories."""
    counts = five_card_poker_counts()
    return {rank: count / TOTAL_FIVE_CARD_POKER_HANDS for rank, count in counts.items()}


def classify_five_card_hand(cards: Sequence[int]) -> PokerHandRank:
    """Classify 5 distinct card indices (0..51) into a PokerHandRank."""
    if len(cards) != 5 or len(set(cards)) != 5:
        raise ValueError("Exactly 5 distinct card indices must be provided.")
    if any(card < 0 or card >= 52 for card in cards):
        raise ValueError("Card indices must be in range 0..51.")

    ranks = [card % 13 for card in cards]
    suits = {card // 13 for card in cards}
    unique_ranks = sorted(set(ranks), reverse=True)

    is_flush = len(suits) == 1
    is_wheel = unique_ranks == [12, 3, 2, 1, 0]
    is_normal_straight = len(unique_ranks) == 5 and (unique_ranks[0] - unique_ranks[4] == 4)
    is_straight = is_wheel or is_normal_straight
    is_royal = is_flush and unique_ranks == [12, 11, 10, 9, 8]

    if is_royal:
        return PokerHandRank.ROYAL_FLUSH
    if is_flush and is_straight:
        return PokerHandRank.STRAIGHT_FLUSH

    counts = sorted(Counter(ranks).values(), reverse=True)
    if counts == [4, 1]:
        return PokerHandRank.FOUR_OF_A_KIND
    if counts == [3, 2]:
        return PokerHandRank.FULL_HOUSE
    if is_flush:
        return PokerHandRank.FLUSH
    if is_straight:
        return PokerHandRank.STRAIGHT
    if counts == [3, 1, 1]:
        return PokerHandRank.THREE_OF_A_KIND
    if counts == [2, 2, 1]:
        return PokerHandRank.TWO_PAIR
    if counts == [2, 1, 1, 1]:
        return PokerHandRank.ONE_PAIR
    return PokerHandRank.HIGH_CARD


def _validate_hypergeometric_params(
    total_pop: int, success_pop: int, draws: int, successes: int | None = None
) -> None:
    if total_pop < 1:
        raise ValueError("total_pop (N) must be >= 1.")
    if success_pop < 0 or success_pop > total_pop:
        raise ValueError("success_pop (K) must satisfy 0 <= K <= N.")
    if draws < 0 or draws > total_pop:
        raise ValueError("draws (n) must satisfy 0 <= n <= N.")
    if successes is not None and (successes < 0 or successes > draws):
        raise ValueError("successes (k) must satisfy 0 <= k <= n.")


def hypergeometric_pmf(
    total_pop: int, success_pop: int, draws: int, successes: int
) -> float:
    """Compute exact P(X = k) for X ~ Hypergeometric(N=total_pop, K=success_pop, n=draws)."""
    _validate_hypergeometric_params(total_pop, success_pop, draws, successes)
    if successes > success_pop or (draws - successes) > (total_pop - success_pop):
        return 0.0
    numerator = math.comb(success_pop, successes) * math.comb(
        total_pop - success_pop, draws - successes
    )
    denominator = math.comb(total_pop, draws)
    return numerator / denominator


def hypergeometric_at_least(
    total_pop: int, success_pop: int, draws: int, min_successes: int
) -> float:
    """Compute exact P(X >= min_successes) for Hypergeometric(N, K, n)."""
    _validate_hypergeometric_params(total_pop, success_pop, draws, min_successes)
    return sum(
        hypergeometric_pmf(total_pop, success_pop, draws, k)
        for k in range(min_successes, min(draws, success_pop) + 1)
    )


def hypergeometric_distribution(
    total_pop: int, success_pop: int, draws: int
) -> dict[int, float]:
    """Return exact Hypergeometric PMF over all valid support values of k."""
    _validate_hypergeometric_params(total_pop, success_pop, draws)
    min_k = max(0, draws - (total_pop - success_pop))
    max_k = min(draws, success_pop)
    return {
        k: hypergeometric_pmf(total_pop, success_pop, draws, k)
        for k in range(min_k, max_k + 1)
    }


def birthday_distinct_probability(num_people: int, num_days: int = 365) -> float:
    """Compute exact probability that all ``num_people`` have distinct birthdays."""
    if num_people < 0:
        raise ValueError("num_people must be >= 0.")
    if num_days < 1:
        raise ValueError("num_days must be >= 1.")
    if num_people <= 1:
        return 1.0
    if num_people > num_days:
        return 0.0

    prob_distinct = 1.0
    for offset in range(num_people):
        prob_distinct *= (num_days - offset) / num_days
    return prob_distinct


def birthday_collision_probability(num_people: int, num_days: int = 365) -> float:
    """Compute exact probability that at least two people share a birthday."""
    return 1.0 - birthday_distinct_probability(num_people, num_days=num_days)
