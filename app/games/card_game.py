"""Pure-Python Heads-Up Simplified One-Card Poker game engine."""

from __future__ import annotations

from app.games.engine import Bot, HandOutcome, run_heads_up_betting_hand
from app.games.rng import GameRNG

RANK_LABELS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUIT_LABELS = ("S", "H", "D", "C")


def format_card(card_index: int) -> str:
    """Format a 0..51 card index as e.g. 'AS' or '10H'."""
    if not (0 <= card_index < 52):
        raise ValueError("card_index must be in range 0..51.")
    return f"{RANK_LABELS[card_index % 13]}{SUIT_LABELS[card_index // 13]}"


class OneCardPokerGame:
    """Simplified two-player one-card poker from a 52-card deck (without replacement).

    Each player posts an ante and is dealt one private card from a 52-card deck.
    Showdown compares card rank (2 lowest, A highest); equal ranks split the pot.
    """

    def __init__(
        self,
        *,
        ante: int = 10,
        min_bet: int = 10,
        max_bet: int = 40,
    ) -> None:
        if ante < 1 or min_bet < 1 or max_bet < min_bet:
            raise ValueError("Invalid ante/bet bounds.")
        self._ante = ante
        self._min_bet = min_bet
        self._max_bet = max_bet

    @property
    def game_type(self) -> str:
        return "one_card_poker"

    @property
    def ante(self) -> int:
        return self._ante

    @property
    def min_bet(self) -> int:
        return self._min_bet

    @property
    def max_bet(self) -> int:
        return self._max_bet

    def exact_showdown_probs(self, private_value: int) -> tuple[float, float]:
        """Return (win_prob, tie_prob) using exact 51-card removal combinatorics.

        ``private_value`` is the card's rank index (0='2' .. 12='A').
        """
        if not (0 <= private_value <= 12):
            raise ValueError("Card rank must be in 0..12.")
        lower_cards = 4 * private_value
        equal_cards = 3
        remaining = 51
        return lower_cards / remaining, equal_cards / remaining

    def play_hand(
        self,
        bots: tuple[Bot, Bot],
        rng: GameRNG,
        *,
        stacks: tuple[int, int] = (1000, 1000),
        hand_number: int = 1,
    ) -> HandOutcome:
        """Deal 2 distinct cards without replacement and run a heads-up betting hand."""
        card0, card1 = rng.sample(range(52), 2)
        rank0 = card0 % 13
        rank1 = card1 % 13

        probs0 = self.exact_showdown_probs(rank0)
        probs1 = self.exact_showdown_probs(rank1)

        return run_heads_up_betting_hand(
            game_type=self.game_type,
            private_values=(rank0, rank1),
            private_labels=(format_card(card0), format_card(card1)),
            showdown_probs=(probs0, probs1),
            bots=bots,
            rng=rng,
            stacks=stacks,
            ante=self._ante,
            min_bet=self._min_bet,
            max_bet=self._max_bet,
            hand_number=hand_number,
        )
