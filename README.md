# Trading Microservices

A miniature trading / risk stack: market data is generated and streamed, trades
are opened and closed, active positions are continuously revalued and their PnL
published, and a blotter backend serves the data a future UI would show.
Postgres is the single source of truth; SSE carries the live streams; everything
runs via Docker Compose.

---

## Architecture


| Service | Port | Responsibility |
|---|---|---|
| market-data-service | 8001 | generate + persist market data; publish `/stream` (SSE) |
| pricing-service | 8002 | value active Trades, write Valuations, publish `/valuation-stream` (SSE) |
| monitoring-service | 8003 | poll `/health` of all services |
| books-service | 8004 | CRUD trading books, validate asset class |
| blotter-service | 8006 | read side: live cache + DB history for the UI |
| trade-generation-service | 8007 | generate OPEN/CLOSE intents and post them to trade-action |
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
- **trade-action**: `GET /health`, `POST /trade-actions`, `POST /trade-actions/batch`, `POST /trade-actions/close-all`, `GET /queue/status`
- **trade-generation**: `GET /health`, `POST /generate-once`, `POST /start`, `POST /stop`, `GET /status`
- **blotter**: `GET /health`, `GET /books/summary`, `GET /trades`, `GET /trades/<id>`, `GET /trades/<id>/valuations`, `GET /trades/<id>/audit-logs`

---

## Database schema

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

### Indexes

Created by the `d19af2df2449_indexes` migration to support the blotter's typical
queries:

| Index | Column(s) | Serves |
|---|---|---|
| `ix_trades_book_id` | `trades.book_id` | `/trades?book_id=`, `/books/summary` |
| `ix_trades_asset_class` | `trades.asset_class` | `/trades?asset_class=` |
| `ix_trades_status` | `trades.status` | `/trades?status=` (DB path for CLOSED) |
| `ix_trades_symbol` | `trades.symbol` | `/trades?symbol=` |
| `ix_valuations_trade_id_time` | `valuations.(trade_id, valuation_time)` | `/trades/<id>/valuations` history (lookup by trade, ordered by time) |
| `ix_audit_logs_entity_id` | `audit_logs.entity_id` | `/trades/<id>/audit-logs` |

The composite `(trade_id, valuation_time)` index matches both the filter and the
`ORDER BY valuation_time` of the valuation-history query, so it's served straight
from the index. Filters on `/trades` compose (`book_id` + `asset_class` +
`status`), each backed by its own single-column index.

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

## Trade generation

A simulated order source. It seeds one default book per asset class via Books
Service on startup, then a single background loop generates intents
and posts them to trade-action (the only writer of `Trades`):

- Each cycle picks a random book, prices its instrument off the market-data
  `/snapshot` (bonds are PV'd off the `USD_GOV` curve), picks a random side, and
  sizes `quantity` to a **target notional** (`TARGET_NOTIONAL`) so every asset
  class carries comparable exposure -- otherwise the futures multiplier would
  dwarf everyone else's PnL.
- ~`CLOSE_PROBABILITY` of cycles close a tracked open trade instead.
- The loop is **off by default**; `POST /start` / `POST /stop` toggle it (a
  `threading.Event`), `POST /generate-once` fires a single cycle. Open trade ids
  are tracked in memory (lost on restart -- a POC limitation).

---

## Audit logs vs technical logging

Two distinct mechanisms, as the spec requires:

- **Technical logs** -- `structlog` (JSON) to stdout, configured once per service
  in `shared/logging_config.py`. For observing the app in the container console.
- **Audit logs** -- business/operational events written to the `audit_logs`
  table via `shared/audit.py` `write_audit(...)`. For later reconstruction of
  what happened. When a business write and its audit belong together they share
  **one DB transaction** (the `session=` argument), so the trade and its
  `TRADE_CREATED` row commit atomically.

Every service writes audit events:

| Service | Events |
|---|---|
| books | `BOOK_CREATED` / `BOOK_UPDATED` / `BOOK_DELETED` |
| trade-action | `TRADE_CREATED`, `TRADE_CLOSED`, `ACTION_REJECTED`, `WORKER_STARTED` |
| trade-generation | `WORKER_STARTED` / `WORKER_STOPPED` |
| market-data | `SNAPSHOT_WRITTEN`, `DB_WRITE_ERROR` |
| pricing | `STREAM_CONNECTED` / `STREAM_DISCONNECTED` |
| blotter | `STREAM_CONNECTED` / `STREAM_DISCONNECTED` |
| monitoring | `WORKER_STARTED` |

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
  (paginated via `limit`/`offset`). `GET /trades` resolves by status:
  `?status=ACTIVE` (or omitted for the active rows) uses the cache,
  `?status=CLOSED` uses the DB, and **no status returns both** -- active from the
  cache plus non-active from the DB.
- **Realized PnL** in `/books/summary` is aggregated **from the DB** (the final
  valuation rows tagged `valuation_payload.final=true`), so it's correct for
  closed trades and survives restarts; **unrealized** PnL is summed live from the
  cache.

Stream projection (`service.handle_valuation`): a `final` valuation evicts the
trade + drops its live PnL; an active valuation refreshes live PnL and
lazy-loads the trade into the store the first time it's seen (only if the DB
confirms it's still ACTIVE -- this also drops stale post-close ticks).

---

## Known limitations

- `queue.Queue` in trade-action is in-process and non-durable -- in-flight
  intents are lost on restart (idempotency makes a re-send safe).
- trade-generation tracks open trade ids **in memory**, so after a restart it can
  only close trades it opened in the new run.
- Blotter live caches are empty for a moment after restart until the first
  valuations stream in; `bootstrap_trades()` warms the active set from the DB to
  shrink that window.
- Per-asset PnL is brought *closer* (notional-sized quantities + uniform relative
  market-data volatility), not made equal -- lot indivisibility (1 futures
  contract) and large FX unit counts keep some spread.

---

## Test scenarios

`.http` files under `scenarios/` (REST Client format), e.g.:

- `health.http` -- every service answers `/health`
- `open-and-price-all-assets.http` -- one trade per asset class, each priced
- `close-and-realized-pnl.http` -- close -> realized PnL finalized
- `idempotency.http` -- idempotent open + double-close guard
- `blotter.http` -- the full read side: `/books/summary`, `/trades` + filters,
  `/trades/<id>`, valuation history, audit logs; open -> price -> close
- `full-flow.http` -- the whole stack driven by trade-generation: start the
  loop, read the blotter, then flatten everything with `/trade-actions/close-all`

---