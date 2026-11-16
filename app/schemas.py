"""Pydantic request and response schemas for Edge Lab."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class HealthResponse(BaseModel):
    """Response payload returned by the /health readiness endpoint."""

    status: str
    app: str
    version: str
    database: str


class RegisterRequest(BaseModel):
    """Validated payload for new user registration."""

    username: str = Field(..., min_length=3, max_length=32)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not USERNAME_PATTERN.fullmatch(cleaned):
            raise ValueError(
                "Username must be 3-32 characters of letters, numbers, or underscores."
            )
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(cleaned):
            raise ValueError("Please provide a valid email address.")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password must not be blank.")
        return value


class LoginRequest(BaseModel):
    """Validated payload for user authentication."""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Username is required.")
        return cleaned


class UserPublic(BaseModel):
    """Safe public representation of a User (excludes password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_bot: bool
    created_at: datetime


class TransactionPublic(BaseModel):
    """Serialized audit ledger transaction for profile history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tx_type: str
    amount: int
    balance_after: int
    description: str
    hand_id: int | None
    created_at: datetime


class AuthResponse(BaseModel):
    """Response returned after successful registration or login."""

    user: UserPublic
    balance: int
    message: str


class LogoutResponse(BaseModel):
    """Response returned after logging out."""

    message: str


class ProfileResponse(BaseModel):
    """Authenticated user's profile, coin balance, and transaction history."""

    user: UserPublic
    balance: int
    transactions: list[TransactionPublic]


class DiceOutcomeSchema(BaseModel):
    """Exact count and probability for a single dice sum."""

    total: int
    count: int
    probability: float


class DiceSumResponse(BaseModel):
    """Exact DP dice sum distribution."""

    num_dice: int
    num_sides: int
    total_outcomes: int
    outcomes: list[DiceOutcomeSchema]


class PokerHandEntry(BaseModel):
    """Exact count and probability for a 5-card poker category."""

    rank: str
    count: int
    probability: float


class PokerDistributionResponse(BaseModel):
    """Full 5-card poker hand combinatorial breakdown."""

    total_hands: int
    hands: list[PokerHandEntry]


class HypergeometricResponse(BaseModel):
    """Exact Hypergeometric(N, K, n) probabilities."""

    total_pop: int
    success_pop: int
    draws: int
    successes: int
    pmf: float
    at_least: float
    distribution: dict[int, float]


class BirthdayResponse(BaseModel):
    """Exact birthday problem collision and distinct probabilities."""

    num_people: int
    num_days: int
    collision_probability: float
    distinct_probability: float


class ConvergenceRequest(BaseModel):
    """Input parameters for convergence and Wilson CI coverage analysis."""

    problem: str = Field(default="birthday_23")
    sample_sizes: list[int] = Field(
        default_factory=lambda: [50, 100, 250, 500, 1000, 2500, 5000, 10000],
        min_length=2,
        max_length=12,
    )
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    trials_per_run: int = Field(default=400, ge=10, le=2000)
    num_experiments: int = Field(default=200, ge=20, le=1000)

    @field_validator("sample_sizes")
    @classmethod
    def validate_sample_sizes(cls, values: list[int]) -> list[int]:
        for n in values:
            if n < 1 or n > 50_000:
                raise ValueError("Each sample size n must be between 1 and 50,000.")
        return sorted(set(values))


class ConvergencePointSchema(BaseModel):
    """Single sample-size data point for error vs n analysis."""

    n: int
    estimate: float
    abs_error: float
    ci_lower: float
    ci_upper: float
    inv_sqrt_n: float
    se_reference: float


class CoverageResultSchema(BaseModel):
    """Empirical Wilson 95% CI coverage summary."""

    exact_probability: float
    trials_per_run: int
    num_experiments: int
    covered_count: int
    empirical_coverage: float
    nominal_coverage: float
    mean_ci_width: float
    seed: int


class ConvergenceAndCoverageResponse(BaseModel):
    """Combined convergence sweep and empirical coverage test payload."""

    problem: str
    label: str
    exact_probability: float
    seed: int
    log_log_slope: float | None
    points: list[ConvergencePointSchema]
    coverage: CoverageResultSchema


class TournamentRequest(BaseModel):
    """Parameters for running a seeded round-robin bot tournament."""

    game_type: str = Field(default="dice_betting")
    hands_per_matchup: int = Field(default=500, ge=20, le=2000)
    starting_stack: int = Field(default=1000, ge=50, le=100_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class MatchupStatsSchema(BaseModel):
    """Head-to-head bot matchup statistics with 95% confidence intervals."""

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


class LeaderboardEntrySchema(BaseModel):
    """Aggregated bot standing in a round-robin tournament."""

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


class TournamentResponse(BaseModel):
    """Full bot-vs-bot round-robin tournament report."""

    game_type: str
    hands_per_matchup: int
    starting_stack: int
    seed: int
    leaderboard: list[LeaderboardEntrySchema]
    matchups: list[MatchupStatsSchema]


class CreateLobbyRequest(BaseModel):
    """Validated payload for creating a live WebSocket game table."""

    game_type: Literal["dice_betting", "one_card_poker"] = "dice_betting"
    opponent_type: Literal["human", "bot"] = "bot"
    bot_strategy: Literal["random", "cautious", "ev_max", "kelly"] | None = None
    ante: int = Field(default=10, ge=1, le=500)
    min_bet: int = Field(default=10, ge=1, le=500)
    max_bet: int = Field(default=40, ge=1, le=2000)

    @model_validator(mode="after")
    def validate_lobby_rules(self) -> CreateLobbyRequest:
        if self.max_bet < self.min_bet:
            raise ValueError("max_bet must be >= min_bet.")
        if self.opponent_type == "bot" and self.bot_strategy is None:
            self.bot_strategy = "ev_max"
        if self.opponent_type == "human" and self.bot_strategy is not None:
            raise ValueError("bot_strategy must be omitted for human-vs-human tables.")
        return self


class SeatSummary(BaseModel):
    """Public seat summary for lobby listings (contains no hidden game state)."""

    seat: int
    username: str | None
    is_bot: bool
    connected: bool


class LobbySummary(BaseModel):
    """Public table metadata for the WebSocket lobby list."""

    table_id: int
    game_type: str
    opponent_type: str
    bot_strategy: str | None
    status: str
    ante: int
    min_bet: int
    max_bet: int
    hand_number: int
    seats: list[SeatSummary]


class DecisionGradePublic(BaseModel):
    """Serialized EV decision grade record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hand_id: int
    game_id: int
    game_type: str
    seat_index: int
    decision_index: int
    private_label: str
    equity: float
    pot_before: int
    to_call: int
    taken_action: str
    taken_amount: int
    taken_ev: float
    best_action: str
    best_amount: int
    best_ev: float
    regret: float
    is_auto: bool
    created_at: datetime


class SkillLeaderboardEntry(BaseModel):
    """Leaderboard standing ranked by cumulative EV (skill)."""

    rank: int
    user_id: int
    username: str
    is_bot: bool
    cumulative_ev: float
    total_best_ev: float
    total_regret: float
    mean_regret: float
    optimal_rate: float
    decisions_count: int
    hands_played: int
    coin_balance: int
    net_coin_profit: int


class CoinsLeaderboardEntry(BaseModel):
    """Leaderboard standing ranked by wallet coin balance (luck + skill)."""

    rank: int
    user_id: int
    username: str
    is_bot: bool
    coin_balance: int
    net_coin_profit: int
    cumulative_ev: float
    total_regret: float
    hands_played: int


class LeaderboardsResponse(BaseModel):
    """Separate Skill (Cumulative EV) and Coins (Luck + Skill) leaderboards."""

    include_bots: bool
    skill_leaderboard: list[SkillLeaderboardEntry]
    coins_leaderboard: list[CoinsLeaderboardEntry]


class DecisionHistoryResponse(BaseModel):
    """Authenticated player's personal EV grading summary and decision log."""

    cumulative_ev: float
    total_best_ev: float
    total_regret: float
    optimal_rate: float
    decisions_count: int
    hands_played: int
    decisions: list[DecisionGradePublic]


class BankrollSimRequest(BaseModel):
    """Validated parameters for bankroll, Kelly, and Risk of Ruin simulation."""

    initial_bankroll: float = Field(default=1000.0, gt=0.0, le=1_000_000.0)
    win_prob: float = Field(default=0.55, gt=0.0, lt=1.0)
    payout_odds: float = Field(default=1.0, gt=0.0, le=50.0)
    bet_fraction: float = Field(default=0.10, gt=0.0, lt=1.0)
    sizing_mode: Literal["proportional", "fixed_stake"] = "proportional"
    num_bets: int = Field(default=200, ge=10, le=2000)
    num_paths: int = Field(default=1000, ge=50, le=5000)
    ruin_threshold: float | None = Field(default=None, ge=0.0)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_ruin_threshold(self) -> BankrollSimRequest:
        if self.ruin_threshold is not None and self.ruin_threshold >= self.initial_bankroll:
            raise ValueError("ruin_threshold must be strictly less than initial_bankroll.")
        return self


class KellyCurvePointSchema(BaseModel):
    """Log-growth rate and ruin probability at a candidate bet fraction."""

    fraction: float
    log_growth: float
    ruin_rate: float


class TrajectoryPointSchema(BaseModel):
    """Cross-path bankroll percentiles at a specific bet step."""

    step: int
    p10: float
    median: float
    p90: float
    mean: float


class HistogramBinSchema(BaseModel):
    """Terminal bankroll frequency bin."""

    bin_start: float
    bin_end: float
    count: int
    frequency: float


class BankrollSimResponse(BaseModel):
    """Analytical Kelly metrics, Risk of Ruin, trajectories, and distribution histogram."""

    initial_bankroll: float
    win_prob: float
    payout_odds: float
    bet_fraction: float
    sizing_mode: Literal["proportional", "fixed_stake"]
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
    trajectories: list[TrajectoryPointSchema]
    histogram: list[HistogramBinSchema]
    kelly_curve: list[KellyCurvePointSchema]


class CalibrationPromptPublic(BaseModel):
    """Safe unanswered prompt payload (hides actual_outcome and true_probability)."""

    id: int
    category: str
    question_text: str
    created_at: datetime


class CalibrationGuessRequest(BaseModel):
    """Validated user probability forecast in [0, 1]."""

    estimated_prob: float = Field(..., ge=0.0, le=1.0)


class CalibrationRoundResult(BaseModel):
    """Revealed outcome, exact probability, and Brier score after guessing."""

    id: int
    category: str
    question_text: str
    estimated_prob: float
    true_probability: float
    actual_outcome: bool
    brier_score: float
    explanation: str
    answered_at: datetime


class CalibrationPointSchema(BaseModel):
    """Single point in chronological Brier-score-over-time series."""

    round_number: int
    round_id: int
    category: str
    estimated_prob: float
    true_probability: float
    actual_outcome: bool
    brier_score: float
    cumulative_mean_brier: float


class CalibrationBinSchema(BaseModel):
    """Forecast reliability bin comparing predicted mean vs observed hit rate."""

    bin_label: str
    count: int
    mean_predicted: float
    empirical_rate: float


class CalibrationHistoryResponse(BaseModel):
    """Authenticated user's calibration state, Brier time series, and reliability curve."""

    pending_prompt: CalibrationPromptPublic | None
    rounds_answered: int
    mean_brier_score: float
    mean_abs_prob_error: float
    points: list[CalibrationPointSchema]
    bins: list[CalibrationBinSchema]
    recent_rounds: list[CalibrationRoundResult]


class CreateOrderBookRequest(BaseModel):
    """Validated parameters to start a market-making order book simulation."""

    num_rounds: int = Field(default=10, ge=5, le=25)
    max_inventory: int = Field(default=10, ge=3, le=50)
    fundamental_volatility: float = Field(default=1.0, ge=0.0, le=5.0)


class QuoteRequest(BaseModel):
    """Validated two-sided bid/ask quote submitted by the user."""

    bid_price: float = Field(..., gt=0.0, le=1000.0)
    ask_price: float = Field(..., gt=0.0, le=1000.0)
    quote_size: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_spread(self) -> QuoteRequest:
        if self.ask_price <= self.bid_price:
            raise ValueError("ask_price must be strictly greater than bid_price.")
        if self.ask_price - self.bid_price < 0.1:
            raise ValueError("Minimum spread is 0.10 ticks.")
        return self


class OrderBookLevelSchema(BaseModel):
    """Order book price level snapshot."""

    side: Literal["bid", "ask"]
    price: float
    quantity: int
    owner: Literal["you", "market"]


class OrderBookFillPublic(BaseModel):
    """Observable execution print (hides bot type and fair value during live play)."""

    round_number: int
    side: Literal["buy", "sell"]
    price: float
    quantity: int


class OrderBookRoundPublic(BaseModel):
    """Observable round history entry during active trading."""

    round_number: int
    public_signal: float
    bid_price: float
    ask_price: float
    quote_size: int
    cash_after: float
    inventory_after: int
    fills: list[OrderBookFillPublic]


class OrderBookFillAnalysis(BaseModel):
    """Post-game fill audit revealing bot kind, hidden fair value, and adverse selection."""

    round_number: int
    side: Literal["buy", "sell"]
    price: float
    quantity: int
    bot_kind: Literal["noise_trader", "retail_flow", "informed_arb"]
    fair_value: float
    spread_captured: float
    adverse_selection: float
    net_edge: float


class OrderBookRoundAnalysis(BaseModel):
    """Post-game round trajectory revealing true fair value and mark-to-market P&L."""

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
    fills: list[OrderBookFillAnalysis]


class OrderBookAnalysisSchema(BaseModel):
    """Post-game P&L decomposition and adverse selection analysis."""

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
    rounds: list[OrderBookRoundAnalysis]


class OrderBookSessionResponse(BaseModel):
    """Information-safe session state; ``analysis`` is None until completed."""

    id: int
    status: Literal["active", "completed"]
    num_rounds: int
    current_round: int
    max_inventory: int
    fundamental_volatility: float
    latest_public_signal: float
    cash: float
    inventory: int
    book_levels: list[OrderBookLevelSchema]
    rounds: list[OrderBookRoundPublic]
    analysis: OrderBookAnalysisSchema | None
    created_at: datetime
    completed_at: datetime | None


class OrderBookSessionSummary(BaseModel):
    """Compact summary for listing a user's past/active order book sessions."""

    id: int
    status: str
    num_rounds: int
    current_round: int
    inventory: int
    total_pnl: float | None
    spread_captured: float | None
    adverse_selection_cost: float | None
    created_at: datetime



