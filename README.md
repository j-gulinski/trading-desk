# Trading Microservices

A miniature trading / risk stack: market data is generated and streamed, trades
are opened and closed, active positions are continuously revalued and their PnL
published, and a blotter backend serves the data a future UI would show.
Postgres is the single source of truth; SSE carries the live streams; everything
runs via Docker Compose.

> _TODO (your input): one or two sentences in your own words on what you built and why._

---

## Architecture

```
 Market Data --SSE /stream--> Pricing --SSE /valuation-stream--> Blotter
   (8001)                      (8002)                             (8006)
     |                           |                                   |
     |                           | reads active Trades, writes       | reads Trades +
     |                           | Valuations                        | Valuations + AuditLogs
     v                           v                                   v
                              Postgres  <------------------------------
                                 ^
        +------------+-----------+-----------+
      Books      Trade Action          (Trade Generation)
      (8004)        (8008)                 (8007, TODO)
                      ^
                  OPEN/CLOSE intents

 Monitoring (8003) polls every service's /health.
```

| Service | Port | Responsibility |
|---|---|---|
| market-data-service | 8001 | generate + persist market data; publish `/stream` (SSE) |
| pricing-service | 8002 | value active Trades, write Valuations, publish `/valuation-stream` (SSE) |
| monitoring-service | 8003 | poll `/health` of all services |
| books-service | 8004 | CRUD trading books, validate asset class |
| blotter-service | 8006 | read side: live cache + DB history for the UI |
| trade-generation-service | 8007 | **not yet implemented** -- generate OPEN/CLOSE intents |
| trade-action-service | 8008 | queue + worker that writes/closes Trades |

---

## Running

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD etc.
docker compose up --build
```

Compose starts Postgres, runs Alembic migrations once (`db-migrations` one-shot
container, gated on the Postgres healthcheck), then starts the services. Schema
is created by Alembic -- **not** `Base.metadata.create_all`. All timestamps are
`TIMESTAMPTZ`; money is `NUMERIC`.

Migrations only (if needed):

```bash
docker compose run --rm db-migrations
```

### Endpoints

- **market-data**: `GET /health`, `GET /snapshot`, `GET /stream`
- **pricing**: `GET /health`, `GET /valuations`, `GET /valuations/<trade_id>`, `GET /valuation-stream`
- **monitoring**: `GET /health`, `GET /status`
- **books**: `GET /health`, `GET/POST /books`, `GET/PUT/DELETE /books/<book_id>`
- **trade-action**: `GET /health`, `POST /trade-actions`, `POST /trade-actions/batch`, `GET /queue/status`
- **blotter**: `GET /health`, `GET /books/summary`, `GET /trades`, `GET /trades/<id>`, `GET /trades/<id>/valuations`, `GET /trades/<id>/audit-logs`

---

## Database schema (rationale for the key columns)

Tables: `books`, `trades`, `valuations`, `market_data_spot_prices`,
`market_data_curves`, `market_data_snapshots`, `audit_logs`.

- **`trades.metadata` (JSONB, mapped as `trade_metadata`)** -- per-trade pricing
  terms copied from the instrument catalog at creation (e.g. `multiplier` for
  futures, bond coupon/maturity/curve). Trades are self-describing so Pricing
  never reads the catalog at runtime. JSONB because the shape varies per asset
  class.
- **`trades.client_request_id` UNIQUE** -- idempotency key; a re-sent intent
  can't create a second trade.
- **money columns are `NUMERIC`** -- never float. `Decimal` is serialised to JSON
  as a string (the custom encoder), since `json.dumps` can't emit `Decimal`.
- **`valuations`** keeps `fair_value` + `unrealized/realized/total_pnl`; the final
  (close) row is tagged `valuation_payload.final = true`.

> _TODO (your input): expand on any column choices you want to justify._

---

## The end-to-end flow

```
generated/manual intent -> trade-action (queue+worker) -> Trades (ACTIVE)
   -> pricing values it on the next market tick -> Valuations (+ valuation_update on SSE)
   -> blotter caches live PnL; on close, pricing finalizes realized PnL
```

1. An `OPEN_TRADE` intent hits trade-action, is queued, gets **202 Accepted**, and
   a worker validates (book exists, asset class matches, idempotency) and inserts
   an `ACTIVE` trade in one DB transaction.
2. Pricing's refresh loop (~2s) discovers the new ACTIVE trade and values it on
   each market tick, writing `Valuations` and publishing `valuation_update`.
3. A `CLOSE_TRADE` intent flips the trade to `CLOSED` (guarded UPDATE). Pricing
   then finalizes: writes one valuation with `unrealized=0`, `realized` set,
   `total=realized`.

---

## SSE

Both `/stream` (market data) and `/valuation-stream` (valuations) are
Server-Sent Events. Each event is `event: <type>\ndata: <json>\n\n` (blank line
terminates). Servers run on a `ThreadingMixIn` WSGI server so a long-lived
`/stream` connection never blocks `/health`. Consumers (Pricing, Blotter)
reconnect forever -- a refused connection or dropped client never crashes the
producer.

---

## Trade Action concurrency

A `queue.Queue` decouples fast HTTP intake (202) from DB writes. A single worker
serialises writes. **Double-close** is prevented in the DB, not just in Python:
`UPDATE trades SET status='CLOSED' WHERE trade_id=:id AND status='ACTIVE'` and
the close only "wins" if `rowcount == 1`. The in-process queue is **not durable**
-- in-flight intents are lost on restart; idempotency (`client_request_id`) makes
a re-sent intent safe.

---

## Fair value & PnL per asset class

| Asset class | Fair value | Notes |
|---|---|---|
| EQUITY / COMMODITY | `price * qty` | price = mid/last/spot |
| FUTURES | `price * multiplier * qty` | `multiplier` from metadata |
| FX (forward) | `forward * notional` | `forward = spot*(1+r_d*T)/(1+r_f*T)` |
| BOND | `sum CF_t / (1+r(t))^t * qty` | rate interpolated off the `USD_GOV` curve |

PnL sign depends on side -- the classic domain bug:
- BUY: `unrealized = (current - trade) * qty * multiplier`
- SELL: `unrealized = (trade - current) * qty * multiplier`

Pricing owns **all** PnL math (one place for the signs). Realized PnL is
finalized on close (`unrealized=0`, `total=realized`).

---

## Blotter design (read side)

The blotter is the CQRS-lite read model. The important distinction (from the
spec): **live lists/PnL come from the valuation-stream cache; single-trade
history comes from the DB.**

- **Live working set (`cache.IndexedStore`)** -- holds **only ACTIVE trades**,
  indexed on `book_id / asset_class / status / symbol`. `query()` intersects the
  per-field id-sets smallest-first instead of scanning. Bootstrapped from the DB
  (ACTIVE rows) at startup, kept current off the stream, and **evicted on close**
  -- so memory is bounded by open positions, not by total trade history.
- **Live PnL cache** -- latest `valuation_update` per ACTIVE trade, dropped on
  close.
- **Closed / historical** trades and their valuations are served from the **DB**
  (paginated via `limit`/`offset`).
- **Realized PnL** in `/books/summary` is aggregated **from the DB** (the final
  valuation rows tagged `valuation_payload.final=true`), so it's correct for
  closed trades and survives restarts; **unrealized** PnL is summed live from the
  cache.

Stream projection (`service.handle_valuation`): a `final` valuation evicts the
trade + drops its live PnL; an active valuation refreshes live PnL and
lazy-loads the trade into the store the first time it's seen (only if the DB
confirms it's still ACTIVE -- this also drops stale post-close ticks).

---

## Known limitations / not yet implemented

- **trade-generation-service (8007)** is not implemented -- trades are created by
  POSTing intents to trade-action directly (see `scenarios/`).
- **Audit logs** (`audit_logs` table) and **structlog** are not yet wired across
  services; the blotter's `/trades/<id>/audit-logs` reads the table but it stays
  empty until producers write to it.
- `queue.Queue` in trade-action is in-process and non-durable.
- Blotter live caches are empty for a moment after restart until the first
  valuations stream in (optional "replay from Valuations" extension would close
  this gap).

---

## Test scenarios

`.http` files under `scenarios/` (REST Client format), e.g.:

- `health.http` -- every service answers `/health`
- `open-and-price-all-assets.http` -- one trade per asset class, each priced
- `close-and-realized-pnl.http` -- close -> realized PnL finalized
- `idempotency.http` -- idempotent open + double-close guard
- `blotter.http` -- the full read side: `/books/summary`, `/trades` + filters,
  `/trades/<id>`, valuation history, audit logs; open -> price -> close

---

## Problems encountered

> _TODO (your input): the spec requires a short write-up of the typical problems
> you hit (Postgres readiness, Alembic import paths, SQLAlchemy session
> lifecycle, double-close, Decimal->JSON, PnL sign, blotter stream-vs-DB, ...).
> Fill this in from your own experience._
