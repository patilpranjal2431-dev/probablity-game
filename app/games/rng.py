"""Server-side RNG abstractions: CSPRNG for live games, seeded PRNG for simulations."""

from __future__ import annotations

import random
import secrets
from collections.abc import Sequence
from typing import Protocol, TypeVar

_T = TypeVar("_T")


class GameRNG(Protocol):
    """Protocol implemented by both live CSPRNG and reproducible seeded PRNG."""

    def randint(self, a: int, b: int) -> int: ...

    def randrange(self, stop: int) -> int: ...

    def random(self) -> float: ...

    def uniform(self, a: float, b: float) -> float: ...

    def sample(self, population: Sequence[_T], k: int) -> list[_T]: ...

    def choice(self, seq: Sequence[_T]) -> _T: ...


class LiveRNG:
    """Cryptographically strong RNG backed by secrets.SystemRandom for live play."""

    def __init__(self) -> None:
        self._rng = secrets.SystemRandom()

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def randrange(self, stop: int) -> int:
        return self._rng.randrange(stop)

    def random(self) -> float:
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def sample(self, population: Sequence[_T], k: int) -> list[_T]:
        return self._rng.sample(population, k)

    def choice(self, seq: Sequence[_T]) -> _T:
        return self._rng.choice(seq)


class SeededRNG:
    """Reproducible Mersenne Twister RNG for simulations and bot tournaments."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def randrange(self, stop: int) -> int:
        return self._rng.randrange(stop)

    def random(self) -> float:
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def sample(self, population: Sequence[_T], k: int) -> list[_T]:
        return self._rng.sample(population, k)

    def choice(self, seq: Sequence[_T]) -> _T:
        return self._rng.choice(seq)
