"""SQLAlchemy ORM models for users, wallets, games, hands, and audit transactions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import DEFAULT_INITIAL_WALLET_BALANCE
from app.database import Base


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class GameStatus(str, Enum):
    """Lifecycle states for a game session."""

    WAITING = "waiting"
    ACTIVE = "active"
    COMPLETED = "completed"


class HandStatus(str, Enum):
    """Lifecycle states for an individual hand within a game."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class TransactionType(str, Enum):
    """Supported ledger transaction categories for virtual-coin auditing."""

    INITIAL_GRANT = "initial_grant"
    WAGER = "wager"
    PAYOUT = "payout"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class User(Base):
    """Registered human player or bot account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    wallet: Mapped[Wallet] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    decision_grades: Mapped[list[DecisionGrade]] = relationship(
        back_populates="user",
        order_by="DecisionGrade.id",
        cascade="all, delete-orphan",
    )
    calibration_rounds: Mapped[list[CalibrationRound]] = relationship(
        back_populates="user",
        order_by="CalibrationRound.id",
        cascade="all, delete-orphan",
    )
    order_book_sessions: Mapped[list[OrderBookSession]] = relationship(
        back_populates="user",
        order_by="OrderBookSession.id",
        cascade="all, delete-orphan",
    )


class Wallet(Base):
    """Virtual-coin wallet owned by a single user (stored in integer coins)."""

    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_wallets_non_negative_balance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    balance: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_INITIAL_WALLET_BALANCE
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="wallet")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="wallet",
        order_by="Transaction.id",
        cascade="all, delete-orphan",
    )


class Game(Base):
    """A game table or simulation session."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=GameStatus.WAITING.value
    )
    seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    hands: Mapped[list[Hand]] = relationship(
        back_populates="game",
        order_by="Hand.hand_number",
        cascade="all, delete-orphan",
    )


class Hand(Base):
    """A single dealt hand or round belonging to a Game."""

    __tablename__ = "hands"
    __table_args__ = (
        UniqueConstraint("game_id", "hand_number", name="uq_hands_game_hand_number"),
        CheckConstraint("hand_number >= 1", name="ck_hands_positive_hand_number"),
        CheckConstraint("pot >= 0", name="ck_hands_non_negative_pot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hand_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    pot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=HandStatus.IN_PROGRESS.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    game: Mapped[Game] = relationship(back_populates="hands")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="hand",
        order_by="Transaction.id",
    )
    decision_grades: Mapped[list[DecisionGrade]] = relationship(
        back_populates="hand",
        order_by="DecisionGrade.decision_index",
        cascade="all, delete-orphan",
    )


class Transaction(Base):
    """Immutable audit log entry for every virtual-coin balance change."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount != 0", name="ck_transactions_non_zero_amount"),
        CheckConstraint("balance_after >= 0", name="ck_transactions_non_negative_balance_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hand_id: Mapped[int | None] = mapped_column(
        ForeignKey("hands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tx_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")
    hand: Mapped[Hand | None] = relationship(back_populates="transactions")


class UserSession(Base):
    """Server-side session record storing only the SHA-256 hash of a session token."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class DecisionGrade(Base):
    """Post-game EV grade comparing a player's chosen action against the optimal action."""

    __tablename__ = "decision_grades"
    __table_args__ = (
        CheckConstraint("regret >= 0", name="ck_decision_grades_non_negative_regret"),
        CheckConstraint("decision_index >= 1", name="ck_decision_grades_positive_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hand_id: Mapped[int] = mapped_column(
        ForeignKey("hands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_index: Mapped[int] = mapped_column(Integer, nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    private_label: Mapped[str] = mapped_column(String(16), nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    pot_before: Mapped[int] = mapped_column(Integer, nullable=False)
    to_call: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taken_action: Mapped[str] = mapped_column(String(16), nullable=False)
    taken_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    taken_ev: Mapped[float] = mapped_column(Float, nullable=False)
    best_action: Mapped[str] = mapped_column(String(16), nullable=False)
    best_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_ev: Mapped[float] = mapped_column(Float, nullable=False)
    regret: Mapped[float] = mapped_column(Float, nullable=False)
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    hand: Mapped[Hand] = relationship(back_populates="decision_grades")
    user: Mapped[User] = relationship(back_populates="decision_grades")


class CalibrationRound(Base):
    """Server-authoritative probability calibration round with Brier score."""

    __tablename__ = "calibration_rounds"
    __table_args__ = (
        CheckConstraint(
            "estimated_prob IS NULL OR (estimated_prob >= 0 AND estimated_prob <= 1)",
            name="ck_calibration_rounds_prob_range",
        ),
        CheckConstraint(
            "brier_score IS NULL OR (brier_score >= 0 AND brier_score <= 1)",
            name="ck_calibration_rounds_brier_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    true_probability: Mapped[float] = mapped_column(Float, nullable=False)
    actual_outcome: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    brier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="calibration_rounds")


class OrderBookSession(Base):
    """Persisted market-making order book simulation session."""

    __tablename__ = "order_book_sessions"
    __table_args__ = (
        CheckConstraint("num_rounds >= 1", name="ck_orderbook_positive_rounds"),
        CheckConstraint("max_inventory >= 1", name="ck_orderbook_positive_max_inv"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    num_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_inventory: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    fundamental_volatility: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    initial_fair_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_fair_value: Mapped[float] = mapped_column(Float, nullable=False)
    latest_public_signal: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    inventory: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_captured: Mapped[float | None] = mapped_column(Float, nullable=True)
    adverse_selection_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    inventory_drift_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    rounds_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="order_book_sessions")
