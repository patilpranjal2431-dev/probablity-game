"""Unit tests for the auditable virtual-coin ledger."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger import (
    AuditMismatchError,
    InsufficientFundsError,
    LedgerError,
    audit_wallet_balance,
    create_user_with_wallet,
    record_transaction,
)
from app.models import Game, Hand, Transaction, TransactionType


def test_new_user_starts_with_1000_coins_and_initial_transaction(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="quant_student",
        email="student@example.com",
        password_hash="argon2-placeholder",
    )
    db_session.commit()

    assert user.wallet.balance == 1000
    assert len(user.wallet.transactions) == 1

    initial_tx = user.wallet.transactions[0]
    assert initial_tx.tx_type == TransactionType.INITIAL_GRANT.value
    assert initial_tx.amount == 1000
    assert initial_tx.balance_after == 1000
    assert audit_wallet_balance(db_session, user.wallet.id) == 1000


def test_wager_payout_and_refund_audit_trail(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="player1",
        email="p1@example.com",
        password_hash="hash",
    )
    game = Game(game_type="five_card_poker")
    db_session.add(game)
    db_session.flush()

    hand = Hand(game_id=game.id, hand_number=1, pot=0)
    db_session.add(hand)
    db_session.flush()

    record_transaction(
        db_session,
        user.wallet,
        amount=-150,
        tx_type=TransactionType.WAGER,
        description="Hand #1 bet",
        hand_id=hand.id,
    )
    record_transaction(
        db_session,
        user.wallet,
        amount=300,
        tx_type=TransactionType.PAYOUT,
        description="Hand #1 pot win",
        hand_id=hand.id,
    )
    record_transaction(
        db_session,
        user.wallet,
        amount=-50,
        tx_type=TransactionType.WAGER,
        description="Hand #1 side bet",
        hand_id=hand.id,
    )
    record_transaction(
        db_session,
        user.wallet,
        amount=50,
        tx_type=TransactionType.REFUND,
        description="Side bet returned",
        hand_id=hand.id,
    )
    db_session.commit()

    assert user.wallet.balance == 1150
    assert audit_wallet_balance(db_session, user.wallet.id) == 1150

    txs = db_session.scalars(
        select(Transaction)
        .where(Transaction.wallet_id == user.wallet.id)
        .order_by(Transaction.id.asc())
    ).all()
    assert [t.balance_after for t in txs] == [1000, 850, 1150, 1100, 1150]


def test_insufficient_funds_and_invalid_amounts_rejected(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="shortstack",
        email="short@example.com",
        password_hash="hash",
    )
    db_session.commit()

    with pytest.raises(InsufficientFundsError):
        record_transaction(
            db_session,
            user.wallet,
            amount=-1001,
            tx_type=TransactionType.WAGER,
            description="Too large",
        )
    assert user.wallet.balance == 1000

    with pytest.raises(LedgerError, match="non-zero"):
        record_transaction(
            db_session,
            user.wallet,
            amount=0,
            tx_type=TransactionType.ADJUSTMENT,
        )

    with pytest.raises(LedgerError, match="integer"):
        record_transaction(
            db_session,
            user.wallet,
            amount=True,  # type: ignore[arg-type]
            tx_type=TransactionType.ADJUSTMENT,
        )


def test_audit_detects_tampered_wallet_balance(db_session: Session) -> None:
    user = create_user_with_wallet(
        db_session,
        username="auditee",
        email="audit@example.com",
        password_hash="hash",
    )
    db_session.commit()

    # Simulate an unauthorized direct balance mutation bypassing Transaction.
    user.wallet.balance = 9999
    db_session.commit()

    with pytest.raises(AuditMismatchError, match="ledger sum"):
        audit_wallet_balance(db_session, user.wallet.id)
