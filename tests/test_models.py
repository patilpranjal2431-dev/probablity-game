"""Unit tests for SQLAlchemy ORM models and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Game,
    GameStatus,
    Hand,
    HandStatus,
    Transaction,
    TransactionType,
    User,
    Wallet,
)


def test_wallet_defaults_to_1000_coins(db_session: Session) -> None:
    user = User(username="alice", email="alice@example.com", password_hash="hashed")
    db_session.add(user)
    db_session.flush()

    wallet = Wallet(user_id=user.id)
    db_session.add(wallet)
    db_session.commit()

    db_session.refresh(wallet)
    assert wallet.balance == 1000
    assert wallet.user.username == "alice"


def test_unique_username_and_email_enforced(db_session: Session) -> None:
    db_session.add(User(username="bob", email="bob@example.com", password_hash="h1"))
    db_session.commit()

    db_session.add(User(username="bob", email="bob2@example.com", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(User(username="bob2", email="bob@example.com", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_game_and_hand_relationships_and_constraints(db_session: Session) -> None:
    game = Game(game_type="five_card_poker", status=GameStatus.ACTIVE.value, seed="seed-42")
    db_session.add(game)
    db_session.flush()

    hand1 = Hand(
        game_id=game.id,
        hand_number=1,
        state_json='{"pot": 20}',
        pot=20,
        status=HandStatus.IN_PROGRESS.value,
    )
    db_session.add(hand1)
    db_session.commit()

    assert len(game.hands) == 1
    assert game.hands[0].hand_number == 1

    # Duplicate hand_number for the same game must fail.
    db_session.add(Hand(game_id=game.id, hand_number=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_foreign_key_and_check_constraints_enforced(db_session: Session) -> None:
    # Non-existent user_id on Wallet must fail when PRAGMA foreign_keys=ON.
    db_session.add(Wallet(user_id=99999, balance=1000))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    user = User(username="carol", email="carol@example.com", password_hash="h")
    db_session.add(user)
    db_session.flush()

    # Negative wallet balance must violate CheckConstraint.
    db_session.add(Wallet(user_id=user.id, balance=-1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_hand_preserves_audit_transaction_with_null_hand_id(db_session: Session) -> None:
    user = User(username="dave", email="dave@example.com", password_hash="h")
    db_session.add(user)
    db_session.flush()

    wallet = Wallet(user_id=user.id, balance=950)
    game = Game(game_type="five_card_poker")
    db_session.add_all([wallet, game])
    db_session.flush()

    hand = Hand(game_id=game.id, hand_number=1, pot=50)
    db_session.add(hand)
    db_session.flush()

    tx = Transaction(
        wallet_id=wallet.id,
        hand_id=hand.id,
        tx_type=TransactionType.WAGER.value,
        amount=-50,
        balance_after=950,
        description="Ante wager",
    )
    db_session.add(tx)
    db_session.commit()

    db_session.delete(hand)
    db_session.commit()

    db_session.refresh(tx)
    assert tx.hand_id is None
    assert tx.amount == -50
