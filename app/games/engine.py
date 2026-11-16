"""Core pure-Python interfaces and state types for heads-up betting games."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.games.rng import GameRNG


class ActionType(str, Enum):
    """Legal betting actions in a heads-up round."""

    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"


@dataclass(frozen=True, slots=True)
class PlayerAction:
    """A validated action chosen by a player or bot."""

    action: ActionType
    amount: int = 0


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    """Information-safe view of a hand exposed to a single player.

    Crucially, this never contains the opponent's hidden die/card or RNG state.
    """

    game_type: str
    player_index: int
    private_value: int
    private_label: str
    exact_win_prob: float
    exact_tie_prob: float
    equity: float
    own_stack: int
    opponent_stack: int
    pot: int
    own_contribution: int
    opponent_contribution: int
    to_call: int
    ante: int
    min_bet: int
    max_bet: int
    legal_actions: tuple[ActionType, ...]


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """Audit record for a single player decision within a hand."""

    player_index: int
    player_name: str
    observation: PlayerObservation
    action: PlayerAction


@dataclass(frozen=True, slots=True)
class HandOutcome:
    """Result of a completed heads-up hand."""

    game_type: str
    hand_number: int
    winner_index: int | None
    net_profits: tuple[int, int]
    pot: int
    ended_by_fold: bool
    private_values: tuple[int, int]
    private_labels: tuple[str, str]
    decisions: list[DecisionRecord] = field(default_factory=list)


class Bot(Protocol):
    """Interface that all automated agents must implement."""

    @property
    def name(self) -> str: ...

    @property
    def strategy_id(self) -> str: ...

    def decide(self, observation: PlayerObservation, rng: GameRNG) -> PlayerAction: ...


class HeadsUpGame(Protocol):
    """Protocol implemented by pure-Python heads-up game engines."""

    @property
    def game_type(self) -> str: ...

    @property
    def ante(self) -> int: ...

    @property
    def min_bet(self) -> int: ...

    @property
    def max_bet(self) -> int: ...

    def exact_showdown_probs(self, private_value: int) -> tuple[float, float]:
        """Return (win_prob, tie_prob) against an unknown opponent draw."""
        ...

    def play_hand(
        self,
        bots: tuple[Bot, Bot],
        rng: GameRNG,
        *,
        stacks: tuple[int, int] = (1000, 1000),
        hand_number: int = 1,
    ) -> HandOutcome: ...


def validate_player_action(
    observation: PlayerObservation,
    chosen: PlayerAction,
) -> PlayerAction:
    """Ensure a player/bot action is legal and within stack/bet bounds."""
    if chosen.action not in observation.legal_actions:
        raise ValueError(
            f"Illegal action {chosen.action.value!r}; "
            f"legal actions are {[a.value for a in observation.legal_actions]}."
        )

    if chosen.action == ActionType.BET:
        if isinstance(chosen.amount, bool) or not isinstance(chosen.amount, int):
            raise ValueError("Bet amount must be an integer.")
        effective_max = min(observation.max_bet, observation.own_stack, observation.opponent_stack)
        if chosen.amount < observation.min_bet or chosen.amount > effective_max:
            raise ValueError(
                f"Bet amount {chosen.amount} out of bounds "
                f"[{observation.min_bet}, {effective_max}]."
            )
        return chosen

    if chosen.amount != 0:
        raise ValueError(f"Action {chosen.action.value!r} must have amount=0.")
    return chosen


def run_heads_up_betting_hand(
    *,
    game_type: str,
    private_values: tuple[int, int],
    private_labels: tuple[str, str],
    showdown_probs: tuple[tuple[float, float], tuple[float, float]],
    bots: tuple[Bot, Bot],
    rng: GameRNG,
    stacks: tuple[int, int],
    ante: int,
    min_bet: int,
    max_bet: int,
    hand_number: int,
) -> HandOutcome:
    """Execute one server-authoritative heads-up betting round and settle the pot."""
    if stacks[0] < ante or stacks[1] < ante:
        raise ValueError(f"Both players must have at least ante={ante} coins.")

    s0 = stacks[0] - ante
    s1 = stacks[1] - ante
    contrib = [ante, ante]
    pot = 2 * ante
    decisions: list[DecisionRecord] = []

    def make_obs(
        idx: int,
        legal: tuple[ActionType, ...],
        to_call: int,
    ) -> PlayerObservation:
        win_p, tie_p = showdown_probs[idx]
        own_s = s0 if idx == 0 else s1
        opp_s = s1 if idx == 0 else s0
        effective_max = min(max_bet, own_s, opp_s)
        return PlayerObservation(
            game_type=game_type,
            player_index=idx,
            private_value=private_values[idx],
            private_label=private_labels[idx],
            exact_win_prob=win_p,
            exact_tie_prob=tie_p,
            equity=win_p + 0.5 * tie_p,
            own_stack=own_s,
            opponent_stack=opp_s,
            pot=pot,
            own_contribution=contrib[idx],
            opponent_contribution=contrib[1 - idx],
            to_call=to_call,
            ante=ante,
            min_bet=min_bet,
            max_bet=effective_max,
            legal_actions=legal,
        )

    def settle_fold(folder_idx: int) -> HandOutcome:
        winner = 1 - folder_idx
        net = [0, 0]
        net[winner] = pot - contrib[winner]
        net[folder_idx] = -contrib[folder_idx]
        return HandOutcome(
            game_type=game_type,
            hand_number=hand_number,
            winner_index=winner,
            net_profits=(net[0], net[1]),
            pot=pot,
            ended_by_fold=True,
            private_values=private_values,
            private_labels=private_labels,
            decisions=decisions,
        )

    def settle_showdown() -> HandOutcome:
        v0, v1 = private_values
        if v0 > v1:
            winner: int | None = 0
            net0 = pot - contrib[0]
            net1 = -contrib[1]
        elif v1 > v0:
            winner = 1
            net0 = -contrib[0]
            net1 = pot - contrib[1]
        else:
            winner = None
            # Contributions are equal at showdown; split pot returns each player's stake.
            half = pot // 2
            remainder = pot - 2 * half
            net0 = (half + remainder) - contrib[0]
            net1 = half - contrib[1]
        return HandOutcome(
            game_type=game_type,
            hand_number=hand_number,
            winner_index=winner,
            net_profits=(net0, net1),
            pot=pot,
            ended_by_fold=False,
            private_values=private_values,
            private_labels=private_labels,
            decisions=decisions,
        )

    # Seat 0 acts first: CHECK or BET (if both stacks allow at least min_bet)
    can_open_bet = min(s0, s1) >= min_bet
    legal_0 = (ActionType.CHECK, ActionType.BET) if can_open_bet else (ActionType.CHECK,)
    obs0 = make_obs(0, legal_0, to_call=0)
    act0 = validate_player_action(obs0, bots[0].decide(obs0, rng))
    decisions.append(DecisionRecord(0, bots[0].name, obs0, act0))

    if act0.action == ActionType.BET:
        bet_amt = act0.amount
        s0 -= bet_amt
        contrib[0] += bet_amt
        pot += bet_amt

        obs1 = make_obs(1, (ActionType.FOLD, ActionType.CALL), to_call=bet_amt)
        act1 = validate_player_action(obs1, bots[1].decide(obs1, rng))
        decisions.append(DecisionRecord(1, bots[1].name, obs1, act1))

        if act1.action == ActionType.FOLD:
            return settle_fold(1)
        s1 -= bet_amt
        contrib[1] += bet_amt
        pot += bet_amt
        return settle_showdown()

    # Seat 0 checked; Seat 1 acts: CHECK or BET
    can_bet_1 = min(s0, s1) >= min_bet
    legal_1 = (ActionType.CHECK, ActionType.BET) if can_bet_1 else (ActionType.CHECK,)
    obs1 = make_obs(1, legal_1, to_call=0)
    act1 = validate_player_action(obs1, bots[1].decide(obs1, rng))
    decisions.append(DecisionRecord(1, bots[1].name, obs1, act1))

    if act1.action == ActionType.CHECK:
        return settle_showdown()

    bet_amt = act1.amount
    s1 -= bet_amt
    contrib[1] += bet_amt
    pot += bet_amt

    obs0_resp = make_obs(0, (ActionType.FOLD, ActionType.CALL), to_call=bet_amt)
    act0_resp = validate_player_action(obs0_resp, bots[0].decide(obs0_resp, rng))
    decisions.append(DecisionRecord(0, bots[0].name, obs0_resp, act0_resp))

    if act0_resp.action == ActionType.FOLD:
        return settle_fold(0)

    s0 -= bet_amt
    contrib[0] += bet_amt
    pot += bet_amt
    return settle_showdown()
