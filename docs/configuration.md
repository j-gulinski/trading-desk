# Configuration

One rule: a tunable
exists only as an environment variable listed in `.env.example`, and its one-line rationale lives here —
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
| `MARKET_DATA_STREAM_URL` | unset; Compose example uses `http://market-data-service:8001/market-data/stream` | pricing-service | Its one canonical SSE inlet for quotes and curves; pricing derives the sibling `/market-data/snapshot` seed from this URL. |
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
| `FRED_API_KEY` | fred.stlouisfed.org | Free instant key, 120 req/min; USD Treasury series and the OECD Poland anchors. |

NBP, ECB and EIOPA require no key. Alpha Vantage is not a Phase 5 runtime dependency.

## Market data — Finnhub

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `PROVIDER_BUDGET_USAGE_PERCENT` | `90` | market-data-service | Shared safety ceiling applied to each provider's published minute/day limit. A 90% cap leaves headroom without duplicating derived values as magic numbers. |
| `PROVIDER_ACTIVE_WINDOW_HOURS` | `12` | market-data-service | Twelve Data spreads its safe daily credits over the half-day window when this desk is expected to run, instead of diluting them over an unused 24-hour day. |
| `FINNHUB_TIER1_POLL_SECONDS` | `15` | market-data-service | Cadence for open-trade symbols + the benchmark — a handful of symbols at 4 req/min each stays far inside the budget; the freshness threshold is 3× this (45 s). |
| `FINNHUB_TIER2_POLL_SECONDS` | `60` | market-data-service | Rest-of-watchlist cadence: the full 25-symbol cap costs ≤ 25 req/min, leaving tier-1 headroom; threshold 3× = 180 s. |
| `FINNHUB_CLOSED_POLL_SECONDS` | `300` | market-data-service | Outside US market hours the last trade does not move — 5-minute confirmation polls keep the board honest for a fraction of the budget. |
| `FINNHUB_PROVIDER_LIMIT_PER_MINUTE` | `60` | market-data-service | Published provider allowance. The scheduler derives a strict rolling 54 req/60 s budget from this limit and `PROVIDER_BUDGET_USAGE_PERCENT`. |
| `SNAPSHOT_RETENTION_DAYS` | `90` | market-data-service | Quote history stays bounded at roughly 1.5M change-only rows in the worst case for a hosted free-tier database. The daily sweep skips rows referenced by a trade's entry or close snapshot ID, so execution provenance outlives the window. |

Scheduler mechanics that are not tuning surface (active-set refresh 15 s, Finnhub market-status
check 10 min, HTTP timeout 10 s, threshold multiplier 3, cooldowns, symbol-search cache 10 min,
history-endpoint bounds) are plain constants in the service's `app/config.py`. The file groups
provider-owned settings under `FINNHUB_*`, `TWELVE_DATA_*`, `NBP_*`, `ECB_*`, `FRED_*` and
`EIOPA_*`. Reused application engines have explicit `OFFICIAL_FIXING_FEED_*` and `CURVE_FEED_*`
prefixes. Thus the NBP/ECB publication windows are source-specific, while the common in-window
5-min retry, hourly confirmation, universe refresh and 4-hour freshness grace are application
policy shared by both fixing feeds—not provider-published limits. Curves are scheduled rather
than windowed (`CURVE_REFETCH_SECONDS`, `CURVE_RETRY_SECONDS`,
`EIOPA_CURVE_REFETCH_SECONDS`, `FRED_PLN_CURVE_REFETCH_SECONDS`). Source facts change only when
a probe shows the source itself changed. `tzdata` is in
`requirements.txt` solely so `zoneinfo` can evaluate those two source timezones inside the
`python:slim` images, which ship no system tz database.

## Reference data — NBP & ECB

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `NBP_FIXING_SYMBOLS` | `EURPLN,USDPLN,XAUPLN_G` | market-data-service | The default official-fixing universe for NBP: the two pairs currency conversion actually needs plus the official gold fixing (`XAUPLN_G` is PLN per **1 g** — deliberately not `XAUPLN`, which would read as PLN per troy ounce). Currencies present on active or closed trades auto-join as `<CCY>PLN` beyond these because both unrealized and realized reports may need conversion; a currency table A does not carry is simply absent, never invented. |
| `ECB_FIXING_SYMBOLS` | `EURUSD,EURPLN` | market-data-service | The default official-fixing universe for ECB: `EURUSD` anchors the resolver's cross-via-EUR path and `EURPLN` powers the NBP-vs-ECB cross-check chip. Active/closed-trade currencies auto-join as `EUR<CCY>` — ECB quotes ~30 currencies against EUR, so one hop covers nearly everything. |
## Curves — FRED and EIOPA

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `FRED_PROVIDER_LIMIT_PER_MINUTE` | `120` | market-data-service | Published FRED allowance; the shared 90% ceiling derives a 108/min bucket. Builders reserve their worst case before starting: 11 requests for Treasury and 2 for PLN. |
| `EIOPA_REQUEST_BUDGET_PER_MINUTE` | `10` | market-data-service | Local application safety budget—not an EIOPA-published limit. It prevents repeated manual refreshes from hammering a public HTML/download host. Each country build reserves two calls; the downloaded archive is reused across the three builds. |

| `CURVE_REFETCH_SECONDS` | `21600` | market-data-service | How often a curve is re-read when the last read succeeded. Six hours suits every daily source here: they publish once a business day, and a manual refresh covers impatience. Two curves override it — EIOPA at 24 h (a monthly release) and `PLN_REFERENCE_PROJECTION_3M` at 7 days (monthly OECD series). |

Fixed knobs behind these: a 15-minute retry after a failed curve read, and a 60-second
client timeout for EIOPA alone, because the shared 10-second budget is right for a quote
and far too short for a three-megabyte archive.

## Market data — Twelve Data

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `TWELVE_DATA_POLL_SECONDS` | `900` | market-data-service | One batch poll per symbol per 15 min: the binding constraint is the 800-credit **daily** cap, and a full 25-symbol watchlist at this cadence costs 2 400 credits/day — the daily governor, not this knob, is what actually paces a big watchlist, so the knob only sets the best case. The freshness threshold is 3× this (2 700 s) in both market regimes, because closed-market confirmation polls run at the same cadence. |
| `TWELVE_DATA_PROVIDER_LIMIT_PER_DAY` | `800` | market-data-service | Published daily allowance. The configured 90% safety ceiling derives a 720-credit ledger. Cadence spreads that ledger across `PROVIDER_ACTIVE_WINDOW_HOURS`; the hard ledger still prevents day-cap overrun. |
| `TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE` | `8` | market-data-service | Published minute allowance. The 90% ceiling derives a 7-credit minute bucket and maximum batch size. |

## Provider-bound trading

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `MAX_ACTIVE_SYMBOLS` | `25` | market-data-service | Ceiling on watchlist symbols. Sizing comes from the tightest budget: 25 symbols at the Twelve Data best-case cadence already costs 2 400 credits/day against a 720 safe ledger, so the governor paces beyond this point — the cap is what keeps the *board* readable and the pacing explicable. The add is refused with a message that says what to do about it. |
| `TRADE_PRICE_TOLERANCE_PCT` | `1.0` | trade-action-service | How far the server's execution price may drift from the price the ticket showed before the trade is refused. 1% is wide enough to survive a poll gap on a normal instrument and tight enough that a number the trader read minutes ago cannot fill. The rejection message carries the actual deviation. |
| `TRADE_ACTION_QUEUE_SIZE` | `1000` | trade-action-service | Bounds accepted-but-not-yet-processed intents in memory. A full queue returns 503 instead of allowing unbounded process growth. |
| `TRADE_ACTION_BATCH_SIZE` | `100` | trade-action-service | Maximum actions accepted by one batch request; larger payloads return 413 before enqueueing. |
| `DEFAULT_QUOTE_PROVIDER` | `FINNHUB` | pricing-service, trade-action-service | The fallback for trades written before provider binding existed. Every use logs `trade_provider_defaulted` — the compatibility path exists but can never be silent. New trades always carry an explicit provider. |

## Risk & benchmark

| Variable | Default | Read by | Why |
| --- | --- | --- | --- |
| `BENCHMARK_SYMBOL` | `SPY` | pricing-service, market-data-service | Symbol whose ticks drive alpha/beta sampling; SPY is the free real-time S&P 500 proxy. The scheduler always keeps it in the active set's first tier. |
| `BENCHMARK_PROVIDER` | `FINNHUB` | pricing-service | The return series must come from exactly one (provider, symbol) feed — the guard stops double-sampling the moment a second provider also quotes SPY. |
| `BOOK_RISK_WINDOW` | `100` | pricing-service | Rolling regression window: stable cov/var, still tracks regime shifts. |
| `BOOK_RISK_MINIMUM_OBSERVATIONS` | `20` | pricing-service | Below this the card reads INSUFFICIENT_DATA instead of noise-fit alpha/beta. |
| `BOOK_CAPITAL_BASE` | `1000000` | pricing-service | Assumed capital turning a book's PnL stream into returns; alpha/beta scale as 1/base. |
| `PORTFOLIO_CAPITAL_BASE` | unset → base × books | pricing-service | Set only to model shared desk capital. |
