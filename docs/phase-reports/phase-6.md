# Phase 6 — final project closure

Delivered 2026-08-26. This is the final project handoff for the real-provider trading desk.
The shipped boundary is seven registered sources, three tradeable quote adapters, official FX
conversion, six stored curves, six supported asset classes, provider/curve-bound execution,
sampled durable valuations and one reconciled portfolio summary.

## Outcome

The complete path is now executable:

```text
provider response
  → typed body/error classification
  → identity/currency normalization
  → budgeted scheduler
  → current board + change snapshot + minimal audit
  → snapshot/SSE consumers
  → ticket preview and server recomputation
  → idempotent trade write with frozen provenance
  → live revaluation + sampled persistence
  → same-source close + terminal valuation
  → blotter/books/portfolio reporting
```

There is no further required phase. Premium endpoints, automatic routing, historical analytics,
licensed projection curves, volatility surfaces, futures, fundamentals/news, order-book depth,
hosting and the optional product experiments in the roadmap remain deliberately outside the
project.

## Final scope ledger

| Classification | Final disposition |
| --- | --- |
| Required | Alpha Vantage equity/FX vertical; restart-safe free-tier controls; complete fetch/quote/curve/trade/valuation audits; stale-curve acknowledgement; bounded valuation persistence; provider/source provenance; full-provider scenario; one portfolio summary; browser and fresh-schema checks |
| Already delivered and retained | Finnhub and Twelve Data quote paths; NBP/ECB official FX and resolver; FRED/ECB/EIOPA curves; bond/IRS/European-option pricing; watchlist/active-set semantics; snapshot-first SSE; provider-bound close; reporting-currency overlay |
| Deliberately excluded | Premium Alpha/bulk APIs, best-price routing, synthetic spreads, provider backfill/history charts, futures, cash/margin capital, licensed index curves, vol surfaces, news/fundamentals and hosting |
| Optional after closure | Product experiments listed below the final acceptance boundary in the implementation roadmap |

Discovery found one unavoidable schema addition: a small provider/day ledger. Phase 6 therefore
contains one schema-only migration. Retiring the PLN pseudo-projection is current-state cleanup,
not schema history: market-data startup deletes stored curve sets absent from the domain catalog.

## Provider and capability matrix

| Source | Group | Quote/curve capability | Current pacing |
| --- | --- | --- | --- |
| Finnhub | quote | US equities/ETFs, REALTIME | 54/60 request safe minute bucket; 15/60 s open tiers, 300 s closed confirmation |
| Twelve Data | quote | equities, FX and XAU/USD, REALTIME | 7/8 credits/min; 720/800 credits/day; batched and daily-ledger paced |
| Alpha Vantage | quote | US equities/ETFs EOD; FX REALTIME | persisted 22/25 calls/day; at least 15 s between any calls; equity after US close, FX at most twice daily |
| NBP | reference | official FX plus PLN per gram of gold | publication-window feed, keyless |
| ECB | reference + curves | official FX; EUR sovereign AAA/all-ratings curves | separate fixing and curve health snapshots, keyless |
| FRED | curves | USD Treasury | 108/120 request safe minute bucket; six-hour builder |
| EIOPA | curves | EUR/USD/PLN monthly risk-free sets | application-safe 10/min; daily release check, keyless |

Capability remains separate from watchlist membership. Alpha has no keystroke search path:
normalized US equity/ETF and FX identities discovered elsewhere can attach the Alpha toggle,
and retained watchlist identity supplies the same fallback when an upstream search budget is
unavailable.

## Alpha Vantage vertical

### Transport and body classification

`ProviderClient` is now an abstract transport contract, so it cannot be instantiated without a
concrete provider/base URL. The Alpha client uses `/query` and maps:

- `GLOBAL_QUOTE` for an unqualified US equity/ETF;
- `CURRENCY_EXCHANGE_RATE` for a six-letter base/quote pair;
- HTTP-200 `Information` or `Note` to `ProviderRateLimited`;
- HTTP-200 `Error Message` to `ProviderDataError`;
- bad-key language to the authentication state.

Classification happens before normalization. These bodies can never become a quote.

### Normalization

Equity requires the exact returned symbol, an unqualified normalized US identity and USD quote
currency. It stores provider `05. price`, `08. previous close` and `07. latest trading day` at
UTC midnight. Bid/ask remain NULL, price basis is `LAST`, grade is `EOD`.

FX validates exact from/to currency codes and a UTC/GMT provider timezone, then stores the
returned bid, ask, exchange rate and refresh timestamp. When both sides exist, mid is their
arithmetic mean and basis is `BID_ASK`.

`GLOBAL_QUOTE` does not return a venue or currency field. The adapter therefore cannot pretend
to verify a venue from the payload: eligibility is restricted before the call to a normalized,
unqualified US identity with USD currency, while the returned symbol is checked exactly. This
is the honest limit of the endpoint.

### Free-tier budget and restart behavior

`provider_request_ledgers` is keyed by provider and UTC usage date. Scheduled refresh, add-time
refresh and manual refresh all pass through the same Alpha request lock, 15-second spacing and
22-call daily ceiling. The published service limit remains visible as 25.

On restart the feed reads stored provider/receive clocks. A fresh retained equity is deferred to
the next post-session slot; fresh FX is deferred for the remainder of its 12-hour interval. The
runtime restores `OK` and its last success time from that retained observation. A restart does
not silently spend a call merely to rebuild process state.

## User-facing quote state

`CLOSED` remains the internal market-session state used for scheduling, freshness and
tradeability. The market UI now presents every usable closing mark consistently as
`EOD (YYYY-MM-DD)` with the neutral closed-state pill. Alpha equity is never labeled LIVE;
Finnhub/Twelve rows in a confirmed closed session use the same presentation. Live intraday/FX,
STALE, MISSING and reference CURRENT remain distinct.

## Trading and provenance lifecycle

Browser-created opens carry `source=TRADING_TICKET`. Trade Action remains the only writer:

1. normalize the intent and derive a deterministic UUID from `client_request_id`;
2. synchronously validate book, symbol/terms, provider/curves, current quote/model value and
   the 1% client-seen tolerance;
3. return the same acknowledgement on an idempotent replay;
4. revalidate in the worker;
5. persist executed value, client-seen value, provider or curve names/as-of, quote time,
   optional exact snapshot FK, `source` and `created_by_service`;
6. revalue only from the frozen provider or named curves;
7. close from the same source and persist terminal timestamp/snapshot or curve provenance.

The blotter exposes both Source and Written by. The option active-set path substitutes the
frozen underlying symbol/provider for an open option, so removing that watchlist membership
blocks new risk but leaves the underlying pollable and the position closable.

## Audit and persistence guarantees

Every external fetch writes one of `PROVIDER_FETCH_SUCCEEDED`, `PROVIDER_FETCH_FAILED` or
`PROVIDER_FETCH_RATE_LIMITED`. Payload fields are deliberately small: provider, method,
endpoint, HTTP status, duration, outcome, optional result count and error type. No response body
or credential enters the audit.

Quote and curve storage is economic-change-only:

- a changed quote updates the board, appends a raw snapshot and writes `QUOTE_WRITTEN`;
- an unchanged confirmation advances the current receive clock without another history/audit;
- a new/revised curve set writes points/source evidence and `CURVE_SET_WRITTEN`;
- trade create/reject/close remain audited;
- a persisted valuation sample and its `VALUATION_UPDATED` audit commit atomically;
- missing required inputs write one deduplicated `VALUATION_BLOCKED` state until recovery.

SSE remains live for every computed revaluation. Non-terminal database writes are throttled per
trade to at most once per `VALUATION_WRITE_INTERVAL_SECONDS` (60 s default); terminal closes
always persist immediately.

## Curve age and explicit acknowledgement

The curve catalog now owns an age limit: 7 days for daily government curves and 75 days for
monthly EIOPA risk-free sets. Public
curve metadata exposes `age_days`, `stale_after_days` and `stale`.

If any selected set is genuinely stale, the New Trade panel names it, shows its source date and
requires the checkbox “Use … despite stale source dates”. The server independently rejects the
open unless top-level `stale_curve_acknowledged` is true, then freezes the acknowledged curve
names in the terms. Close remains possible from the retained contract.

## IRS single-curve contract

Phase 6 retires `PLN_REFERENCE_PROJECTION_3M`. It combined one monthly three-month interbank
observation with a ten-year government yield, filled the middle by straight-line interpolation,
and was structurally late. Its `3M` metadata made the ticket suppress the approximation warning
even though the set was not a forward curve calibrated to the contract's floating index. Keeping
it would add false precision rather than market information.

The public IRS contract now selects one catalog-approved same-currency risk-free curve under the
label `DISCOUNT / PROJECTION CURVE`. Validation assigns it to both internal roles and freezes
`pricing_approach: SINGLE_CURVE_APPROXIMATION` in the trade terms. The ticket states:

> **Single-curve approximation**  
> Floating payments are implied from the selected risk-free curve, not from a curve calibrated
> to the contract's 3-month or 6-month index.

Same currency is necessary but not sufficient: government-bond curves remain eligible only for
bond discounting and cannot forecast an IRS floating leg. The numerical IRS functions still
accept a separate projection curve; a future index-calibrated source can therefore restore a
two-curve public contract without replacing the pricing engine.

The ticket presents this adaptively. It asks for currency first, resolves the only eligible
same-currency IRS curve into a compact `Auto` readout, and shows a selector only when a role has
more than one approved alternative. The paired-curve layout remains implemented but dormant;
it becomes useful only after a defensible index-projection source is added, not merely because
another same-currency government curve exists.

## Financial calculations and portfolio reporting

The existing shared pricing modules remain the only math used by preview and execution:

- spot execution: BUY ask, SELL bid, otherwise mid;
- bond PV: discounted coupons plus principal from face, percent coupon, maturity and frequency;
- IRS NPV: fixed and floating legs from notional, direction, percent fixed rate and payment
  frequency, with one risk-free curve supplying discount factors and implied forwards;
- European option: Black-Scholes-style European premium from the frozen provider underlying,
  strike, maturity, selected discount curve and explicit volatility default;
- quote valuation/PnL: signed quantity × multiplier × current/entry difference;
- open gross entry: `abs(quantity × entry price × multiplier)`;
- total PnL: realized plus unrealized;
- display conversion: identity, direct/inverse official rate, one-source EUR cross or one-source
  PLN cross; nothing converted is persisted.

`frontend/src/domain/portfolio.js` is the single aggregation used by Business Overview, Books
and Valuations. It supplies gross entry, unrealized, realized, total, open count, closed count and
per-currency subtotals. Closed trades contribute realized PnL and count but never open gross
entry. The selected reporting currency is a labeled overlay with provider/path/as-of.

## Table, label and sorting contract

Phase 6 includes a page-by-page table audit. Labels now describe the financial meaning instead
of reusing one equity-shaped `Price` or `Fair value` concept for every asset:

| Surface | Final presentation | Unit and currency contract | Ordering contract |
| --- | --- | --- | --- |
| Market quotes | Symbol/name/class/market first; quote source, mark, day move, tick move, quote status, quote age and actions second | Mark uses the native quote unit (`USD`, `USD per EUR`, `JPY per USD`, `USD per XAU (troy oz)`); absolute moves carry that currency; usable session closes display `EOD (date)` | Identity columns are structurally sortable; provider observations stay grouped under their instrument identity |
| Trades | Default columns are Trade, Book, Instrument, Position, Size, Entry value, Pricing source, Current value, Position value, PnL and Valuation status; Class remains available in the column picker | Equity `USD/sh`; FX quote/base; commodity quote/XAU oz; option currency/contract; bond currency/100; IRS currency NPV; position value and PnL always carry settlement currency | Position value and PnL compare through one captured approximate USD snapshot; the active non-USD sort cells show that captured `≈ USD` value under the native amount |
| Valuations | Current model/mark is separate from position value and gross entry; contract identity includes option type/strike/term, bond maturity/coupon and IRS maturity/fixed rate | Every monetary cell carries native settlement currency, and current values use the same asset-specific units as Trades | Monetary sorts use the same captured USD comparator; structural sorts remain native and the result remains capped at 100 rows |
| Valuation history | Valuation time, Position value, Unrealized PnL, Realized PnL and Total PnL | Every historical amount carries its currency | Newest first; no false cross-currency ranking is implied |
| Books and portfolio | Book totals use Gross entry, Unrealized, Realized and Total PnL; expanded positions use contract-specific measures | Bonds show Face and Entry/Current per 100; IRS shows Notional and Entry/Current NPV; options show contracts and premium/contract; FX shows notional and rates | Native currency subtotals remain separate; the reporting overlay uses official, dated conversion provenance |

This makes the previously odd non-equity rows interpretable. FX displays the executable rate
separately from the converted position value. XAU is a price per troy ounce. A bond's `100.00`
is a clean-price-style amount per 100 face, not a EUR 100 position. An option value is a premium
per contract. An IRS has no generic spot price at all: it displays entry and current NPV against
notional. A newly struck par swap can therefore show `0.00 EUR NPV` honestly; that is a priced
at-par contract, not missing data.

The mixed-currency path is intentionally cheap. Each page fetches the USD conversion set once
and refreshes it on the existing one-minute cadence. Selecting a monetary sort performs one
linear pass to capture converted values; each comparator call is then an O(1) map lookup. Live
native marks keep updating without making the table jump. Re-sorting captures a new order, while
a missing FX rate disables only the affected money header instead of blocking the table.

Desktop widths above 900 px honor the saved column selection and keep horizontal overflow inside
the table shell. At 900 px and below the compact priority set takes over and the column picker is
hidden; the existing 620 px rules retain only the decision-critical columns. Captions, accessible
sort state, source labels and named action buttons remain present at every width.

## Application density and page rhythm

The final style review covers System Overview, Trade Actions, Logs, Business Overview, Market
Data, Valuations, Books, Trades and both side-panel families. The desktop shell now uses a 13 px
system UI base, reserving the monospaced face for identifiers and numbers. Page gutters are 24 px,
the navigation rail is 196 px expanded / 52 px collapsed, the title bar is shorter, and standard
controls use a 30 px desktop height. Shared cards use 12 px internal padding; ordinary tables use
12 px body text, 10 px headings, 9–10 px cell padding and a 44 px sortable header.

This is a density change, not blanket miniaturization. Primary monetary values remain 22 px,
status tones and hierarchy are unchanged, and mobile rules restore larger controls where touch
matters. Detail/new-trade drawers are 420/600 px on wide screens, become full viewport below
1,100 px and preserve 36–44 px interactive targets at narrow widths. Overflow stays inside the
responsible table or panel rather than widening the document.

## Demonstration portfolio reset

The old demonstration rows, including the unrelated legacy bonds, were cleared before final
acceptance. The replacement dataset is deliberately broad but plausible rather than optimized to
manufacture a gain:

- 18 watched instruments: 14 widely followed US companies plus EUR/USD, GBP/USD, USD/JPY and
  XAU/USD;
- 20 open trades across six books: 10 equities, three FX positions, one commodity, two bonds,
  two IRS contracts and two European options;
- three settlement currencies (EUR, JPY and USD), with entry levels close enough to current marks
  to show both modest gains and losses without overwhelming the presentation;
- zero closed rows at handoff, so later closes create clean realized-PnL history from this reset.

OTC contracts remain separate in book aggregation by their frozen terms. Two bonds or swaps in
the same currency are not merged merely because their display symbol is generic.

## Executable evidence

The repeatable integrated path is `scenarios/full-provider-flow.http`. Focused companions remain
for provider comparison, official FX and curves. `scripts/phase6-stress.sh` performs the bounded
local idempotency, SSE fan-out, board-read and valuation-growth probes; latest numbers are in
`docs/performance.md`.

Live acceptance on 2026-08-26 produced:

| Evidence | Observed result |
| --- | --- |
| Alpha AAPL | last/mid `309.9000` USD, previous close `310.3400`, provider date `2026-08-25T00:00:00Z`, received `2026-08-26T12:27:50.658706Z`, grade EOD, no bid/ask |
| Alpha EUR/USD | bid `1.16749500`, ask `1.16752681`, exchange-rate last `1.16749646`, mid `1.167510905`, provider time `2026-08-26T12:28:14Z` |
| Ledger restart | retained `2` requests / `2` credits before and after rebuild; limit 22 safe / 25 published; no refetch |
| Provider fetch audits | two Alpha success rows with `/query`, 200 status and durations 178/160 ms; no body fields |
| Alpha lifecycle | request `phase6-alpha-1787747542`, trade `d7073e85-b6ca-5e70-bf68-043a61d2a40e`; replay returned same ID; entry/close `309.9000`; same snapshot `f927c087-cf21-4489-a16a-f2077decb57f`; terminal reason `PHASE6_ACCEPTANCE` |
| Concurrent idempotency | 20 identical requests in 0.244 s, one trade `9764b098-7ccf-5c7c-b010-9a329da5549e`, one persisted row, then normal cleanup close |
| Valuation sampling | 52 consecutive non-terminal intervals inspected; minimum durable gap `60.175` seconds against the 60-second setting |
| IRS curve contract | the pseudo-projection set was removed from catalog, FRED runtime and stored current state; the schema exposes one combined curve field, accepted terms freeze the same risk-free name for both roles, and a distinct projection or same-currency government curve is rejected |
| Portfolio read | six retained books, 20 open and 0 closed trades after the final reset, currencies EUR/JPY/USD; gross/unrealized/realized/total originate from the shared book summary |
| Fresh schema | disposable PostgreSQL 18 migrated from base through `c8e1f6a2b4d7`; 11 public tables including `provider_request_ledgers`; container/network removed afterward |

## Browser acceptance

The in-app browser exercised System Overview, Market Data, Business Overview, Valuations, Books,
Trades and the New Trade panel against the running stack. Observed facts included seven healthy
services, seven provider cards, separate ECB `fixings OK · curves OK`, AAPL under three provider
rows, Alpha FX bid/ask, one consistent EOD presentation, the combined IRS risk-free selector,
the single-curve notice, exact portfolio metric labels and Alpha trade Source/Written by/close
provenance.

The final table pass additionally verified all four tabular surfaces and the expanded Books
positions. Trades opened with the 11-column semantic default (Current value included, redundant
Class omitted), and spot, FX, XAU, bond, IRS and option rows all displayed their own units. The
USD/JPY loss displayed both `−1,725.75 JPY` and captured `≈ −10.85 USD`, and its position among
USD losses followed the approximate USD amount rather than the raw JPY number. Valuations used
the same order, valuation history included currency in all four money columns, and expanded bond,
swap and option positions showed Face/per-100, Notional/NPV and Contracts/premium respectively.

Desktop and 390×844 checks had no console warnings/errors. The narrow portfolio subtotal grid
was corrected to a two-column metric layout and finished with document width equal to viewport
width (390 px) on Books; market/trades views also had no page-level horizontal overflow. EOD and
closed-session quote pills have the same class, color and background because both now render as
EOD.

## Build and runtime checks

Completed checks:

```text
python3 -m compileall -q shared services db
npm run lint --prefix frontend
npm run deadcode --prefix frontend
npm run build --prefix frontend
bash -n scripts/phase6-stress.sh
git diff --check
docker compose up --build -d
alembic heads  → c8e1f6a2b4d7
```

All six services reported UP; Pricing reported CONNECTED to Market Data, and the browser showed
both market and pricing streams connected. Portfolio, watchlist and book data remained intact;
only stored rows belonging to the retired curve key were pruned.

## Honest limitations

- Alpha free service is sparse by design: one EOD US mark and at most two selected FX refreshes
  daily under the safe budget; it is not an intraday equity feed.
- Alpha `GLOBAL_QUOTE` does not independently identify venue/currency; the adapter restricts
  admission using normalized identity and verifies only fields the response actually contains.
- Provider observations are a change audit, not a complete historical series or chart.
- IRS floating payments are a documented single-risk-free-curve approximation, not projections
  from licensed Euribor, WIBOR/POLSTR or term-SOFR curves. The two-curve numerical interface is
  retained for a future defensible source.
- The application has no cash ledger, deposits/withdrawals, financing, margin or regulatory
  capital model. “Gross entry value” is intentionally not labeled capital.
- Benchmark alpha/beta remains honest `INSUFFICIENT_DATA` outside a sufficient real SPY return
  sample; no observations are manufactured.
- The local stress sample demonstrates bounded behavior, not a production SLA.
