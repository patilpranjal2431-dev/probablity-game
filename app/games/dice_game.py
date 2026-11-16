"""Pure-Python Heads-Up Private-Roll Dice Betting game engine."""

from __future__ import annotations

from app.games.engine import Bot, HandOutcome, run_heads_up_betting_hand
from app.games.rng import GameRNG


class DiceBettingGame:
    """Two-player hidden-roll dice betting game.

    Each player posts an ante and privately rolls a fair d-sided die (default d6).
    One round of betting occurs before showdown; highest die wins the pot.
    """

    def __init__(
        self,
        *,
        num_sides: int = 6,
        ante: int = 10,
        min_bet: int = 10,
        max_bet: int = 40,
    ) -> None:
        if num_sides < 2:
            raise ValueError("num_sides must be >= 2.")
        if ante < 1 or min_bet < 1 or max_bet < min_bet:
            raise ValueError("Invalid ante/bet bounds.")
        self.num_sides = num_sides
        self._ante = ante
        self._min_bet = min_bet
        self._max_bet = max_bet

    @property
    def game_type(self) -> str:
        return "dice_betting"

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
        """Return (win_prob, tie_prob) against an unknown independent die roll."""
        if not (1 <= private_value <= self.num_sides):
            raise ValueError(f"Die roll must be in 1..{self.num_sides}.")
        win_prob = (private_value - 1) / self.num_sides
        tie_prob = 1.0 / self.num_sides
        return win_prob, tie_prob

    def play_hand(
        self,
        bots: tuple[Bot, Bot],
        rng: GameRNG,
        *,
        stacks: tuple[int, int] = (1000, 1000),
        hand_number: int = 1,
    ) -> HandOutcome:
        """Deal private dice rolls and run a full heads-up betting hand."""
        roll0 = rng.randint(1, self.num_sides)
        roll1 = rng.randint(1, self.num_sides)

        probs0 = self.exact_showdown_probs(roll0)
        probs1 = self.exact_showdown_probs(roll1)

        return run_heads_up_betting_hand(
            game_type=self.game_type,
            private_values=(roll0, roll1),
            private_labels=(f"d{self.num_sides}:{roll0}", f"d{self.num_sides}:{roll1}"),
            showdown_probs=(probs0, probs1),
            bots=bots,
            rng=rng,
            stacks=stacks,
            ante=self._ante,
            min_bet=self._min_bet,
            max_bet=self._max_bet,
            hand_number=hand_number,
        )
