"""Real-time WebSocket lobby manager with atomic wallet settlement and timeout handling."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.games.bots import (
    CautiousBot,
    EVMaximisingBot,
    KellySizingBot,
    RandomBot,
)
from app.games.card_game import OneCardPokerGame, format_card
from app.games.dice_game import DiceBettingGame
from app.games.engine import (
    ActionType,
    Bot,
    PlayerAction,
    PlayerObservation,
    validate_player_action,
)
from app.games.grading import grade_decision
from app.games.rng import LiveRNG
from app.ledger import InsufficientFundsError, create_user_with_wallet, record_transaction
from app.models import (
    DecisionGrade,
    Game,
    GameStatus,
    Hand,
    HandStatus,
    TransactionType,
    User,
    Wallet,
    utc_now,
)


def make_bot(strategy_id: str) -> Bot:
    """Instantiate one of the four server-side bots by strategy_id."""
    if strategy_id == "random":
        return RandomBot()
    if strategy_id == "cautious":
        return CautiousBot()
    if strategy_id == "ev_max":
        return EVMaximisingBot()
    if strategy_id == "kelly":
        return KellySizingBot()
    raise ValueError(f"Unsupported bot strategy: {strategy_id!r}")


def get_or_create_bot_user(db: Session, strategy_id: str) -> User:
    """Fetch or create a persistent bot User + Wallet so bot wagers are auditable."""
    bot_username = f"bot_{strategy_id}"
    existing = db.scalar(select(User).where(User.username == bot_username))
    if existing is not None:
        return existing

    user = create_user_with_wallet(
        db,
        username=bot_username,
        email=f"{bot_username}@edgelab.local",
        password_hash="!bot-login-disabled!",
        is_bot=True,
        starting_balance=100_000,
    )
    db.flush()
    return user


@dataclass
class TableSeat:
    """One of two seats at a heads-up WebSocket table."""

    seat_index: int
    user_id: int | None = None
    username: str | None = None
    is_bot: bool = False
    bot: Bot | None = None
    websocket: WebSocket | None = None
    connected: bool = False


@dataclass(frozen=True, slots=True)
class RecordedDecision:
    """In-memory snapshot of a legal decision taken during an active hand."""

    seat_index: int
    observation: PlayerObservation
    action: PlayerAction
    is_auto: bool = False


@dataclass
class ActiveHandState:
    """Server-authoritative state for an in-progress hand (never exposed raw)."""

    hand_id: int
    hand_number: int
    private_values: tuple[int, int]
    private_labels: tuple[str, str]
    showdown_probs: tuple[tuple[float, float], tuple[float, float]]
    pot: int
    contributions: list[int]
    first_actor: int
    current_turn: int
    has_bet: bool = False
    bet_amount: int = 0
    actions_taken: int = 0
    pending_decisions: list[RecordedDecision] = field(default_factory=list)


@dataclass
class LobbyTable:
    """In-memory coordinator for a persistent Game row and its WebSocket connections."""

    table_id: int
    game_type: str
    opponent_type: str
    bot_strategy: str | None
    ante: int
    min_bet: int
    max_bet: int
    status: str = GameStatus.WAITING.value
    hand_count: int = 0
    seats: list[TableSeat] = field(
        default_factory=lambda: [TableSeat(seat_index=0), TableSeat(seat_index=1)]
    )
    active_hand: ActiveHandState | None = None
    turn_timer: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class LobbyError(Exception):
    """Domain error raised for invalid lobby operations."""


class LobbyManager:
    """Manages active tables, WebSocket routing, turn timers, and atomic settlement."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        turn_timeout_seconds: float = 30.0,
    ) -> None:
        self.session_factory = session_factory
        self.turn_timeout_seconds = turn_timeout_seconds
        self._tables: dict[int, LobbyTable] = {}
        self._rng = LiveRNG()

    def _make_engine(self, table: LobbyTable) -> DiceBettingGame | OneCardPokerGame:
        if table.game_type == "dice_betting":
            return DiceBettingGame(ante=table.ante, min_bet=table.min_bet, max_bet=table.max_bet)
        if table.game_type == "one_card_poker":
            return OneCardPokerGame(ante=table.ante, min_bet=table.min_bet, max_bet=table.max_bet)
        raise ValueError(f"Unsupported game_type: {table.game_type!r}")

    def list_tables(self) -> list[dict[str, Any]]:
        """Return safe public metadata for all active/waiting tables."""
        return [self.table_summary(t) for t in self._tables.values()]

    def get_table(self, table_id: int) -> LobbyTable | None:
        return self._tables.get(table_id)

    def table_summary(self, table: LobbyTable) -> dict[str, Any]:
        return {
            "table_id": table.table_id,
            "game_type": table.game_type,
            "opponent_type": table.opponent_type,
            "bot_strategy": table.bot_strategy,
            "status": table.status,
            "ante": table.ante,
            "min_bet": table.min_bet,
            "max_bet": table.max_bet,
            "hand_number": table.hand_count,
            "seats": [
                {
                    "seat": s.seat_index,
                    "username": s.username,
                    "is_bot": s.is_bot,
                    "connected": s.connected,
                }
                for s in table.seats
            ],
        }

    def create_table(
        self,
        *,
        creator: User,
        game_type: str,
        opponent_type: str,
        bot_strategy: str | None,
        ante: int,
        min_bet: int,
        max_bet: int,
    ) -> LobbyTable:
        """Persist a new Game row and register its LobbyTable."""
        with self.session_factory() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == creator.id))
            if wallet is None or wallet.balance < ante:
                raise LobbyError(f"Insufficient balance: at least {ante} coins required.")

            game = Game(game_type=game_type, status=GameStatus.WAITING.value, seed=None)
            db.add(game)
            db.flush()

            seat0 = TableSeat(
                seat_index=0,
                user_id=creator.id,
                username=creator.username,
                is_bot=False,
                connected=False,
            )
            seat1 = TableSeat(seat_index=1)

            if opponent_type == "bot":
                if not bot_strategy:
                    raise LobbyError("bot_strategy is required for bot tables.")
                bot_instance = make_bot(bot_strategy)
                bot_user = get_or_create_bot_user(db, bot_strategy)
                if bot_user.wallet.balance < ante + max_bet:
                    record_transaction(
                        db,
                        bot_user.wallet,
                        amount=100_000,
                        tx_type=TransactionType.ADJUSTMENT,
                        description="Bot bankroll replenishment",
                    )
                seat1 = TableSeat(
                    seat_index=1,
                    user_id=bot_user.id,
                    username=bot_user.username,
                    is_bot=True,
                    bot=bot_instance,
                    connected=True,
                )

            db.commit()
            table_id = game.id

        table = LobbyTable(
            table_id=table_id,
            game_type=game_type,
            opponent_type=opponent_type,
            bot_strategy=bot_strategy,
            ante=ante,
            min_bet=min_bet,
            max_bet=max_bet,
            seats=[seat0, seat1],
        )
        self._tables[table_id] = table
        return table

    def _cancel_timer(self, table: LobbyTable) -> None:
        current = asyncio.current_task()
        if (
            table.turn_timer is not None
            and table.turn_timer is not current
            and not table.turn_timer.done()
        ):
            table.turn_timer.cancel()
        table.turn_timer = None

    def _schedule_timer(self, table: LobbyTable, hand_number: int, seat_idx: int) -> None:
        self._cancel_timer(table)
        if table.seats[seat_idx].is_bot:
            return

        async def _timeout_watchdog() -> None:
            try:
                await asyncio.sleep(self.turn_timeout_seconds)
            except asyncio.CancelledError:
                return

            async with table.lock:
                hand = table.active_hand
                if (
                    hand is None
                    or hand.hand_number != hand_number
                    or hand.current_turn != seat_idx
                ):
                    return
                legal = self._legal_actions(hand)
                auto_action = (
                    PlayerAction(ActionType.CHECK)
                    if ActionType.CHECK in legal
                    else PlayerAction(ActionType.FOLD)
                )
                await self._broadcast(
                    table,
                    {
                        "type": "hand:timeout",
                        "seat": seat_idx,
                        "username": table.seats[seat_idx].username,
                        "auto_action": auto_action.action.value,
                    },
                )
                await self._apply_action_locked(table, seat_idx, auto_action, is_auto=True)

        table.turn_timer = asyncio.create_task(_timeout_watchdog())

    def _legal_actions(self, hand: ActiveHandState) -> tuple[ActionType, ...]:
        if hand.has_bet:
            return (ActionType.FOLD, ActionType.CALL)
        return (ActionType.CHECK, ActionType.BET)

    def _load_wallet_balances(self, db: Session, table: LobbyTable) -> tuple[int, int]:
        balances = [0, 0]
        for idx, seat in enumerate(table.seats):
            if seat.user_id is not None:
                wallet = db.scalar(select(Wallet).where(Wallet.user_id == seat.user_id))
                balances[idx] = wallet.balance if wallet is not None else 0
        return balances[0], balances[1]

    def _build_observation(
        self,
        table: LobbyTable,
        hand: ActiveHandState,
        seat_idx: int,
        balances: tuple[int, int],
    ) -> PlayerObservation:
        own_stack = balances[seat_idx]
        opp_stack = balances[1 - seat_idx]
        to_call = (
            max(0, hand.contributions[1 - seat_idx] - hand.contributions[seat_idx])
            if hand.has_bet
            else 0
        )
        legal = self._legal_actions(hand)
        if ActionType.BET in legal and min(own_stack, opp_stack) < table.min_bet:
            legal = (ActionType.CHECK,)

        win_p, tie_p = hand.showdown_probs[seat_idx]
        effective_max = min(table.max_bet, own_stack, opp_stack)
        return PlayerObservation(
            game_type=table.game_type,
            player_index=seat_idx,
            private_value=hand.private_values[seat_idx],
            private_label=hand.private_labels[seat_idx],
            exact_win_prob=win_p,
            exact_tie_prob=tie_p,
            equity=win_p + 0.5 * tie_p,
            own_stack=own_stack,
            opponent_stack=opp_stack,
            pot=hand.pot,
            own_contribution=hand.contributions[seat_idx],
            opponent_contribution=hand.contributions[1 - seat_idx],
            to_call=to_call,
            ante=table.ante,
            min_bet=table.min_bet,
            max_bet=effective_max,
            legal_actions=legal,
        )

    def _build_client_state(
        self,
        table: LobbyTable,
        seat_idx: int,
        balances: tuple[int, int],
    ) -> dict[str, Any]:
        """Build an information-safe per-recipient state snapshot."""
        hand = table.active_hand
        your_private: dict[str, Any] | None = None
        legal_actions: list[str] = []
        to_call = 0
        effective_max_bet = table.max_bet
        current_turn_seat: int | None = None
        pot = 0
        contributions = [0, 0]

        if hand is not None:
            obs = self._build_observation(table, hand, seat_idx, balances)
            your_private = {
                "value": obs.private_value,
                "label": obs.private_label,
                "equity": obs.equity,
            }
            current_turn_seat = hand.current_turn
            pot = hand.pot
            contributions = list(hand.contributions)
            to_call = obs.to_call
            effective_max_bet = obs.max_bet
            if hand.current_turn == seat_idx:
                legal_actions = [a.value for a in obs.legal_actions]

        return {
            "type": "table:state",
            "table_id": table.table_id,
            "game_type": table.game_type,
            "opponent_type": table.opponent_type,
            "status": table.status,
            "hand_number": table.hand_count,
            "your_seat": seat_idx,
            "current_turn_seat": current_turn_seat,
            "pot": pot,
            "ante": table.ante,
            "min_bet": table.min_bet,
            "max_bet": table.max_bet,
            "effective_max_bet": effective_max_bet,
            "to_call": to_call,
            "legal_actions": legal_actions,
            "your_private": your_private,
            "turn_timeout_seconds": self.turn_timeout_seconds,
            "players": [
                {
                    "seat": s.seat_index,
                    "username": s.username,
                    "is_bot": s.is_bot,
                    "connected": s.connected,
                    "stack": balances[s.seat_index],
                    "contribution": contributions[s.seat_index],
                }
                for s in table.seats
            ],
        }

    async def _send_to_seat(
        self, table: LobbyTable, seat_idx: int, payload: dict[str, Any]
    ) -> None:
        ws = table.seats[seat_idx].websocket
        if ws is None:
            return
        try:
            await ws.send_json(payload)
        except Exception:
            table.seats[seat_idx].connected = False
            table.seats[seat_idx].websocket = None

    async def _broadcast(self, table: LobbyTable, payload: dict[str, Any]) -> None:
        for seat in table.seats:
            if seat.websocket is not None and not seat.is_bot:
                await self._send_to_seat(table, seat.seat_index, payload)

    async def _broadcast_state(self, table: LobbyTable) -> None:
        with self.session_factory() as db:
            balances = self._load_wallet_balances(db, table)
        for seat in table.seats:
            if seat.websocket is not None and not seat.is_bot:
                state = self._build_client_state(table, seat.seat_index, balances)
                await self._send_to_seat(table, seat.seat_index, state)

    async def _send_error(
        self,
        table: LobbyTable,
        seat_idx: int,
        code: str,
        detail: str,
    ) -> None:
        await self._send_to_seat(
            table,
            seat_idx,
            {"type": "error", "code": code, "detail": detail},
        )

    async def connect_player(
        self, table: LobbyTable, user: User, websocket: WebSocket
    ) -> int | None:
        """Seat or reconnect ``user`` at ``table`` and start a hand if ready."""
        async with table.lock:
            assigned_seat: TableSeat | None = None
            for seat in table.seats:
                if seat.user_id == user.id:
                    assigned_seat = seat
                    break
            if assigned_seat is None:
                for seat in table.seats:
                    if seat.user_id is None and not seat.is_bot:
                        assigned_seat = seat
                        break

            if assigned_seat is None:
                return None

            await websocket.accept()
            assigned_seat.user_id = user.id
            assigned_seat.username = user.username
            assigned_seat.websocket = websocket
            assigned_seat.connected = True

            both_ready = all(
                s.user_id is not None and (s.is_bot or s.connected) for s in table.seats
            )
            if both_ready and table.active_hand is None:
                await self._start_hand_locked(table)
            else:
                await self._broadcast_state(table)

            return assigned_seat.seat_index

    async def disconnect_player(self, table: LobbyTable, seat_idx: int) -> None:
        """Handle WebSocket disconnect, forfeiting any in-progress hand atomically."""
        async with table.lock:
            seat = table.seats[seat_idx]
            seat.connected = False
            seat.websocket = None

            if table.active_hand is not None:
                self._cancel_timer(table)
                await self._resolve_fold_locked(
                    table,
                    folder_idx=seat_idx,
                    reason="disconnect_forfeit",
                )
            else:
                if all(s.is_bot or not s.connected for s in table.seats):
                    table.status = GameStatus.WAITING.value
                await self._broadcast_state(table)

    async def handle_message(self, table: LobbyTable, seat_idx: int, raw_text: str) -> None:
        """Parse, validate, and process an incoming client WebSocket event."""
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            async with table.lock:
                await self._send_error(table, seat_idx, "invalid_json", "Invalid JSON payload.")
            return

        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            async with table.lock:
                await self._send_error(
                    table, seat_idx, "invalid_message", "Message must include string 'type'."
                )
            return

        msg_type = payload["type"]
        async with table.lock:
            if msg_type == "next_hand":
                if table.active_hand is not None:
                    await self._send_error(
                        table, seat_idx, "hand_in_progress", "Current hand is still active."
                    )
                    return
                both_ready = all(
                    s.user_id is not None and (s.is_bot or s.connected) for s in table.seats
                )
                if not both_ready:
                    await self._send_error(
                        table, seat_idx, "waiting_for_opponent", "Opponent is not connected."
                    )
                    return
                await self._start_hand_locked(table)
                return

            if msg_type != "action":
                await self._send_error(
                    table, seat_idx, "unknown_event", f"Unsupported event type {msg_type!r}."
                )
                return

            hand = table.active_hand
            if hand is None:
                await self._send_error(table, seat_idx, "no_active_hand", "No hand is in progress.")
                return
            if hand.current_turn != seat_idx:
                await self._send_error(table, seat_idx, "not_your_turn", "It is not your turn.")
                return

            raw_action = payload.get("action")
            raw_amount = payload.get("amount", 0)
            try:
                action_type = ActionType(raw_action)
            except ValueError:
                await self._send_error(
                    table, seat_idx, "illegal_move", f"Invalid action {raw_action!r}."
                )
                return

            if isinstance(raw_amount, bool) or not isinstance(raw_amount, int):
                await self._send_error(
                    table, seat_idx, "illegal_move", "Bet amount must be an integer."
                )
                return

            chosen = PlayerAction(action=action_type, amount=raw_amount)
            with self.session_factory() as db:
                balances = self._load_wallet_balances(db, table)
            obs = self._build_observation(table, hand, seat_idx, balances)

            try:
                validate_player_action(obs, chosen)
            except ValueError as exc:
                await self._send_error(table, seat_idx, "illegal_move", str(exc))
                return

            self._cancel_timer(table)
            await self._apply_action_locked(table, seat_idx, chosen)

    async def _start_hand_locked(self, table: LobbyTable) -> None:
        """Deal private state using LiveRNG and atomically debit both antes."""
        engine = self._make_engine(table)
        next_hand_num = table.hand_count + 1

        if table.game_type == "dice_betting":
            v0 = self._rng.randint(1, 6)
            v1 = self._rng.randint(1, 6)
            labels = (f"d6:{v0}", f"d6:{v1}")
        else:
            c0, c1 = self._rng.sample(range(52), 2)
            v0, v1 = c0 % 13, c1 % 13
            labels = (format_card(c0), format_card(c1))

        probs = (engine.exact_showdown_probs(v0), engine.exact_showdown_probs(v1))
        first_actor = (next_hand_num - 1) % 2

        with self.session_factory() as db:
            try:
                w0 = db.scalar(select(Wallet).where(Wallet.user_id == table.seats[0].user_id))
                w1 = db.scalar(select(Wallet).where(Wallet.user_id == table.seats[1].user_id))
                if w0 is None or w1 is None:
                    raise LobbyError("Both players must have valid wallets.")

                # Replenish bot wallet if needed before starting a hand.
                for idx, wallet in ((0, w0), (1, w1)):
                    if table.seats[idx].is_bot and wallet.balance < table.ante + table.max_bet:
                        record_transaction(
                            db,
                            wallet,
                            amount=100_000,
                            tx_type=TransactionType.ADJUSTMENT,
                            description="Bot bankroll replenishment",
                        )

                if w0.balance < table.ante or w1.balance < table.ante:
                    raise InsufficientFundsError(
                        f"Both players need at least {table.ante} coins for the ante."
                    )

                game_row = db.get(Game, table.table_id)
                if game_row is None:
                    raise LobbyError("Game record not found.")
                game_row.status = GameStatus.ACTIVE.value

                hand_row = Hand(
                    game_id=table.table_id,
                    hand_number=next_hand_num,
                    state_json=json.dumps({"private_labels": list(labels)}),
                    pot=2 * table.ante,
                    status=HandStatus.IN_PROGRESS.value,
                )
                db.add(hand_row)
                db.flush()

                record_transaction(
                    db,
                    w0,
                    amount=-table.ante,
                    tx_type=TransactionType.WAGER,
                    description=f"Table #{table.table_id} Hand #{next_hand_num} ante",
                    hand_id=hand_row.id,
                )
                record_transaction(
                    db,
                    w1,
                    amount=-table.ante,
                    tx_type=TransactionType.WAGER,
                    description=f"Table #{table.table_id} Hand #{next_hand_num} ante",
                    hand_id=hand_row.id,
                )
                db.commit()
                hand_id = hand_row.id
            except Exception as exc:
                db.rollback()
                await self._broadcast(
                    table,
                    {"type": "error", "code": "cannot_start_hand", "detail": str(exc)},
                )
                return

        table.status = GameStatus.ACTIVE.value
        table.hand_count = next_hand_num
        table.active_hand = ActiveHandState(
            hand_id=hand_id,
            hand_number=next_hand_num,
            private_values=(v0, v1),
            private_labels=labels,
            showdown_probs=probs,
            pot=2 * table.ante,
            contributions=[table.ante, table.ante],
            first_actor=first_actor,
            current_turn=first_actor,
        )

        await self._broadcast_state(table)
        await self._drive_bot_turns_or_schedule_timer(table)

    async def _drive_bot_turns_or_schedule_timer(self, table: LobbyTable) -> None:
        while table.active_hand is not None:
            hand = table.active_hand
            turn_seat = table.seats[hand.current_turn]
            if not turn_seat.is_bot or turn_seat.bot is None:
                self._schedule_timer(table, hand.hand_number, hand.current_turn)
                return

            with self.session_factory() as db:
                balances = self._load_wallet_balances(db, table)
            obs = self._build_observation(table, hand, turn_seat.seat_index, balances)
            bot_action = validate_player_action(obs, turn_seat.bot.decide(obs, self._rng))
            await self._apply_action_locked(table, turn_seat.seat_index, bot_action)

    async def _apply_action_locked(
        self,
        table: LobbyTable,
        seat_idx: int,
        action: PlayerAction,
        *,
        is_auto: bool = False,
    ) -> None:
        hand = table.active_hand
        if hand is None:
            return

        with self.session_factory() as db:
            pre_balances = self._load_wallet_balances(db, table)
        obs = self._build_observation(table, hand, seat_idx, pre_balances)

        if action.action == ActionType.FOLD:
            hand.pending_decisions.append(
                RecordedDecision(
                    seat_index=seat_idx,
                    observation=obs,
                    action=action,
                    is_auto=is_auto,
                )
            )
            await self._broadcast(
                table,
                {
                    "type": "hand:action",
                    "seat": seat_idx,
                    "username": table.seats[seat_idx].username,
                    "action": action.action.value,
                    "amount": 0,
                },
            )
            await self._resolve_fold_locked(table, folder_idx=seat_idx, reason="fold")
            return

        wager_debit = 0
        if action.action == ActionType.BET:
            wager_debit = action.amount
        elif action.action == ActionType.CALL:
            wager_debit = hand.bet_amount

        if wager_debit > 0:
            with self.session_factory() as db:
                try:
                    wallet = db.scalar(
                        select(Wallet).where(Wallet.user_id == table.seats[seat_idx].user_id)
                    )
                    if wallet is None:
                        raise LobbyError("Wallet not found.")
                    record_transaction(
                        db,
                        wallet,
                        amount=-wager_debit,
                        tx_type=TransactionType.WAGER,
                        description=(
                            f"Table #{table.table_id} Hand #{hand.hand_number} "
                            f"{action.action.value}"
                        ),
                        hand_id=hand.hand_id,
                    )
                    hand_row = db.get(Hand, hand.hand_id)
                    if hand_row is not None:
                        hand_row.pot = hand.pot + wager_debit
                    db.commit()
                except InsufficientFundsError as exc:
                    db.rollback()
                    await self._send_error(table, seat_idx, "insufficient_funds", str(exc))
                    self._schedule_timer(table, hand.hand_number, seat_idx)
                    return
                except Exception as exc:
                    db.rollback()
                    await self._send_error(table, seat_idx, "wager_failed", str(exc))
                    return

            hand.contributions[seat_idx] += wager_debit
            hand.pot += wager_debit

        hand.pending_decisions.append(
            RecordedDecision(
                seat_index=seat_idx,
                observation=obs,
                action=action,
                is_auto=is_auto,
            )
        )
        hand.actions_taken += 1
        await self._broadcast(
            table,
            {
                "type": "hand:action",
                "seat": seat_idx,
                "username": table.seats[seat_idx].username,
                "action": action.action.value,
                "amount": wager_debit,
            },
        )

        if action.action == ActionType.BET:
            hand.has_bet = True
            hand.bet_amount = action.amount
            hand.current_turn = 1 - seat_idx
            await self._broadcast_state(table)
            await self._drive_bot_turns_or_schedule_timer(table)
            return

        if action.action == ActionType.CALL:
            await self._resolve_showdown_locked(table)
            return

        # CHECK
        if hand.actions_taken >= 2:
            await self._resolve_showdown_locked(table)
            return

        hand.current_turn = 1 - seat_idx
        await self._broadcast_state(table)
        await self._drive_bot_turns_or_schedule_timer(table)

    def _persist_decision_grades(
        self,
        db: Session,
        table: LobbyTable,
        hand: ActiveHandState,
    ) -> list[dict[str, Any]]:
        """Grade all decisions in ``hand`` and store DecisionGrade rows in ``db``."""
        grades_payload: list[dict[str, Any]] = []
        for decision_idx, rec in enumerate(hand.pending_decisions, start=1):
            seat = table.seats[rec.seat_index]
            if seat.user_id is None:
                continue
            ev = grade_decision(rec.observation, rec.action)
            grade_row = DecisionGrade(
                hand_id=hand.hand_id,
                game_id=table.table_id,
                user_id=seat.user_id,
                seat_index=rec.seat_index,
                decision_index=decision_idx,
                game_type=table.game_type,
                private_label=rec.observation.private_label,
                equity=rec.observation.equity,
                pot_before=rec.observation.pot,
                to_call=rec.observation.to_call,
                taken_action=ev.taken_action.value,
                taken_amount=ev.taken_amount,
                taken_ev=ev.taken_ev,
                best_action=ev.best_action.value,
                best_amount=ev.best_amount,
                best_ev=ev.best_ev,
                regret=ev.regret,
                is_auto=rec.is_auto,
            )
            db.add(grade_row)
            grades_payload.append(
                {
                    "seat": rec.seat_index,
                    "username": seat.username,
                    "decision_index": decision_idx,
                    "private_label": rec.observation.private_label,
                    "equity": round(rec.observation.equity, 6),
                    "taken_action": ev.taken_action.value,
                    "taken_amount": ev.taken_amount,
                    "taken_ev": ev.taken_ev,
                    "best_action": ev.best_action.value,
                    "best_amount": ev.best_amount,
                    "best_ev": ev.best_ev,
                    "regret": ev.regret,
                    "is_auto": rec.is_auto,
                }
            )
        return grades_payload

    async def _resolve_fold_locked(
        self,
        table: LobbyTable,
        *,
        folder_idx: int,
        reason: str,
    ) -> None:
        hand = table.active_hand
        if hand is None:
            return
        self._cancel_timer(table)

        winner_idx = 1 - folder_idx
        pot = hand.pot

        with self.session_factory() as db:
            try:
                winner_wallet = db.scalar(
                    select(Wallet).where(Wallet.user_id == table.seats[winner_idx].user_id)
                )
                if winner_wallet is None:
                    raise LobbyError("Winner wallet not found.")

                record_transaction(
                    db,
                    winner_wallet,
                    amount=pot,
                    tx_type=TransactionType.PAYOUT,
                    description=(
                        f"Table #{table.table_id} Hand #{hand.hand_number} win ({reason})"
                    ),
                    hand_id=hand.hand_id,
                )
                graded_payloads = self._persist_decision_grades(db, table, hand)
                hand_row = db.get(Hand, hand.hand_id)
                if hand_row is not None:
                    hand_row.pot = pot
                    hand_row.status = HandStatus.COMPLETED.value
                    hand_row.completed_at = utc_now()
                db.commit()
            except Exception:
                db.rollback()
                raise

        net = [0, 0]
        net[winner_idx] = pot - hand.contributions[winner_idx]
        net[folder_idx] = -hand.contributions[folder_idx]

        table.active_hand = None
        table.status = GameStatus.WAITING.value

        with self.session_factory() as db:
            balances = self._load_wallet_balances(db, table)

        # Keep folded private cards & opponent EV/equity private on fold/forfeit!
        for seat in table.seats:
            if seat.websocket is not None and not seat.is_bot:
                own_grades = [g for g in graded_payloads if g["seat"] == seat.seat_index]
                await self._send_to_seat(
                    table,
                    seat.seat_index,
                    {
                        "type": "hand:resolved",
                        "hand_number": hand.hand_number,
                        "reason": reason,
                        "winner_seat": winner_idx,
                        "winner_username": table.seats[winner_idx].username,
                        "pot": pot,
                        "net_profits": net,
                        "revealed_hands": None,
                        "decision_grades": own_grades,
                        "balances": list(balances),
                    },
                )
        await self._broadcast_state(table)

    async def _resolve_showdown_locked(self, table: LobbyTable) -> None:
        hand = table.active_hand
        if hand is None:
            return
        self._cancel_timer(table)

        v0, v1 = hand.private_values
        pot = hand.pot

        if v0 > v1:
            winner_idx: int | None = 0
            payouts = (pot, 0)
        elif v1 > v0:
            winner_idx = 1
            payouts = (0, pot)
        else:
            winner_idx = None
            half = pot // 2
            payouts = (pot - half, half)

        with self.session_factory() as db:
            try:
                for idx, payout in enumerate(payouts):
                    if payout <= 0:
                        continue
                    wallet = db.scalar(
                        select(Wallet).where(Wallet.user_id == table.seats[idx].user_id)
                    )
                    if wallet is None:
                        raise LobbyError("Player wallet not found.")
                    tx_type = (
                        TransactionType.PAYOUT
                        if winner_idx is not None
                        else TransactionType.REFUND
                    )
                    record_transaction(
                        db,
                        wallet,
                        amount=payout,
                        tx_type=tx_type,
                        description=f"Table #{table.table_id} Hand #{hand.hand_number} showdown",
                        hand_id=hand.hand_id,
                    )

                graded_payloads = self._persist_decision_grades(db, table, hand)
                hand_row = db.get(Hand, hand.hand_id)
                if hand_row is not None:
                    hand_row.pot = pot
                    hand_row.status = HandStatus.COMPLETED.value
                    hand_row.completed_at = utc_now()
                db.commit()
            except Exception:
                db.rollback()
                raise

        net = [payouts[0] - hand.contributions[0], payouts[1] - hand.contributions[1]]
        table.active_hand = None
        table.status = GameStatus.WAITING.value

        with self.session_factory() as db:
            balances = self._load_wallet_balances(db, table)

        await self._broadcast(
            table,
            {
                "type": "hand:resolved",
                "hand_number": hand.hand_number,
                "reason": "showdown",
                "winner_seat": winner_idx,
                "winner_username": (
                    table.seats[winner_idx].username if winner_idx is not None else None
                ),
                "pot": pot,
                "net_profits": net,
                "revealed_hands": [
                    {"seat": 0, "label": hand.private_labels[0], "value": v0},
                    {"seat": 1, "label": hand.private_labels[1], "value": v1},
                ],
                "decision_grades": graded_payloads,
                "balances": list(balances),
            },
        )
        await self._broadcast_state(table)
