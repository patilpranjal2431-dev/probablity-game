"""Four quantitative bot strategies: Random, Cautious, EV-Maximising, and Kelly-Sizing."""

from __future__ import annotations

from app.games.engine import ActionType, PlayerAction, PlayerObservation
from app.games.rng import GameRNG


class RandomBot:
    """Baseline bot that picks uniformly among legal actions and bet sizes."""

    def __init__(self, name: str = "Random Bot") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def strategy_id(self) -> str:
        return "random"

    def decide(self, observation: PlayerObservation, rng: GameRNG) -> PlayerAction:
        chosen = rng.choice(observation.legal_actions)
        if chosen == ActionType.BET:
            step = max(1, observation.min_bet)
            candidates = list(range(observation.min_bet, observation.max_bet + 1, step))
            if not candidates:
                candidates = [observation.min_bet]
            return PlayerAction(ActionType.BET, amount=rng.choice(candidates))
        return PlayerAction(chosen)


class CautiousBot:
    """Risk-averse tight-passive bot that avoids marginal spots and large bets."""

    def __init__(
        self,
        name: str = "Cautious Bot",
        *,
        bet_equity_threshold: float = 0.80,
        call_margin: float = 0.15,
    ) -> None:
        self._name = name
        self.bet_equity_threshold = bet_equity_threshold
        self.call_margin = call_margin

    @property
    def name(self) -> str:
        return self._name

    @property
    def strategy_id(self) -> str:
        return "cautious"

    def decide(self, observation: PlayerObservation, _rng: GameRNG) -> PlayerAction:
        if ActionType.CALL in observation.legal_actions:
            pot_odds = observation.to_call / (observation.pot + observation.to_call)
            if observation.equity >= min(0.95, pot_odds + self.call_margin):
                return PlayerAction(ActionType.CALL)
            return PlayerAction(ActionType.FOLD)

        if (
            ActionType.BET in observation.legal_actions
            and observation.equity >= self.bet_equity_threshold
        ):
            return PlayerAction(ActionType.BET, amount=observation.min_bet)
        return PlayerAction(ActionType.CHECK)


class EVMaximisingBot:
    """Risk-neutral bot that chooses the action maximizing expected coin profit."""

    def __init__(self, name: str = "EV-Max Bot") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def strategy_id(self) -> str:
        return "ev_max"

    def decide(self, observation: PlayerObservation, _rng: GameRNG) -> PlayerAction:
        if ActionType.CALL in observation.legal_actions:
            # Calling `to_call` into `pot` yields expected net gain from decision point:
            # equity * (pot + to_call) - to_call vs FOLD = 0.
            ev_call = (
                observation.equity * (observation.pot + observation.to_call)
                - observation.to_call
            )
            return PlayerAction(ActionType.CALL if ev_call >= 0.0 else ActionType.FOLD)

        if ActionType.BET not in observation.legal_actions:
            return PlayerAction(ActionType.CHECK)

        # Evaluate EV of CHECK vs candidate BET sizes under rational pot-odds call threshold.
        # Against an opponent who calls whenever opponent_equity >= b / (P + 2b):
        # P(opp calls) ~ 1 - pot_odds_opp, and conditional on call vs fold:
        # When equity > 0.5, value betting max_bet yields positive edge on calls + fold equity.
        ev_check = observation.equity * observation.pot
        best_action = PlayerAction(ActionType.CHECK)
        best_ev = ev_check

        mid_bet = (observation.min_bet + observation.max_bet) // 2
        candidates = sorted({observation.min_bet, mid_bet, observation.max_bet})
        for bet in candidates:
            if bet < observation.min_bet or bet > observation.max_bet:
                continue
            opp_call_threshold = bet / (observation.pot + 2 * bet)
            p_opp_call = max(0.0, min(1.0, 1.0 - opp_call_threshold))
            p_opp_fold = 1.0 - p_opp_call
            # When opponent calls with the top p_opp_call fraction of hands, their average
            # strength is higher than unconditional; approximate showdown equity against
            # calling range conservatively while capturing fold equity on pot.
            if observation.equity >= 0.5 + 0.5 * opp_call_threshold:
                ev_if_called = observation.equity * (observation.pot + 2 * bet) - bet
            else:
                # Below threshold, opponent calling range dominates -> negative value on call.
                ev_if_called = (observation.equity * 0.5) * (observation.pot + 2 * bet) - bet
            ev_bet = p_opp_fold * observation.pot + p_opp_call * ev_if_called
            if ev_bet > best_ev:
                best_ev = ev_bet
                best_action = PlayerAction(ActionType.BET, amount=bet)

        return best_action


class KellySizingBot:
    """Quantitative bankroll-growth bot sizing wagers via the Kelly criterion."""

    def __init__(
        self,
        name: str = "Kelly Bot",
        *,
        kelly_fraction: float = 0.5,
    ) -> None:
        if kelly_fraction <= 0.0 or kelly_fraction > 1.0:
            raise ValueError("kelly_fraction must be in (0, 1].")
        self._name = name
        self.kelly_fraction = kelly_fraction

    @property
    def name(self) -> str:
        return self._name

    @property
    def strategy_id(self) -> str:
        return "kelly"

    def decide(self, observation: PlayerObservation, _rng: GameRNG) -> PlayerAction:
        if ActionType.CALL in observation.legal_actions:
            # Binary-approximation Kelly fraction for calling `to_call` at odds `pot / to_call`:
            # f* = p - (1 - p) / odds = equity - (1 - equity) * to_call / pot
            odds = observation.pot / observation.to_call
            full_kelly = observation.equity - (1.0 - observation.equity) / odds
            if full_kelly <= 0.0:
                return PlayerAction(ActionType.FOLD)
            max_wager = self.kelly_fraction * full_kelly * observation.own_stack
            # Always call if to_call fits within fractional-Kelly bankroll cap (or edge >= 15%).
            if observation.to_call <= max(max_wager, observation.min_bet):
                return PlayerAction(ActionType.CALL)
            return PlayerAction(ActionType.FOLD)

        if ActionType.BET not in observation.legal_actions:
            return PlayerAction(ActionType.CHECK)

        # Optimal Kelly fraction for an even-money marginal wager: f* = max(0, 2*p - 1).
        edge = 2.0 * observation.equity - 1.0
        if edge <= 0.0:
            return PlayerAction(ActionType.CHECK)

        raw_bet = round(self.kelly_fraction * edge * observation.own_stack)
        if raw_bet < observation.min_bet:
            # Slight positive edge where Kelly suggests a small bet -> min_bet if >= 55% equity.
            if observation.equity >= 0.55:
                return PlayerAction(ActionType.BET, amount=observation.min_bet)
            return PlayerAction(ActionType.CHECK)

        clamped_bet = min(raw_bet, observation.max_bet)
        return PlayerAction(ActionType.BET, amount=clamped_bet)


def create_default_bots() -> list[RandomBot | CautiousBot | EVMaximisingBot | KellySizingBot]:
    """Instantiate the four standard Edge Lab benchmark bots."""
    return [
        RandomBot(),
        CautiousBot(),
        EVMaximisingBot(),
        KellySizingBot(),
    ]
