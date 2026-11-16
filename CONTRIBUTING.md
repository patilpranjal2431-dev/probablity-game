# Contributing to Edge Lab

Welcome! Edge Lab is structured to stay readable, strictly typed, and thoroughly tested so a 2nd-year engineering student (or any contributor) can understand every module from first principles.

---

## 1. Local Development Setup

**Requirements**: Python `3.11+` (tested down to `3.10.12` locally and `3.11` / `3.12` in GitHub Actions CI).

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run the development server (default port `8000`, or `3000` inside preview containers):

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Optional environment overrides (see `app/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `EDGE_LAB_DATABASE_URL` | `sqlite:///./edge_lab.db` | SQLAlchemy database URL |
| `EDGE_LAB_INITIAL_WALLET_BALANCE` | `1000` | Starting virtual coins per user |
| `EDGE_LAB_SESSION_TTL_SECONDS` | `604800` (7 days) | Server session expiration |
| `EDGE_LAB_COOKIE_SECURE` | `false` | Force `Secure` flag on session cookie |
| `EDGE_LAB_TURN_TIMEOUT_SECONDS` | `30.0` | Live WebSocket lobby turn deadline |

---

## 2. Repository Map

```text
app/
├── main.py                 # FastAPI factory, lifespan init_db(), page routes, /health
├── config.py               # Immutable dataclass settings from environment
├── database.py             # SQLAlchemy 2.0 engine, SessionLocal, get_db dependency
├── models.py               # ORM tables: User, UserSession, Wallet, Transaction, Game, Hand,
│                           # DecisionGrade, CalibrationRound, OrderBookSession
├── schemas.py              # Pydantic v2 request/response contracts
├── security.py             # Argon2id password hashing + SHA-256 session tokens
├── auth.py                 # /api/auth/* + /api/profile routes
├── ledger.py               # Atomic record_transaction() + audit_wallet_balance()
├── quant/                  # Pure-Python probability & finance engines
│   ├── exact.py            # DP dice sums, 5-card poker combinatorics, hypergeometric, birthday
│   ├── monte_carlo.py      # Seeded estimators + Wilson 95% confidence intervals
│   ├── convergence.py      # Log-log O(1/sqrt(n)) slope & empirical CI coverage
│   ├── bankroll.py         # Kelly criterion, log-growth, Gambler's Ruin, MC trajectories
│   └── calibration.py      # Prompt generator, Brier score, 5-bin reliability curve
├── games/                  # Pure-Python game, bot, grading, and market engines
│   ├── rng.py              # GameRNG protocol: LiveRNG (SystemRandom) & SeededRNG
│   ├── engine.py           # Heads-up turn state machine & privacy-safe observations
│   ├── dice_game.py        # 1d6 heads-up betting rules
│   ├── card_game.py        # 1-Card Poker (52-card deck without replacement)
│   ├── bots.py             # RandomBot, CautiousBot, EVMaximisingBot, KellySizingBot
│   ├── tournament.py       # Round-robin seeded tournament runner + Wilson/t CIs
│   ├── grading.py          # Post-game action EV, best alternative, and regret
│   └── order_book.py       # Market-making simulator & P&L / adverse-selection accounting
├── lobby.py                # WebSocket LobbyManager (matches, timeouts, disconnects, settlement)
├── *_routes.py             # FastAPI routers connecting engines + DB to HTTP/WS endpoints
static/                     # Plain HTML, CSS, and vanilla JS + inline SVG charts
docs/                       # Plain-language algorithm guide (docs/index.html, docs/algorithms.md)
tests/                      # Pytest suite covering unit math, games, WebSockets, and APIs
```

---

## 3. Engineering Rules & Conventions

1. **Keep Pure Engines Decoupled from FastAPI & SQLAlchemy**
   - Put mathematical models and game rules in `app/quant/` or `app/games/` as pure typed functions/dataclasses.
   - Never import `Session` or `fastapi` inside `app/quant/*` or `app/games/*`.

2. **Live Randomness vs. Reproducible Simulations**
   - Live user-facing games, calibration prompts, and order-book market sessions must take a `LiveRNG` (`random.SystemRandom`).
   - Monte Carlo experiments, convergence sweeps, bankroll paths, and bot tournaments must accept an explicit integer `seed` and use `random.Random(seed)` / `SeededRNG(seed)` so results are 100% reproducible.

3. **Never Expose Hidden Server State**
   - When adding or modifying routes, verify that opponent cards, hidden fair values, or unsolved answers are omitted from responses until the round completes. Add an explicit privacy assertion in `tests/`.

4. **Atomic Coin Ledger Updates**
   - Never mutate `wallet.balance` directly. Always call `record_transaction(...)` in `app/ledger.py` inside a database transaction so `audit_wallet_balance()` holds after every operation.

5. **No Heavy Frontend Frameworks**
   - Keep frontend pages in plain HTML (`static/` or `docs/`), shared CSS (`static/styles.css`), vanilla JS, and inline `<svg>` charts.

6. **Type Hints & Style**
   - Target Python `3.10+` / `3.11+` typing (`from __future__ import annotations`, built-in `list[...]`, `dict[...]`, `X | None`).
   - Conform to `ruff` rules in `pyproject.toml` (`E`, `F`, `I`, `UP`, `B`, max line length `100`).

---

## 4. Running Tests & Checks

Before opening a pull request, run the full verification suite:

```bash
# 1. Lint Python code
.venv/bin/ruff check app tests

# 2. Run all tests with line coverage
.venv/bin/pytest -v --cov=app --cov-report=term-missing

# 3. Verify vanilla JS syntax
for f in static/*.js; do node --check "$f"; done
```

### Testing Exact Probability & Conservation Laws
- Exact probability modules must be tested against known closed-form values (for example, the `2,598,960` 5-card poker hand counts and `sum(probs.values()) == 1.0`).
- Accounting modules must assert exact conservation identities (e.g., `audit_wallet_balance`, zero-sum match settlements, and `Total P&L == Spread Captured - Adverse Selection + Inventory Drift`).

---

## 5. Commit Message Style

Use clear Conventional Commits describing the phase or scope:

- `feat(quant): add fractional Kelly comparison endpoint`
- `fix(lobby): guard disconnect forfeiture race on turn timer`
- `docs(algorithms): clarify adverse selection sign convention`
- `test(orderbook): add edge case for zero volatility market`
