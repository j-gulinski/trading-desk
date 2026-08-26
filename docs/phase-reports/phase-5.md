# Phase 5 — market data, curves and model-priced trades

This is the durable engineering guide to the implemented Phase 5. It explains the phase
boundary, the end-to-end processes, the financial calculations, the persistence model and
the smallest code map needed to find each responsibility. The Polish companion,
[phase-5-krzywe-i-kod.md](phase-5-krzywe-i-kod.md), concentrates on financial intuition
and oral defence.

## 1. Scope and shortest mental model

Phase 5 connects real quote and rate data to the existing trade lifecycle:

```text
provider response
  -> provider client validates the transport/body
  -> normalizer creates a shared quote or curve model
  -> store persists current state and provenance
  -> snapshot + SSE distribute current state
  -> ticket previews a server-owned price
  -> trade-action validates again and records the trade
  -> pricing revalues it when a relevant quote or curve changes
  -> blotter presents value, PnL and close state
```

The implemented owner-approved boundary is intentionally narrower than the literal
assignment:

- quote providers: Finnhub and Twelve Data;
- official reference fixings: NBP and ECB;
- curves: ECB, FRED and EIOPA;
- model-priced contracts: bond, IRS and European option;
- Alpha Vantage and a three-quote-provider ticket belong to the next phase;
- the optional trade comment and the assignment's full per-fetch/per-valuation AuditLogs
  matrix are not implemented; this phase audits trade create/close, domain-validation and
  worker rejects, the first quote and each created/revised curve set; malformed request
  bodies and queue-capacity rejects return HTTP errors without a business audit row;
- no historical market-data analysis, curve bootstrapping, volatility surface or security
  master was added.

Only data used by a visible workflow was retained. The phase has one schema-only migration,
`db/versions/a9c4e5f61b27_curve_provenance.py`: it adds curve-provenance and instrument-identity
columns and contains no business-data `INSERT`, `UPDATE` or `DELETE`. Because local history was
disposable, the development database was rebuilt from a fresh volume. Current curves were then
ingested by the normal feeds, while the intentional watchlist and demonstration trades were
created through the same application APIs as ordinary user actions.

Four prices must not be confused:

| Value | Meaning |
| --- | --- |
| Provider mark | Normalized bid, ask, last or reference mid for one provider-symbol pair. |
| Trade price | The server-side quote/model value frozen when the position opens. |
| Current price | The latest provider mark or model PV used in a valuation. |
| Fair value / PnL | Current price scaled by contract size; PnL is its signed change from entry. |

For a bond and IRS, contract size is already inside the model (`face_value` or `notional`),
so technical trade quantity is exactly one. An option model price is per one-unit contract;
its Phase 5 multiplier is one.

## 2. Market-data process

### 2.1 One provider contract, then six explicit implementations

The code has related catalogs with different jobs. `shared/providers.py` states broad provider
capabilities: which source may quote which asset class and whether it serves curves.
`shared/curves.py` is the single assignment catalog for each curve's owning provider, currency,
functional identity and allowed trade uses. `app/providers/registration.py` is the Market Data
runtime contract. Every wired provider exports the same `ProviderRegistration` shape:

```text
name
quote_mode = symbol | table | none
quote_feed = implementation | none
curve_feed = implementation | none
normalize_search = implementation | none
```

The absence of a capability is explicit. FRED does not pretend to implement `refresh_symbol`;
Finnhub does not pretend to build a curve. `app/providers/__init__.py` contains the six
registrations, and `scheduler.py` derives its quote maps, curve map, health readers and seven
background loops from them. Adding a source therefore means implementing one provider package
and registering it, not editing several unrelated scheduler lists. Startup also rejects a
runtime registration whose quote/curve capabilities disagree with `shared/providers.py`.
It also requires every curve feed to expose exactly the curve keys assigned to that provider in
`shared/curves.py`. Finally, `build_curve_set` rejects an output whose provider or currency differs
from the catalog. This checks ownership both when the application is wired and when data is built.

The reusable pipeline is deliberately small and visible:

1. `app/config.py` reads environment keys, provider limits, cadences and publication windows.
2. A provider `feed.py` wires those values into its client, `ProviderRuntime` and the appropriate
   common feed engine.
3. `providers/base.py` builds the URL with `urllib`, adds authentication parameters, decodes the
   body, logs endpoint/status/duration and converts HTTP failures to typed provider errors.
4. The provider `client.py` owns only source facts: base URL, endpoint, parameter names, response
   format and errors hidden inside a successful HTTP response.
5. The provider `normalizer.py` or `curves.py` translates source-specific fields into the shared
   `NormalizedQuote` or `CurveSet`; provider series codes remain provenance.
6. `ProviderRuntime`, `OfficialFixingFeed` or `CurveFeed` applies budget/cooldown/schedule rules. These
   common engines call provider functions; they do not know vendor field names.
7. `quote_store.py` or `curve_store.py` applies revision ordering and writes PostgreSQL.
8. `publisher.py` emits the normalized `market_tick` or `curve_tick`; consumers never receive a
   raw vendor contract.

Configuration follows the same ownership boundary. `app/config.py` is grouped into global policy,
Finnhub, Twelve Data, NBP, ECB, FRED, EIOPA, shared HTTP/failure policy, `OfficialFixingFeed` mechanics
and `CurveFeed` mechanics. A provider prefix means a source fact or adapter choice: for example,
`NBP_WINDOW_START` and `FINNHUB_PROVIDER_LIMIT_PER_MINUTE`. An `OFFICIAL_FIXING_FEED_*` prefix means one
application mechanism deliberately reused by NBP and ECB: publication-window retry, hourly
confirmation, universe refresh, loop tick and post-publication freshness grace. These are not
provider-published limits. `CURVE_FEED_*` likewise belongs to the reusable curve scheduler; each
provider package still registers its own builders, request cost and cadence.

For a quote, the database key is `(provider, symbol)`. The current board row is upserted and a raw
snapshot is appended only when price fields change. The lifecycle lock rechecks the active set
before write, so a late HTTP response cannot restore a removed feed. For a curve, the retained key
is `(provider, curve_name, as_of_date)`; a newer receipt for the same source date revises its
points, while an older source date cannot replace the current set.

### 2.2 Provider-by-provider path, including the extraction method

| Package | Extraction | From source to stored fact |
| --- | --- | --- |
| `providers/finnhub/` | JSON API | `client.quote/search/market_status` → `normalizer` → symbol feed → quote store |
| `providers/twelve_data/` | JSON API, optionally batched | provider-symbol mapping → `client.quotes` → per-symbol normalization → quote store |
| `providers/nbp/` | JSON tables | table A/gold client → reference normalizer → publication-calendar feed → quote store |
| `providers/ecb/` | CSV API | EXR rows → reference quote; YC rows → two government `CurveSet`s |
| `providers/fred/` | JSON time-series API | selected observations → USD/PLN curve builders → curve store |
| `providers/eiopa/` | HTML discovery + ZIP + XLSX/XML extraction | release link → held archive → workbook reader → three risk-free `CurveSet`s |

**Finnhub.** `feed.py` imports its API key, 15 s/60 s open cadences, 300 s closed cadence
and 90%-safe minute budget. `client.py` calls `/quote`, `/search` and US market status. The
normalizer maps `c`, `pc` and Unix `t` to last, prior close and provider time. Before every store,
the feed resolves the symbol again from watchlist/open positions/benchmark. It also polls market
status so freshness can distinguish a valid close from a failed live feed.

**Twelve Data.** `client.py` converts canonical six-character FX/metal pairs to the provider's
`AAA/BBB` notation and can request several symbols in one `/quote` call. `feed.py` charges one
daily credit per symbol, isolates an invalid member of a batch and spreads the next due-times over
the daily allowance. `normalizer.py` additionally checks returned currency and exchange against
the instrument identity; this is what prevents a USD response being labelled PLN. Search mapping
keeps the venue in symbols such as `ASB:GPW`.

**NBP.** There is no API key or invented rate limit. `client.py` reads table A and the gold endpoint.
`normalizer.py` turns the published mid into a `REFERENCE` quote in PLN and uses `effectiveDate`
as provider time. `feed.py` builds the needed universe from configured defaults plus settlement
currencies required for reporting. Common `OfficialFixingFeed` retries inside the Warsaw publication
window and confirms hourly outside it. These rows support comparison and FX conversion, never a
trade fill.

**ECB.** One package owns both capabilities. `client.py` decodes CSV rather than JSON. EXR rows go
through `normalizer.py` and the Berlin publication calendar into reference quotes. YC rows go
through `curves.py`: the provider dataset keys `G_N_A` and `G_N_C` select AAA and all-ratings
government curves, eleven tenor codes become points, and incomplete coverage is rejected. Both
feeds share one keyless runtime, so health and request counts describe the actual ECB source.

The fixing universe is dynamic, but the conversion map is not guessed or written onto a trade.
`official_fixing_set.py` starts with the configured NBP/ECB pairs and reads the distinct settlement
currencies of active and closed trades. For each missing currency it requires an NBP pair against
PLN and an ECB pair against EUR. `OfficialFixingFeed` reloads this in-memory requirement set every
60 seconds; its loop wakes every 15 seconds, but an HTTP call is made only when the provider fetch
is due: every five minutes while waiting inside the publication window, otherwise hourly. The
normalizer then stores the latest published fixing in the ordinary quote tables with reference
grade. A valuation remains in its native settlement currency. The reporting screen independently
requests the stored conversion paths from `/fx/rates` on entry/reporting-currency change and every
60 seconds. Selecting a reporting currency therefore never starts an external provider request,
and a newly discovered trade currency can wait for the next due fixing round unless the provider
is refreshed manually.

**FRED.** `client.py` calls `/series/observations` with the API key and classifies FRED's body-level
400/429 errors. `curves.py` selects the latest usable DGS observation at each US Treasury tenor.
For PLN it reads only the published 3M interbank and 10Y government anchors, then marks the
1Y/2Y/5Y points as derived. `feed.py` declares worst-case request costs (11 and 2) before a builder
starts, so a partial curve cannot silently overrun the shared budget.

**EIOPA.** This is the only scraping-like path rather than a direct data endpoint. `client.py`
reads the official release HTML, extracts the newest ZIP link, downloads it and holds the archive
so EUR/USD/PLN do not download the same file three times. `workbook.py` opens the nested XLSX as
ZIP/XML, finds `RFR_spot_no_VA`, resolves shared strings and reads the chosen country columns.
`curves.py` converts decimal rates to percent, records LLP/UFR/CRA evidence and marks points beyond
the last liquid point as extrapolated. `feed.py` schedules the three monthly risk-free curves. Its
10-request rolling minute budget is local self-restraint for the public download host, not an
EIOPA-published limit; `keyless` means only that no API credential is required.

Provider dataset names stay in these packages and provenance. The UI uses functional families:
`Risk-free`, `Government bonds` and `Reference projection`, qualified by currency and necessary
rating/index details. Stable keys remain the database/API identity.

The two clocks must not be merged: `provider_timestamp`/curve `as_of_date` says when source data
applies; `received_at` says when this process obtained it. A market can therefore be `CLOSED` on a
valid previous close, while `STALE` means the expected observation did not arrive.

### 2.3 Watchlist, market identity and refresh

The watchlist is the user-owned instrument master for this phase. `symbol_search.py` queries
enabled Finnhub and Twelve Data clients concurrently under their normal budgets/cooldowns,
normalizes and ranks results, deduplicates within each provider and caches only a fully successful
search. The UI adds that normalized identity, including exchange-qualified symbols such as
`ASB:GPW`. The add API itself validates shape and consistency with an existing row, not external
truth: Twelve rejects a returned currency/exchange mismatch when those fields exist, while
Finnhub quotes trust the stored US-search identity.

There are two related sets:

- **new-trade catalog**: watchlisted symbols and only providers selected for them;
- **polling set**: watchlist + symbols required by open positions + benchmark.

A held-only symbol continues to receive marks for valuation and closing, but cannot create
new risk until it is added to the watchlist again. A successful add/remove broadcasts a
frontend invalidation so an open ticket refreshes its instrument and option-underlying
choices.

The Market Data table exposes manual refresh. `POST /market-data/refresh` uses the same
provider budget, validation, store and publication path as scheduled polling. A failure is
reported for the actual provider; the UI does not invent a substitute price.

### 2.4 Pacing and failure isolation

Finnhub prioritizes open positions and the benchmark over ordinary watchlist rows. Twelve
Data batches symbols and spreads a best-effort, process-local daily ledger across the active
window. Strict rolling 60-second budgets default to 90% of configured provider limits; polling,
search and manual refresh all spend the same budgets. NBP/ECB follow publication windows and curve
builders use scheduled refetches.

Each provider has its own runtime state. Authentication, rate-limit, transport and unexpected
processing failures degrade only that provider and apply cooldown/backoff. A data-quality error
for one symbol is request-local and does not by itself mark the provider unhealthy. Twelve
isolates malformed symbols inside a batch, but explicitly degrades the provider when the whole
batch is unusable. Feed loops catch failures at their guarded boundaries and continue polling.

## 3. Persistence, snapshots and streams

### 3.1 Stored facts

| Table | Stored fact |
| --- | --- |
| `watchlist_items` | user-selected instrument identity and providers |
| `market_data_spot_prices` | latest normalized row per `(provider, symbol)` |
| `market_data_snapshots` | change-only quote history with raw provider payload |
| `market_data_curves` | one retained curve set per provider/name/as-of |
| `market_data_curve_points` | tenor, rate and source series/as-of for each point |
| `trades` | fixed contract, entry/close value, provider/curve evidence, `source` and `created_by_service` |
| `valuations` | append-only calculated fair value and PnL observations |

Unchanged quote polls update the current board's clocks/classifier but do not create a raw
history row. Quote history is therefore an observed-change audit tape, not a complete
intraday chart. Retention removes old unreferenced quote snapshots; entry/close snapshots
referenced by trades are protected. Consequently, a spot trade receives a snapshot ID only when
its exact board revision is also a change snapshot; provider, execution price and provider time
remain stored when an unchanged poll advanced the board clock. Ticket opens persist
`source=MANUAL` and `created_by_service=trade-action-service`.

A model-priced trade stores its contract terms plus selected curve names and their entry
provider/as-of. It does not store a private copy of every point. Later valuation resolves
the current retained set by curve name. Entry provenance explains the original price;
current curve revisions drive current fair value. Close metadata records the discount and
projection provider/as-of actually used at close.

### 3.2 Snapshot plus SSE

SSE is a notification channel, not durable replay. The market-data stream has the stronger
protocol: its consumers open the stream, buffer events, read a complete snapshot with
`(stream_id, event_id)`, replace local maps, then apply only buffered same-stream events
above that watermark. This prevents both the reconnect gap and a stale snapshot replacing
a newer quote or curve.

If a bounded server queue overflows, the connection is deliberately closed. If a snapshot
fails or times out, the consumer reconnects instead of continuing with an unknown partial
state. Pricing and the browser also reject lower quote/curve revisions as defence in depth.

The browser replaces both spot and curve maps, so removals survive a disconnect. Pricing
does the same and immediately revalues every active trade. The valuation stream has no
event IDs: browser and blotter open it first, fetch the valuation snapshot, then keep the
newer row by `valuation_time`; the browser merges this seed while blotter reconciles its
active valuation map.

## 4. Curve model and selection

### 4.1 Stored rate, interpolation and discount factor

Curve points store provider rates in percent for display and convert them to decimal
fractions for pricing. For a required time `t`, `shared/pricing/curves.py` linearly
interpolates the rate between neighbouring tenors and uses the nearest rate outside the
grid. It then applies one deliberately simple annual-compounding convention:

```text
DF(t) = 1 / (1 + r(t))^t
```

`DF(t)` is the value today of one currency unit paid at time `t`. It is not itself a
tradable price. A displayed rate at 10Y discounts the cashflow paid at 10Y; coupons paid
earlier use their own interpolated rates and discount factors.

Builders reject non-finite points, duplicate/insufficient tenors and unusably short
coverage. The US Treasury and ECB government curves require at least eight points,
including a short point and coverage to at least 10Y. A failed partial refresh leaves the
last good set in place.

### 4.2 The seven intentional curves

| Desk label | Stable key / source | Allowed use | Limitation |
| --- | --- | --- | --- |
| EUR · Risk-free | `EUR_RISK_FREE` / EIOPA | bond, option and IRS discount; IRS projection fallback | monthly; projection is not an index forecast |
| USD · Risk-free | `USD_RISK_FREE` / EIOPA | same in USD | monthly; same projection caveat |
| PLN · Risk-free | `PLN_RISK_FREE` / EIOPA | same in PLN | partly extrapolated after the source's liquid horizon |
| EUR · Government bonds · AAA | `EUR_GOVERNMENT_BONDS_AAA` / ECB | EUR bond discount | best-rated sovereign basket only |
| EUR · Government bonds · all ratings | `EUR_GOVERNMENT_BONDS_ALL` / ECB | EUR bond discount | includes sovereign credit-quality spread |
| USD · Government bonds | `USD_GOVERNMENT_BONDS` / FRED | USD bond discount | par yields treated as zero rates |
| PLN · Reference projection · 3M | `PLN_REFERENCE_PROJECTION_3M` / FRED | PLN IRS 3M floating projection | only 3M and 10Y are published anchors; middle points are linear |

Currency and the product-use allow-list are server-side guards, not UI suggestions. A EUR
contract cannot use a USD curve. Government curves are offered for bonds because their
yields include the market basis of government borrowing. Risk-free curves are appropriate
for option discounting and the simplified collateral-style IRS discount role. They can
also discount a bond when the exercise intentionally models a credit-free cashflow.

The all-ratings government curve will normally be above the AAA curve because weaker
issuers require compensation for credit risk, but this is an empirical relationship, not
a hard invariant. A higher selected curve produces smaller discount factors and usually a
lower bond PV.

### 4.3 Curve construction and provenance

The provider assignments come from `CURVE_CATALOG`; each provider's `curves.py` translates only
its assigned keys into source-specific datasets:

- `providers/fred/curves.py` US Treasury: current usable DGS observations across 1M–30Y;
- the same FRED module's PLN projection: published 3M interbank and 10Y government anchors, with derived
  1Y/2Y/5Y points;
- `providers/ecb/curves.py`: selected AAA and all-ratings euro-area government-yield tenors;
- `providers/eiopa/curves.py`: nine selected tenors for EUR/USD/PLN from the stated monthly
  risk-free release parsed by `workbook.py`.

Each set carries `provider`, `curve_name`, `curve_basis`, `currency`, optional
`index_tenor`, `as_of_date` and `received_at`. Each point carries its tenor/rate and, when
published directly, `source_series` plus `source_as_of`. A null source series marks a
derived/extrapolated point. The UI keeps functional selection simple and reveals these
source details only in the expanded curve view.

## 5. What the three model prices mean

### 5.1 Bond

The user defines currency, face amount, annual coupon percent, maturity and payments per
year, then selects an allowed discount curve. Currency comes from the contract/curve;
face amount is user-defined. The coupon is also user-defined unless the user presses
`Use as coupon`.

For each payment time `t_i`, the model discounts the coupon and adds principal at maturity:

```text
coupon_i = face × coupon_rate × accrual_i
PV = Σ (coupon_i + principal_if_final) × DF(t_i)
price per 100 face = PV / face × 100
```

The backend's `price` and stored `trade_price` are the total PV for the entered face
amount. The ticket displays `price per 100 face` because that is the usual market quote
convention. A displayed 98 means the modeled cashflows are worth 98 per 100 face, not that
the face amount was changed.

`Curve-implied par coupon` answers a different question: which coupon rate would make the
same face/maturity/payment schedule worth approximately 100 under all selected discount
factors?

```text
par coupon = (1 - DF(T)) / Σ(accrual_i × DF(t_i))
```

The maturity curve rate discounts only the final payment, whereas the par coupon balances every
coupon date plus redemption; the two need not match. `Use as coupon` copies this derived starting
input, rounded for the form. The coupon is not controlled by later curve changes.

The position is synthetic: there is no bond master, settlement/accrued interest, day-count
calendar or issuer spread. A large difference between PV and face can be perfectly
consistent with the entered coupon versus current rates. It becomes “not market-like” only
when the entered cashflows or selected basis do not represent the intended real bond.

### 5.2 Interest-rate swap

The user defines direction, currency, notional, fixed rate, maturity and 3M/6M floating
index tenor. The discount curve values future cashflows today; the projection curve
estimates the floating coupons.

For period `[t_(i-1), t_i]`:

```text
forward return_i = DF_projection(t_(i-1)) / DF_projection(t_i) - 1
fixed cashflow_i = notional × fixed_rate × accrual_i
floating cashflow_i = notional × forward return_i

PV_fixed = Σ fixed cashflow_i × DF_discount(t_i)
PV_float = Σ floating cashflow_i × DF_discount(t_i)
```

For pay-fixed, `NPV = PV_float - PV_fixed`; receive-fixed reverses the sign. This NPV is
the value of the whole stated notional today. It is not the notional and not a periodic
coupon. At the displayed fair fixed rate both legs have the same PV, so a new swap begins
near zero. Entering a different fixed rate creates positive value for one direction and
negative value for the other.

“Projection is an approximation” has a precise meaning. A production IRS projects each
floating reset from a curve calibrated to that exact market index and discounts under a
collateral/OIS curve. This phase has no licensed WIBOR/Euribor/term-SOFR curve. The PLN 3M
set uses one 3M interbank anchor, one 10Y government anchor and linear middle points; an
EIOPA risk-free set has no matching index tenor at all. The math is dual-curve and shows
the correct roles, but the forward coupons are educational estimates, not dealer quotes.

### 5.3 European option

The user selects a watchlisted equity underlying and its provider, call/put, strike,
maturity and a same-currency discount curve. The server uses the provider's current
underlying mid, the selected discount factor and Black–Scholes with fixed 22% volatility:

```text
premium = BS(spot, strike, maturity, DF(T), volatility, call_or_put)
total model value = premium × quantity × multiplier
```

The displayed premium is per one-unit Phase 5 contract; multiplier is one. A call usually gains
when spot or rates rise; a put usually gains when spot falls and tends to lose when rates rise.
More volatility raises both prices in this model. More maturity often adds optionality, but is not
guaranteed to raise every European put under positive rates. The model omits dividends, an
implied-volatility surface, early exercise and listed-contract multipliers, so it demonstrates
dependency wiring rather than a broker-reproducible premium.

### 5.4 One pricing interface, explicit implementation per asset

Pricing follows the same pattern as providers. `app/pricers/contract.py` defines one
`PricerRegistration`: supported asset classes plus four operations — load market inputs,
calculate, shock inputs and optionally explain details. `pricers/registry.py` is the only router
used by the preview API, scenario API and live valuation engine.

| Pricer | Market inputs loaded from pricing cache | Reusable formula |
| --- | --- | --- |
| `spot.py` | `(provider, symbol)` quote | normalized mid, then last fallback |
| `bond.py` | selected discount curve | `shared/pricing/bond.py` cashflow PV |
| `european_option.py` | selected underlying provider quote + discount curve | `shared/pricing/european_option.py` |
| `irs.py` | discount curve + the required Phase 5 projection curve | `shared/pricing/irs.py` legs and directional NPV |

The sequence for every preview and revaluation is therefore readable in the same order:

```text
asset_class -> pricers/registry -> asset pricer.load_inputs
            -> asset pricer.calculate -> shared/pricing/<asset>.py
            -> finite Decimal price + multiplier
```

`valuation_engine.py` no longer contains branches for every asset. It takes the routed result,
applies signed quantity/PnL, adds quote or curve provenance, persists through `repository.py`,
then publishes. `scenario.py` uses the same registration and formula after replacing only the
declared market input: spot for spot/options, or both rate curves for bond/IRS parallel shocks.
Trade Action imports the same shared formulas when it independently recomputes an open/close;
the execution gate and Pricing cannot drift into different bond/IRS/option math.

## 6. Trade lifecycle and revaluation

### 6.1 Preview and open

`NewTradePanel` derives fields from the selected book's asset class. Currency/underlying
changes clear incompatible curves; a sole eligible curve/provider is auto-selected. The
pricing preview is debounced and invalidated by every contract input plus the selected
quote/curve revisions. The request sends expected revisions; pricing returns 409 until its
independent cache has caught up, preventing an old model value from being labelled current.

Submission sends `client_seen_price`, not an executable price chosen by the browser.
Trade-action:

1. normalizes a required non-empty `client_request_id` and derives a deterministic trade ID;
2. returns the prior acknowledgement when that request was already accepted/stored;
3. validates book/class, symbol/provider or terms/curves, quantity and finite bounds;
4. reads the current provider quote or current retained curves and recomputes the price;
5. rejects excessive drift from the displayed value;
6. enqueues the intent in a bounded in-memory queue;
7. validates again in the worker, then writes the trade and audit event.

Spot BUY uses ask, SELL uses bid, falling back to the normalized mid when there is no
spread. Model-priced contracts use the recalculated PV. IRS drift is scaled by notional
because a near-zero NPV cannot provide a stable percentage denominator.

HTTP 202 means accepted into a process-local queue, not a durable execution commitment.
The queue and batch sizes are bounded; overload returns 503/413 instead of growing memory.

### 6.2 Revaluation, PnL and close

Pricing loads active trades from PostgreSQL and keeps a process-local market cache. A
relevant quote or curve tick targets affected trades; a successful snapshot replacement
revalues all active trades. Each finite calculation is persisted before it is cached and
published. Active-set polling also detects new/reassigned trades and triggers immediate
revaluation.

For BUY:

```text
PnL = (current price - entry price) × quantity × multiplier
```

SELL reverses the sign. Bond/IRS size is already embedded in their price, so quantity is one.
Currency follows a separate, explicit path; it is never inferred from the numeric mark:

1. Search normalization records the quote currency and venue in `watchlist_items`. Twelve also
   validates returned quote currency/exchange before accepting a mark.
2. A spot trade copies that instrument currency. Bond/IRS currency comes from
   `settlement_currency`; an option takes the underlying currency. `term_schemas.py` rejects a
   selected curve whose currency differs.
3. Pricing copies the frozen `trade_currency` into every valuation. `fair_value` and PnL therefore
   remain amounts in the instrument's settlement currency; Pricing performs no portfolio FX.
4. Market Data stores NBP/ECB reference pairs in the same quote table but marks them non-tradeable.
   `GET /fx/rates?to=...` calls `shared/fx.py`, which loads only those official FX rows.
5. The resolver tries the newest direct or inverse pair, then an ECB cross through EUR, then an
   NBP cross through PLN. Both legs of a cross must use the same provider; its `as_of` is the older
   leg. Missing paths return a reason rather than a guessed rate.
6. The frontend first groups rows into currency subtotals. Only after the user chooses a reporting
   currency does `domain/fx.js` multiply every subtotal—even when the portfolio has only one native
   currency—and display path, provider and as-of. Headline and book aggregate cards use those
   converted totals; individual position rows retain their settlement currency. Converted amounts
   are not written back to trades or valuations.

This separation prevents the original ASB-type error: `309 USD` cannot become `309 PLN` merely
because the instrument was expected to be Polish. Book-risk analytics are a known exception:
their process-local PnL series currently sums raw currencies before alpha/beta, so mixed-currency
results there are not comparable amounts.

Alpha/beta readiness depends on time observations, not on the number of positions. Each new
Finnhub SPY tick pairs the SPY return with the change in each book's PnL; the first tick only sets
the baseline. After 20 aligned returns, OLS reports alpha (the average PnL change not explained by
SPY) and beta (PnL sensitivity to the SPY return), scaled by the configured capital base. Before
that the status is `INSUFFICIENT_DATA`; 20 unchanged closed-market observations instead produce
`ZERO_BENCHMARK_VARIANCE`. This rolling window is process-local and intentionally has no
historical backfill, so a pricing-service restart begins a new measurement window.

Manual spot close sends opposite-side bid/ask when present and otherwise the displayed mid/last;
the current Finnhub and Twelve adapters normally supply only last/close. Model trades send the
latest model value. Closing is risk-reducing, so the server allows a market-close or stale spot
observation (and a stale option underlying) but never a missing/unusable one; the UI exposes its
status and age. The server applies drift protection and stores close value/time plus an available
snapshot or curve provenance. Finalization writes one terminal valuation and realized PnL.
Repository row locks prevent a late valuation after close or reassignment, and terminal values
are restored before pricing serves after restart.

The non-mutating scenario endpoint applies decimal spot shocks (`0.10` = +10%) and parallel rate
shocks in basis points (`25` = +25 bp); IRS shifts both curves. It is a sensitivity demonstration,
not VaR, DV01 or Greeks. When a caller supplies `current_price`, that observed value anchors the
base and the model contributes only the shocked-minus-base change; otherwise the model base price
is used directly.

## 7. UI contract

The UI is intentionally an explanation layer over server rules, not a second pricing
engine.

- Market Data shows symbol, class, name, mark with quote currency, day/tick move with
  units, venue, provider, feed state and provider age. Less important columns hide on
  narrow screens; the table remains horizontally usable.
- Search displays full instrument identity before add. Refresh controls sit with the row
  or feed they affect. Loading skeletons retain layout during refreshes.
- Curve charts group by currency, use a readable auto-padded Y range and a bounded plot
  width on large displays. Selecting a point exposes source detail without putting provider
  series codes in every label.
- The ticket keeps contract inputs together and curve evidence in the right-hand column.
  It auto-corrects provider/curve choices after book, currency or underlying changes.
- Bond output separates price per 100 from total position value. IRS separates NPV, fixed
  leg, floating leg and fair fixed rate. Option separates premium per contract from total.
- Trades uses a responsive default column set, optional columns and explicit incremental
  loading of older history. Search/sort state says when it covers only the loaded window.
- Books keeps `(symbol, currency, provider)` positions separate, so two feeds are not
  collapsed into one mark; it applies the same quote/curve freshness rules as the blotter.
- `LIVE`, `MARKET CLOSED`, `STALE`, `PENDING` and trade `CLOSED` are distinct. Blotter and
  valuation-stream fallbacks use the same quote/curve revision checks.

## 8. Code map and tracing recipes

### Shared domain

| Path | Responsibility |
| --- | --- |
| `shared/providers.py` | provider groups and asset capabilities |
| `shared/quotes.py` | normalized quote invariants and wire shape |
| `shared/curves.py` | curve identities, desk metadata, roles/uses and set validation |
| `shared/curve_registry.py` | latest persisted curve metadata and pricing arrays |
| `shared/term_schemas.py` | bond/IRS/option fields, defaults and currency/use/index guards |
| `shared/pricing/` | separate curve, bond, IRS, option and risk formulas reused across services |
| `shared/active_set.py` | watchlist versus held versus benchmark polling roles |
| `shared/fx.py` | official direct/inverse, ECB/EUR-cross and NBP/PLN-cross resolution |
| `shared/models.py` | SQLAlchemy persistence model |
| `shared/service_runtime.py` | startup hooks and daemon-thread launch |

### Market-data service

| Path | Responsibility |
| --- | --- |
| `services/market-data-service/app/config.py` | provider budgets, cadences and source windows |
| `services/market-data-service/app/providers/registration.py` | common provider capability contract |
| `services/market-data-service/app/providers/<provider>/` | colocated client, normalizer/builder and runtime wiring for one source |
| `services/market-data-service/app/providers/base.py` | reusable HTTP transport, logging and typed provider failures |
| `services/market-data-service/app/symbol_search.py` | generic concurrent search, ranking and cache over registered search providers |
| `services/market-data-service/app/official_fixing_feed.py`, `curve_feed.py` | reusable official-fixing and scheduled-curve engines |
| `services/market-data-service/app/quote_store.py`, `curve_store.py` | SQL state/history and revision ordering |
| `services/market-data-service/app/quote_service.py`, `curve_service.py` | board/watchlist/refresh use cases |
| `services/market-data-service/app/provider_runtime.py`, `budget.py`, `poll_schedule.py` | failure state and pacing |
| `services/market-data-service/app/publisher.py` | bounded SSE fan-out and market checkpoints |
| `services/market-data-service/app/scheduler.py` | maps and loops derived from provider registrations |
| `services/market-data-service/app/api.py` | HTTP boundary, snapshot assembly and SSE subscriptions |

### Trading, pricing and blotter

| Path | Responsibility |
| --- | --- |
| `services/trade-action-service/app/api.py`, `action_queue.py` | request boundary, idempotent ACK and bounded queue |
| `services/trade-action-service/app/trade_validation.py` | authoritative open/close validation and repricing |
| `services/trade-action-service/app/trade_handlers.py`, `repository.py` | trade lifecycle use cases and main trade writer |
| `services/pricing-service/app/market_data_client.py` | market snapshot/SSE reconciliation and dispatch |
| `services/pricing-service/app/pricers/contract.py`, `registry.py` | one asset-pricer contract and router |
| `services/pricing-service/app/pricers/<asset>.py` | explicit market inputs, calculation and shock for each asset |
| `services/pricing-service/app/valuation_engine.py` | PnL/provenance assembly, persistence and revaluation loop |
| `services/pricing-service/app/cache.py`, `repository.py` | live/durable valuations and finalization flag write |
| `services/pricing-service/app/scenario.py`, `schemas.py` | validated non-mutating shocks |
| `services/blotter-service/app/pricing_service_client.py` | valuation snapshot/SSE reconciliation |
| `services/blotter-service/app/service.py`, `repository.py` | trade, position and currency-split PnL read model |

### Frontend

| Path | Responsibility |
| --- | --- |
| `frontend/src/hooks/useMarketFeed.js`, `useValuationFeed.js` | reconciled snapshot/SSE state |
| `frontend/src/hooks/useWatchlist.js` | add/remove/manual-refresh commands |
| `frontend/src/hooks/useFxRates.js`, `useReportingCurrency.js` | FX fetch and persisted reporting choice |
| `frontend/src/domain/marketData.js`, `valuations.js` | normalization, monotonic merge and freshness |
| `frontend/src/domain/curves.js` | curve view model plus UI par-coupon/fair-rate helpers |
| `frontend/src/domain/fx.js`, `components/fx/FxReport.jsx` | currency subtotals, conversion and exclusions |
| `frontend/src/domain/tradeActions.js`, `trades.js` | ticket intent and blotter view models |
| `frontend/src/components/trades/NewTradePanel.jsx`, `TermFields.jsx` | preview lifecycle and curve-assisted inputs |
| `frontend/src/services/endpoints.js` | browser API registry; proxy supplies service routing |

Fast tracing paths:

```text
wrong quote
  providers/<name>/client -> normalizer -> feed -> quote_store -> snapshot/SSE

wrong provider schedule/health
  app/config -> providers/<name>/feed -> ProviderRuntime/common feed -> registration -> scheduler

wrong curve choice
  providers/<name>/curves -> curve_store -> shared/curves catalog -> term_schemas guard

wrong model value
  stored terms -> pricers/registry -> pricers/<asset> -> shared/pricing/<asset> -> valuation

wrong converted total
  reference provider -> quote_store -> /fx/rates -> shared/fx -> domain/fx currency subtotals

trade accepted but absent
  trade-action API -> idempotency/queue -> validator -> handler -> repository/audit

stale blotter row
  market revision -> pricing valuation payload -> valuation SSE/DB fallback -> statusOf()
```

## 9. Limits and verification

### Why the correction pass was necessary

The long correction pass came from five planning errors rather than five unrelated UI bugs:

- the first plan treated assignment bullets as features to accumulate before checking which
  user decision each feature served;
- curve identity, provider mapping, allowed use and display language initially had more than one
  owner, so provider terminology leaked into the desk vocabulary and mappings could drift;
- inputs and outputs were implemented before their units and financial interpretation were
  written down, making bond PV, par coupon, IRS projection and currency labels hard to defend;
- browser checks followed the happy path and one viewport, missing dependent-selector state,
  fast switching, watchlist refresh, stale/closed states and wide-screen scaling;
- documentation described the result after it grew instead of constraining the domain and code
  path before implementation.

The carried rule is therefore domain-first and vertical: define the number, unit, provenance,
freshness and user action; assign one semantic owner; trace one value from provider to screen;
then implement and verify the interaction matrix. New phases must rewrite a stale roadmap task
instead of preserving complexity merely because it was once planned.

### Financial and technical limits

- published par/government yields are treated as zero rates;
- rate interpolation is linear and extrapolation is flat, with one annual convention;
- no day counts, settlement calendars, accrued interest, issuer spread or bond master;
- no index-calibrated projection curve, collateral agreement or production multi-curve bootstrap;
- fixed 22% option volatility, no dividends/surface/early exercise/listed multiplier lifecycle;
- curve points are not copied into each trade, so entry provider/as-of is provenance rather
  than an immutable reconstruction of every input point;
- book-risk alpha/beta sums raw PnL currencies; use the reporting views for converted totals;
- the trade-action queue and Twelve daily ledger are process-local, not crash-safe ledgers;
- SSE has no event replay; recovery reconstructs current state, not the missed sequence;
- source holiday calendars and licensed market conventions are outside this phase.

### Verification contract

Run the static checks:

```bash
python3 -m compileall -q shared services db/versions
git diff --check
cd frontend
npm run lint
npm run deadcode
npm run build
```

Then rebuild the affected containers and prove these behaviors against the running stack:

- snapshot counts and provider health are plausible; no service traceback/error log;
- add/remove/refresh a watchlist feed and confirm the ticket updates;
- open one provider-bound spot trade and one bond, IRS and option;
- change a relevant quote/curve and observe targeted valuation/PnL movement;
- reject wrong currency, curve role/index, non-finite values and a stale preview;
- replay one `client_request_id` and confirm the same 202/trade ID with no second trade row;
- close a trade using the displayed mark and retain terminal PnL after restart;
- reconnect market/pricing/blotter streams and recover full current state;
- paginate/load older blotter rows and inspect a row's valuation history/provenance;
- check wide and narrow layouts for overlap and horizontal overflow.

Repeatable request examples live in `scenarios/provider-trading.http`,
`scenarios/reference-fx.http`, `scenarios/curves.http` and
`scenarios/scenario-analysis.http`.
