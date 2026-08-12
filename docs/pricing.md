# Pricing — instruments, models, and one code path

Six asset classes: EQUITY, COMMODITY, FUTURES, FX, BOND, plus the two derivative classes this
project added — EUROPEAN_OPTION and IRS. This document explains how an instrument is defined,
how each one is priced, and why all of it runs through a single function.

The one sentence to remember: **terms frozen in JSONB + one pricing function dispatched by asset
class, repriced by the market event that moves it, delivered over the existing valuation
stream.**

## 1. The path in five steps

```text
1. define   — a trade's economics are validated once and frozen into metadata JSONB
2. select   — a market event picks the trades it can move, by matching frozen metadata
3. gather   — market_inputs() reads the live cache: a spot, a curve, or both
4. price    — price_from_inputs() dispatches on asset_class and returns a unit price
5. publish  — PnL against the frozen trade price → valuations table + SSE
```

Scenario analysis is the same steps 3–5 with the inputs bumped (§7). That reuse is the whole
design.

## 2. Terms travel with the trade

Opening a trade freezes the instrument's terms into `trade_metadata`. From then on the trade is
priced from its own frozen terms — strike, maturity, volatility, notional, fixed rate,
direction, curve name, underlying — never by looking anything up again.

```text
listed class:  INSTRUMENT_CATALOG["GOVT_5Y"] ──┐
                                               ├── frozen at OPEN ──► trade.metadata (JSONB)
OTC class:     user-defined terms (validated) ─┘
                                                       │
Pricing dispatch: trade.asset_class ──► price function reads everything else from metadata
```

This is why adding two asset classes changed no tables. The alternative — an `instruments` table
with typed term schemas — is real future work, but writing it now would have coupled the core
work to a side quest. **A migration is justified by a structure the current schema cannot hold,
not by one that merely feels more proper.**

### Listed vs OTC is the only mode switch

Pricing was parameter-driven from the start: nothing in `price_from_inputs` knows about any
particular symbol — hand it metadata with strike 137 and maturity 1.25 and it prices it. What
lagged behind was *intake*: trade-action only accepted catalog symbols, and the catalog
contained pre-baked products like `ACME_CALL_100_6M` — a fixed call at 100 pretending to be
*the* option you can trade. The final split follows how a desk actually works:

- **`INSTRUMENT_CATALOG` holds only listed, quoted instruments** — ACME, EURUSD, XAUUSD, ES_FUT,
  GOVT_2Y/5Y. They exist independently of any trade, they tick in market data, and you trade
  them by *picking* one (the buy-side mode: quote what exists).
- **OTC classes have no catalog entries at all.** Every option and every swap is defined by its
  terms at the moment of opening (the sell-side mode: define the product). Deleting the
  pre-baked entries broke nothing, because every existing trade already carried its frozen terms
  — the design proving itself.
- **There is no mode toggle.** The book's asset class alone decides what the ticket shows. One
  rule, no UI state.

The machinery is one shared declaration:

- **`shared/term_schemas.py`** declares, per OTC class, which fields define a product — name,
  label, type, bounds — plus server-side defaults the user never types (curve, multiplier,
  volatility). `validate_terms` is the single validator: coerces numbers, checks bounds and
  choices, injects defaults, stamps `asset_class`/`currency`. **Having a schema is what makes a
  class OTC** — the form, the validation, and the default-book bootstrap all derive the split
  from this one file.
- **Trade-action** requires `terms` for OTC opens and freezes the validated result. There is no
  code branch asking "is this OTC?" — an OTC symbol simply never matches the catalog, so the two
  paths enforce themselves.
- **`POST /price`** quotes either a catalog symbol or `{asset_class, terms}` — the sell-side
  preview: see the model mark of an instrument that has never traded before you open it.
- **The New Trade form** renders its fields *from* the schemas, so adding a field to a schema
  changes the form with zero frontend edits. Rates are entered in percent (the schema's `unit`
  marks the field; the wire format stays decimal) and underlyings come from the published spot
  list, never free text.
- **The symbol is derived, never typed** — `ACME_PUT_137_1.25Y`, `USD_IRS_PAY_FIXED_5Y` — from a
  fixed naming scheme, shown read-only. Two people defining the same product get the same
  symbol. When real market data arrives, that one function adopts market conventions instead;
  the form does not change.

**Volatility is deliberately not a field.** The user defines the *contract* — underlying,
strike, maturity, type — which is what two counterparties agree on. Volatility is the market's
opinion used to *price* it; on a real desk it comes from an implied-vol surface, not from the
ticket. With no vol feed here, the house default (`DEFAULT_VOLATILITY = 0.22`) is stamped into
the frozen terms server-side, so every trade stays self-contained and a real vol source later
replaces the default's *origin*, not the form and not the formula.

**A worthless product cannot be traded.** If the model mark rounds to 0.00 — a call struck at
10212 against a spot of 100 — the ticket refuses the open and the worker independently rejects
any non-positive `trade_price`. Both checks exempt IRS, because an at-par swap legitimately
opens at PV ≈ 0: an option *premium* of zero means the product is economically empty, while a
swap PV of zero means the fixed rate is exactly fair. Same number, opposite meaning — so the
rule must be per class.

## 3. Discount factors — the primitive everything shares

Market Data publishes one curve, `USD_GOV`, as `{tenors, rates}` — a handful of points like
`5y → 4.12%`. Two small functions in `shared/pricing_math.py` turn that into everything else:

```text
rate_at(curve, t)         linear interpolation between tenors, flat beyond the ends
discount_factor(curve, t) = 1 / (1 + rate_at(t))^t
```

`DF(t)` answers one question: *what is 1 USD paid at time t worth today?* It is 1 at t=0 and
shrinks as t grows, because money later is worth less than money now — that is the entire
concept. Annual compounding is a course-level simplification; every formula's shape survives a
switch to continuous compounding.

Every product here is priced off this primitive: a bond is coupons times their DFs; an option's
strike is discounted by `DF(T)`; a swap discounts both legs with it and *forecasts* with ratios
of it (§5); a rate scenario bumps the rates and recomputes the DFs. That is why "the curve
ticked" reprices three asset classes at once, and why the one existing curve is the default
wherever a curve name is missing.

## 4. European options — Black–Scholes from the standard library

```text
d1 = [ln(S/K) − ln(DF) + ½σ²T] / (σ√T)        d2 = d1 − σ√T
call = S·N(d1) − K·DF·N(d2)                   put = K·DF·N(−d2) − S·N(−d1)
```

Where each input comes from is the important engineering fact:

| Input | Meaning | Source |
| --- | --- | --- |
| `S` | underlying spot | live tick cache for `underlying_symbol` (mid → last → spot) |
| `K`, `T`, call/put | strike, maturity, type | frozen trade terms — the *contract* |
| `σ` | volatility | frozen terms too, but stamped by the system, never typed (§2) |
| `DF` | discount factor to expiry | the `USD_GOV` curve at `T` (§3) |

Two deliberate choices sit in that formula:

- **`−ln(DF)` stands where textbooks write `rT`.** The curve is the only rate authority, so
  there is no separate risk-free-rate parameter that could drift out of sync with it.
- **`N(x)` is built from `math.erf`** — `N(x) = ½(1 + erf(x/√2))` — keeping the dependency
  footprint at the standard library. The identity is exact, not an approximation.

**The whiteboard reading.** A call finishes worth something only if the stock ends above the
strike. `K·DF·N(d2)` is what you expect to pay — the strike, discounted, weighted by (roughly)
the probability of exercising. `S·N(d1)` is what you expect to receive — the stock side, with
`N(d1)` carrying an extra tilt because the payoff grows with how far in the money it ends. `d1`
measures moneyness in units of total uncertainty `σ√T`. Assumptions are the standard interview
list: lognormal spot, constant volatility and rates, no dividends.

**The degenerate branches are business rules, not error paths.** At `T ≤ 0` the option is worth
its intrinsic value — no time means no optionality. At `σ ≤ 0` there is no randomness either, so
it collapses to the discounted payoff of a forward. Genuinely invalid inputs (non-positive spot,
strike, or DF) raise instead of guessing.

The formula returns a *unit premium*; quantity, multiplier, BUY/SELL sign, and PnL are applied
by the same shared path as every other class. That is also why an option reprices when its
underlying or the curve ticks, but **not when time merely passes** — `T` is a frozen term, a
documented simplification (no time decay between sessions).

## 5. IRS — the float leg teaches the two-curve model

The fixed leg was always honest — known coupons, discounted:

```text
fixed leg PV = Σ  N × fixed_rate × accrual × DF_disc(tᵢ)
```

The float leg was `N × (1 − DF(maturity))`: the correct number, but a magic formula that shows
nothing about *why* a floating leg is worth that. The general model — a **discount curve** for
present value, a **projection curve** for forecasting the floating rate — is the one worth being
able to explain. Three options existed:

1. **Keep the closed form.** Correct but opaque; reads as memorized.
2. **Full dual-curve with a second published market-data curve.** Drags the generator,
   persistence, and UI into scope for no additional insight at this level.
3. **Chosen:** the float leg walks the same payment schedule as the fixed leg, forecasting each
   period's rate as the forward implied by a projection curve that *defaults to the discount
   curve*.

```text
forward(tᵢ₋₁, tᵢ) = DF_proj(tᵢ₋₁) / DF_proj(tᵢ) − 1
float leg PV      = Σ  N × forward(tᵢ₋₁, tᵢ) × DF_disc(tᵢ)
```

A forward rate is nothing exotic: it is the interest implied between two dates by the ratio of
their discount factors.

**The telescoping identity** is the one-line proof that this changed no numbers. With one curve
in both roles, each term simplifies:

```text
N × (DF(tᵢ₋₁)/DF(tᵢ) − 1) × DF(tᵢ)  =  N × (DF(tᵢ₋₁) − DF(tᵢ))
```

and summing over the schedule, every interior DF cancels pairwise:

```text
Σ N × (DF(tᵢ₋₁) − DF(tᵢ)) = N × (DF(0) − DF(T)) = N × (1 − DF(T))
```

— exactly the old closed form. Verified numerically to `1e-10` for annual, quarterly, and stub
schedules. So the sentence to say out loud is: *"my float leg is the sum of projected cashflows;
under a single curve it collapses to the textbook closed form; a real projection curve is a
one-argument change."*

PV then follows direction: pay-fixed = float − fixed; receive-fixed is the negative.

**One domain fact worth saying in a demo:** the cataloged 5-year swap prices near zero, and that
is not a bug. Its 4.12% fixed rate sits at the curve's own level, so the swap is struck near
*par* — the rate at which both legs start out equal in value, which is how real swaps are quoted
at inception (nobody pays to enter a fair exchange). The PV that then moves on screen measures
how rates have shifted since the trade was struck, which is exactly what holding a swap means.

## 6. One pricing path, split at the inputs

```text
market_inputs(asset_class, symbol, meta)     → {spot?, curve?}      (reads the live cache)
price_from_inputs(asset_class, meta, inputs) → (unit price, multiplier)
price_instrument = price_from_inputs ∘ market_inputs
```

The split exists so the scenario engine (§7) can reuse the *identical* pricing code with shocked
inputs instead of maintaining its own copy. The valuation stream and scenario analysis can no
longer disagree about what an instrument is worth, because there is only one implementation.

Which market event reprices which trade:

| Event | Cache selector | Reprices |
| --- | --- | --- |
| spot tick (`ACME`) | trade symbol matches, **or** `metadata.underlying_symbol` matches | equities/FX/futures *and options on that underlying* |
| curve tick (`USD_GOV`) | `metadata.curve` matches, defaulting to `USD_GOV` for curve-priced classes without the key | bonds, IRS, options (through the discount factor) |
| benchmark tick (`MARKET_INDEX`) | equality with `BENCHMARK_SYMBOL` | nothing directly — it drives the book-risk sampler ([alpha-beta.md](alpha-beta.md)) |

Two bugs found by audit are worth keeping as lessons:

- **The default-curve fallback must be symmetric.** Older bond trades were opened before `curve`
  was written into metadata. The pricer defaulted a missing curve to `USD_GOV`, but the *cache
  selector* required an exact key match — so those trades priced correctly once and then never
  again. Whatever curve the pricer would use is the curve the selector must match on.
- **Falsy is not missing.** `spot.get("mid") or spot.get("last")` skips a legitimate price of
  `0`, because `0` is falsy. The shared `first_present` helper takes the first value that is not
  `None`, which is the actual intent.

## 7. Scenario analysis — shock the inputs, not the price

```text
inputs         = market_inputs(instrument)
base           = price_from_inputs(inputs)
shocked        = price_from_inputs(shock applied to inputs)
scenario price = base price + (shocked − base)
```

The shock is applied to *market inputs* and pricing is re-run, so an option automatically picks
up its convexity (a +10% spot bump moves a call by more than delta alone) and an IRS reprices
off a genuinely bumped curve. Shock conventions are per input type:

| Asset classes | Shock means | Applied to |
| --- | --- | --- |
| EQUITY, COMMODITY, FUTURES, FX, EUROPEAN_OPTION | fraction (`0.10` = +10%) | spot levels (options through the underlying) |
| BOND, IRS | basis points (`25` = +25 bps) | parallel bump of every curve rate |

A client-supplied `current_price` is still honored as the base mark; the model contributes the
*delta* between shocked and unshocked repricing on top of it. One behavior change to know: the
scenario now always requires live market inputs, where the old equity path could shock a
client-supplied price with an empty cache.

Before this, `scenario.py` had its own copies of equity/FX/bond pricing and returned 404 for
options and IRS. Rebuilding it on the §6 split killed the duplication and the gap in one move.

## 8. The generator simulates cash, but tracks everything

The trade generator stays a simulator and generates **cash products only** — derivatives are
opened manually through the New Trade form. But its equilibrium logic (close probability rises
as the open book approaches the target) counted only trades whose symbols it generates, so every
manually opened option or swap was invisible to it.

The fix separates two roles that one filter had conflated: `sync_open_trades` tracks **all** open
trades (truthful count, truthful equilibrium), while the close-picker draws only from
**generated** symbols — the simulator never closes a manually opened derivative, because it has
no price authority over it. **Track vs act.**

The equilibrium itself is one line:

```text
p_close = min(0.9, 0.5 × open_trades / target_open_trades)
```

At the target the book closes about half of what it opens, and the 0.9 ceiling keeps the
generator from stalling out entirely when it overshoots. **Capacity and close probability are two
percentages that look alike and answer different questions** — `open / target` says how full the
book is, `p_close` says how likely the next tick is to close something — so they are deliberately
not the same number. Reporting one as the other is the kind of mistake a dashboard makes once and
nobody notices for weeks.

Two related behaviors:

- It bootstraps one default book per asset class, derived from the catalog's classes *plus* the
  OTC schema classes, so EUROPEAN_OPTION and IRS books exist for manual trading even though the
  generator never trades them.
- Books are re-synced every 10 s. Originally the book list was read once at startup, so a book
  created while it ran — a live-demo scenario — never received a single generated trade.

## 9. Current limits

- Options carry a fixed house-default volatility (0.22): no vol feed, no implied vol, no Greeks,
  and no repricing on the passage of time alone.
- One published curve serves both discounting and projection; the dual-curve argument exists in
  the code but is fed a single curve.
- A custom-defined instrument lives only in its trade's frozen terms — there is no `instruments`
  table, so defined products are not published to a shared catalog another trader could pick up.
  Defining and *publishing* are different features; only the first is built.
- Trade entry prices come from the simulator; only market data is slated to become real.
- Deliberately out of scope: vol surface, time decay between sessions, Greeks, a separate risk
  service, hedge-aware exposure netting, real order matching.

## 10. Main files

| File | Holds |
| --- | --- |
| `shared/pricing_math.py` | `rate_at`, `discount_factor`, `black_scholes_price` (via `erf`), `forward_rate`/`irs_legs`/`irs_pv`, `alpha_beta` |
| `shared/catalog.py` | listed instrument terms, `BENCHMARK_SYMBOL`, `DEFAULT_CURVE`, `CURVE_PRICED_ASSET_CLASSES` |
| `shared/term_schemas.py` | per-class term declarations and `validate_terms` |
| `services/pricing-service/app/valuation_engine.py` | the `market_inputs` / `price_from_inputs` split and per-class dispatch |
| `services/pricing-service/app/scenario.py` | shocked-inputs scenario engine |
| `services/pricing-service/app/cache.py` | `trades_for_symbol` (underlying match), `trades_for_curve` (default fallback), terminal valuations |
| `services/trade-action-service/app/trade_processor.py` | intake, validation, the freeze moment |
