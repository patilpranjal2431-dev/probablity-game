"""Expected value (EV) decision grading and regret calculation for heads-up games."""

from __future__ import annotations

from dataclasses import dataclass

from app.games.engine import (
    ActionType,
    DecisionRecord,
    HandOutcome,
    PlayerAction,
    PlayerObservation,
    validate_player_action,
)

TIE_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    """Post-game EV grade for a single player decision."""

    taken_action: ActionType
    taken_amount: int
    taken_ev: float
    best_action: ActionType
    best_amount: int
    best_ev: float
    regret: float


def _opponent_outcomes(
    game_type: str,
    own_private_value: int,
) -> list[tuple[int, float, float]]:
    """Return exact (opp_value, prob, opp_unconditional_equity) outcomes."""
    if game_type == "dice_betting":
        # Default 6-sided independent die roll.
        num_sides = 6
        return [
            (opp_val, 1.0 / num_sides, (opp_val - 0.5) / num_sides)
            for opp_val in range(1, num_sides + 1)
        ]

    if game_type == "one_card_poker":
        # 52-card deck without replacement: 51 remaining cards across ranks 0..12.
        outcomes: list[tuple[int, float, float]] = []
        for opp_rank in range(13):
            remaining_count = 3 if opp_rank == own_private_value else 4
            opp_equity = (4 * opp_rank + 1.5) / 51.0
            outcomes.append((opp_rank, remaining_count / 51.0, opp_equity))
        return outcomes

    return []


def _evaluate_bet_ev(observation: PlayerObservation, bet_amount: int) -> float:
    """Compute incremental EV of betting ``bet_amount`` into ``observation.pot``.

    Models a rational pot-odds opponent: opponent calls iff their equity is at
    least ``bet / (pot + 2 * bet)``, otherwise folds immediately.
    """
    pot = observation.pot
    call_threshold = bet_amount / (pot + 2 * bet_amount)
    outcomes = _opponent_outcomes(observation.game_type, observation.private_value)

    if outcomes:
        ev = 0.0
        own_val = observation.private_value
        for opp_val, prob, opp_equity in outcomes:
            if opp_equity + TIE_EPSILON < call_threshold:
                # Opponent folds -> win existing pot.
                ev += prob * pot
            elif own_val > opp_val:
                # Opponent calls and loses -> win existing pot + opponent's call.
                ev += prob * (pot + bet_amount)
            elif own_val == opp_val:
                # Split pot -> net incremental gain is half the existing pot.
                ev += prob * (pot / 2.0)
            else:
                # Opponent calls and wins -> lose our incremental bet.
                ev -= prob * bet_amount
        return ev

    # Continuous fallback for custom synthetic observations.
    p_call = max(0.0, min(1.0, 1.0 - call_threshold))
    p_fold = 1.0 - p_call
    ev_if_called = observation.equity * (pot + bet_amount) - (1.0 - observation.equity) * bet_amount
    return p_fold * pot + p_call * ev_if_called


def evaluate_action_ev(observation: PlayerObservation, action: PlayerAction) -> float:
    """Compute the incremental expected coin profit of ``action`` from ``observation``.

    Payoffs are measured relative to the decision point (sunk ante/previous chips
    already inside ``observation.pot`` are sunk costs so they cancel cleanly in
    regret comparisons and ``EV(FOLD) = 0.0``):
    - ``FOLD``: ``0.0``
    - ``CALL``: ``equity * (pot + to_call) - to_call``
    - ``CHECK``: ``equity * pot``
    - ``BET b``: exact rational-response expectation over opponent's remaining hands
    """
    validate_player_action(observation, action)

    if action.action == ActionType.FOLD:
        return 0.0

    if action.action == ActionType.CALL:
        return (
            observation.equity * (observation.pot + observation.to_call)
            - observation.to_call
        )

    if action.action == ActionType.CHECK:
        return observation.equity * observation.pot

    # ActionType.BET
    return _evaluate_bet_ev(observation, action.amount)


def _candidate_bet_amounts(observation: PlayerObservation, chosen: PlayerAction) -> list[int]:
    """Generate candidate legal bet sizes to locate the EV-maximising wager."""
    effective_max = min(
        observation.max_bet,
        observation.own_stack,
        observation.opponent_stack,
    )
    if effective_max < observation.min_bet:
        return []

    span = effective_max - observation.min_bet
    if span <= 200:
        amounts = set(range(observation.min_bet, effective_max + 1))
    else:
        step = max(1, span // 100)
        amounts = set(range(observation.min_bet, effective_max + 1, step))
        amounts.add(observation.min_bet)
        amounts.add(effective_max)
        for frac in (observation.pot // 2, observation.pot, observation.pot * 2):
            if observation.min_bet <= frac <= effective_max:
                amounts.add(frac)

    if chosen.action == ActionType.BET and observation.min_bet <= chosen.amount <= effective_max:
        amounts.add(chosen.amount)

    return sorted(amounts)


def grade_decision(observation: PlayerObservation, chosen: PlayerAction) -> DecisionEvaluation:
    """Grade a chosen action against the highest-EV legal alternative.

    Returns ``taken_ev``, ``best_action``, ``best_ev``, and non-negative
    ``regret = max(0.0, best_ev - taken_ev)``.
    """
    taken_ev = evaluate_action_ev(observation, chosen)

    candidates: list[PlayerAction] = []
    for legal in observation.legal_actions:
        if legal == ActionType.BET:
            for amount in _candidate_bet_amounts(observation, chosen):
                candidates.append(PlayerAction(ActionType.BET, amount=amount))
        else:
            candidates.append(PlayerAction(legal, amount=0))

    best_action = chosen
    best_ev = taken_ev

    for cand in candidates:
        cand_ev = evaluate_action_ev(observation, cand)
        if cand_ev > best_ev + TIE_EPSILON:
            best_ev = cand_ev
            best_action = cand
        elif abs(cand_ev - best_ev) <= TIE_EPSILON:
            # Tie-breaking: prefer non-bet actions first, then smaller bets.
            if cand == chosen and abs(best_ev - taken_ev) <= TIE_EPSILON:
                best_action = chosen
            elif cand.action != ActionType.BET and best_action.action == ActionType.BET:
                best_action = cand
            elif (
                cand.action == ActionType.BET
                and best_action.action == ActionType.BET
                and cand.amount < best_action.amount
                and abs(best_ev - taken_ev) > TIE_EPSILON
            ):
                best_action = cand

    raw_regret = best_ev - taken_ev
    if abs(raw_regret) <= TIE_EPSILON:
        regret = 0.0
        best_ev = taken_ev
        best_action = chosen
    else:
        regret = max(0.0, raw_regret)

    return DecisionEvaluation(
        taken_action=chosen.action,
        taken_amount=chosen.amount,
        taken_ev=round(taken_ev, 6),
        best_action=best_action.action,
        best_amount=best_action.amount,
        best_ev=round(best_ev, 6),
        regret=round(regret, 6),
    )


def grade_hand_decisions(
    outcome: HandOutcome,
) -> list[tuple[DecisionRecord, DecisionEvaluation]]:
    """Grade every decision recorded in a completed pure-Python ``HandOutcome``."""
    return [(rec, grade_decision(rec.observation, rec.action)) for rec in outcome.decisions]
