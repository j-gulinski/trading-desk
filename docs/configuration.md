# Configuration

One rule (D24 in [hw5-plan-v2.md](hw5-plan-v2.md)): a tunable
exists only as an environment variable listed in `.env.example`, and its rationale lives here —
`.env.example` stays scannable, this table carries the why. `os.environ` is read in exactly one
place, `shared/config.py` (`env_str` / `env_int` / `env_float` / `env_required`); every other
module imports typed values from its own `app/config.py` or from `shared.config`. A missing
required variable fails at boot with its name, not with an anonymous type error.

Provider budget knobs (poll cadences, daily ledgers, tolerances) arrive with their phases and
join this table then.

## Database

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | — (required) | compose `postgres` block | Container bootstrap role and database; must match the credentials inside `DATABASE_URL`. |
| `DATABASE_URL` | — (required, named boot failure) | every service via `shared/db.py` | The single SQLAlchemy DSN; host `postgres` is the compose network name. |
| `DATABASE_MIGRATION_URL` | — | `db/env.py` (alembic) | Same database reached from the host for hand-run alembic; in compose the migrate container gets `DATABASE_URL` substituted. |

## Service wiring

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `MARKET_DATA_STREAM_URL` | unset | pricing-service | Its one SSE inlet for quotes and curves. |
| `VALUATION_STREAM_URL` | unset | blotter-service | Live-valuation SSE inlet feeding the read models. |
| `BLOTTER_SERVICE_URL` | unset | books-service | Verifies zero ACTIVE trades before deactivating a book; unset refuses every delete. |
| `*_HEALTHCHECK_URL` (6) | unset | monitoring-service | One poll target per service, so removing a service from watch is unsetting one line. |

## Logging

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `LOG_LEVEL` | `INFO` | all services | DEBUG turns on per-tick pricing lines; INFO is the volume-safe default. |
| `LOG_DIR` | unset → stdout-only | all services + monitoring collector | The shared `./logs` bind-mount where each service writes `<name>.log` and monitoring tails. |
| `LOG_FILE_MAX_BYTES` | `5000000` | all services | 5 MB per rotating file bounds the mount. |
| `LOG_FILE_BACKUP_COUNT` | `3` | all services | ~20 MB ceiling per service with rotation. |

## Provider keys

| Variable | Registered at | Why |
| --- | --- | --- |
| `FINNHUB_API_KEY` | finnhub.io | Real-time US equities/ETF, 60 req/min free tier; the first provider wired in. |
| `TWELVE_DATA_API_KEY` | twelvedata.com | Batch quotes; the binding free-tier constraint is 800 credits/day; also the XAU/USD (metals) source. |
| `ALPHA_VANTAGE_API_KEY` | alphavantage.co | 25 req/day: EOD-grade equities plus the only free FX quote with true bid/ask. |
| `FRED_API_KEY` | fred.stlouisfed.org | Free instant key, 120 req/min; USD Treasury series and the OECD Poland anchors. |

NBP and ECB require no key — the four above are the complete registration list.

## Market data — Finnhub (Phase 2)

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `FINNHUB_TIER1_POLL_SECONDS` | `15` | market-data-service | Cadence for open-trade symbols + the benchmark — a handful of symbols at 4 req/min each stays far inside the budget; the D3 freshness threshold is 3× this (45 s). |
| `FINNHUB_TIER2_POLL_SECONDS` | `60` | market-data-service | Rest-of-watchlist cadence: the full 25-symbol cap costs ≤ 25 req/min, leaving tier-1 headroom; threshold 3× = 180 s. |
| `FINNHUB_CLOSED_POLL_SECONDS` | `300` | market-data-service | Outside US market hours the last trade does not move — 5-minute confirmation polls keep the board honest for a fraction of the budget. |
| `FINNHUB_BUDGET_PER_MINUTE` | `48` | market-data-service | Token-bucket capacity = ~80% of the published 60 req/min free tier (D7) — self-imposed headroom so scheduled polls plus manual refreshes never trip the provider's own limiter. |
| `SNAPSHOT_RETENTION_DAYS` | `90` | market-data-service | Quote history kept 90 days (raised from 30, owner decision 2026-08-19): ~1.5M change-only rows worst case, bounded for a hosted free-tier database. The daily sweep skips rows referenced by `trades.entry_snapshot_id`, so trade provenance outlives the window. |

Scheduler mechanics that are not tuning surface (active-set refresh 15 s, market-status check
10 min, HTTP timeout 10 s, threshold multiplier 3, cooldowns) are plain constants in the
service's `app/config.py`.

## Risk & benchmark

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `BENCHMARK_SYMBOL` | `SPY` | pricing-service, market-data-service | Symbol whose ticks drive alpha/beta sampling; SPY is the free real-time S&P 500 proxy (D14). The scheduler always keeps it in the active set's first tier. |
| `BENCHMARK_PROVIDER` | `FINNHUB` | pricing-service | The return series must come from exactly one (provider, symbol) feed — the guard stops double-sampling the moment a second provider also quotes SPY. |
| `BOOK_RISK_WINDOW` | `100` | pricing-service | Rolling regression window: stable cov/var, still tracks regime shifts. |
| `BOOK_RISK_MINIMUM_OBSERVATIONS` | `20` | pricing-service | Below this the card reads INSUFFICIENT_DATA instead of noise-fit alpha/beta. |
| `BOOK_CAPITAL_BASE` | `1000000` | pricing-service | Assumed capital turning a book's PnL stream into returns; alpha/beta scale as 1/base. |
| `PORTFOLIO_CAPITAL_BASE` | unset → base × books | pricing-service | Set only to model shared desk capital. |
