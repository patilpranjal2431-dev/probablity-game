"""Unit tests for LiveRNG (secrets.SystemRandom) and SeededRNG."""

from __future__ import annotations

from app.games.rng import LiveRNG, SeededRNG


def test_seeded_rng_is_reproducible() -> None:
    r1 = SeededRNG(2026)
    r2 = SeededRNG(2026)

    seq1 = [r1.randint(1, 6) for _ in range(20)] + [r1.sample(range(52), 2) for _ in range(10)]
    seq2 = [r2.randint(1, 6) for _ in range(20)] + [r2.sample(range(52), 2) for _ in range(10)]
    assert seq1 == seq2


def test_live_rng_produces_valid_samples() -> None:
    rng = LiveRNG()
    rolls = [rng.randint(1, 6) for _ in range(30)]
    assert all(1 <= r <= 6 for r in rolls)

    pair = rng.sample(range(52), 2)
    assert len(pair) == 2 and len(set(pair)) == 2
    assert 0.0 <= rng.random() < 1.0
    assert rng.choice(["a", "b", "c"]) in {"a", "b", "c"}
