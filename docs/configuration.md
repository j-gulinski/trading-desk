# Configuration

One rule (D24 in [hw5-plan-v2.md](hw5-plan-v2.md), format revised by the owner): a tunable
exists only as an environment variable listed in `.env.example`, and its rationale lives here —
`.env.example` stays scannable, this table carries the why. `os.environ` is read in exactly one
place, `shared/config.py` (`env_str` / `env_int` / `env_float` / `env_required`); every other
module imports typed values from its own `app/config.py` or from `shared.config`. A missing
required variable fails at boot with its name, not with an anonymous type error.

Provider budget knobs (poll cadences, daily ledgers, tolerances) arrive with their phases and
join this table then; a hosted profile column (D18) arrives with Phase 8.

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
| `TWELVE_DATA_API_KEY` | twelvedata.com | Batch quotes; the binding free-tier constraint is 800 credits/day; a real key also decides XAUUSD's fate. |
| `ALPHA_VANTAGE_API_KEY` | alphavantage.co | 25 req/day: EOD-grade equities plus the only free FX quote with true bid/ask. |
| `FRED_API_KEY` | fred.stlouisfed.org | Free instant key, 120 req/min; USD Treasury series and the OECD Poland anchors. |

NBP and ECB require no key — the four above are the complete registration list.


## Risk & benchmark

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `BENCHMARK_SYMBOL` | `MARKET_INDEX` (code) / `SPY` (env) | pricing-service | Symbol whose ticks drive alpha/beta sampling; SPY is the free real-time S&P 500 proxy — sampling stays inert until the Finnhub feed lands. |
| `BOOK_RISK_WINDOW` | `100` | pricing-service | Rolling regression window: stable cov/var, still tracks regime shifts. |
| `BOOK_RISK_MINIMUM_OBSERVATIONS` | `20` | pricing-service | Below this the card reads INSUFFICIENT_DATA instead of noise-fit alpha/beta. |
| `BOOK_CAPITAL_BASE` | `1000000` | pricing-service | Assumed capital turning a book's PnL stream into returns; alpha/beta scale as 1/base. |
| `PORTFOLIO_CAPITAL_BASE` | unset → base × books | pricing-service | Set only to model shared desk capital. |
