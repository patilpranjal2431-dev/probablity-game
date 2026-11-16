# Edge Lab — Algorithms Explained in Plain Language

This guide explains every algorithm inside Edge Lab without heavy notation. If you want to read the code right alongside each explanation, every section links to the exact Python module.

---

## 1. Exact Dice Sums by Dynamic Programming (`app/quant/exact.py`)

**The problem**: If you roll $d$ fair 6-sided dice, how many ways can they add up to each total $s$? Checking every combination by brute force takes $6^d$ steps, which explodes quickly.

**How it works**: Instead of listing every sequence of rolls, we count how many ways we can reach each running sum **one die at a time**:
1. Before rolling any dice, there is `1` way to have sum `0`: `{0: 1}`.
2. For each new die, we take every `(running_sum, ways)` in our current table and add `1, 2, ..., 6` to `running_sum`, adding `ways` into the new sum's count.
3. After $d$ dice, dividing each count by $6^d$ gives the exact probability.

**Why it matters**: Dynamic programming collapses exponential combinations ($6^d$) into a small table whose size only grows linearly with the number of dice and faces.

---

## 2. Counting All 2,598,960 Five-Card Poker Hands (`app/quant/exact.py`)

**The problem**: Out of all $\binom{52}{5} = 2,598,960$ possible 5-card hands, what is the exact chance of being dealt a Royal Flush, Full House, One Pair, etc.?

**How it works**: We use combinatorics (`math.comb`) to count mutually exclusive categories carefully so no hand is double-counted:
- **Royal Flush**: `4` hands (one per suit: 10-J-Q-K-A).
- **Straight Flush**: `10` possible high cards (5-high wheel up to A-high) $\times 4$ suits, minus the `4` Royal Flushes = `36`.
- **Flush (non-straight)**: Choose 5 cards from one of 4 suits ($4 \times \binom{13}{5}$), minus the `40` straight/royal flushes = `5,108`.
- **High Card**: Choose 5 distinct ranks that do not form a straight ($\binom{13}{5} - 10$), with suits that are not all identical ($4^5 - 4$) = `1,302,540`.

Every category sums to **exactly `2,598,960`**, which our unit tests enforce as an invariant.

---

## 3. Hypergeometric & Birthday Collisions (`app/quant/exact.py`)

- **Hypergeometric (`hypergeometric_pmf`)**: Sampling *without replacement* (like drawing 5 cards from a 52-card deck containing 4 Aces). Unlike coin flips, each draw changes the deck's composition. We compute:
  $$P(X = k) = \frac{\binom{K}{k}\binom{N-K}{n-k}}{\binom{N}{n}}$$
- **Birthday Collision (`birthday_collision_probability`)**: Rather than counting all ways *at least two* people share a birthday, it is much simpler to compute the complement—everyone having *distinct* birthdays:
  $$P(\text{at least one match}) = 1 - \prod_{i=0}^{m-1} \frac{365 - i}{365}$$
  At $m = 23$ people, this already crosses **50.7%**.

---

## 4. Monte Carlo, Wilson Confidence Intervals & $1/\sqrt{n}$ Convergence (`app/quant/monte_carlo.py`, `app/quant/convergence.py`)

**How Monte Carlo works**: When a formula is unknown or hard to derive, run $n$ independent simulated trials with a fixed `seed` and take the fraction of successes $\hat{p} = k / n$.

**Why Wilson intervals instead of the textbook $\hat{p} \pm 1.96\sqrt{\hat{p}(1-\hat{p})/n}$?**
The simple textbook ("Wald") interval breaks near $p = 0$ or $p = 1$ (it can collapse to zero width when $k=0$ or overshoot $[0, 1]$). The **Wilson score interval** solves the quadratic boundary equation directly so it always stays inside $[0, 1]$ and achieves near-95% coverage even on rare events like Four of a Kind.

**Why $1/\sqrt{n}$?**
By the Central Limit Theorem, Monte Carlo standard error shrinks proportionally to $1/\sqrt{n}$. To cut your error in **half**, you must run **4× as many trials**. On a log-log plot of $|\hat{p} - p|$ vs. $n$, the error tracks a straight line of slope **$-0.5$**.

---

## 5. The Four Quantitative Bots (`app/games/bots.py`)

All four bots play the same heads-up Dice Betting and 1-Card Poker rules through a single `PlayerObservation` interface (never seeing the opponent's hidden card/die):

1. **Random Bot**: Picks uniformly among legal actions and bet sizes. Baseline benchmark.
2. **Cautious Bot**: Only calls when its showdown equity beats pot odds by a safety margin (`+15%`), and only bets the minimum when it holds a monster (`>= 80%` equity). Avoids variance, misses thin value.
3. **EV-Maximising Bot**: Risk-neutral decision maker.
   - Facing a bet, calls whenever $\text{EV}(\text{CALL}) = \text{equity} \cdot (\text{pot} + \text{to\_call}) - \text{to\_call} \ge 0$.
   - First to act, checks candidate bet sizes against a pot-odds-rational opponent and picks the action with the highest expected coin profit.
4. **Kelly-Sizing Bot**: Maximizes long-run *logarithmic bankroll growth* rather than single-hand EV. It computes the fractional Kelly wager (`0.5 * f* * stack`) so it bets aggressively when it has a big edge and scales back to protect its stack from ruin.

---

## 6. Decision EV Grading & Regret (`app/games/grading.py`)

**Why coins alone mislead you**: In a short session, lucky cards can beat good math. Edge Lab grades **what you knew when you acted**—before the opponent's card or die is revealed.

After every hand completes:
1. We reconstruct your exact decision point (`pot`, `to_call`, your `equity`, and legal actions).
2. We compute the exact incremental Expected Value of every legal action (`FOLD = 0`, `CALL`, `CHECK`, or `BET b`).
3. Your **Regret** is:
   $$\text{Regret} = \text{Best Legal EV} - \text{Taken EV} \ge 0$$

- **Skill Leaderboard**: Ranks players by **Cumulative EV** (and lowest average regret).
- **Coins Leaderboard**: Ranks players by **Audited Wallet Balance** (Skill + Luck).

---

## 7. Bankroll Simulator: Kelly Criterion & Risk of Ruin (`app/quant/bankroll.py`)

- **Kelly Criterion**: If a bet wins with probability $p$ and pays $b$ to $1$ on a win (losing $1$ on a loss), the fraction of your bankroll that maximizes long-run compound growth is:
  $$f^* = \max\left(0,\; p - \frac{1 - p}{b}\right)$$
  Betting *more* than $2f^*$ actually gives **negative expected growth** even with a positive edge! That is why quant desks often use **Half-Kelly** ($\frac{1}{2} f^*$), capturing 75% of the optimal growth rate with dramatically smaller drawdowns.
- **Risk of Ruin**: For fixed-unit even-money bets ($b=1$), classical **Gambler's Ruin** gives an exact closed-form probability of hitting zero from $k$ units when $p > 0.5$:
  $$P(\text{ruin}) = \left(\frac{1 - p}{p}\right)^k$$
  For proportional sizing or arbitrary odds, Edge Lab simulates hundreds of seeded bankroll trajectories and reports P10 / Median / P90 paths and a Wilson CI around empirical ruin.

---

## 8. Probability Calibration & Brier Score (`app/quant/calibration.py`)

Being "right" about a coin flip isn't just picking a winner—it's stating probabilities whose long-run frequencies match your predictions (when you say `70%`, the event should happen ~70% of the time).

Edge Lab scores each forecast $\hat{p} \in [0, 1]$ against the binary outcome $y \in \{0, 1\}$ using the **Brier Score**:
$$\text{Brier Score} = (\hat{p} - y)^2$$
- **0.00** is a clairvoyant perfect forecast.
- **0.25** is the score of always guessing `50%` on a fair coin.
- Because the Brier score is a **strictly proper scoring rule**, your expected score is minimized *if and only if* you report your true belief $\hat{p} = p_{\text{true}}$.

The calibration chart groups your predictions into 5 buckets (`0–20%`, ..., `80–100%`) and plots predicted probability vs. actual empirical hit rate against the ideal 45° diagonal.

---

## 9. Order Book Market Making & Adverse Selection (`app/games/order_book.py`)

**The market maker's dilemma**: Market makers earn the **half-spread** on uninformed retail/noise flow, but lose whenever **informed arbitrageurs** ("toxic flow") pick off stale quotes whose prices are wrong relative to the true fair value $V_t$.

In each round:
1. The server updates hidden fair value $V_t$ and shows you a noisy `public_signal`.
2. You post a `bid_price`, `ask_price`, and `quote_size` (capped by `max_inventory`).
3. Three bot types interact with your resting quotes:
   - **Informed Arb** buys your ask if $\text{ask} < V_t - 0.10$ or hits your bid if $\text{bid} > V_t + 0.10$.
   - **Noise Trader** & **Retail Flow** trade randomly around fair value if your spread isn't prohibitively wide.
4. At session end, Edge Lab reveals $V_t$ and verifies the exact accounting identity:
   $$\text{Total P\&L} = \underbrace{\sum q \cdot \frac{\text{ask} - \text{bid}}{2}}_{\text{Spread Captured}} - \underbrace{\sum q \cdot d \cdot (\text{midpoint} - V_t)}_{\text{Adverse Selection Cost}} + \underbrace{\sum Q_{t-1}(V_t - V_{t-1})}_{\text{Inventory Drift}}$$
   where $d = +1$ when you buy (hit on your bid) and $d = -1$ when you sell (lifted on your ask).
