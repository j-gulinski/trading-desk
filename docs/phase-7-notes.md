---
phase: 7
status: complete
revised: 2026-08-10
tags:
  - pricing
  - options
  - irs
  - alpha-beta
  - scenario
---

# Phase 7 — what you should know

This phase added the two derivative asset classes (European options, interest-rate swaps) and
per-book alpha/beta, then refactored the first implementation for correctness and real-data
compatibility. Its main lesson is that every instrument fits one shape: **terms frozen in JSONB +
one pricing function dispatched by asset class, repriced by the market event that moves it,
delivered over the existing valuation stream**.

The sections build on each other: what a trade carries (§2), the one pricing primitive (§3), the
two new models (§4–§5), the machinery that runs them (§6–§7), the analytics on top (§8), the
simulator around them (§9), and one trade walked end to end (§10).

## 1. What changed, and in which round

The work landed in two rounds. Round one added the features; round two fixed what a code audit and
a design review found wrong with them.

| Change | Round | Why |
| --- | --- | --- |
| `EUROPEAN_OPTION` / `IRS` enums, catalog entries, JSONB terms | add | new asset classes with per-trade economics |
| `black_scholes_price`, `irs_legs`/`irs_pv`, `alpha_beta` in `shared/pricing_math.py` | add | one owner for all pricing math |
| `BookRiskEngine` + `book_risk_update` SSE + `GET /book-risk` | add | alpha/beta computed in Pricing, streamed per book |
| IRS float leg rewritten as forward-implied cashflows | refactor | closed form showed nothing of the two-curve model (§5) |
| Scenario engine rebuilt on the shared pricing path | refactor | duplicated pricing logic 404'd on options and IRS (§7) |
| `trades_for_curve` default-curve fallback | refactor | trades without `metadata.curve` silently stopped repricing |
| `mid or last` chains → explicit None checks (`first_present`) | refactor | `or` treats a legitimate price of 0 as missing |
| One owner for `minimum_observations`, benchmark symbol, default curve | refactor | magic values referenced from one place each |
| Generator tracks all open trades, closes only cash products | refactor | equilibrium logic undercounted manually opened derivatives |
| `BookRiskCard` renders published alpha/beta; Business Overview receives the risk map | refactor | backend published metrics the UI hardcoded to `n/a` |
| Term schemas + custom terms on OPEN + adaptive New Trade form | add | catalog was "too static" — sell-side products need arbitrary parameters (§2) |
| Catalog stripped to listed instruments; OTC classes are terms-only | refactor | pre-baked `ACME_CALL_100_6M`-style entries were the static-catalog critique in object form (§2) |
| Generator re-syncs books every 10 s, all active books per class | fix | a book created at runtime never received generated trades (found in live testing) |
| Book-risk samples stored in dollar space; capital divides at publish only | refactor | changing the capital base must rescale output, not invalidate the window (§8) |
| Annualized alpha removed; window totals published instead | fix | ×15.7M periods/year turned minutes of noise into six-digit percentages (§8) |
| Synthetic `PORTFOLIO` metric through the same engine | add | dollar betas add across books, so desk-level netting is one summed series (§8) |
| Cards restructured: RETURN/ALPHA/BETA/UNREAL + expandable breakdown | refactor | benchmark is one global fact (section header), and the identity `return ≈ β × index + α` is shown, not asserted (§8) |
| Breakdown label renamed to `return details` | fix | the label's `text-transform: uppercase` capitalizes Greek (β→Β, α→Α), rendering the equation as a cryptic "B × INDEX + A" |
| `book_risk.py` comments cut to constraints only | refactor | design rationale is owned by `docs/alpha-beta.md`; in-code essays duplicated it and drifted from the repo's comment density |

Nothing here required a database migration: `trades.asset_class` is `TEXT` and terms live in the
existing `metadata JSONB` column.

## 2. Terms travel with the trade

Opening a trade freezes the instrument's terms into `trade_metadata`. From then on the trade is
priced from its own frozen terms — strike, maturity, volatility, notional, fixed rate, direction,
curve name, underlying — never by looking anything up again. If the catalog changes tomorrow, an
open trade keeps the economics it was executed with.

```text
listed class:  INSTRUMENT_CATALOG["GOVT_5Y"] ──┐
                                               ├── frozen at OPEN ──► trade.trade_metadata (JSONB)
OTC class:     user-defined terms (validated) ─┘
                                                       │
Pricing dispatch: trade.asset_class ──► price function reads everything else from metadata
```

This is why adding two asset classes changed no tables. The alternative — an `instruments` table
with typed term schemas — is real future work (the generic catalog), but writing it now would have
coupled the core work to a side quest. The rule worth remembering: a migration is justified by a
structure the current schema *cannot* hold, not by a structure that merely feels more proper.

Pricing was built parameter-driven from the start: nothing in `price_from_inputs` knows about any
particular symbol — hand it metadata with strike 137 and maturity 1.25 and it prices it. What
initially lagged behind was *intake*: Trade Action only accepted catalog symbols, and the catalog
contained pre-baked derivative products like `ACME_CALL_100_6M` — the reviewed "too static"
critique in object form (a fixed call at 100 pretending to be *the* option you can trade). The
final shape splits the instrument universe the way a desk does:

- **`INSTRUMENT_CATALOG` holds only listed, quoted instruments** — ACME, EURUSD, XAUUSD, ES_FUT,
  GOVT_2Y/5Y. These exist independently of any trade, they tick in market data, and you trade
  them by *picking* one (the buy-side mode: quote what exists).
- **OTC classes have no catalog entries at all.** Every option and every swap is defined by its
  terms at the moment of opening (the sell-side mode: define the product). The pre-baked
  option/IRS entries were deleted; removing them broke nothing, because every existing trade
  already carries its frozen terms — the design proving itself.
- **There is no mode toggle.** The book's asset class alone decides what the ticket shows: a
  listed class gets an instrument picker, an OTC class gets term fields. One rule, no UI state.

The machinery behind that, one shared piece:

- **`shared/term_schemas.py`** declares, per OTC asset class (`EUROPEAN_OPTION`, `IRS`), which
  fields define a product — name, label, type, bounds — plus server-side defaults the user never
  types (curve, option multiplier, volatility). One `validate_terms` function is the single
  validator: coerces numbers, checks bounds and choices, injects defaults, stamps
  `asset_class`/`currency`. Having a schema *is* what makes a class OTC — the frontend, Trade
  Action, and the default-book bootstrap all derive the split from this one declaration.
- **Trade Action** requires a `terms` object for OTC opens (validated, plus a symbol-format
  check) and freezes the validated result into `trade_metadata`; listed opens still go through
  the catalog lookup. Bad terms are rejected with the precise reason in the audit trail. There
  is no code branch asking "is this OTC?" — an OTC symbol simply never matches the catalog, so
  the two paths enforce themselves.
- **Pricing's `POST /price`** quotes either a catalog symbol or `{asset_class, terms}` — the
  sell-side preview: see the model mark of an instrument that has never traded before you open it.
- **The New Trade form** fetches the schemas and renders its fields *from* them — an
  interface that adapts to the instrument type being defined — with the live backend
  mark recomputed as the terms change. Adding a field to a schema changes the form with zero
  frontend edits. Rates are entered in percent (the schema's `unit` marks the field; the wire
  format stays decimal), two-option choices render as toggles, and underlyings come from the
  published spot list, never free text. Volatility is deliberately *not* a field: the user
  defines the contract (underlying, strike, maturity, type); vol is a pricing input, not a term
  of the product, so the house default is stamped into the terms server-side (§4).
- **The symbol is derived, never typed.** A product's identifier is generated from its terms by a
  fixed naming scheme (`ACME_PUT_137_1.25Y`, `USD_IRS_PAY_FIXED_5Y`) and shown as
  a read-only fact on the ticket. Users name nothing; two people defining the same product get
  the same symbol. This is the test-data convention — when real data arrives, the same derivation
  point adopts market conventions instead (provider tickers for listed underlyings, venue-style
  identifiers for OTC products), which is a change to one function, not to the form.

### The life of the terms, in process order

The design above is static structure. This is the runtime sequence — which process touches the
trade, in what order, and what the terms are doing at each step. Three facts organize everything:
the services never call each other about trades (the **database row is the only handoff**), the
open is **asynchronous** (a queue accepts the intent, a worker executes it), and pricing works
from an **in-memory copy** of the active trades refreshed from the database on a timer.

**Phase 1 — preview (nothing exists yet).**

1. The ticket opens and fetches two things: the book list, and `GET /instruments/term-schemas`
   from Trade Action. The schema declares the fields, so the form for an OTC class renders
   itself; a listed class renders the instrument picker instead.
2. As the user edits terms, the frontend validates against the schema bounds locally (instant
   feedback) and derives the symbol from the terms. When the terms are complete it posts
   `{asset_class, terms}` to Pricing `POST /price`. Pricing runs the *same* `validate_terms` —
   the server never trusts frontend validation — then `market_inputs` + `price_from_inputs`
   produce the live mark shown on the ticket. Nothing is stored; the preview is a pure quote,
   recomputed when terms change or the relevant market input ticks.

A worthless product cannot be traded. If the model mark rounds to 0.00 — a call struck at
10212 against a spot of 100, a put struck at pennies — the ticket refuses the open ("Mark
rounds to 0.00"), and the worker independently rejects any non-positive `trade_price`. Both
checks exempt IRS, because an at-par swap legitimately opens at PV ≈ 0: an option *premium*
of zero means the product is economically empty, while a swap PV of zero means the fixed rate
is exactly fair — same number, opposite meaning, so the rule must be per-class.

**Phase 2 — open (the freeze moment).**

3. Submit builds the intent: `OPEN_TRADE`, a client-generated `client_request_id`
   (`manual-open-<uuid>`), book, asset class, the derived symbol, side, quantity, the displayed
   snapshot price as `trade_price`, and — for OTC — the raw terms. One POST to
   `/trade-actions`.
4. The API does not execute the trade. It puts the intent on an in-process `queue.Queue`,
   bumps the `accepted` counter, and returns immediately. This is the same entry path the
   generator's intents use — manual and generated flow through one pipe, which is why the
   audit trail and the queue stats describe both.
5. A single worker thread dequeues and runs `_open`. First, `_resolve_terms` — the fork where
   listed and OTC part ways with no explicit "is this OTC?" branch: if the intent carries
   `terms`, the symbol is pattern-checked and `validate_terms` runs (coercion, bounds,
   choices); if not, the symbol is looked up in `INSTRUMENT_CATALOG` and its asset class must
   match. An OTC symbol simply never matches the catalog, so the paths enforce themselves.
   `validate_terms` is also where the server-side defaults are stamped — curve, option
   multiplier, volatility. The user never sent them; the server's word is authoritative. *This
   output is the object that gets frozen.*
6. In one database transaction: the book must exist, be active, and its
   `expected_asset_class` must equal the intent's. Any failure → an `ACTION_REJECTED` audit
   row with the precise reason, `rejected` counter, no trade. Success →
   `repository.insert_trade` writes the trades row with `metadata` = the validated terms and
   status `ACTIVE`, plus a `TRADE_CREATED` audit row in the same transaction — the trade and
   its audit trail cannot exist without each other. A duplicate `client_request_id` violates
   the unique constraint and lands in the `duplicates` counter instead of creating a second
   trade: idempotency by database constraint, not by checking first.

**Phase 3 — discovery (pricing learns the trade exists).**

7. Nobody tells Pricing. Its `trade_refresh_loop` re-queries all `ACTIVE` trades (joined with
   book names) every `TRADE_REFRESH_SECONDS = 2` and swaps the in-memory `active_trades` map
   wholesale — metadata included. Within ~2 seconds the new trade is in pricing's working set.
   Polling the database instead of messaging keeps the services independent: pricing restarts
   and rebuilds its world from the one source of truth with no replay protocol.

**Phase 4 — the tick loop (steady state, where the trade lives).**

8. Pricing's SSE consumer receives market data ticks. Each tick triggers only the trades it
   can move, and the frozen metadata is the routing key:
   - a **spot tick** for `ACME` revalues trades where `symbol == "ACME"` *or*
     `metadata.underlying_symbol == "ACME"` — that second clause is how an option trade whose
     own symbol (`ACME_PUT_137_1.25Y`) never ticks still reprices when its underlying moves;
   - a **curve tick** for `USD_GOV` revalues trades whose `metadata.curve` is `USD_GOV`
     (falling back to `DEFAULT_CURVE` for curve-priced classes with no stamp) — bonds, swaps,
     *and* options, since an option needs the discount factor too.
9. Each triggered trade is revalued from its own row: `market_inputs(asset_class, symbol,
   metadata)` gathers what the class needs (spot of the underlying, curve), `price_from_inputs`
   prices it from the frozen strike/maturity/notional/direction, and PnL is the difference
   against the frozen `trade_price`. The result is published on the valuations SSE stream
   (blotter and Business Overview render it) and persisted to the valuations table. The
   catalog is not consulted — change it, delete entries, nothing already open notices.

**Phase 5 — close and finalization.**

10. A close is again an intent through the same queue; the worker sets status `CLOSED`, stores
    `close_price` and reason, writes a `TRADE_CLOSED` audit row.
11. Pricing's refresh loop notices on its next pass — a closed trade drops out of the active
    map (no more tick-driven valuations), and `finalize_closed_trades` picks up any `CLOSED`
    trade not yet finalized: realized PnL is computed once from the close price, one final
    valuation is written (unrealized zero, total = realized), and `valuation_finalized` flips
    so it never happens twice. The frozen terms stay in the row forever — the historical
    record of exactly what was traded, priceable again at any time.

The pattern to name when defending this: **freeze at the boundary, poll the truth, route by
what you froze.** Validation and defaults happen exactly once, at intake; every later process
reads the frozen result; and no service depends on another being alive at the right moment,
because the database row carries everything the trade will ever need.

The honest boundary that remains: a defined instrument exists only as that trade's frozen terms.
It is not published anywhere another trader could pick it up — that needs the `instruments` table
(typed templates, `is_active`, seeded from the catalog), which stays future work. Defining and
*publishing* are different features; only the first is built.

## 3. Discount factors — the primitive everything shares

Market Data publishes one curve, `USD_GOV`, as `{tenors, rates}` — a handful of points like
`5y → 4.12%`. Two small functions in `pricing_math` turn that into everything else:

```text
rate_at(curve, t)        linear interpolation between tenors, flat beyond the ends
discount_factor(curve, t) = 1 / (1 + rate_at(t))^t
```

`DF(t)` answers one question: *what is 1 USD paid at time t worth today?* It is 1 at t=0 and
shrinks as t grows, because money later is worth less than money now — that is the entire concept.
Annual compounding is a course-level simplification; the shape of every formula survives a switch
to continuous compounding.

Every product in the system is priced off this primitive: a bond is coupons multiplied by their
DFs; an option's strike is discounted by `DF(T)`; a swap discounts both legs with it and *forecasts*
with ratios of it (§5); a rate scenario bumps the rates and recomputes the DFs. That is why "the
curve ticked" reprices three asset classes at once, and why the one existing curve is the default
wherever a curve name is missing.

## 4. European options: Black–Scholes from the standard library

An equity option's unit premium comes from the Black–Scholes formula, written in terms of the
discount factor:

```text
d1 = [ln(S/K) − ln(DF) + ½σ²T] / (σ√T)        d2 = d1 − σ√T
call = S·N(d1) − K·DF·N(d2)                   put = K·DF·N(−d2) − S·N(−d1)
```

Where each input comes from is the important engineering fact:

| Input | Meaning | Source |
| --- | --- | --- |
| `S` | underlying spot | live tick cache for `underlying_symbol` (mid → last → spot) |
| `K`, `T`, call/put | strike, maturity, type | frozen trade terms (JSONB) — the *contract* |
| `σ` | volatility | frozen terms too, but stamped by the system (`DEFAULT_VOLATILITY = 0.22`), never typed by a user |
| `DF` | discount factor to expiry | `USD_GOV` curve at `T` (§3) |

The contract/input distinction matters: strike, maturity, and type *define* the option — they are
what two counterparties agree on. Volatility is the market's opinion used to *price* it; on a real
desk it comes from an implied-vol surface, not from the trade ticket. With no vol feed in the
system, the house default is stamped into the trade's frozen terms at open (so every trade stays
self-contained), and a real implied-vol source later replaces the default's origin — not the form,
not the formula.

Two deliberate choices sit in that formula. First, `−ln(DF)` stands where textbooks write `rT`:
the curve is the only rate authority, so there is no separate risk-free-rate parameter that could
drift out of sync with it. Second, `N(x)` — the standard normal CDF — is built from `math.erf`
(`N(x) = ½(1 + erf(x/√2))`) to keep the dependency footprint at the standard library — no
scipy; the identity is exact, not an approximation.

The whiteboard-level reading of the formula: a call finishes worth something only if the stock
ends above the strike. `K·DF·N(d2)` is what you expect to pay — the strike, discounted, weighted
by (roughly) the probability of exercising; `S·N(d1)` is what you expect to receive — the stock
side, with `N(d1)` carrying an extra tilt because the payoff grows with how far the stock ends
in the money. `d1` measures moneyness in units of total uncertainty `σ√T`. The model's assumptions
are the standard interview list: lognormal spot, constant volatility and rates, no dividends.

The degenerate branches are business rules, not error paths. At `T ≤ 0` the option is worth its
intrinsic value — `max(S−K, 0)` for a call — because no time means no optionality. At `σ ≤ 0`
there is no randomness either, so the option collapses to the discounted payoff of a forward.
Genuinely invalid inputs (non-positive spot, strike, or DF) raise instead of guessing.

The formula returns a *unit premium*; quantity, multiplier, BUY/SELL sign, and PnL are applied by
the same shared valuation path as every other asset class. That is also why an option reprices
when its underlying ticks or the curve ticks, but not when time merely passes — `T` is a frozen
term, a documented simplification (no time decay between sessions).

## 5. IRS: the float leg teaches the two-curve model

The fixed leg was always honest — known coupons, discounted:

```text
fixed leg PV = Σ  N × fixed_rate × accrual × DF_disc(tᵢ)
```

The float leg was `N × (1 − DF(maturity))` — the correct number, but a magic formula: it shows
nothing about *why* a floating leg is worth that. The general model — a **discount curve** for
present value, a **projection curve** for forecasting the floating rate — is the one worth
understanding and being able to explain. Three options existed:

1. Keep the closed form — correct but opaque; teaches nothing, reads as memorized.
2. Full dual-curve with a second published market-data curve — drags the generator,
   persistence, and UI into scope for no additional insight at this stage.
3. **Chosen:** the float leg walks the same payment schedule as the fixed leg, forecasting each
   period's rate as the forward implied by a projection curve that *defaults to the discount
   curve* (the standard simplification at this level).

```text
forward(tᵢ₋₁, tᵢ) = DF_proj(tᵢ₋₁) / DF_proj(tᵢ) − 1
float leg PV      = Σ  N × forward(tᵢ₋₁, tᵢ) × DF_disc(tᵢ)
```

A forward rate is nothing exotic: it is the interest implied between two dates by the ratio of
their discount factors. The one-line proof that this refactor changed no numbers is the
**telescoping identity**. With one curve for both roles, each term simplifies:

```text
N × (DF(tᵢ₋₁)/DF(tᵢ) − 1) × DF(tᵢ)  =  N × (DF(tᵢ₋₁) − DF(tᵢ))
```

Summing over the schedule, every interior DF cancels pairwise:

```text
Σ N × (DF(tᵢ₋₁) − DF(tᵢ)) = N × (DF(0) − DF(T)) = N × (1 − DF(T))
```

— exactly the old closed form. Verified numerically to `1e-10` for annual, quarterly, and stub
schedules. So the sentence to say out loud is: *"my float leg is the sum of projected cashflows;
under a single curve it collapses to the textbook closed form; a real projection curve is a
one-argument change."* PV then follows direction: pay-fixed = float − fixed, receive-fixed is the
negative.

One domain fact worth saying in a demo: the cataloged 5-year swap prices near zero, and that is
not a bug. Its 4.12% fixed rate sits at the curve's own level, so the swap is struck near *par* —
the rate at which both legs start out equal in value, which is how real swaps are quoted at
inception (nobody pays to enter a fair exchange). The PV that then moves on screen measures how
rates have shifted since the trade was struck — which is exactly what holding a swap position
means.

## 6. One pricing path, split at the inputs

With the models in place, the engine question is how they run. `price_instrument` used to gather
cache data and price in one function. It is now split:

```text
market_inputs(asset_class, symbol, meta)   → {spot?, curve?}   (reads the live cache)
price_from_inputs(asset_class, meta, inputs) → (unit price, multiplier)
price_instrument = price_from_inputs ∘ market_inputs
```

The split exists so the scenario engine (§7) can reuse the *identical* pricing code with shocked
inputs instead of maintaining its own copy. The valuation stream and scenario analysis can no
longer disagree about what an instrument is worth, because there is only one implementation.

Which market event reprices which trade:

| Event | Cache selector | Reprices |
| --- | --- | --- |
| spot tick (`ACME`) | trade symbol matches, or `metadata.underlying_symbol` matches | equities/FX/futures **and options on that underlying** |
| curve tick (`USD_GOV`) | `metadata.curve` matches, defaulting to `USD_GOV` for curve-priced classes without the key | bonds, IRS, options (through the discount factor) |
| benchmark tick (`MARKET_INDEX`) | equality with `BENCHMARK_SYMBOL` | nothing directly — it feeds the book-risk sampler (§8) |

The default-curve fallback matters: older bond trades were opened before `curve` was written into
metadata. The pricing side always defaulted missing curves to `USD_GOV`, but the cache selector
required an exact key match — so those trades were priced correctly *once* and then never again.
Symmetry restored: whatever curve the pricer would use is the curve the selector matches on.

The same audit killed the `spot.get("mid") or spot.get("last")` chains. `or` skips falsy values,
and a price of `0` is falsy — a legitimate zero would fall through to another field. The shared
`first_present` helper takes the first value that is not `None`, which is the actual intent.

## 7. Scenario analysis: shock the inputs, not the price

The old scenario engine had its own copies of equity/FX/bond pricing and returned 404 for options
and IRS. It is now one uniform rule built directly on the §6 split:

```text
inputs         = market_inputs(instrument)
base           = price_from_inputs(inputs)
shocked        = price_from_inputs(shock applied to inputs)
scenario price = base price + (shocked − base)
```

The shock is applied to *market inputs*, and pricing is re-run — so an option automatically picks
up its convexity (a +10% spot bump moves a call by more than delta alone), and an IRS reprices off
a genuinely bumped curve. Shock conventions are per input type, matching the existing collection:

| Asset classes | Shock means | Applied to |
| --- | --- | --- |
| EQUITY, COMMODITY, FUTURES, FX, EUROPEAN_OPTION | fraction (`0.10` = +10%) | spot levels (options through the underlying) |
| BOND, IRS | basis points (`25` = +25 bps) | parallel bump of every curve rate |

A client-supplied `current_price` is still honored as the base mark; the model contributes the
*delta* between shocked and unshocked repricing on top of it. One behavior change to know about:
scenario now always requires live market inputs, where the old equity path could shock a
client-supplied price with an empty cache.

## 8. Alpha/beta: the estimator is already the real-data shape

The full write-up — what alpha and beta mean, why a capital base must be assumed for a
PnL stream and how everything scales with it, the end-to-end data flow, configuration,
and limitations — lives in [`docs/alpha-beta.md`](alpha-beta.md). The shape, per book:

```text
one sample     = (book return, benchmark return), taken per benchmark tick
book return    = ΔPnL since last benchmark tick / capital base (1m default, configurable)
beta           = cov(book, benchmark) / var(benchmark)      over the last 100 samples
alpha          = mean(book) − beta × mean(benchmark)        (also published as window totals)
```

What the two numbers mean: **beta is market exposure** — the slope of the one-variable regression
of book returns on benchmark returns, and `cov/var` *is* that regression's slope (OLS with a
single regressor reduces to exactly this ratio). Beta 1.3 reads as "when the market moves 1%,
this book tends to move 1.3%." **Alpha is what's left** — the average book return after removing
the market's contribution (`beta × mean benchmark return`); the excess a hedge fund claims as
skill rather than exposure. That is why beta must be computed first: alpha is defined relative to
it.

The capital base exists because returns need a denominator: a book has only a PnL stream, no NAV,
so each book is treated as a fund with a fixed capital base (default 1m, `BOOK_CAPITAL_BASE`).
Alpha and beta both scale as `1/capital_base`, so the base is carried in every published event
along with the capital-free `dollar_beta` and an `r_squared` fit quality. Two guard statuses are
first-class values, not errors: `INSUFFICIENT_DATA` below 20 aligned pairs,
`ZERO_BENCHMARK_VARIANCE` when the benchmark has not moved (beta divides by that variance).

The decision worth being able to defend: an earlier idea — *constructing* a benchmark by averaging
the generated ticks, or otherwise tuning the synthetic index to behave realistically — was
dropped. What stays is the opposite split:

- The **estimator** is kept untouched, because cov/var over a return series is *defined* over real
  data; today it merely runs on a fake series. When the benchmark becomes a real index series,
  the same code samples per update instead of per tick and the window covers a longer horizon.
  The engine is cadence-agnostic; nothing changes.
- The **synthetic parts** get zero further investment. `MARKET_INDEX` stays a dumb synthetic
  basket, its unrealistic dynamics are a documented limitation, and the symbol is read from one
  env-overridable constant (`BENCHMARK_SYMBOL`) so pointing the sampler at a real series is a
  config change.

`minimum_observations` follows the same one-owner rule: the default lives next to `alpha_beta` in
`shared/pricing_math.py`, and the engine passes it through instead of restating `20`. The engine
also does not pre-check the observation count — the estimator owns its own guard, so there is
exactly one place where "not enough data" is decided.

A second refactor round hardened the engine after live inspection. Four decisions, each with a
concrete failure or requirement behind it:

- **Samples are stored in dollar space.** The window holds raw `(ΔPnL, benchmark return)` pairs;
  the capital base divides in only at publish time. Consequence one: changing
  `BOOK_CAPITAL_BASE` rescales the next event instantly instead of invalidating minutes of
  accumulated samples. Consequence two: portfolio aggregation is a sum — dollar exposures add,
  return-space betas don't.
- **Annualization was removed, not fixed.** The first version multiplied per-2-second alpha by
  ~15.7 million periods per year and the UI showed six-digit percentages — mathematically
  consistent extrapolation of pure noise. Published numbers are now **window totals**
  (`alpha_window_return`, `book_window_return`): honest at any cadence, because they only ever
  describe the period actually observed. The rule to keep: never annualize tick-cadence
  statistics.
- **`PORTFOLIO` is a synthetic book, not a special case.** All books' PnL summed into one series
  and fed through the identical steps; its capital defaults to base × book count. The live
  additivity check (per-book β$ per +1% summing to the portfolio's, verified to timing jitter)
  doubles as an engine self-test.
- **The benchmark correlation is real, and that was verified, not assumed.** `MARKET_INDEX` is an
  equal-weight basket of ACME/XAUUSD/ES_FUT, so a single-name equity book's R² should equal
  roughly that component's share of basket variance (~0.5). A generator-faithful simulation and
  the live UI both reproduce it — which corrected an earlier written claim that the index had
  "no engineered correlation." The self-referential nature of a benchmark built from the books'
  own instruments stays a documented limitation.

On screen, each card shows RETURN / ALPHA / BETA / UNREAL. plus an expandable `return details`
ledger that performs the regression identity `return ≈ β × index + α` with live numbers in both
% and dollars — the benchmark itself appears once, in the section header, because it is a global
fact, not a per-book one. The ledger's label was originally the equation itself, which failed in
an instructive way: the summary's `text-transform: uppercase` capitalizes Greek glyphs, so β and α
rendered as "B" and "A" — a reminder that CSS text transforms apply to the whole Unicode alphabet,
not just ASCII. Full walkthrough with a worked example in [`docs/alpha-beta.md`](alpha-beta.md).

A related ownership rule was applied to the engine's source: `book_risk.py` first shipped with
paragraph-length comments explaining dollar-space storage, the annualization ban, and window
totals. All of that rationale is owned by `docs/alpha-beta.md` (linked from the docstring), so the
comments were cut to the two facts the code cannot show — the one-paragraph docstring stating the
dollar-space/capital-at-publish design, and the `window + 1` sizing of the benchmark-level deque.
Rationale in docs, constraints in code; prose duplicated in both places drifts apart.

## 9. The generator simulates cash, but tracks everything

The decision from review: the trade generator stays a simulator and keeps generating cash products
only — derivatives are opened manually through the New Trade form. But its equilibrium logic
(close probability rises as the open book approaches the target) was counting only trades whose
symbols it generates, so every manually opened option or swap was invisible to it and to its
status endpoint.

The fix separates two roles that had been conflated in one filter: `sync_open_trades` now tracks
**all** open trades (truthful count, truthful equilibrium), while the close-picker draws only from
**generated** symbols (the simulator never closes a manually opened derivative — it has no price
authority over them).

The generator also bootstraps one default book per asset class — derived from the catalog's
classes *plus* the OTC schema classes, so `EUROPEAN_OPTION` and `IRS` books exist for manual
trading even though the generator never trades them itself.

Books had the same staleness problem in a worse form: the generator learned the book list exactly
once, at startup. A book created while it ran — a live-demo scenario — never
appeared in its universe and never received a generated trade. Books are now re-synced on the same
10-second cadence as open trades, inactive books drop out, and every active book of a generated
asset class receives flow (previously only the first book per class ever could).

## 10. One trade, end to end

Every earlier section appears once in the life of a single custom option:

1. **Define.** In New Trade, an options book is selected. Because `EUROPEAN_OPTION` is an OTC
   class, the form shows no instrument picker — it renders the schema's term fields directly
   (§2): underlying ACME, Put, strike 137, maturity 1.25. Volatility is not asked for — the
   schema default (0.22) is stamped server-side.
2. **Preview.** As soon as the terms validate, the form shows the derived symbol
   `ACME_PUT_137_1.25Y` and posts `{asset_class, terms}` to `POST /price`; pricing runs
   Black–Scholes (§4) on the live ACME spot and the curve's `DF(1.25)` (§3) and returns the mark.
3. **Open.** Submit sends an `OPEN_TRADE` intent carrying the terms. `202` means *queued, not
   done* (the phase-5 lesson). The worker re-validates the terms against the schema, checks the
   book's asset class, inserts the trade with the terms frozen in `trade_metadata`, and writes a
   `TRADE_CREATED` audit.
4. **Enter the pricing universe.** Pricing's refresh loop re-queries active trades and the new
   trade lands in the in-memory cache within `TRADE_REFRESH_SECONDS`.
5. **Spot tick.** ACME ticks. `trades_for_symbol("ACME")` matches the trade through
   `metadata.underlying_symbol` (§6), `price_from_inputs` reprices the premium, the valuation is
   persisted and published — unless a newer/final valuation has superseded it.
6. **Curve tick.** `USD_GOV` ticks. `trades_for_curve` matches through `metadata.curve` (with the
   default fallback), and the same trade reprices because `DF(1.25)` changed.
7. **Benchmark tick.** `MARKET_INDEX` ticks. No trade reprices; the book-risk engine samples each
   book's PnL change (over the capital base) against the benchmark return (§8) and publishes
   `book_risk_update`.
8. **Screen.** The browser merges the valuation into the feed context (latest-per-trade buffer,
   500 ms flush — the phase-4 machinery); the row shows LIVE fair value and unrealized PnL, and
   the book's card counts `13/20 returns` toward its first alpha/beta.
9. **Close.** A close intent finalizes the trade: a terminal valuation (`final: true`) converts
   unrealized to realized PnL, the row flips to CLOSED, and no later live value can overwrite it.

```text
curve tick ──► reprice IRS/bonds/options ──► valuation SSE ──► Valuations table / Blotter rows
spot tick  ──► reprice equities + options ─┘
index tick ──► BookRiskEngine.update ──► book_risk_update SSE + GET /book-risk seed
                                              └──► useValuationFeed.bookRisk map
                                                     ├── Valuations: bookRisksOf(rows, bookRisk) → BookRiskCard
                                                     └── Business Overview: same call, same map
```

Derivative trades are ordinary valuation rows: same fair value, unrealized/realized PnL, LIVE /
STALE / CLOSED derivation, same terminal-close behavior. The new surface is the book-risk path.
`BookRiskCard` had the real rendering commented out and hardcoded `n/a`; it now shows three honest
states:

- **READY:** RETURN, ALPHA (both as window percentages), BETA, and UNREAL., with the expandable
  `return ≈ β × index + α` breakdown and a `87/100 returns · R² 0.49` footer.
- **Insufficient data:** metrics stay `n/a` and the footer counts `12/20 returns`, so a demo
  audience can watch the window fill.
- **Zero variance:** `benchmark variance zero` — beta's denominator, so the metric cannot exist.

One deliberate style rule for all of this copy: the UI states facts in desk shorthand
(`Benchmark: MARKET_INDEX`, `12/20 returns`, `Close pending — awaiting confirmation.`) and never
explains concepts. Explanations of *why* — what a floating leg is, why beta needs variance — live
in this document and the README, not in labels. Tutorial prose inside a trading screen is the
fastest way for a portfolio project to read as generated instead of built.

Business Overview had a subtler version of the same bug: it called `bookRisksOf(rows)` without the
risk map, so alpha/beta was structurally always null there. It now passes the same `bookRisk`
context value the Valuations screen uses. The lesson generalizes: *a backend publishing correct
data proves nothing until a screen consumes it — wiring is part of the feature.*

## Mental model

```text
catalog or user-defined terms ── validated, frozen into trade_metadata at OPEN
                       │
market event ──► cache selectors (symbol / underlying / curve-with-default)
                       │
             price_from_inputs(asset_class, meta, inputs)     ◄── scenario reuses with shocked inputs
                       │
        valuation (fair value, PnL) ──► SSE ──► screens
benchmark tick ──► NAV returns vs benchmark returns ──► alpha/beta per book ──► SSE ──► book cards
```

## Concepts to keep

- **Terms frozen at execution:** a trade prices off the economics it was executed with; catalogs
  can change, history cannot.
- **Listed vs OTC is the only mode switch:** quoted instruments are picked from the catalog; OTC
  products are defined by terms. Having a term schema is what makes a class OTC — one
  declaration drives the form, the validation, and the book bootstrap.
- **Discount factor as the primitive:** every model here is sums of cashflows × DF; forwards are
  ratios of DFs; scenarios are DFs recomputed from bumped rates.
- **One pricing implementation:** scenario analysis is the same function with shocked inputs, not
  a second model that can drift.
- **The general model, fed simply:** the float leg is written as projected cashflows; the simple
  closed form is its single-curve special case, proven by telescoping.
- **Keep what real data won't change:** the cov/var estimator survives the switch to real returns
  untouched; the synthetic index gets zero investment because it will not.
- **Never annualize tick-cadence statistics:** report window totals; extrapolating seconds to a
  year multiplies noise by millions and produces confident-looking garbage.
- **Store risk in dollars, apply capital at the edge:** raw `(ΔPnL, r)` samples make config
  changes cheap and portfolio aggregation a sum.
- **Falsy is not missing:** `a or b` on prices treats 0 as absent; test for `None` explicitly.
- **Track vs act:** the generator counts every open trade but only closes what it generated.
- **Statuses over fabrication:** `INSUFFICIENT_DATA` rendered as `12/20 returns` with `n/a`
  metrics beats a fake 0.0000.

## Current limits

- Options carry a fixed house-default volatility (0.22): no vol feed, no implied vol, no Greeks,
  and no repricing on the passage of time alone.
- One published curve serves both discounting and projection; the dual-curve argument exists but
  is fed a single curve.
- Alpha/beta measures book PnL at face exposure; hedge-aware netting (an option offsetting its
  underlying) is deliberately parked as nontrivial.
- The benchmark is built from the books' own instruments (equal-weight basket), so betas measure
  real co-movement but are partly self-referential until real market data replaces the feed.
- Trade entry prices come from the simulator; only market data is slated to become real.
- A custom-defined instrument lives only in its trade's frozen terms — there is no
  `instruments` table yet, so defined products are not published to a shared catalog.

## Main files

- `shared/pricing_math.py` — Black–Scholes via `erf`, `forward_rate`/`irs_legs`/`irs_pv`,
  `alpha_beta` with its guard statuses and `MINIMUM_OBSERVATIONS`.
- `shared/catalog.py` — instrument terms, `BENCHMARK_SYMBOL`, `DEFAULT_CURVE`,
  `CURVE_PRICED_ASSET_CLASSES`.
- `shared/term_schemas.py` — per-class term declarations and `validate_terms`, consumed by
  trade-action, pricing previews, and the New Trade form.
- `services/pricing-service/app/valuation_engine.py` — `market_inputs` / `price_from_inputs`
  split and per-class dispatch.
- `services/pricing-service/app/scenario.py` — shocked-inputs scenario engine.
- `services/pricing-service/app/book_risk.py` and `market_data_client.py` — dollar-space
  (ΔPnL, benchmark return) sampling per benchmark tick, PORTFOLIO aggregate, publication,
  repricing triggers.
- `services/pricing-service/app/cache.py` — `trades_for_symbol` (underlying match),
  `trades_for_curve` (default-curve fallback), book-risk store.
- `services/trade-generation-service/app/generator.py` and `book_client.py` — track-all /
  close-generated split; default books per catalog + OTC class.
- `frontend/src/components/valuations/BookRiskCard.jsx`, `views/BusinessOverview/`,
  `domain/valuations.js` — book-risk rendering and the risk-map merge.
