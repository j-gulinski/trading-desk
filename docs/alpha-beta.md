# Alpha and beta per book — a step-by-step guide

What the ALPHA / BETA cards mean, how the numbers are computed tick by tick, how to
read them, and what changes when real market data arrives.

## 1. The idea in 60 seconds

Every book is compared against one benchmark (`MARKET_INDEX`). Two questions:

- **Beta — "how much of this book's PnL is just the market?"**
  β = 1.3 means: when the market moves +1%, this book tends to gain 1.3% of its
  capital. It measures *exposure*.
- **Alpha — "what's left after removing the market's part?"**
  The average return the book earns that beta does **not** explain — the part a fund
  would claim as skill. Alpha is always defined *relative to* beta, so beta is
  computed first.

The two connect through one identity — the single most useful line in this topic,
and the one every card can expand and show (§3):

```text
book return  ≈  beta × benchmark return  +  alpha
(what happened)  (market's share, at this   (the rest —
                  book's exposure)            skill or noise)
```

**The classic misreading** is taking alpha as "return minus the market's return".
It is return minus **beta × the market's return** — what the market was due to
deliver *at this book's exposure*, which is rarely 1×. The difference is not
pedantry; it flips signs. Live example: index +0.19%, commodity book returned
+0.12%. Naive subtraction says the book *underperformed* by −0.07%. But its beta
is only 0.46, so the market's share was just 0.46 × 0.19% ≈ +0.09% — the book
beat its exposure by **+0.03%** (positive alpha). One number, opposite verdicts;
only the beta-adjusted one is right.

Despite the Greek letters these are **portfolio statistics from return history**, not
option greeks (delta, gamma…). Delta says how one option reacts to its underlying;
beta says how a whole book has been reacting to the market.

## 2. Step by step: what happens on every benchmark tick

Concrete numbers throughout; the code path is listed in §8.

**Step 1 — the benchmark ticks.**
Market Data Service publishes a `MARKET_INDEX` tick every ~2 s, say
`5,000.00 → 5,010.00`.

**Step 2 — Pricing computes the benchmark return.**
`r = 5010 / 5000 − 1 = +0.20%`.

**Step 3 — Pricing reads each book's PnL.**
From the live valuation cache (realized + unrealized, cumulative). Say the equity
book went `12,400 → 16,000`, so `ΔPnL = +3,600` since the previous benchmark tick.

*Why cumulative total, not open-positions-only?* Because the regression uses
**differences**, closed trades neutralize themselves: their realized PnL is frozen, so
they add the same constant to every snapshot and contribute exactly zero to every
future ΔPnL — only open positions can make the series move. Open-only PnL would be
*worse*: each close would drop the trade's whole lifetime PnL out of the series in one
sample, a fake market-unrelated jump (and the generator closes trades constantly),
biasing beta toward zero and adding alpha noise. The cumulative series is the
continuous one, which is exactly what a difference-based estimator needs. Note the
card's UNREAL. figure is open-only — a display choice; the risk series is total.

**Step 4 — one sample is stored per book.**
The pair `(ΔPnL = +3600, r = +0.20%)` is appended to that book's rolling window —
the last **100** pairs (~3–4 minutes at 2 s ticks). Nothing is computed from a single
sample; every published number describes the whole window.

*Why only the last 100?* Book exposure is a moving target (trades open and close
constantly), so a rolling window measures the exposure *now-ish*; all-history would
average today's book with long-gone positions and never forget them. 100 samples puts
beta's standard error around ±10% at typical R² — smooth enough to read, short enough
to notice a book flipping sides within ~1 window. The costs, accepted knowingly: after
a large position change the estimate blends old and new exposure until the window
flushes, and an outlier sample nudges the numbers once entering and once leaving (an
EWMA-weighted covariance would smooth that, at the price of a harder-to-explain
model). `BOOK_RISK_WINDOW` tunes the trade-off.

**Step 5 — regression over the window.**

Picture the window as a scatter plot: one dot per sample, x = benchmark return `r`,
y = book `ΔPnL`. The regression finds the straight line

```text
ΔPnL ≈ a + b·r
```

that predicts the book's PnL change from the market's move. "Best fit" means **least
squares**: choose `a` and `b` so the sum of squared vertical misses (actual ΔPnL minus
the line's prediction) is as small as possible — squaring makes misses positive,
punishes big ones hardest, and has a closed-form solution:

```text
dollar_beta  b = cov(ΔPnL, r) / var(r)        slope, in $ per 100% market move
dollar_alpha a = mean(ΔPnL) − b · mean(r)     intercept, $ per sample at r = 0
r_squared      = cov² / (var(ΔPnL) · var(r))  fit quality, 0..1
```

**Why is the slope cov/var?** Think of each sample as a *witness* proposing a slope.
A sample where the market moved `dr` (vs its average) and the book moved `dp` suggests
"the slope is `dp/dr`". But witnesses aren't equally reliable: when the market barely
moved, `dp/dr` divides by almost nothing — that sample's ratio is mostly noise. Least
squares resolves this by taking a **weighted average of the per-sample slopes,
weighted by the squared market move** — big market moves are trustworthy witnesses,
tiny ones get ignored:

```text
b = Σ(dp·dr) / Σ(dr²) = Σ [ (dr²/Σdr²) · (dp/dr) ]
    └── cov/var ──┘         └ weight ┘  └ slope ┘
```

That is all `cov/var` is. (`var(x) = mean((x−mean)²)` — how much a series wiggles
around its own average; `cov(x,y) = mean((x−mean)·(y−mean))` — whether two series
wiggle to the same side together.) Units check it: cov is $·return, var is return² —
the ratio is $ per unit of return, a slope.

**Worked example** — 5 samples instead of 100 so every number is checkable by hand
(deviations use fractions: 0.001 = 0.10%):

| sample | `r` | `ΔPnL` | `dr = r − r̄` | `dp = ΔPnL − mean` | `dp·dr` | `dr²` |
|---|---|---|---|---|---|---|
| 1 | +0.10% | +$2,600 | +0.001 | +$2,300 | 2.3 | 1·10⁻⁶ |
| 2 | −0.20% | −$3,700 | −0.002 | −$4,000 | 8.0 | 4·10⁻⁶ |
| 3 | +0.30% | +$6,500 | +0.003 | +$6,200 | 18.6 | 9·10⁻⁶ |
| 4 | 0.00% | −$400 | 0.000 | −$700 | 0.0 | 0 |
| 5 | −0.20% | −$3,500 | −0.002 | −$3,800 | 7.6 | 4·10⁻⁶ |

Means: `r̄ = 0.00%`, `mean(ΔPnL) = +$300`. Then:

```text
cov = (2.3 + 8.0 + 18.6 + 0.0 + 7.6) / 5 = 7.3
var = (1 + 4 + 9 + 0 + 4)·10⁻⁶ / 5     = 3.6·10⁻⁶

dollar_beta  = 7.3 / 3.6·10⁻⁶ ≈ $2,030,000    ⇒ ≈ +$20,300 PnL per +1% market move
dollar_alpha = 300 − 2,030,000 × 0 = $300      ⇒ +$300/sample of market-independent drift
```

Check the witness story against the same table: samples 1, 2, 3, 5 individually
suggest slopes of `2300/0.001 = 2.30M`, `2.00M`, `2.07M`, `1.90M`; sample 4 (market
flat) casts no vote. Their `dr²`-weighted average is 2.03M — identical to cov/var.

**Alpha is the intercept.** The fitted line passes through the point of means; its
height at `r = 0` is what the book earns *when the market does nothing* — here
+$300 per sample. That's the market-independent drift: subtract from the book's
average PnL the part its exposure would have delivered anyway (`b × mean(r)`), and
alpha is what remains.

**R² is "how much of the book is the line".** Split each sample's `dp` into the part
the line predicts (`b·dr`) and the leftover; R² is the predicted part's share of the
book's total variance. Here `var(ΔPnL) = 14.93M`, so
`R² = 7.3² / (14.93M × 3.6·10⁻⁶) ≈ 0.99` — this book is almost a pure lever on the
market. That's the example being clean by construction; real books carry idiosyncratic
PnL and land nearer 0.3–0.8 (a bond or FX book near 0).

**Step 6 — convert dollars to the familiar unitless numbers.**

Continuing the worked example (`dollar_beta ≈ 2,030,000`, `dollar_alpha = $300`):

```text
beta  = dollar_beta  / capital_base           2,030,000 / 1,000,000 = 2.03
alpha = dollar_alpha / capital_base           300 / 1,000,000 = 0.00003 per sample
alpha_window_return = alpha × observations    e.g. × 100 samples = +0.30% over the window
alpha_window_pnl    = dollar_alpha × obs.     $300 × 100 = +$30,000 over the window
```

The capital base (default $1M, see §4) is what makes a PnL stream comparable to a
fund return. Per-sample alpha over 2 seconds is unreadably small, so the UI shows the
**window total**: `ALPHA +0.30%` = the book earned 0.30% of its capital above what
its market exposure explains, over the same window in which the section header shows
the benchmark's own move (e.g. `+0.23% over 100 samples`). The two are directly
comparable. (Example magnitudes are chosen for easy arithmetic — live books hover
within a few tenths of a percent either side of zero.)

*Why not annualize?* Multiplying a per-2-second alpha by ~15.7 million samples per
year extrapolates a few minutes of noise into six-digit percentages — mathematically
consistent, practically meaningless. Window totals stay honest at any cadence: at
2-second ticks the window is minutes; at 60-second real-data polls it is ~1–2 hours;
on daily closes it would be ~100 trading days. The number always answers "over the
period actually observed."

**Step 7 — publish.**
The metric goes out as a `book_risk_update` SSE event and is kept for the
`GET /book-risk` seed. A synthetic `PORTFOLIO` book (summed PnL of all books, §5) goes
through the identical steps. The Valuations view renders each book's card — with an
expandable `return ≈ β × index + α` breakdown (§3) — and one benchmark strip in the
section header (global fact, stated once, not repeated per card).

## 3. Reading the numbers

| You see | It means |
| --- | --- |
| β ≈ 0 | Book's PnL doesn't follow the market (rates/FX books read this — correct, their drivers aren't in the index) |
| β ≈ 1 | Moves one-for-one with the market, per unit of assumed capital |
| β = 1.8 | Holds ~1.8× more market exposure than its assumed capital — leverage, not "extra volatility" |
| β < 0 | Profits when the market falls (net short / hedge profile) |
| `RETURN +0.13%` | The book's own raw move over the window (sum of ΔPnL ÷ capital) — the left-hand side of `return ≈ β × index + α`, no interpretation applied |
| `ALPHA +0.06%` | Over the current sample window the book earned 0.06% of capital beyond what its **beta × market move** explains — not beyond the market move itself (random generated trades → expect ≈ 0, wandering slightly either side) |
| R² ≈ 0.5 | Half the book's PnL variance is market-driven; the other half is idiosyncratic |
| R² ≈ 0 | Beta is statistically meaningless noise — don't read α/β with confidence |
| `13/20 returns` | Warming up: fewer than 20 samples (`INSUFFICIENT_DATA`) — no fabricated numbers |
| `benchmark variance zero` | Benchmark hasn't moved in the window (`ZERO_BENCHMARK_VARIANCE`) — happens on real data when the market is closed |

### The breakdown on every card

Each card carries a collapsed `▸ RETURN DETAILS` row. Opening it shows the identity
`return ≈ β × index + α` computed with the live numbers — what a desk would call
*return attribution*: splitting a result into its market part and its alpha part —
as a three-row ledger in both units (a real capture, equity book):

| | % of capital | dollars |
| --- | --- | --- |
| β −1.59 × index +0.19% | −0.31% | −3,054.81 |
| + α beyond the market | −0.33% | −3,319.21 |
| **≈ return this window** | **−0.64%** | **−6,380.64** |

How to read it, and why it is built this way:

- **Two columns on purpose.** The % column depends on the assumed capital base (§4);
  the $ column is the capital-free truth (`dollar_beta × index move`,
  `dollar_alpha × samples`, summed window PnL) and would survive any change of the
  base. Showing both keeps the assumption visible instead of hidden.
- **Why "≈", not "="?** The regression identity is exact for the *sum* of per-sample
  returns; the index move shown is the *compounded* level change over the window.
  Over minutes of tiny returns the gap is a rounding-sized residual — in the capture
  above the two upper rows sum to −$6,374 against an actual −$6,381.
- **The meta line** ("each +1% index move ≈ −$15,942 PnL") is `dollar_beta / 100`:
  the sensitivity a risk desk would actually quote, no capital assumption attached.
- The rows are exactly the misreading-proof from §1 made permanent: alpha is always
  displayed *next to* the `β × index` term it is measured against, so "alpha =
  return − market" has no room to creep back in.

Sanity anchors for this app (confirmed live and in simulation): a book's dollar beta
≈ its **net position** in index instruments (long $1.8M ACME → β ≈ +1.8 vs the $1M
base); a single-name equity book shows R² roughly 0.4–0.8 (ACME's share of index
variance, varying with the window); BOND and FX books show β ≈ 0 with R² ≈ 0; window
alphas land within a few tenths of a percent — the same order as the benchmark's own
window move; and the PORTFOLIO card often sits near β ≈ 0 while individual books run
large opposite exposures (long/short netting).

## 4. The $1M capital base — what it is and is not

A fund computes `return = ΔNAV / NAV`. A book here has **no NAV** — only a PnL stream
in dollars — so a capital figure must be *assumed* to express PnL as a return.

- **It is** a fixed, published modelling assumption: $1M per book
  (`BOOK_CAPITAL_BASE`), carried in every event as `capital_base`.
- **It is not** a scaling of anything. Positions are never resized or normalized to
  it. A book holding $1.8M net exposure against an assumed $1M simply — and correctly
  — reads as β = 1.8.
- **Consequence:** alpha and beta both scale as `1 / capital_base` (double the base,
  halve both). The capital-free truth is `dollar_beta`; unitless beta is just dollar
  beta per unit of assumed capital.

Internally the rolling window stores raw `(ΔPnL, r)` pairs and capital is divided in
only at publish time — so changing the base rescales the next event instantly without
throwing away accumulated samples.

## 5. The PORTFOLIO card

Dollar exposures **add**: book A making +$3,000 per 1% move plus book B losing
−$1,000 nets to +$2,000. So the engine feeds one synthetic book — the sum of all
books' PnL — through the same steps, published with `is_portfolio: true`.

- Its capital defaults to `BOOK_CAPITAL_BASE × number of books` (six $1M books = a
  $6M desk), overridable via `PORTFOLIO_CAPITAL_BASE`. Under the default, portfolio β
  is the equal-weight average of book betas.
- Long and short books offset — a desk can be near market-neutral (portfolio β ≈ 0)
  while individual books run large opposite exposures.
- R² does **not** add. Portfolio R² is measured from the summed series; comparing it
  with the books' own R² shows how much market exposure survives netting —
  the diversification readout.
- **A check you can do off the open cards:** the books' "each +1% index move" lines
  should sum to the PORTFOLIO card's, because dollar betas are additive (verified
  live: five books summing to −$9,588.12 against a portfolio reading of −$9,588.30 —
  equal up to sample-timing jitter). If they ever diverged materially, something
  would be wrong with the sampling.

## 6. Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BENCHMARK_SYMBOL` | `MARKET_INDEX` | Which symbol's ticks drive sampling |
| `BOOK_RISK_WINDOW` | `100` | Rolling samples per book |
| `BOOK_RISK_MINIMUM_OBSERVATIONS` | `20` | Samples required before publishing numbers |
| `BOOK_CAPITAL_BASE` | `1000000` | Assumed capital per book (USD) |
| `PORTFOLIO_CAPITAL_BASE` | unset | Portfolio capital; unset = base × book count |

## 7. Event reference (`book_risk_update` / `GET /book-risk`)

```jsonc
{
  "book_id": "…", "book_name": "…",
  "is_portfolio": false,
  "benchmark": "MARKET_INDEX",
  "benchmark_level": 5012.34,            // current level
  "benchmark_window_return": 0.0021,     // benchmark's own move over the window
  "capital_base": 1000000.0,
  "book_window_return": 0.0011,          // the book's own raw move over the window
  "book_window_pnl": 1100.0,             // …in dollars (sum of ΔPnL in the window)
  "alpha": 0.0000012,                    // per sample
  "alpha_window_return": 0.0006,         // excess return over the window (UI headline)
  "alpha_window_pnl": 600.0,             // the same excess, in dollars
  "beta": 0.84,
  "dollar_beta": 840000.0,               // $ per 100% benchmark move (÷100 → per 1%)
  "r_squared": 0.41,
  "observations": 100, "window": 100, "minimum_observations": 20,
  "status": "READY",                     // or INSUFFICIENT_DATA / ZERO_BENCHMARK_VARIANCE
  "calculated_at": "…"
}
```

## 8. Where the code is

| Step (§2) | File |
| --- | --- |
| Benchmark generation | `services/market-data-service/app/generator.py` (`generate_index_tick` — equal-weight basket of ACME/XAUUSD/ES_FUT) |
| Steps 1–3: trigger + PnL read | `services/pricing-service/app/market_data_client.py` → `cache.book_pnl_snapshot()` |
| Steps 4, 6, 7: sampling, capital, payload | `services/pricing-service/app/book_risk.py` (`BookRiskEngine`) |
| Step 5: the regression | `shared/pricing_math.py` (`alpha_beta` — pure function, unit-agnostic) |
| Config | `services/pricing-service/app/config.py`; benchmark symbol in `shared/catalog.py` |
| Fan-out | `app/valuation_publisher.py`, `app/api.py` (`GET /book-risk`) |
| UI | `frontend/src/domain/valuations.js` (`bookRiskOf`, `benchmarkOf`) → `components/valuations/BookRiskCard.jsx` (metrics + the `return ≈ β × index + α` breakdown), header strip in `views/Valuations/Valuations.jsx` |

## 9. Switching to real market data

The estimator never asks what a "period" is — it only needs the two series sampled at
the same instants. So the switch is configuration, not code:

1. Point `BENCHMARK_SYMBOL` at a real index proxy (e.g. SPY) once external providers
   feed Market Data Service.
2. Samples then arrive at polling cadence (30–60 s). Warm-up (20 samples) takes
   10–20 min; the 100-sample window spans ~1–2 h — widen `BOOK_RISK_WINDOW` for a
   steadier estimate.
3. Window totals reframe themselves automatically — `ALPHA` simply describes a
   longer window — and a closed market shows itself as `ZERO_BENCHMARK_VARIANCE`
   instead of garbage.

Betas then become externally meaningful (real positions vs a real index). Alphas stay
≈ 0 while trades come from the random generator — a correct reading, and a good
pipeline sanity check; alpha gets interesting once a real strategy creates positions
with intent.

## 10. Known limitations

- The synthetic benchmark is built *from* the books' own instruments — betas are
  partly self-referential until real data replaces the feed.
- Engine state is in-memory: a pricing-service restart re-enters warm-up.
- Exposure is regression-estimated at face PnL; hedge-aware netting (option vs its
  underlying) is deliberate future work.
- Population moments over 100 samples; the n vs n−1 distinction is far below the
  noise floor.
