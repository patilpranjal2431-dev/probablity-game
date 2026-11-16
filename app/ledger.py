"""Auditable virtual-coin ledger operations for wallets and transactions."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Transaction, TransactionType, User, Wallet, utc_now


class LedgerError(Exception):
    """Base error for invalid or inconsistent ledger operations."""


class InsufficientFundsError(LedgerError):
    """Raised when a debit would cause a wallet's balance to drop below zero."""


class AuditMismatchError(LedgerError):
    """Raised when a wallet's balance disagrees with its transaction ledger."""


def _validate_int_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise LedgerError("Transaction amount must be an integer.")
    if amount == 0:
        raise LedgerError("Transaction amount must be non-zero.")


def record_transaction(
    db: Session,
    wallet: Wallet,
    *,
    amount: int,
    tx_type: TransactionType,
    description: str = "",
    hand_id: int | None = None,
) -> Transaction:
    """Apply a coin delta to a wallet and record an immutable Transaction row."""
    _validate_int_amount(amount)

    new_balance = wallet.balance + amount
    if new_balance < 0:
        raise InsufficientFundsError(
            f"Wallet {wallet.id} has balance {wallet.balance}, cannot apply {amount}."
        )

    wallet.balance = new_balance
    wallet.updated_at = utc_now()

    tx = Transaction(
        wallet_id=wallet.id,
        hand_id=hand_id,
        tx_type=tx_type.value,
        amount=amount,
        balance_after=new_balance,
        description=description,
    )
    db.add(tx)
    db.flush()
    return tx


def create_user_with_wallet(
    db: Session,
    *,
    username: str,
    email: str,
    password_hash: str,
    is_bot: bool = False,
    starting_balance: int | None = None,
) -> User:
    """Create a User, initialize a Wallet, and record the initial grant Transaction."""
    initial_coins = (
        get_settings().initial_wallet_balance
        if starting_balance is None
        else starting_balance
    )
    if isinstance(initial_coins, bool) or not isinstance(initial_coins, int) or initial_coins <= 0:
        raise LedgerError("Starting wallet balance must be a positive integer.")

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        is_bot=is_bot,
    )
    db.add(user)
    db.flush()

    wallet = Wallet(user_id=user.id, balance=0)
    db.add(wallet)
    db.flush()

    record_transaction(
        db,
        wallet,
        amount=initial_coins,
        tx_type=TransactionType.INITIAL_GRANT,
        description="Initial virtual coin grant",
    )
    return user


def audit_wallet_balance(db: Session, wallet_id: int) -> int:
    """Verify that a wallet's stored balance matches the sum and sequence of its transactions."""
    wallet = db.get(Wallet, wallet_id)
    if wallet is None:
        raise LedgerError(f"Wallet {wallet_id} does not exist.")

    ledger_sum = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.wallet_id == wallet_id
        )
    )
    if ledger_sum != wallet.balance:
        raise AuditMismatchError(
            f"Wallet {wallet_id} balance {wallet.balance} != ledger sum {ledger_sum}."
        )

    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.wallet_id == wallet_id)
        .order_by(Transaction.id.asc())
    ).all()

    running_balance = 0
    for tx in transactions:
        running_balance += tx.amount
        if running_balance != tx.balance_after:
            raise AuditMismatchError(
                f"Transaction {tx.id} balance_after {tx.balance_after} != "
                f"expected running balance {running_balance}."
            )

    return wallet.balance
