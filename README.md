# trading-desk

A mini front-to-back trading desk: market data → trade ticket → blotter → books → risk.
Six Python microservices (bottle, SQLAlchemy, structlog) plus Postgres and a React/Vite
frontend, communicating through database rows and server-sent events.

Forked from [trading-microservices](https://github.com/j-gulinski/trading-microservices),
which stays archived as the runnable synthetic demo. This repository removes every synthetic
flow and rebuilds market data around six real providers — Finnhub, Twelve Data, Alpha Vantage
(quotes), NBP, ECB, FRED (official rates and curves) — landing phase by phase per
[docs/hw5-plan-v2.md](docs/hw5-plan-v2.md). Current state: Finnhub powers the first live
slice — real US equity/ETF quotes on a provider-tagged board with honest freshness and
budget-governed polling, and every valuation stamped with the provider and quote time it used
([docs/market-data.md](docs/market-data.md)).

## Operating decisions

The rules the system currently runs on. Each was set by a phase; mechanics and rationale
in depth are in the phase reports, knob values in
[docs/configuration.md](docs/configuration.md).

| Area | Policy | Rationale |
| --- | --- | --- |
| Polling universe | Only the active set is polled: watchlist symbols, symbols with open trades, and the benchmark (SPY). | Free-tier budgets do not cover open-ended polling; the watchlist defines scope. |
| Polling tiers | Tier 1 (open-trade symbols, benchmark): 15 s. Tier 2 (remaining watchlist): 60 s. | Open positions and the benchmark return series require the freshest marks. |
| Closed market | All polling drops to 300 s after the provider confirms the market is closed. Unknown status is treated as open. | Prices do not change while the market is closed; 300 s confirmation polls remain to detect data issues and reopen. |
| Freshness | A quote is STALE after 3× its tier's open-market cadence (45 s / 180 s). The threshold does not widen when the market closes. | Staleness is measured against the feed's expected update rate; overnight rows are old and display as such. |
| Request budget | Client-side cap at ~80% of each provider's published limit (Finnhub: 48 of 60 req/min). Every request counts: quotes, market-status checks, manual refreshes. | The margin absorbs window misalignment and network retries; the provider's own limiter is never reached. |
| Budget exhaustion | An empty token bucket ends the polling round; due symbols retry on the next 1 s cycle. No state change, no audit. | Client-side throttling is normal operation, distinct from provider failure. |
| Provider failure | Provider responses drive a per-provider state machine: 429 → RATE_LIMITED (cooldown = `Retry-After`, default 60 s); 401/403 → AUTH_FAILED (300 s); network/5xx → ERROR (10 s). Audits are written on state transitions only. Per-symbol data errors do not change provider state. | Failures are visible, scoped to the provider that caused them, and one symbol cannot stop the feed. |
| Storage | `market_data_spot_prices`: one row per (provider, symbol), updated in place. `market_data_snapshots`: append only when the price changed, with the raw provider payload. | Bounded board size; history records price changes, not polling activity. |
| Retention | Snapshots older than 90 days are deleted daily, except rows referenced by `trades.entry_snapshot_id`. | Chart depth vs. hosted database storage; trade provenance must survive retention. |
| Registration | Inserting a watchlist row or opening a trade adds the symbol to polling within one active-set reload (≤15 s). `POST /refresh` forces the reload immediately. | The database row is the integration point; there is no registration API. |
| Streams vs. database | SSE streams deliver updates; the database is the source of truth. Every consumer seeds from the database (or `/snapshot`) and reconciles against it. | SSE has no replay; reconciliation recovers events lost during disconnects. |
| Valuation source | A valuation uses exactly one provider's quote. Trades without a recorded provider resolve to `DEFAULT_QUOTE_PROVIDER` (FINNHUB). Benchmark sampling accepts only (`BENCHMARK_PROVIDER`, `BENCHMARK_SYMBOL`) ticks. | PnL must be attributable to a single quote source; the benchmark return series must not be double-sampled. |
| Price handling | `bid`/`ask`/`last` are stored as received; missing fields stay NULL. `mid` is derived (bid/ask → reference → last) and drives valuation and display. Every quote carries `price_basis` and `quote_grade`. | Derived and end-of-day prices are identifiable as such. |
| Tradeability | Only watchlisted symbols are tradeable; the watchlist is the symbol master. | The tradeable universe is user-defined, not hardcoded. |

## Running

```
cp .env.example .env      # set a real POSTGRES_PASSWORD (and mirror it in both DATABASE_* URLs)
docker compose up --build
open http://localhost:3000
```

Provider API keys go into `.env` as they are registered — signup links: [finnhub.io](https://finnhub.io),
[twelvedata.com](https://twelvedata.com/register), [alphavantage.co](https://www.alphavantage.co/support/#api-key),
[fred.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys). NBP and ECB need no key.

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
| Finnhub → market-data | HTTP polling | 15 s / 60 s by tier; 300 s market closed; market status every 10 min | Quote and market-status ingestion, within the 48/min budget. |
| market-data → Postgres | upsert + conditional insert | per successful poll | Board update; a history row only when the price changed. |
| market-data → pricing, browser | SSE `market_tick`; `GET /snapshot` seed | per successful poll | Quote distribution; the snapshot provides full state at connect and after restart. |
| `trades` table → pricing | DB poll | 2 s | Detects new ACTIVE trades (valued from the cached quote) and CLOSED trades (one final valuation with realized PnL). |
| pricing → Postgres; → blotter, browser | valuation insert + SSE valuation stream | per revaluation | Valuation persistence and distribution; the `final: true` event propagates a close. |
| `trades` table → blotter | DB poll (reconcile) | 5 s; full load at boot | Adds ACTIVE trades that have no valuations yet; removes trades no longer ACTIVE if the final event was missed. |
| service `/health`, Postgres → monitoring | HTTP poll; `SELECT 1` | 5 s per target | Health state; UP/DOWN transitions are audited. |
| service log files → monitoring | file scan | 1 s | Central log collection for the Logs view; local disk only. |
| ticket → trade-action | in-memory queue, blocking consumer | on submit; no polling | Trade writes (the only writer of trades). |
| `market_data_snapshots` | DELETE sweep | daily | 90-day retention; rows referenced by trades are skipped. |
| browser ← monitoring | SSE `/logs/stream`; REST seed | per log line | Live log tail. |
| browser ← blotter, books, monitoring, trade-action | REST polling | ~5 s while the view is open | View data: trades list, books summary, health cards, intent queue. |

## Testing

No unit-test suite by design: behavior is verified end-to-end through the HTTP flows in
`scenarios/*.http` (any REST-client runner).

## Where to read more

[docs/README.md](docs/README.md) is the index: the base architecture, the configuration
reference, the plan of record (`docs/hw5-plan-v2.md`), and per-phase reports. Documentation is
produced phase by phase — each phase ships the docs for what it built.
