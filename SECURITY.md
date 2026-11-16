# Security Policy & Architecture Note

## 1. Educational Scope (Virtual Coins Only)
Edge Lab is an educational portfolio project for quantitative probability, expected value (EV) decision grading, and market-making simulation. **There is no real money, fiat payment processing, cryptocurrency, or financial custody.** All virtual coins exist solely as integer ledger entries in SQLite (`1,000` starting coins per account).

---

## 2. Implemented Security Controls

### Authentication & Password Storage (`app/security.py`, `app/auth.py`)
- **Argon2id Hashing**: Passwords are hashed and verified using `argon2-cffi` (`PasswordHasher`) with automatic parameter rehash checks (`password_needs_rehash`) on successful login.
- **Username-Enumeration Timing Mitigation**: Failed logins for nonexistent usernames execute a dummy Argon2id verification (`_DUMMY_PASSWORD_HASH`) so response latency remains uniform across valid and invalid usernames.
- **Session Tokens**: Login and registration generate 256-bit URL-safe tokens via `secrets.token_urlsafe(32)`. Only the **SHA-256 hex digest** (`token_hash`) is persisted in `user_sessions`—raw tokens are never stored in the database.
- **Cookie Flags & Revocation**: Session cookies are marked `HttpOnly`, use `SameSite=Lax` over HTTP (`SameSite=None; Secure` when TLS / `X-Forwarded-Proto: https` or `EDGE_LAB_COOKIE_SECURE=true` is active), and are explicitly revoked in the database (`revoked_at`) on `POST /api/auth/logout`.

### Server-Authoritative Randomness & Hidden-State Privacy
- **Cryptographic RNG for Live Play (`app/games/rng.py`)**: All live WebSocket games, calibration prompts, and order-book market sessions use `LiveRNG`, backed by `random.SystemRandom` (`os.urandom`), never client-supplied seeds or client-side randomness. Deterministic `SeededRNG` is reserved strictly for reproducible simulations and tests.
- **Anti-Cheat Privacy Filtering**:
  - **Heads-Up Games (`app/lobby.py`, `app/games/engine.py`)**: Players only receive `PlayerObservation` payloads containing their own private card/die and public pot state; opponent cards/dice remain on the server until showdown.
  - **Probability Calibration (`app/calibration_routes.py`)**: Active prompts never expose `true_probability` or `actual_outcome` before the user submits an estimate.
  - **Order Book Simulator (`app/orderbook_routes.py`)**: Active sessions omit `fair_value`, `mtm_pnl`, `bot_kind`, and `adverse_selection` (`analysis` remains `null` until completion).
- **Ownership Enforcement**: Protected session endpoints (`/api/orderbook/sessions/{id}`, `/api/calibration/...`) verify `session.user_id == current_user.id` and reject unauthorized access (`401` unauthenticated, `403` wrong owner).

### Data Integrity & Input Validation
- **Pydantic Validation (`app/schemas.py`)**: All REST and WebSocket payloads enforce strict types, bounds, quote ordering (`0 < bid_price < ask_price`), and non-boolean integer checks.
- **Append-Only Coin Ledger (`app/ledger.py`)**: Every coin movement writes an immutable `Transaction` row alongside `Wallet.balance`. `record_transaction` rejects negative balances (`InsufficientFundsError`), and `audit_wallet_balance` verifies `SUM(Transaction.amount) == Wallet.balance` and sequential `balance_after` consistency.
- **Parameterized Queries**: All database access uses SQLAlchemy 2.0 ORM and parameterized statements; raw SQL string interpolation is never used.

---

## 3. Known Limitations & Hardening Before Public Deployment
If deploying Edge Lab beyond local study or a private demo:
1. **Rate Limiting**: Login, registration, and Monte Carlo endpoints do not include built-in rate limiting or brute-force lockouts; place a reverse proxy (Nginx, Caddy, Cloudflare) in front with IP/route throttling.
2. **CSRF Protection**: State-changing POST routes rely on `SameSite` cookie attributes rather than double-submit CSRF tokens. Avoid setting `EDGE_LAB_COOKIE_SECURE=true` with cross-origin embedding unless an explicit CSRF token header is added.
3. **Single-Process WebSocket State**: `LobbyManager` holds active table state in memory; running multiple Uvicorn workers without sticky sessions or a shared Redis broker will split lobbies.
4. **Transport Security**: Always terminate HTTPS at a reverse proxy and set `EDGE_LAB_COOKIE_SECURE=true` in production.

---

## 4. Reporting a Vulnerability
Because this is an educational open-source project, please do not open public GitHub issues with exploit details for live deployments. Instead, report security findings privately to the repository maintainer via email (`patilpranjal729@gmail.com`) or GitHub Private Vulnerability Reporting with:
- Affected endpoint or module
- Steps to reproduce
- Impact assessment
