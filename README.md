# Trading Microservices System

## 1. System Description
A simplified trading/risk stack built in Python. Market data is generated, streamed and persisted; trading books are managed; trades are opened and closed through an internal action queue; active positions are continuously valued (fair value + realized/unrealized PnL) off the live market stream and written to the database; a monitoring service watches everything. PostgreSQL is the single durable store and its schema is created by Alembic migrations.

## 2. Architecture Description
*   **Market Data Service (8001)**: generates randomized ticks for every catalog instrument, streams them via SSE (`market_tick` + a multi-tenor `USD_GOV` `curve_tick`), and persists spots/curves/snapshots to the database.
*   **Pricing Service (8002)**: subscribes to the market stream, keeps an in-memory market-state cache, discovers active trades from `Trades`, computes fair value + PnL per asset class, writes `Valuations`, and re-broadcasts `valuation_update` on its own SSE stream.
*   **Books Service (8004)**: CRUD for trading books (a book = a logical portfolio/desk with an expected asset class).
*   **Trade Action Service (8008)**: accepts trade intents, queues them, and a background worker writes/closes `Trades` in DB transactions (the concurrency centerpiece).
*   **Monitoring Service (8003)**: polls every service's `/health` plus an optional DB `SELECT 1` check.
*   **PostgreSQL + db-migrations**: the durable store; `db-migrations` runs `alembic upgrade head` before the services start.
*   *Planned (not yet built): Trade Generation (8007), Blotter (8006).*

## 3. How to Run
Prerequisites: Docker and Docker Compose.

```bash
docker compose up --build
```

Migrations run automatically: `db-migrations` waits for Postgres to be healthy, runs `alembic upgrade head`, and the services depend on it completing. Every service gets its config from `.env` (`env_file: .env`).

## 4. Database & Migrations
Tables: `books`, `trades`, `valuations`, `market_data_spot_prices`, `market_data_curves`, `market_data_snapshots`, `audit_logs`. Money columns are `NUMERIC` and timestamps are `TIMESTAMPTZ`. The schema is built by Alembic (not `create_all`).
*   `trades.client_request_id` is `UNIQUE` — the idempotency key (a re-sent open cannot create a second trade).
*   `books.name` is `UNIQUE`.
*   `trades.metadata` (JSONB) holds the per-instrument pricing terms (e.g. `multiplier`, `tenor_years`, bond coupon/maturity/curve) copied from the instrument catalog at creation, so each trade is self-describing.
*   `trades.valuation_finalized` (bool) coordinates realized-PnL-on-close: Trade Action sets it `false` on close, Pricing computes realized PnL once and flips it `true`.

## 5. Endpoints Description
### Market Data Service (8001)
*   `GET /stream`: SSE of `market_tick` / `curve_tick` events.
*   `GET /snapshot`: current spots + the `USD_GOV` curve.
*   `GET /health`: status + generated-event count.

### Pricing Service (8002)
*   `GET /valuation-stream`: SSE of `valuation_update` events (fair_value + unrealized/realized/total PnL).
*   `GET /valuations`: latest computed valuation for every tracked trade (from the cache).
*   `GET /valuations/<trade_id>`: latest valuation for one trade.
*   `GET /health`: status + market-data connection state + active-trade count.

### Books Service (8004)
*   `GET /books`, `GET /books/<id>`, `POST /books`, `PUT /books/<id>`, `DELETE /books/<id>` (soft delete), `GET /health`.

### Trade Action Service (8008)
*   `POST /trade-actions`: enqueue an `OPEN_TRADE` / `CLOSE_TRADE` intent, returns **202 Accepted** (OPEN also returns the new `trade_id`).
*   `POST /trade-actions/batch`, `GET /queue/status` (counters), `GET /health`.

### Monitoring Service (8003)
*   `GET /status`: latest health/response-time per service + DB connectivity.
*   `GET /health`: self check.

## 6. Trade Lifecycle (the flow)
`OPEN_TRADE intent -> Trade Action (202 -> queue -> worker validates the book exists + its asset class matches, then inserts Trades ACTIVE) -> Pricing discovers the active trade and values it off the live market -> Valuations + valuation_update`. On `CLOSE_TRADE`, Trade Action runs a guarded close, then Pricing finalizes realized PnL (unrealized -> 0). Execution prices are taken from the live market (BUY fills at the ask, SELL/close at the bid).

## 7. Streaming Mechanism
Server-Sent Events, same shape as before: route handlers return a generator that `yield`s `event: <type>\ndata: {json}\n\n` (blank-line terminated). Each connected client gets its own `queue.Queue`; background threads push events into them. Market Data emits `market_tick`/`curve_tick`; Pricing emits `valuation_update`. The WSGI server uses `ThreadingMixIn` so a long-lived `/stream` never blocks `/health`.

## 8. Concurrency Mechanism
*   **Web server**: built-in WSGI server wrapped with `ThreadingMixIn`; each request (and SSE connection) runs in its own thread.
*   **Background tasks**: daemon threads for the generators, the market-data consumer, the trade-refresh/finalize loop, and the monitoring pollers.
*   **Thread safety**: `threading.Lock` guards shared in-memory state (market snapshot, valuation cache, client-queue sets, counters).
*   **Trade Action — the centerpiece**: a `queue.Queue` decouples fast HTTP intake (202) from DB writes done by a single background worker.
    *   **Double-close protection**: the close is a guarded `UPDATE ... WHERE trade_id=:id AND status='ACTIVE'` with a `rowcount` check — of two racing closes only one matches a row; the other is a no-op (rejected).
    *   **Idempotency**: `client_request_id` is `UNIQUE`; a duplicate open raises `IntegrityError` and is skipped, so no second trade is created.
    *   **Limitation**: `queue.Queue` is in-process, not durable — in-flight intents are lost on restart. Idempotency makes a re-sent intent safe.

## 9. Fair Value & PnL per Asset Class
*   **EQUITY**: `mid * qty`  ·  **COMMODITY**: `spot * qty`
*   **FUTURES**: `price * multiplier * qty`
*   **FX**: `forward(spot, r_d, r_f, T) * notional`, `forward = spot * (1 + r_d*T) / (1 + r_f*T)`
*   **BOND**: PV of future coupons + face discounted off the interpolated `USD_GOV` curve, `* qty`
*   **PnL**: BUY `unrealized = (current - trade_price) * qty * mult`; SELL flips the sign. Closed trades: `realized` is fixed at the close price and `unrealized = 0, total = realized`.

## 10. How to Test the System
Bring the stack up with `docker compose up --build`, then drive the `scenarios/*.http` files with the VS Code REST Client (or `curl`):
*   `health.http`, `market-data.http`, `open-and-price-all-assets.http`, `close-and-realized-pnl.http`, `idempotency.http`.
*   SSE streams can't be rendered by the REST Client — test them with `curl -N http://localhost:8001/stream` and `curl -N http://localhost:8002/valuation-stream`.
*   `curl http://localhost:8003/status` shows the health of every service + the database.

## 11. Known Limitations / Not Yet Done
*   **AuditLogs** are not yet written (the table + model exist) — a spec requirement still outstanding.
*   Trade Action enforces business validation in the worker (book exists + asset-class match); deeper intake-shape validation is still minimal (POC).
*   Structured logging still uses stdlib `logging` rather than `structlog`.
*   Trade Generation and Blotter services are not implemented yet (Monitoring shows them DOWN until they exist).

## 12. Implementation Problems Encountered
- overcoming initial lack of knowledge of python threading - (GIL, threads, multiprocessing)
- no parallel threads in single process - deamon processes for continous tasks
- `postgres:18` rejects a volume mounted at the data root - mount the parent `/var/lib/postgresql` on a clean volume
- alembic could not see the models/`DATABASE_URL` inside the migrate container - fixed env.py import path + `COPY shared/ shared/`
- `Decimal` is not JSON-serializable - custom encoder (serialize as string to keep precision); money stays `NUMERIC`
- same PnL formula for BUY and SELL is the #1 domain bug - the short side has the opposite sign

## 13. Fixed Concurrency Potential Problems
- scalling consumers with one single lock
	- everything locked until all events added to queue
	- data lock time linearly connected with number of consumers, locked other endpoints eg: snapshot
	- solution: 2 locks - data lock only aquired for quick generation of data and updating snapshot - mitigating race conditions
- shallow copy locking
	- when returning market data object the lock was aquired for shallow copy with .copy()
	- might return inconsistant data for instruments mid-update
	- lock and map whole object (not only copy) to JSON so we keep consistent state
- healthcheck false fail
	- when market data generator had a lot of clients, healtheckeck request could be starved resulting in false failed healtcheck
	- mitigated by reducing time of data lock to calculations and data assignment only
- new client could connect and miss first tick
	- fixed by locking creation and adding queue to consumer queues together
- O(n) client disconnecting
    - switched client list to set do make disconnecting clients more efficient
- slow consumer - overflow potential
    - add max size for event queues, dropping events when client is slow
- lock could block new clients from connecting
    - client lock only for making snapshot snapshot, released for sending events
- double-close race (Trade Action)
    - two intents closing the same position could both succeed
    - guarded `UPDATE ... WHERE status='ACTIVE'` + `rowcount` check so only one wins
