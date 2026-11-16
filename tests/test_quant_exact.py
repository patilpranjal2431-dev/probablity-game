"""Unit tests for exact probability, DP, and combinatorial modules."""

from __future__ import annotations

import math

import pytest

from app.quant.exact import (
    TOTAL_FIVE_CARD_POKER_HANDS,
    PokerHandRank,
    birthday_collision_probability,
    birthday_distinct_probability,
    classify_five_card_hand,
    dice_sum_counts,
    dice_sum_distribution,
    five_card_poker_counts,
    five_card_poker_probabilities,
    hypergeometric_at_least,
    hypergeometric_distribution,
    hypergeometric_pmf,
)


def _card(rank_label: str, suit_idx: int) -> int:
    rank_map = {
        "2": 0,
        "3": 1,
        "4": 2,
        "5": 3,
        "6": 4,
        "7": 5,
        "8": 6,
        "9": 7,
        "10": 8,
        "J": 9,
        "Q": 10,
        "K": 11,
        "A": 12,
    }
    return suit_idx * 13 + rank_map[rank_label]


def test_dice_sum_distribution_dp_known_values() -> None:
    counts_2d6 = dice_sum_counts(2, 6)
    assert [counts_2d6[s] for s in range(2, 13)] == [1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1]
    assert sum(counts_2d6.values()) == 36

    dist_2d6 = dice_sum_distribution(2, 6)
    assert dist_2d6[7] == pytest.approx(6 / 36)
    assert sum(dist_2d6.values()) == pytest.approx(1.0)

    dist_3d6 = dice_sum_distribution(3, 6)
    assert dist_3d6[10] == pytest.approx(27 / 216)
    assert dist_3d6[11] == pytest.approx(27 / 216)
    assert sum(dist_3d6.values()) == pytest.approx(1.0)

    with pytest.raises(ValueError, match="num_dice"):
        dice_sum_counts(0, 6)
    with pytest.raises(ValueError, match="num_sides"):
        dice_sum_counts(2, 1)


def test_five_card_poker_exact_counts_and_probabilities() -> None:
    counts = five_card_poker_counts()
    expected = {
        PokerHandRank.ROYAL_FLUSH: 4,
        PokerHandRank.STRAIGHT_FLUSH: 36,
        PokerHandRank.FOUR_OF_A_KIND: 624,
        PokerHandRank.FULL_HOUSE: 3_744,
        PokerHandRank.FLUSH: 5_108,
        PokerHandRank.STRAIGHT: 10_200,
        PokerHandRank.THREE_OF_A_KIND: 54_912,
        PokerHandRank.TWO_PAIR: 123_552,
        PokerHandRank.ONE_PAIR: 1_098_240,
        PokerHandRank.HIGH_CARD: 1_302_540,
    }
    assert TOTAL_FIVE_CARD_POKER_HANDS == 2_598_960
    assert counts == expected
    assert sum(counts.values()) == 2_598_960

    probs = five_card_poker_probabilities()
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs[PokerHandRank.ROYAL_FLUSH] == pytest.approx(4 / 2_598_960)
    assert probs[PokerHandRank.ONE_PAIR] == pytest.approx(1_098_240 / 2_598_960)


def test_classify_five_card_hand_all_categories() -> None:
    cases = [
        (
            [_card("10", 0), _card("J", 0), _card("Q", 0), _card("K", 0), _card("A", 0)],
            PokerHandRank.ROYAL_FLUSH,
        ),
        (
            [_card("A", 1), _card("2", 1), _card("3", 1), _card("4", 1), _card("5", 1)],
            PokerHandRank.STRAIGHT_FLUSH,
        ),
        (
            [_card("9", 0), _card("9", 1), _card("9", 2), _card("9", 3), _card("K", 0)],
            PokerHandRank.FOUR_OF_A_KIND,
        ),
        (
            [_card("K", 0), _card("K", 1), _card("K", 2), _card("4", 0), _card("4", 3)],
            PokerHandRank.FULL_HOUSE,
        ),
        (
            [_card("2", 2), _card("5", 2), _card("7", 2), _card("J", 2), _card("A", 2)],
            PokerHandRank.FLUSH,
        ),
        (
            [_card("A", 0), _card("2", 1), _card("3", 2), _card("4", 3), _card("5", 0)],
            PokerHandRank.STRAIGHT,
        ),
        (
            [_card("8", 0), _card("8", 1), _card("8", 2), _card("2", 0), _card("A", 3)],
            PokerHandRank.THREE_OF_A_KIND,
        ),
        (
            [_card("Q", 0), _card("Q", 1), _card("5", 2), _card("5", 3), _card("A", 0)],
            PokerHandRank.TWO_PAIR,
        ),
        (
            [_card("J", 0), _card("J", 1), _card("2", 2), _card("7", 3), _card("A", 0)],
            PokerHandRank.ONE_PAIR,
        ),
        (
            [_card("2", 0), _card("5", 1), _card("7", 2), _card("J", 3), _card("A", 0)],
            PokerHandRank.HIGH_CARD,
        ),
    ]
    for hand, expected_rank in cases:
        assert classify_five_card_hand(hand) == expected_rank

    with pytest.raises(ValueError, match="distinct"):
        classify_five_card_hand([0, 0, 1, 2, 3])
    with pytest.raises(ValueError, match="0..51"):
        classify_five_card_hand([0, 1, 2, 3, 52])


def test_hypergeometric_known_values() -> None:
    # 5-card hand from 52 cards with 4 Aces
    p_zero_aces = hypergeometric_pmf(52, 4, 5, 0)
    assert p_zero_aces == pytest.approx(math.comb(48, 5) / math.comb(52, 5))

    p_four_aces = hypergeometric_pmf(52, 4, 5, 4)
    assert p_four_aces == pytest.approx(48 / 2_598_960)

    # 5 Aces in a 5-card draw is impossible -> probability 0.0
    assert hypergeometric_pmf(52, 4, 5, 5) == 0.0

    p_at_least_one = hypergeometric_at_least(52, 4, 5, 1)
    assert p_at_least_one == pytest.approx(1.0 - p_zero_aces)

    dist = hypergeometric_distribution(52, 4, 5)
    assert set(dist.keys()) == {0, 1, 2, 3, 4}
    assert sum(dist.values()) == pytest.approx(1.0)

    with pytest.raises(ValueError):
        hypergeometric_pmf(52, 60, 5, 1)


def test_birthday_problem_known_values() -> None:
    assert birthday_collision_probability(0, 365) == 0.0
    assert birthday_collision_probability(1, 365) == 0.0
    assert birthday_collision_probability(22, 365) == pytest.approx(0.4756953076625501)
    assert birthday_collision_probability(23, 365) == pytest.approx(0.5072972343239854)
    assert birthday_collision_probability(50, 365) == pytest.approx(0.9703735795779884)
    assert birthday_collision_probability(366, 365) == 1.0
    assert birthday_distinct_probability(23, 365) == pytest.approx(1.0 - 0.5072972343239854)

    with pytest.raises(ValueError):
        birthday_collision_probability(-1, 365)
