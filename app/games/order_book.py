"""Server-authoritative market-making order book simulation with adverse selection tracking."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from app.games.rng import GameRNG

FillSide = Literal["buy", "sell"]  # From user's perspective: buy = hit bid, sell = lift ask
BotKind = Literal["noise_trader", "retail_flow", "informed_arb"]


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    """Single execution against the user's resting bid/ask quote."""

    round_number: int
    side: FillSide
    price: float
    quantity: int
    bot_kind: BotKind
    fair_value: float
    quoted_midpoint: float
    half_spread: float
    spread_captured: float
    adverse_selection: float
    net_edge: float


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """Displayed resting quote level on the simulated order book."""

    side: Literal["bid", "ask"]
    price: float
    quantity: int
    owner: Literal["you", "market"]


@dataclass(frozen=True, slots=True)
class RoundSnapshot:
    """Completed round record storing hidden fair value alongside observable tape."""

    round_number: int
    fair_value: float
    public_signal: float
    bid_price: float
    ask_price: float
    quote_size: int
    cash_after: float
    inventory_after: int
    mtm_pnl_after: float
    inventory_drift_step: float
    fills: list[SimulatedFill] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PostGameAnalysis:
    """Post-game P&L decomposition and adverse selection report."""

    initial_fair_value: float
    terminal_fair_value: float
    total_pnl: float
    spread_captured: float
    adverse_selection_cost: float
    inventory_drift_pnl: float
    final_cash: float
    final_inventory: int
    max_abs_inventory: int
    total_fills: int
    total_volume: int
    informed_fills: int
    informed_volume: int
    informed_volume_share: float
    avg_quoted_spread: float
    rounds: list[RoundSnapshot]


def generate_initial_market(
    rng: GameRNG,
    *,
    signal_sigma: float = 8.0,
) -> tuple[float, float]:
    """Draw a hidden initial fair value V_0 and an initial noisy public hint."""
    fair_value = round(rng.uniform(85.0, 115.0), 2)
    # Sum of 2 centered uniforms approximates symmetric bell noise in [-signal_sigma, +signal_sigma]
    noise = ((rng.uniform(0.0, 1.0) + rng.uniform(0.0, 1.0)) - 1.0) * signal_sigma
    public_signal = round(max(10.0, fair_value + noise), 2)
    return fair_value, public_signal


def evolve_fair_value(
    prev_fair_value: float,
    rng: GameRNG,
    *,
    volatility: float,
    signal_sigma: float = 6.0,
) -> tuple[float, float]:
    """Advance hidden fair value by a zero-mean shock and emit a noisy public signal."""
    if volatility <= 0.0:
        next_fair = prev_fair_value
    else:
        shock = ((rng.uniform(0.0, 1.0) + rng.uniform(0.0, 1.0)) - 1.0) * (volatility * 2.0)
        next_fair = round(max(10.0, prev_fair_value + shock), 2)

    noise = ((rng.uniform(0.0, 1.0) + rng.uniform(0.0, 1.0)) - 1.0) * signal_sigma
    public_signal = round(max(10.0, next_fair + noise), 2)
    return next_fair, public_signal


def build_book_snapshot(
    *,
    public_signal: float,
    bid_price: float | None,
    ask_price: float | None,
    quote_size: int | None,
) -> list[OrderBookLevel]:
    """Construct an information-safe 6-level resting order book around public reference."""
    levels: list[OrderBookLevel] = [
        OrderBookLevel(
            side="ask", price=round(public_signal + 5.0, 2), quantity=4, owner="market"
        ),
        OrderBookLevel(
            side="ask", price=round(public_signal + 3.0, 2), quantity=2, owner="market"
        ),
        OrderBookLevel(
            side="bid",
            price=round(max(1.0, public_signal - 3.0), 2),
            quantity=2,
            owner="market",
        ),
        OrderBookLevel(
            side="bid",
            price=round(max(0.5, public_signal - 5.0), 2),
            quantity=4,
            owner="market",
        ),
    ]
    if bid_price is not None and ask_price is not None and quote_size is not None:
        levels.append(OrderBookLevel(side="ask", price=ask_price, quantity=quote_size, owner="you"))
        levels.append(OrderBookLevel(side="bid", price=bid_price, quantity=quote_size, owner="you"))

    asks = sorted((lvl for lvl in levels if lvl.side == "ask"), key=lambda x: -x.price)
    bids = sorted((lvl for lvl in levels if lvl.side == "bid"), key=lambda x: -x.price)
    return [*asks, *bids]


def _make_fill(
    *,
    round_number: int,
    side: FillSide,
    price: float,
    quantity: int,
    bot_kind: BotKind,
    fair_value: float,
    quoted_midpoint: float,
    half_spread: float,
) -> SimulatedFill:
    direction = 1.0 if side == "buy" else -1.0
    spread_cap = quantity * half_spread
    adverse_sel = quantity * direction * (quoted_midpoint - fair_value)
    net_edge = spread_cap - adverse_sel
    return SimulatedFill(
        round_number=round_number,
        side=side,
        price=round(price, 2),
        quantity=quantity,
        bot_kind=bot_kind,
        fair_value=round(fair_value, 2),
        quoted_midpoint=round(quoted_midpoint, 4),
        half_spread=round(half_spread, 4),
        spread_captured=round(spread_cap, 4),
        adverse_selection=round(adverse_sel, 4),
        net_edge=round(net_edge, 4),
    )


def simulate_quote_round(
    *,
    round_number: int,
    prev_fair_value: float,
    curr_fair_value: float,
    public_signal: float,
    bid_price: float,
    ask_price: float,
    quote_size: int,
    cash_before: float,
    inventory_before: int,
    max_inventory: int,
    rng: GameRNG,
) -> RoundSnapshot:
    """Execute one round of bot order flow against the user's resting bid/ask."""
    if bid_price <= 0.0 or ask_price <= bid_price:
        raise ValueError("Require 0 < bid_price < ask_price.")
    if quote_size < 1:
        raise ValueError("quote_size must be >= 1.")

    midpoint = 0.5 * (bid_price + ask_price)
    spread = ask_price - bid_price
    half_spread = 0.5 * spread

    # Inventory carry / drift as fair value evolves from V_{t-1} to V_t.
    inventory_drift_step = inventory_before * (curr_fair_value - prev_fair_value)

    cash = cash_before
    inventory = inventory_before
    fills: list[SimulatedFill] = []

    def try_fill(side: FillSide, bot_kind: BotKind, requested_qty: int) -> None:
        nonlocal cash, inventory
        if requested_qty <= 0:
            return
        if side == "buy":
            headroom = max_inventory - inventory
            qty = min(requested_qty, quote_size, headroom)
            if qty <= 0:
                return
            price = bid_price
            cash -= qty * price
            inventory += qty
        else:
            headroom = max_inventory + inventory
            qty = min(requested_qty, quote_size, headroom)
            if qty <= 0:
                return
            price = ask_price
            cash += qty * price
            inventory -= qty

        fills.append(
            _make_fill(
                round_number=round_number,
                side=side,
                price=price,
                quantity=qty,
                bot_kind=bot_kind,
                fair_value=curr_fair_value,
                quoted_midpoint=midpoint,
                half_spread=half_spread,
            )
        )

    # 1. Informed arbitrage bot: picks off stale quotes that cross hidden fair value.
    arb_edge_threshold = 0.10
    if ask_price < curr_fair_value - arb_edge_threshold:
        try_fill("sell", "informed_arb", quote_size)
    elif bid_price > curr_fair_value + arb_edge_threshold:
        try_fill("buy", "informed_arb", quote_size)

    # 2. Uninformed noise trader: private valuation centered around fair value +/- noise.
    noise_val = curr_fair_value + rng.uniform(-7.0, 7.0)
    spread_ratio = spread / max(1.0, midpoint)
    noise_willing = spread_ratio <= 0.18
    if noise_willing:
        if noise_val >= ask_price and rng.uniform(0.0, 1.0) < 0.70:
            qty = rng.randint(1, min(2, quote_size))
            try_fill("sell", "noise_trader", qty)
        elif noise_val <= bid_price and rng.uniform(0.0, 1.0) < 0.70:
            qty = rng.randint(1, min(2, quote_size))
            try_fill("buy", "noise_trader", qty)

    # 3. Retail liquidity taker: random small order when spread is reasonably tight.
    retail_prob = max(0.05, min(0.75, 0.80 - 4.0 * spread_ratio))
    if rng.uniform(0.0, 1.0) < retail_prob:
        side: FillSide = rng.choice(("buy", "sell"))
        try_fill(side, "retail_flow", 1)

    mtm_pnl = cash + inventory * curr_fair_value
    return RoundSnapshot(
        round_number=round_number,
        fair_value=round(curr_fair_value, 2),
        public_signal=round(public_signal, 2),
        bid_price=round(bid_price, 2),
        ask_price=round(ask_price, 2),
        quote_size=quote_size,
        cash_after=round(cash, 4),
        inventory_after=inventory,
        mtm_pnl_after=round(mtm_pnl, 4),
        inventory_drift_step=round(inventory_drift_step, 4),
        fills=fills,
    )


def compute_post_game_analysis(
    *,
    initial_fair_value: float,
    rounds: list[RoundSnapshot],
) -> PostGameAnalysis:
    """Compute exact P&L decomposition and adverse selection statistics after session end."""
    if not rounds:
        return PostGameAnalysis(
            initial_fair_value=round(initial_fair_value, 2),
            terminal_fair_value=round(initial_fair_value, 2),
            total_pnl=0.0,
            spread_captured=0.0,
            adverse_selection_cost=0.0,
            inventory_drift_pnl=0.0,
            final_cash=0.0,
            final_inventory=0,
            max_abs_inventory=0,
            total_fills=0,
            total_volume=0,
            informed_fills=0,
            informed_volume=0,
            informed_volume_share=0.0,
            avg_quoted_spread=0.0,
            rounds=[],
        )

    last = rounds[-1]
    spread_captured = sum(f.spread_captured for r in rounds for f in r.fills)
    adverse_selection = sum(f.adverse_selection for r in rounds for f in r.fills)
    inventory_drift = sum(r.inventory_drift_step for r in rounds)
    total_pnl = last.cash_after + last.inventory_after * last.fair_value

    # Sanity check exact accounting conservation identity:
    # Total P&L = Spread Captured - Adverse Selection + Inventory Drift
    reconstructed = spread_captured - adverse_selection + inventory_drift
    if not math.isclose(total_pnl, reconstructed, rel_tol=1e-6, abs_tol=1e-3):
        raise AssertionError(
            f"P&L decomposition mismatch: {total_pnl} != {reconstructed}"
        )

    all_fills = [f for r in rounds for f in r.fills]
    total_volume = sum(f.quantity for f in all_fills)
    informed = [f for f in all_fills if f.bot_kind == "informed_arb"]
    informed_volume = sum(f.quantity for f in informed)

    return PostGameAnalysis(
        initial_fair_value=round(initial_fair_value, 2),
        terminal_fair_value=round(last.fair_value, 2),
        total_pnl=round(total_pnl, 2),
        spread_captured=round(spread_captured, 2),
        adverse_selection_cost=round(adverse_selection, 2),
        inventory_drift_pnl=round(inventory_drift, 2),
        final_cash=round(last.cash_after, 2),
        final_inventory=last.inventory_after,
        max_abs_inventory=max(abs(r.inventory_after) for r in rounds),
        total_fills=len(all_fills),
        total_volume=total_volume,
        informed_fills=len(informed),
        informed_volume=informed_volume,
        informed_volume_share=(
            round(informed_volume / total_volume, 4) if total_volume > 0 else 0.0
        ),
        avg_quoted_spread=round(
            sum(r.ask_price - r.bid_price for r in rounds) / len(rounds), 2
        ),
        rounds=rounds,
    )
