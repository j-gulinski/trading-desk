# Trading Desk

A portfolio project for exploring market data, instrument pricing and simulated trading.
Python 3.14, Bottle, SQLAlchemy, PostgreSQL and React/Vite. Trades are recorded locally;
the app does not send orders to a broker.

## Features

- Provider watchlist for equities, FX and commodities, with quote history and freshness states.
- Spot trades, fixed-coupon bonds, interest-rate swaps and European options.
- Model previews, trade opening/closing, valuation history and P&L grouped into books.
- Live updates through server-sent events, reporting-currency conversion and basic risk views.
- Provider status, request budgets and operational logs.

Quote sources: Finnhub, Twelve Data and Alpha Vantage. NBP and ECB supply reference FX;
FRED, ECB and EIOPA supply rate curves. Availability depends on credentials and provider access.

## Run

Install Docker with Compose, then:

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD and use it in DATABASE_URL and DATABASE_MIGRATION_URL.
# Add provider API keys for the sources you want to use.
docker compose up --build
```

Open [localhost:3000](http://localhost:3000). Add instruments from Market Data, create a
book for the intended asset class, then open a trade. Quote-priced instruments need a usable
provider quote; model contracts also need an eligible curve. Missing API keys disable their feeds.

`.env.example` lists the main settings; optional defaults live in each service's `config.py`.
The main storage defaults are 90 days of quote observations
and at most one ordinary persisted valuation per trade per 60 seconds. Live updates are more frequent.

The instrument schema change requires a fresh development database. To discard the old local
Compose data and rebuild:

```sh
docker compose down -v
docker compose up --build
```

This removes the local database and cached frontend dependencies. There is no legacy-data backfill.

## Structure

| Location | Responsibility |
| --- | --- |
| `libs/desk-domain` | Instrument catalogue, contract terms, trade rules, storage models, provider vocabulary and domain queries |
| `libs/desk-pricing` | Pure numerical functions for curves, bonds, swaps, options and risk |
| `libs/desk-runtime` | Configuration, database sessions, logging and HTTP runtime |
| `services/market-data-service` · 8001 | Provider adapters, watchlist, quote/curve storage and streams |
| `services/pricing-service` · 8002 | Pricing, valuation persistence, scenarios and valuation stream |
| `services/monitoring-service` · 8003 | Health, audit and logs |
| `services/books-service` · 8004 | Book management |
| `services/blotter-service` · 8006 | Trade, valuation and portfolio reads |
| `services/trade-action-service` · 8008 | Trade validation, command queue and trade writes |
| `frontend/src` | React views, components, state and API clients |
| `db` | Alembic schema migrations |

Providers inherit HTTP handling from `ProviderClient`; `@runtime.guard` handles their errors
and cooldowns. Quote feeds normalize responses, then share storage and publication in
`quote_ingestion.py`. `desk-domain/instruments.py` is the instrument catalogue: one
`FinancialInstrument` subclass per asset class declares the contract (ticket fields, symbol
prefix, curve roles, underlying, trade rules). Instances hold typed attributes
(`option.strike`, `bond.face_value`); JSON dicts exist only at the HTTP/DB edge
(`from_dict`, `contract()`, `pricing()`, `as_terms()`). Spots, bonds and swaps call their
formula from `_value()`. A European option stores the engine name on `option.model`
(`BLACK_SCHOLES` or `INTRINSIC`); `_value()` looks up that function in `desk-pricing`.
`desk-domain/pricing.py` maps those two names for the ticket picker. Term validation, the
served ticket schema, contract storage, the active quote set, trade validation and the blotter
read the catalogue declarations instead of branching on asset class. Each class also declares
`label` and `ticket_kind` (`spot`, `bond`, `swap`, or `premium`); the ticket and blotter read
those instead of copying asset-class maps. Adding an instrument is one class plus a function
in `desk-pricing`, and approving its curves in `curves.py`. A new option engine is another
function plus one row in `OPTION_MODELS`. A new premium-style contract reuses the premium
ticket. Provider response parsing stays in provider adapters.
`valuation.py` shares position-value and P&L arithmetic. Trade actions share validation and
one close operation. `desk-runtime` owns configuration, transactions and streams. The trade
ticket reads one options payload for schema, tradeable instruments and curves, then shows the
execution value, the total and its key assumptions above a compact price-source list.

Course architecture notes for this phase (schema, inheritance, composition) are in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Database

[Editable schema](assets/database.svg) · [ORM models](libs/desk-domain/src/desk_domain/models.py)

![Database schema](assets/database.svg)

- `instruments` is the shared identity (unique symbol, currency, JSON contract terms). Trades
  and the watchlist used to copy `symbol` / `asset_class`; they now point at this row instead.
  An option’s underlying is `underlying_instrument_id`, not a second copy of the ticker.
- `watchlist_items` is membership only: which providers serve an instrument. Unwatch removes
  that row (or one provider). It does not delete the instrument. A source still required by
  an active trade — including an option on that underlying — cannot be removed. Open and
  removal lock the same instrument row.
- `trades.instrument_id` is `ON DELETE RESTRICT`. Closed trades still reference the row, so
  history keeps a symbol. Closing is not a delete. There is no public instrument-delete API.
- Contract fields live in `instruments.terms`; pricing settings (`model`, curve, volatility)
  live in trade metadata. Python rebuilds a typed instrument (`from_dict`) rather than
  mutating a terms bag. The blotter still receives one merged JSON object.
- `valuations` stores calculated values, P&L and calculation context. Book and instrument
  identity come from the trade. Quote snapshots record observed price changes per provider
  and symbol.

## Scope and simplifications

Execution is simulated from stored quotes or model prices. Contracts use fixed `maturity_years`;
calendar aging, automatic expiry and contract versioning are outside the current scope.
IRS pricing uses one curve for discounting and projection. European options default to
Black–Scholes; the same contract can be valued with intrinsic payoff instead. Quote history
contains observations collected by this app, without vendor backfill.
Valuation history follows a trade's current book after reassignment. Exact historical replay,
authentication, broker connectivity and durable command delivery are not implemented.

## Development and checks

Dependencies are pinned in `requirements.txt`. To work on the Python packages locally:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
for package in libs/* services/*; do
  .venv/bin/pip install --no-deps -e "$package"
done
```

Load configuration with a local database URL before running a service entry point.
Service addresses default to Compose hostnames. For local processes, set the corresponding
`MARKET_DATA_SERVICE_URL=http://localhost:8001`, `PRICING_SERVICE_URL=http://localhost:8002`,
and other `<NAME>_SERVICE_URL` values. Health and stream URLs are derived from those addresses;
the old separate `*_HEALTHCHECK_URL` and `*_STREAM_URL` settings are replaced.
The Vite proxy in `frontend/vite.config.js` uses Compose service names by default.

```sh
.venv/bin/python -m compileall -q libs services db
cd frontend
npm ci
npm run build
npm run lint
npm run deadcode
```

Verify changed behavior through the running app: import → preview → open → value → close;
check rejected removal while active, unwatch/re-add after close, retained history and restart.
Exercise concurrency with separate database connections. Recompute financial results independently.
Check empty, missing/stale-data and closed states, plus normal and narrow browser widths.
