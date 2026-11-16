"""Reproducible bot-vs-bot tournament runner with win rate and EV confidence intervals."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.games.engine import Bot, HeadsUpGame
from app.games.rng import SeededRNG
from app.quant.monte_carlo import Z_95, wilson_confidence_interval


@dataclass(frozen=True, slots=True)
class MatchupStats:
    """Head-to-head statistics from Bot A's perspective against Bot B."""

    game_type: str
    bot_a_id: str
    bot_a_name: str
    bot_b_id: str
    bot_b_name: str
    hands_played: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    win_rate_ci_lower: float
    win_rate_ci_upper: float
    ev_per_game: float
    ev_std_error: float
    ev_ci_lower: float
    ev_ci_upper: float
    seed: int


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    """Aggregated round-robin tournament standing for a single bot."""

    strategy_id: str
    name: str
    hands_played: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    win_rate_ci_lower: float
    win_rate_ci_upper: float
    ev_per_game: float
    ev_std_error: float
    ev_ci_lower: float
    ev_ci_upper: float


@dataclass(frozen=True, slots=True)
class TournamentReport:
    """Full round-robin bot tournament report."""

    game_type: str
    hands_per_matchup: int
    starting_stack: int
    seed: int
    leaderboard: list[LeaderboardEntry]
    matchups: list[MatchupStats]


def _mean_and_ci(values: list[int], z: float = Z_95) -> tuple[float, float, float, float]:
    n = len(values)
    if n == 0:
        raise ValueError("Cannot compute mean/CI of empty sample.")
    mean = sum(values) / n
    if n == 1:
        return mean, 0.0, mean, mean
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std_err = math.sqrt(variance / n)
    margin = z * std_err
    return mean, std_err, mean - margin, mean + margin


def _win_rate_wilson_ci(wins: int, ties: int, total: int) -> tuple[float, float, float]:
    # Count ties as half-wins for Wilson interval while keeping integer counts bounded.
    # For Wilson bounds on strict wins vs total, or half-point adjusted rounded successes:
    score_points = wins + 0.5 * ties
    win_rate = score_points / total
    p_hat = win_rate
    z2 = Z_95 * Z_95
    denom = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denom
    margin = (
        Z_95
        * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z2 / (4.0 * total * total)))
        / denom
    )
    return win_rate, max(0.0, center - margin), min(1.0, center + margin)


def run_head_to_head(
    game: HeadsUpGame,
    bot_a: Bot,
    bot_b: Bot,
    *,
    num_hands: int = 500,
    seed: int = 42,
    starting_stack: int = 1000,
) -> MatchupStats:
    """Run ``num_hands`` seat-alternating hands between ``bot_a`` and ``bot_b``."""
    if num_hands < 1:
        raise ValueError("num_hands must be >= 1.")
    if starting_stack < game.ante:
        raise ValueError("starting_stack must be >= game.ante.")

    profits_a: list[int] = []
    wins = 0
    losses = 0
    ties = 0

    for idx in range(num_hands):
        rng = SeededRNG(seed + idx)
        # Alternate first-to-act seat every hand to eliminate positional bias.
        if idx % 2 == 0:
            outcome = game.play_hand(
                (bot_a, bot_b),
                rng,
                stacks=(starting_stack, starting_stack),
                hand_number=idx + 1,
            )
            net_a = outcome.net_profits[0]
        else:
            outcome = game.play_hand(
                (bot_b, bot_a),
                rng,
                stacks=(starting_stack, starting_stack),
                hand_number=idx + 1,
            )
            net_a = outcome.net_profits[1]

        profits_a.append(net_a)
        if net_a > 0:
            wins += 1
        elif net_a < 0:
            losses += 1
        else:
            ties += 1

    if ties == 0:
        ci = wilson_confidence_interval(wins, num_hands)
        win_rate = wins / num_hands
        wr_lo, wr_hi = ci.lower, ci.upper
    else:
        win_rate, wr_lo, wr_hi = _win_rate_wilson_ci(wins, ties, num_hands)

    ev_mean, ev_se, ev_lo, ev_hi = _mean_and_ci(profits_a)

    return MatchupStats(
        game_type=game.game_type,
        bot_a_id=bot_a.strategy_id,
        bot_a_name=bot_a.name,
        bot_b_id=bot_b.strategy_id,
        bot_b_name=bot_b.name,
        hands_played=num_hands,
        wins=wins,
        losses=losses,
        ties=ties,
        win_rate=win_rate,
        win_rate_ci_lower=wr_lo,
        win_rate_ci_upper=wr_hi,
        ev_per_game=ev_mean,
        ev_std_error=ev_se,
        ev_ci_lower=ev_lo,
        ev_ci_upper=ev_hi,
        seed=seed,
    )


def run_round_robin_tournament(
    game: HeadsUpGame,
    bots: list[Bot],
    *,
    hands_per_matchup: int = 500,
    seed: int = 42,
    starting_stack: int = 1000,
) -> TournamentReport:
    """Run a seeded round-robin tournament across all bot pairs."""
    if len(bots) < 2:
        raise ValueError("At least 2 bots are required for a tournament.")

    per_bot_profits: dict[str, list[int]] = {b.strategy_id: [] for b in bots}
    per_bot_wlt: dict[str, list[int]] = {b.strategy_id: [0, 0, 0] for b in bots}
    bot_names: dict[str, str] = {b.strategy_id: b.name for b in bots}
    matchups: list[MatchupStats] = []

    matchup_idx = 0
    for i in range(len(bots)):
        for j in range(i + 1, len(bots)):
            bot_a = bots[i]
            bot_b = bots[j]
            matchup_seed = seed + matchup_idx * 10_000
            matchup_idx += 1

            # Track hand-level profits directly for exact leaderboard CIs.
            profits_a: list[int] = []
            profits_b: list[int] = []
            w_a = l_a = t_a = 0

            for hand_i in range(hands_per_matchup):
                rng = SeededRNG(matchup_seed + hand_i)
                if hand_i % 2 == 0:
                    outcome = game.play_hand(
                        (bot_a, bot_b),
                        rng,
                        stacks=(starting_stack, starting_stack),
                        hand_number=hand_i + 1,
                    )
                    net_a, net_b = outcome.net_profits
                else:
                    outcome = game.play_hand(
                        (bot_b, bot_a),
                        rng,
                        stacks=(starting_stack, starting_stack),
                        hand_number=hand_i + 1,
                    )
                    net_b, net_a = outcome.net_profits

                profits_a.append(net_a)
                profits_b.append(net_b)
                if net_a > 0:
                    w_a += 1
                elif net_a < 0:
                    l_a += 1
                else:
                    t_a += 1

            per_bot_profits[bot_a.strategy_id].extend(profits_a)
            per_bot_profits[bot_b.strategy_id].extend(profits_b)

            per_bot_wlt[bot_a.strategy_id][0] += w_a
            per_bot_wlt[bot_a.strategy_id][1] += l_a
            per_bot_wlt[bot_a.strategy_id][2] += t_a

            per_bot_wlt[bot_b.strategy_id][0] += l_a
            per_bot_wlt[bot_b.strategy_id][1] += w_a
            per_bot_wlt[bot_b.strategy_id][2] += t_a

            wr_a, wr_lo, wr_hi = _win_rate_wilson_ci(w_a, t_a, hands_per_matchup)
            ev_mean, ev_se, ev_lo, ev_hi = _mean_and_ci(profits_a)

            matchups.append(
                MatchupStats(
                    game_type=game.game_type,
                    bot_a_id=bot_a.strategy_id,
                    bot_a_name=bot_a.name,
                    bot_b_id=bot_b.strategy_id,
                    bot_b_name=bot_b.name,
                    hands_played=hands_per_matchup,
                    wins=w_a,
                    losses=l_a,
                    ties=t_a,
                    win_rate=wr_a,
                    win_rate_ci_lower=wr_lo,
                    win_rate_ci_upper=wr_hi,
                    ev_per_game=ev_mean,
                    ev_std_error=ev_se,
                    ev_ci_lower=ev_lo,
                    ev_ci_upper=ev_hi,
                    seed=matchup_seed,
                )
            )

    leaderboard: list[LeaderboardEntry] = []
    for bot in bots:
        sid = bot.strategy_id
        w, losses, ties = per_bot_wlt[sid]
        total = w + losses + ties
        wr, wr_lo, wr_hi = _win_rate_wilson_ci(w, ties, total)
        ev_mean, ev_se, ev_lo, ev_hi = _mean_and_ci(per_bot_profits[sid])
        leaderboard.append(
            LeaderboardEntry(
                strategy_id=sid,
                name=bot_names[sid],
                hands_played=total,
                wins=w,
                losses=losses,
                ties=ties,
                win_rate=wr,
                win_rate_ci_lower=wr_lo,
                win_rate_ci_upper=wr_hi,
                ev_per_game=ev_mean,
                ev_std_error=ev_se,
                ev_ci_lower=ev_lo,
                ev_ci_upper=ev_hi,
            )
        )

    leaderboard.sort(key=lambda entry: entry.ev_per_game, reverse=True)

    return TournamentReport(
        game_type=game.game_type,
        hands_per_matchup=hands_per_matchup,
        starting_stack=starting_stack,
        seed=seed,
        leaderboard=leaderboard,
        matchups=matchups,
    )
