# trading-desk

A mini front-to-back trading desk: market data → trade ticket → blotter → books → risk.
Six Python microservices (bottle, SQLAlchemy, structlog) plus Postgres and a React/Vite
frontend, communicating through database rows and server-sent events.

Forked from [trading-microservices](https://github.com/j-gulinski/trading-microservices),
which stays archived as the runnable synthetic baseline. This repository replaces its
synthetic feed with real sources: Finnhub (US equities/ETFs) and Twelve Data (equities, FX,
metals) as quote providers, NBP and ECB official FX fixings as reference data feeding
the reporting-currency conversion, and real rate curves — FRED's US Treasury series, ECB
euro-area yield curves, EIOPA risk-free term structures and a documented PLN composite — plotted on the Market Data view and
pricing the curve-priced classes (BOND, IRS, EUROPEAN_OPTION).

Alpha Vantage is required by Homework 5 but intentionally belongs to the next project
phase. It has no Phase 5 capability, configuration or runtime entry.

Each symbol is watched per provider, so the same asset can be compared on both feeds and
either membership can be removed independently. The Market Data board groups provider feeds
under each symbol and shows a structured benchmark summary, a discrete tape of observed
price changes, and market-aware LIVE/CLOSED/STALE/MISSING states.
The trade ticket compares selected feeds and stores the
provider used for execution; pricing and closing continue to use that same provider. Facts
in [docs/market-data.md](docs/market-data.md); the detailed record in
[docs/phase-reports/](docs/phase-reports/).

## Operating decisions

The rules the system currently runs on. The reasoning behind each is in the phase report
that introduced it; knob values are in
[docs/configuration.md](docs/configuration.md).

| Area | Policy | Rationale |
| --- | --- | --- |
| Polling universe | Only the active set is polled: watchlist symbols, symbols with open trades, and the benchmark (SPY). | Free-tier budgets do not cover open-ended polling; the watchlist defines scope. |
| Polling tiers | Finnhub: tier 1 (open-trade symbols, benchmark) 15 s, tier 2 (remaining watchlist) 60 s. Twelve Data: flat batches whose true cadence is the greater of the 15-min knob and the daily-ledger pace (60 s × symbol count at defaults), with per-symbol due-times staggered after each batch; the strategy line states the computed cadence and next batch time. | Open positions and the benchmark return series require the freshest marks; Twelve Data's binding constraint is daily, so tiers would not buy freshness there — and a cadence the ledger stretched must be visible, not silent. |
| Closed market | Polling drops to confirmation cadence after the provider reports the market closed (Finnhub: exchange status, 300 s; Twelve Data: per-symbol `is_market_open`). Unknown status is treated as open. | Prices do not change while the market is closed; confirmation polls remain to detect data issues and reopen. |
| Freshness | Five states per (provider, symbol). Market open: LIVE until 3× the open cadence on the provider clock, then STALE. Market closed: CLOSED while confirmation polls keep arriving (3× closed cadence on the received clock), then STALE. MISSING = no data yet; UNSUPPORTED = capability fact, served by `/quotes` but never rendered as a board row. Capability appears in search results, where provider selection happens. | STALE means "this feed should be updating and is not" in both regimes; a closed market's closing price is the current price and renders neutral, not broken. |
| Valuation freshness | A valuation classifies against its own feed's cadence: LIVE while its mark keeps up with the feed's newest tick (within one freshness window), MKT CLOSED while the venue is shut, STALE when the feed is broken or pricing lags it. The 10 s wall-clock rule survives only as the fallback when the tab has no market data. | Only genuinely problematic rows may read STALE; a healthy 15-min Twelve Data cadence is not a problem, and "market closed" is not "trade closed". |
| Provider binding | Opening a spot trade requires an explicit provider choice on the ticket (options = providers actually polling the symbol; auto-selected only when there is exactly one). The trade row freezes the choice and pricing values the trade exclusively from it, close path included. | A trade priced by "whatever the default was" is unauditable. |
| Execution price | The **server** prices the fill from the chosen provider's board row: the ask for a BUY, the bid for a SELL, the mid when the feed quotes no spread. The client's number travels as `client_seen_price` and is only compared against it — if they differ by more than `TRADE_PRICE_TOLERANCE_PCT` (1%), the ticket is refused with the arithmetic in the message. A close is priced the same way from the provider frozen on the trade, side inverted. | A price a client can choose is a price nobody can audit; the tolerance is what stops a trade filling at a number that scrolled off the screen. |
| Execution gate | One validation function runs twice: synchronously on `POST /trade-actions` so the ticket hears the reason (**422 with the sentence in the body**), and again in the worker before the row is written, because the market moves in between. Every failure writes `ACTION_REJECTED` with the same reason. | `202 accepted` followed by a silent rejection is not feedback; re-validating at write time is what makes the accept-time check safe to trust. |
| Freshness at the ticket | LIVE and CLOSED rows with a usable price can be selected. MISSING, UNSUPPORTED and STALE rows cannot open a trade. Manual close keeps the existing internal stale-exit safeguard so a position is not trapped by a quiet feed. | The booking UI does not offer a stale-price override; current quote quality is part of provider eligibility. |
| Trade provenance | Every trade written by the gate records the executed price, the price the trader saw, the provider, the provider's quote timestamp, and an optional snapshot FK when that exact observation created a change row. Close records the same timestamp/optional snapshot provenance. `TRADE_CREATED` carries the same pricing facts. | These fields reconstruct why a fill had that number without pointing unchanged polls at an older raw response. |
| Curve catalog | `shared/curves.py` is the single catalog for seven curve keys, their owning provider, currency, desk-facing family and product-use allow-list. Startup requires each provider feed to wire exactly its assigned keys, and curve construction rejects a wrong provider or currency. Provider packages retain only source translations such as ECB dataset keys, FRED series and EIOPA workbook countries. `curve_basis` states how each set was derived; points keep the published percent rate with per-point `source_series` + `source_as_of`, and NULL series marks a derived point. | One domain catalog answers which provider owns a curve, while vendor codes remain adapter details and cannot silently redefine the product. |
| Curve-priced execution | BOND, IRS and EUROPEAN_OPTION open through the same server-priced gate as spot: the ticket previews a model value (pricing `POST /price`), the server recomputes the PV from the stored curves (and the underlying's board row for options), compares it against `client_seen_price` (IRS deviation measured against notional), and freezes each chosen curve's name, provider and as-of into the trade terms. Currency and index-tenor guards reject incompatible choices with the sentence ("a PLN IRS cannot discount on USD_GOVERNMENT_BONDS — it is a USD curve"). Close recomputes the same model value from the current stored curves. | A model-priced fill is auditable only if the server owns the model inputs; the guards make the projection-vs-discount choice a real, checked decision instead of a free-text field. |
| Request budget | A shared configurable 90% ceiling is derived from each provider's configured published limit (Finnhub: 54 of 60 req/min; Twelve Data: 7 of 8 credits/min and 720 of 800 credits/day). Twelve Data cadence spreads the safe daily allowance across a configurable 12-hour active window. | One safety rule replaces duplicated magic budgets, while the active window spends capacity when the desk actually runs. |
| Budget exhaustion | A full rolling 60-second budget ends the polling round; due symbols retry when enough safe capacity expires. No state change, no audit. | Client-side throttling is normal operation, distinct from provider failure; a strict window cannot burst above a vendor's minute cap. |
| Provider failure | Provider responses drive a per-provider state machine: 429 → RATE_LIMITED (cooldown = `Retry-After`, default 60 s); 401/403 → AUTH_FAILED (300 s); network/5xx → ERROR (10 s). Audits are written on state transitions only. Per-symbol data errors do not change provider state. | Failures are visible, scoped to the provider that caused them, and one symbol cannot stop the feed. |
| Storage | `market_data_spot_prices`: one row per (provider, symbol), updated in place. `market_data_snapshots`: append only when the price changed, with the raw provider payload. | Bounded board size; history records price changes, not polling activity. |
| Retention | Snapshots older than 90 days are deleted daily, except rows referenced by a trade's entry or close snapshot ID. | Hosted database storage stays bounded while trade provenance survives retention. |
| Quote history | Selecting a board row loads the latest 60 change-only snapshots for that provider-symbol. A price-changing `market_tick` refreshes the selected tape; unchanged ticks do not. The current quote and both clocks stay visible while only the observation tape scrolls. No connected intraday chart or vendor backfill is shown. | Sparse application observations are useful as a discrete audit trail, but connecting them would imply movement and coverage the application does not have. The history read is database-only and spends no provider budget. |
| Quote audit volume | `QUOTE_WRITTEN` is audited on the **first** stored quote per (provider, symbol); every later tick is in the structured log only. | Auditing every tick is ~8 000 rows a day of noise at these cadences; AuditLogs is the business record, not the poll log. |
| Registration | The watchlist stores a **provider choice per symbol**, not a capability. Search results list capable providers as toggles; the board can be filtered by provider. Adding a provider merges and fires one targeted, budget-aware refresh for each feed just added. `DELETE /watchlist/<symbol>?provider=` drops one feed and leaves the others ticking; `market_remove` tells every tab which row left. The configured benchmark is shown in its own strip rather than mixed into watchlist quotes. | Each feed must be addable/removable and comparable independently; a new pair should quote within seconds, not after a full paced interval; benchmark context is not watchlist membership. |
| Tradeable universe | `GET /instruments` serves watchlisted symbols only. A held-only symbol stays in the polling set on the provider frozen on its open trade, but cannot be used for a new trade until it is added back to the watchlist. | Removing a symbol must stop new risk without starving an existing position of marks; SPY remains benchmark-only. |
| Streams vs. database | SSE streams deliver updates; the database is the source of truth. Every consumer seeds from the database (or `/market-data/snapshot`) and reconciles against it. | SSE has no replay; reconciliation recovers events lost during disconnects. |
| Market Data API | Direct port 8001 uses `/market-data/snapshot`, `/market-data/quotes`, provider quote detail, all/provider SSE streams and `/market-data/refresh` as its canonical quote contract. Existing short routes remain aliases. | The brief's contract is executable as written while current browser and service consumers remain compatible. |
| Valuation source | A valuation uses exactly one provider's quote: the one frozen on the trade at the ticket. Legacy rows without a recorded provider resolve to `DEFAULT_QUOTE_PROVIDER` (FINNHUB). Benchmark sampling accepts only (`BENCHMARK_PROVIDER`, `BENCHMARK_SYMBOL`) ticks. | PnL must be attributable to a single quote source; the benchmark return series must not be double-sampled. |
| Capital invested | The Valuations summary and each open row show gross entry value: `abs(quantity) × entry price × multiplier`. A mixed-currency portfolio does not display one combined capital total. | The portfolio total stays traceable to its rows, while unlike currencies are not added without an FX conversion policy. |
| Price handling | `bid`/`ask`/`last` are stored as received; missing fields stay NULL. `mid` is derived (bid/ask → reference → last) and drives valuation and display. Every quote carries `price_basis` and `quote_grade`. | Derived and end-of-day prices are identifiable as such. |
| Tradeability | Only watchlisted symbols are tradeable; the watchlist is the symbol master. | The tradeable universe is user-defined, not hardcoded. |
| Official reference data | NBP (EUR/PLN, USD/PLN, gold per 1 g) and ECB (EUR/USD, EUR/PLN) fixings join the board as a fourth origin, `reference` — system-owned, beside watched/held/benchmark. The universe is the configured defaults plus settlement currencies still needed by active or closed reportable trades. Watchlist, search and `/instruments` offer watchlisted quote instruments only; a forged reference-provider intent is refused with the reason. | Reference data powers current and realized-PnL conversion, so removing a watchlist row or closing the last position must not silently break reporting — and a fixing is not a fillable price. |
| Source scheduling | NBP and ECB reference fixings use publication windows (NBP ~11:45–12:20 Warsaw; ECB EXR ~15:55–16:45 Frankfurt): 5-minute retries until a new as-of, then hourly confirmation. Curve builders are scheduled separately: six-hour default, EIOPA daily, `PLN_REFERENCE_PROJECTION_3M` weekly, with a 15-minute failure retry. FRED/EIOPA builders reserve worst-case minute tokens before starting; keyless NBP/ECB use calls-today counters without invented provider limits. | A fixing's calendar and a lagged curve release are different clocks; each is polled with the smallest defensible mechanism. |
| Reference freshness | A fixing's stale threshold is computed from the publication calendar: time to the next expected publication plus a 4-hour grace. The UI renders the as-of date, not a seconds counter, and labels an in-date fixing CURRENT. | A Friday fixing must read current through the weekend; STALE has to mean a genuinely missed publication (source holidays excepted — documented limitation). |
| Currency conversion | One resolver (`shared/fx.py`) with fixed precedence — identity, direct official rate or its inverse, one cross via EUR (ECB), cross via PLN (NBP) — and a path never mixes sources. Served as `GET /fx/rates?to=`; the browser multiplies for display. Valuations, Books and Business Overview show per-currency subtotals; converted totals and per-book figures appear only after an explicit reporting-currency choice (remembered per browser), labeled with rate, path, provider and as-of. PnL is never summed across currencies: a single-currency book shows its own amount, a multi-currency book shows the converted one or `MIXED` with the reason. Nothing converted is persisted. | Ad-hoc conversion at call sites drifts and silently mixes sources; positions keep settlement currency and only portfolio reporting converts (the review's rule). |
| Price units | Every rendered pair price names its unit ("4.3122 PLN per EUR"; gold "PLN per 1 g of gold"); search results name their quote currency. | A bare 4.31 next to a bare 0.86 invites misreading — the demo's TWD confusion was exactly this. |

## Running

```
cp .env.example .env      # set a real POSTGRES_PASSWORD (and mirror it in both DATABASE_* URLs)
./scripts/docker-dev.sh up
open http://localhost:3000
```

The development launcher trims rebuild debris, caps BuildKit cache at 8 GB and refuses a
rebuild when the host has less than 10 GB free. `./scripts/docker-dev.sh status` reports host
and Docker usage; `./scripts/docker-dev.sh clean` performs the same safe cache cleanup without
starting the stack. It never prunes named volumes, so Postgres data is not part of cleanup.
Compose also rotates every container's local JSON log at three 10 MB files, and the frontend
reuses one named `node_modules` cache instead of creating an orphan on each recreation.

Provider API keys go into `.env` as their adapters are registered — signup links:
[finnhub.io](https://finnhub.io), [twelvedata.com](https://twelvedata.com/register) and
[fred.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). The Alpha Vantage key
placeholder is already in `.env.example`; its runtime adapter lands in final Phase 6. NBP, ECB
and EIOPA need no key.

The browser talks only to the Vite dev server; every `/api/<service>/…` call is proxied to the
matching container (`frontend/vite.config.js`). Every configuration knob is listed in
`.env.example`; each one's rationale is in [docs/configuration.md](docs/configuration.md).

## Services

| Service | Port | Owns |
| --- | --- | --- |
| market-data-service | 8001 | provider quotes and curves, snapshot + SSE stream |
| pricing-service | 8002 | valuations, PnL, book alpha/beta, valuation SSE |
| monitoring-service | 8003 | health polling, audit trail queries, central log tail |
| books-service | 8004 | trading books CRUD |
| blotter-service | 8006 | trade and valuation read models |
| trade-action-service | 8008 | the only writer of trades; intent queue |

Each service builds its own image from the shared `docker/service.Dockerfile` template
(python:3.14-slim, multi-stage, one dependency layer from the root `requirements.txt`) and
boots through `shared/service_runtime.py`.

## Data flows

Every poll and stream in the system. Streams deliver updates; the database is the source
of truth (see Operating decisions). Services exchange business data through rows and
streams only — never through each other's APIs.

| Flow | Mechanism | Cadence / trigger | Purpose |
| --- | --- | --- | --- |
| Finnhub → market-data | HTTP polling | 15 s / 60 s by tier; 300 s market closed; market status every 10 min | Quote and market-status ingestion, within the 54/min safe budget. |
| Twelve Data → market-data | HTTP polling, batched (≤7 symbols/call by default) | 15 min best case; the 720-credit safe ledger is spread across the configured 12-hour active window | Quote ingestion for equities, FX, metals — one credit per symbol per batch. |
| Finnhub + Twelve Data → market-data | HTTP search calls | on watchlist search, cached 10 min per query | Symbol discovery; each upstream search is budgeted and Twelve Data records one request credit. |
| watchlist add → provider | targeted quote refresh, budget-aware | once per feed added to the watchlist | First quote lands within seconds instead of at the next scheduled poll; declined silently when the budget disallows it. |
| NBP → market-data | HTTP polling, publication calendar | every 5 min inside the ~11:45–12:20 Warsaw window until a new as-of; hourly confirmation otherwise | Table A FX fixings + the gold fixing as reference board rows; the full raw table lands in each row's snapshot. |
| ECB → market-data | HTTP polling, publication calendar | every 5 min inside the ~15:55–16:45 Frankfurt window until a new as-of; hourly confirmation otherwise | EXR euro reference rates (csvdata) as reference board rows. |
| ECB YC → market-data | scheduled HTTP polling | six-hour default, 15-minute failure retry | EUR · Government bonds · AAA/all ratings, one csvdata request per curve. |
| FRED → market-data | scheduled HTTP polling, budget-reserved builders | US government bonds every six hours; the two OECD Poland anchors weekly; 15-minute failure retry | 11 DGS series → USD · Government bonds; interbank + gov-bond anchors → PLN · Reference projection · 3M. |
| EIOPA → market-data | scheduled release-page/archive reads, budget-reserved builders | every 24 hours; 15-minute failure retry | The monthly risk-free term structure per currency → `EUR_RISK_FREE`, `USD_RISK_FREE`, `PLN_RISK_FREE`; one held archive normally serves all three. |
| market-data → pricing, browser (curves) | SSE `curve_tick` on the same stream; curve sets in `/market-data/snapshot` | per successful curve fetch | Curve distribution with points, provenance and flattened pricing arrays; pricing revalues every trade frozen to that curve. |
| ticket ← pricing model preview | REST `POST /price`, debounced | on each completed change to a curve-priced ticket's terms | The model value the trader sees — and the `client_seen_price` the server later checks the fill against. |
| ticket ← trade-action term schemas | REST polling | every 5 s while the New trade panel is open | Term fields plus the curve catalog (currency, index tenor, as-of) behind the ticket's curve pickers. |
| browser ← market-data FX rates | REST `GET /fx/rates?to=` | every 60 s while a reporting currency is selected on Valuations or Books | Conversion rates with full provenance for the display-only reporting overlay. |
| market-data → Postgres | upsert + conditional insert | per successful poll | Board update; a history row only when the price changed. |
| market-data → pricing, browser | SSE `market_tick` on `/market-data/stream`; `GET /market-data/snapshot` seed | per successful poll | Quote distribution; the snapshot provides full state at connect and after restart. |
| browser ← market-data history | REST `GET /market-data/quotes/<provider>/<symbol>/history?limit=60` | when a board row is selected; again only after a price-changing tick for that selected row | Latest stored observations for the independently scrollable detail tape; database read only, with no timer and no provider request. |
| `trades` table → pricing | DB poll | 2 s | Detects new ACTIVE trades (valued from the cached quote) and CLOSED trades (one final valuation with realized PnL). |
| pricing → Postgres; → blotter, browser | valuation insert + SSE valuation stream | per revaluation | Valuation persistence and distribution; the `final: true` event propagates a close. |
| `trades` table → blotter | DB poll (reconcile) | 5 s; full load at boot | Adds ACTIVE trades that have no valuations yet; removes trades no longer ACTIVE if the final event was missed. |
| service `/health`, Postgres → monitoring | HTTP poll; `SELECT 1` | 5 s per target | Health state; UP/DOWN transitions are audited. |
| service log files → monitoring | file scan | 1 s | Central log collection for the Logs view; local disk only. |
| ticket → trade-action | in-memory queue, blocking consumer | on submit; no polling | Trade writes (the only writer of trades). |
| `market_data_snapshots` | DELETE sweep | daily | 90-day retention; rows referenced by trades are skipped. |
| browser ← monitoring | SSE `/logs/stream`; REST seed | per log line | Live log tail. |
| browser ← blotter, books, monitoring, trade-action | REST polling | ~5 s while the view is open | View data: trades list, books summary, health cards, intent queue. |
| browser ← market-data | REST polling + one-shot seed | watchlist 10 s, provider ops 5 s while the view is open | Board placeholders and the ops card. |
| browser ← trade-action | REST polling | every 5 s while the New trade panel is open | The tradeable universe (`/instruments`) with the providers polling each symbol. |
| ticket ← market-data | the market SSE stream already open | per tick | The provider comparison prices and ages update in place, with no extra request and no reload. |

## Testing

No unit-test suite by design: the focused provider workflow is retained in
`scenarios/provider-trading.http`, the reference-data/FX-resolver workflow in
`scenarios/reference-fx.http`, and the curve/curve-priced-trading workflow in
`scenarios/curves.http` (any REST-client runner). The browser review follows the
Observe → Explain → Probe contract in `docs/validation-runbook.md`, covering the interactive
watchlist, quote clocks, provider-bound ticket, failure isolation and provider-log paths.

## Where to read more

[docs/README.md](docs/README.md) is the index. Two layers: lean reference sheets
(architecture, market data, configuration, the validation runbook) carry the current
facts, and the phase reports under `docs/phase-reports/` carry the detailed record —
every decision with its reasoning, the difficult concepts taught step by step, and the
evidence. The roadmap (`docs/implementation-roadmap.md`) is the working plan.
