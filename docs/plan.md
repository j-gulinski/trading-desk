# Refactoring Plan: market-data-streaming → trading-microservices

## Current state

Already done:
- Folder structure split from `app.py` into modules (main, api, generator, publisher, persistence, health, config)
- PostgreSQL + Docker Compose + Alembic migrations
- All DB tables + SQLAlchemy models
- market-data-service: 3 independent generator threads (equity, bond, FX)
- market-data-service: DB save for spot prices via `persistence.save_tick`
- market-data-service: publisher/persistence separation, `emit_tick` in publisher
- docker-compose: postgres → db-migrate → db-seed → services chain

Not done yet:
- `structlog` (all services)
- AuditLogs writes (all services)
- MarketDataSnapshot periodic saves (market-data-service)
- `shared` module restructuring
- Pricing Service DB refactor (price trades, save Valuations, PnL stream)
- Books Service (new)
- Trade Action Service (new)
- Trade Generation Service (new)
- Blotter Service (new)
- Monitoring Service extension

---

## Design decisions: where to save market data ticks

### Problem

The DB has three market data tables: `MarketDataSpotPrices`, `MarketDataCurves`, `MarketDataSnapshots`.
The generator produces three tick types: EQUITY, BOND (yield), FX FORWARD.
The requirement says spot prices go to `MarketDataSpotPrices`, curves go to `MarketDataCurves`,
and periodic full snapshots go to `MarketDataSnapshots`.

---

### Option A — Each tick type to its semantically correct table

| Tick type  | Table                  | Reasoning |
|------------|------------------------|-----------|
| EQUITY     | `MarketDataSpotPrices` | bid/ask/mid/last are spot prices by definition |
| BOND yield | `MarketDataCurves`     | a yield is rate/curve data, not a spot price |
| FX FORWARD | `MarketDataSpotPrices` | spot rate is a spot price; rates go in raw_payload |
| Full state | `MarketDataSnapshots`  | periodic, all instruments at once |

**Problem with BOND → MarketDataCurves:**
`MarketDataCurves` has `tenors JSONB` and `rates JSONB` as arrays — designed for full yield curves
with multiple maturities (1M, 3M, 1Y, 5Y...). We only generate one bond with one tenor (5Y).
Saving `["5Y"] / [0.047]` to a curves table misrepresents what a curve is.
It works technically but is semantically misleading.

**Verdict:** Correct per requirements but awkward for a single-tenor simulation.
Best if you later add more bond instruments across maturities.

---

### Option B — All individual ticks to MarketDataSpotPrices, curves table reserved for actual curves

| Tick type  | Table                  | Reasoning |
|------------|------------------------|-----------|
| EQUITY     | `MarketDataSpotPrices` | correct |
| BOND yield | `MarketDataSpotPrices` | yield stored in `spot` column; `asset_class='BOND'` makes intent clear |
| FX FORWARD | `MarketDataSpotPrices` | spot stored in `spot` column |
| Full state | `MarketDataSnapshots`  | periodic |

**Problem:** A bond yield in a column called `spot` is not semantically pure.
However `bid`, `ask`, `mid`, `last` are all NULL for bonds, and `raw_payload` contains
the full context including `asset_class`. Any query that filters `WHERE asset_class='BOND'`
gets only bond data.

**Verdict:** Pragmatic for the current simulation. Simpler code — one save path for all ticks.
Correct if you treat `spot` as "the primary scalar market value" rather than literally a spot price.

---

### Option C — BOND generates a periodic curve snapshot instead of per-tick saves

Instead of saving each bond yield tick to any table, accumulate yield ticks in memory
and periodically write a proper yield curve record to `MarketDataCurves` alongside the
full snapshot. The snapshot thread already captures full state — it could also write
a curve record when it runs.

| Tick type   | Table                  | When |
|-------------|------------------------|------|
| EQUITY      | `MarketDataSpotPrices` | per tick |
| FX FORWARD  | `MarketDataSpotPrices` | per tick |
| BOND yield  | `MarketDataCurves`     | periodic (same interval as snapshot) |
| Full state  | `MarketDataSnapshots`  | periodic |

**Verdict:** Most semantically correct. `MarketDataCurves` gets a real curve record
(even if one-tenor), and individual bond ticks are not persisted per-tick which is
arguably fine since pricing only needs the latest state (available from the stream or snapshot).

---

### Recommended approach

**Option B for now, with a note to migrate to Option C if more bond instruments are added.**

Rationale:
- Option A forces a single-tenor "curve" which is misleading
- Option B keeps all per-tick saves in one code path (simpler `save_tick`)
- Option C is architecturally correct but adds a second save path and a periodic thread
- The `asset_class` column disambiguates bond records from equity/FX records in queries
- `raw_payload` preserves full fidelity regardless of which columns are NULL

---

### FX domestic_rate / foreign_rate

These are currently stored only in `raw_payload` JSONB.
JSONB stores numbers as IEEE 754 floats — potential precision loss.

**Options:**
1. Keep in `raw_payload` — acceptable if pricing always reads rates from the SSE stream
   (in-memory, Python float) rather than querying historical DB records for live pricing.
   The precision loss only matters if you replay historical rates from the DB.
2. Add `domestic_rate NUMERIC` and `foreign_rate NUMERIC` columns to `MarketDataSpotPrices` —
   correct but makes a "spot prices" table carry FX-specific fields.
3. Store rates as strings in JSON (`"0.0375"` instead of `0.0375`) and parse on read —
   preserves precision in JSONB without schema changes, but awkward.

**Recommended:** Keep in `raw_payload` for now. Document in README that rates in JSONB
carry float precision and should not be used for historical pricing replay without
a schema migration to add NUMERIC columns.

---

## Phase 1 — Finish market-data-service

### Step 1.1 — structlog

Learn: `structlog` wraps Python's standard `logging` and adds structured key-value context
to every log line. Configure once in a `logging_config.py`, call `structlog.get_logger()`
per module. Every log call should include context: `service`, `symbol`, `event_id`.
Logs become machine-readable JSON events instead of free-form strings.
Distinction: structlog → stdout/container logs (technical observability),
AuditLogs table → DB (business event history). Both should be used together.

### Step 1.2 — Periodic MarketDataSnapshot saves

Learn: A snapshot is a point-in-time capture of the full market state — all three instruments
at once, saved every N seconds regardless of individual tick generation.
Needs a background thread (or timer) that reads `snapshot` under `data_lock` and writes
to `MarketDataSnapshots` with `snapshot_type="FULL"` and full state as `payload` JSONB.
Understand event-driven saves (per tick) vs time-driven saves (per interval).

### Step 1.3 — AuditLogs writes

Learn: Market-data-service should write to `AuditLogs` on:
service start, each stream client connect/disconnect, DB write errors, each snapshot save.
Create a `write_audit_log` function in shared `audit.py` that accepts `service_name`,
`event_type`, `severity`, `message`, optional `payload`, and inserts using its own session.
AuditLog writes should not be in the same transaction as the business write —
a failed tick save should still produce an audit log entry for the error.

---

## Phase 2 — Restructure shared module

### Step 2.1 — Convert shared.py to a package

Current: `shared.py` at repo root, copied into each container as a single file.
Target: `shared/trading_shared/` package with focused modules:

```
shared/trading_shared/
    __init__.py
    models.py       — SQLAlchemy models (move from root models.py)
    db.py           — engine + Session factory (remove per-service db.py)
    audit.py        — write_audit_log function
    logging_config.py — structlog setup
    enums.py        — AssetClass, TradeStatus, TradeSide, EventType, Severity
    serialization.py — Decimal-to-JSON encoder
```

Each Dockerfile copies `shared/` instead of `shared.py`.
Each service imports `from trading_shared.db import Session` etc.

### Step 2.2 — Decimal serialization

Learn: SQLAlchemy NUMERIC returns Python `Decimal`, not float.
`json.dumps()` cannot serialize `Decimal` by default — raises `TypeError`.
Write a custom `JSONEncoder` subclass or a `serialize(obj)` helper that converts
`Decimal` to `str` or `float` at the JSON boundary (API response layer only).
Financial values stay `Decimal` through the ORM layer.
All `json.dumps(...)` calls in `api.py` files should use this encoder.

---

## Phase 3 — Books Service (port 8004)

### Step 3.1 — What a Book is

A trading book is a logical portfolio or desk. Every trade belongs to exactly one book.
A book has `expected_asset_class` — trades must match it.
Soft-delete via `is_active=False` (not hard delete) because trades reference books via FK.

### Step 3.2 — Layered structure

```
api.py         — parse request, call service, return response (no business logic)
service.py     — validate input, enforce rules, call repository
repository.py  — SQLAlchemy queries only, no business rules
schemas.py     — request/response shapes using dataclasses
```

Every write operation calls `write_audit_log` in the same session (same transaction).

### Step 3.3 — Endpoints

```
GET    /health
GET    /books                — all active books
GET    /books/<book_id>      — one book or 404
POST   /books                — create, returns 201
PUT    /books/<book_id>      — update name/description, returns 200
DELETE /books/<book_id>      — soft-delete (is_active=False), returns 200
```

Status codes: 201 create, 200 read/update, 404 not found, 400 validation error.

---

## Phase 4 — Trade Action Service (port 8008)

### Step 4.1 — Queue-based architecture

HTTP endpoint receives action → validates format → puts on `queue.Queue` → returns `202 Accepted`.
Background worker pulls from queue → validates business rules → writes to DB → commits.
HTTP thread and worker share only the queue — no shared sessions, no shared state.

### Step 4.2 — Idempotency via client_request_id

`client_request_id` has a UNIQUE constraint in DB.
On insert, catch `IntegrityError` (unique violation) and treat as "already processed".
Return the original result, not an error. This handles network retries safely.

### Step 4.3 — Concurrency-safe position closing

Pattern: inside a DB transaction, use `SELECT ... WHERE trade_id=X AND status='ACTIVE' FOR UPDATE`.
SQLAlchemy: `session.query(Trade).filter_by(trade_id=X, status='ACTIVE').with_for_update().first()`.
`FOR UPDATE` locks the row — second concurrent transaction blocks until first commits.
After first commits (trade now CLOSED), second reads CLOSED and rejects.
Without `FOR UPDATE`: both read ACTIVE, both proceed, double-close happens.

### Step 4.4 — Transaction scope

One session per action: read book → validate → insert/update Trade → insert AuditLog → commit.
If anything fails: rollback everything. AuditLog and Trade write must be atomic.

### Step 4.5 — Endpoints

```
GET  /health
POST /trade-actions          — single action, returns 202
POST /trade-actions/batch    — list of actions, returns 202
GET  /queue/status           — queue size, processed count
```

---

## Phase 5 — Trade Generation Service (port 8007)

### Step 5.1 — Separation of concerns

Generates intentions only — never writes to DB directly.
Calls Trade Action Service HTTP endpoint with OPEN_TRADE or CLOSE_TRADE actions.
If Trade Action Service is down: log the error, continue the loop. Do not crash.

### Step 5.2 — Start/stop control

Use `threading.Event` as stop signal: loop checks `stop_event.is_set()` each iteration.
`POST /start` — clears event, starts thread.
`POST /stop` — sets event.
`GET /status` — returns running state, generated count.
`POST /generate-once` — one synchronous generation regardless of loop state.

### Step 5.3 — Generating actions

OPEN_TRADE: pick random active book from Books Service or DB, pick random asset class
matching `expected_asset_class`, generate plausible price, pick BUY/SELL randomly,
generate UUID-based `client_request_id`.
CLOSE_TRADE: query DB for active trades, pick one randomly, use current market price
as `close_price`, set `close_reason="RANDOM_TRADE_OUT"`.

---

## Phase 6 — Pricing Service refactor

### Step 6.1 — What changes

Homework 2: priced hardcoded instruments from in-memory state.
Homework 3: prices active trades from DB. On each tick, query trades where
`status='ACTIVE'` and `symbol` matches the tick's symbol. Reprice only those trades.

### Step 6.2 — PnL calculation (implement in pnl.py)

```
fair_value    = current market value per unit (equity: mid/last, bond: DCF, FX: forward)
market_value  = fair_value * quantity
unrealized_pnl (BUY)  = (current_price - trade_price) * quantity
unrealized_pnl (SELL) = (trade_price - current_price) * quantity
realized_pnl  = locked in at close, read from trade.close_price
total_pnl     = unrealized_pnl + realized_pnl
closed trade  = unrealized_pnl=0, realized_pnl fixed
```

### Step 6.3 — Saving Valuations

Valuations are append-only — insert a new row on every reprice, never update.
One trade accumulates many valuation records. Latest = max(valuation_time).

### Step 6.4 — Valuation stream with named events

Change SSE format from `data: {json}\n\n` to `event: valuation_update\ndata: {json}\n\n`.
Named events allow SSE clients to filter by event type.
Blotter Service subscribes to this and parses the event name.

### Step 6.5 — Endpoints

```
GET /health
GET /valuations                    — latest valuation per active trade
GET /valuations/<trade_id>         — latest valuation for one trade
GET /valuation-stream              — SSE stream of valuation_update events
```

---

## Phase 7 — Blotter Service (port 8006)

### Step 7.1 — Live cache from valuation stream

Background thread subscribes to `/valuation-stream` from Pricing Service.
Maintains dict `{trade_id: latest_valuation_dict}` updated on every event.
This cache is the source for list endpoints — O(1) lookup, always live.
Alternative (querying DB for latest valuation per trade) would require
`DISTINCT ON (trade_id) ORDER BY valuation_time DESC` — slower and always slightly stale.

### Step 7.2 — Combining cache with DB

```
GET /trades              — read from DB (for filtering), enrich with cache valuations
GET /trades/<id>         — DB trade + cache latest valuation + DB valuation history
GET /trades/<id>/valuations  — DB only (all historical rows ordered by valuation_time)
GET /trades/<id>/audit-logs  — DB only (all audit_logs for this entity_id)
GET /books/summary       — in-memory aggregation of cache across all trades per book
```

Filtering: `?book_id=X&asset_class=EQUITY&status=ACTIVE&symbol=ACME` — all optional,
applied as SQLAlchemy `.filter()` conditions.

### Step 7.3 — books/summary

Aggregate across cache: for each book, sum `unrealized_pnl`, `realized_pnl`, `total_pnl`
across all trades in that book using cached valuations. Count active trades.
Pure in-memory — no DB query for the aggregation itself.

---

## Phase 8 — Monitoring Service extension

Add health check threads for: books-service (8004), trade-generation-service (8007),
trade-action-service (8008), blotter-service (8006).
Existing pattern (one thread per service, poll `/health` every second) scales by adding threads.
Optional: DB connectivity check — open a session, run `SELECT 1`, catch exception.

---

## Phase 9 — docker-compose

Four new services in docker-compose, all depending on `db-seed: service_completed_successfully`.

Dependency order:
```
postgres (healthy)
  → db-migrate (completed)
    → db-seed (completed)
      → books-service (started)
        → trade-action-service (started)
          → trade-generation-service (started)
      → market-data-service (started)
        → pricing-service (started)
          → blotter-service (started)
      → monitoring-service (started)
```

`service_started` is sufficient for inter-service dependencies (except postgres)
because services handle connection errors gracefully with retry.

---

---

## Implementation decisions with tradeoffs

### 1. SQLAlchemy session management

**Problem:** Multiple background threads (generators, workers) all need DB access.
Sessions are not thread-safe and must not be shared.

**Option A — New session per operation (current approach)**
Open `with Session() as session` for each save. Connection returned to pool after commit.
Tradeoff: small overhead per tick (acquiring/releasing connection), but pool handles this efficiently.
Good for: infrequent writes, simple operations.

**Option B — Session per thread, reused across operations**
Create one session at thread start, reuse it in the loop.
Must handle `session.rollback()` on error and reconnect on connection loss.
Tradeoff: more complex error handling, but fewer pool round-trips.
Good for: high-frequency writes where connection acquisition overhead matters.

**Option C — Thread-local sessions**
Use `scoped_session(Session)` which gives each thread its own session automatically.
Tradeoff: less explicit, can hide lifecycle bugs, but convenient.

**Recommended for this project:** Option A. Tick rate (100ms interval) does not make
connection overhead a problem. Simplicity and correctness matter more here.

---

### 2. Handling DB write failures in generators

**Problem:** Generator thread produces ticks continuously. If `save_tick` fails (DB down,
constraint violation), should the generator stop or continue?

**Option A — Catch and log, continue generating**
Tick is lost from DB but still published to SSE stream. In-memory state stays correct.
Risk: extended DB outage silently loses market data history.
Mitigated by: AuditLog error entry (if AuditLog write also fails, log to structlog).

**Option B — Retry with backoff**
On failure, sleep and retry the DB write before continuing.
Risk: generator falls behind, SSE stream delays, clients see gaps.
Unacceptable for a real-time streaming service.

**Option C — Stop the generator on DB failure**
Safe but kills the service's primary function.
Overcorrection for a transient DB hiccup.

**Recommended:** Option A. SSE stream is the primary function. DB write failure should
be logged (structlog + AuditLog if possible) but must not stop tick generation.

---

### 3. Active trades loading in Pricing Service

**Problem:** Pricing Service needs active trades to reprice. When and how often does it
query the DB for them?

**Option A — Query DB on every tick**
Always fresh. High DB load at 100ms tick rate with many trades.
Tradeoff: correct but expensive. SELECT on every tick.

**Option B — Poll DB every N seconds, cache in memory**
Background thread refreshes active trades cache every 5-10 seconds.
Repricer uses the cache. New trades take up to N seconds to appear in pricing.
Tradeoff: slight staleness, but acceptable for simulation. Much lower DB load.

**Option C — Query DB only when a tick arrives for a new symbol**
On cache miss (unknown symbol), fetch trades for that symbol from DB.
Tradeoff: first tick for a new trade is delayed by one DB query. After that, cached.
Problem: doesn't detect newly opened trades with existing symbols.

**Option D — Combine B and C**
Periodic full refresh (catch new trades) + cache for performance.

**Recommended:** Option B with a 5-second refresh interval.
Simple, predictable, low DB load. New trades picked up within 5 seconds.

---

### 4. Realized PnL at trade close

**Problem:** When a trade closes, who calculates and stores the realized PnL?

**Option A — Trade Action Service stores realized PnL at close**
When closing, Trade Action Service receives `close_price`, calculates
`realized_pnl = (close_price - trade_price) * quantity` (or inverted for SELL),
stores it on the Trade record itself in a new column.
Pricing Service reads it from there.
Tradeoff: pricing logic leaks into Trade Action Service. But atomic with the close.

**Option B — Pricing Service calculates realized PnL from closed trade**
When Pricing Service sees a trade with `status='CLOSED'`, it uses `close_price`
from the Trade record to calculate realized PnL.
`unrealized_pnl = 0`, `realized_pnl = (close_price - trade_price) * quantity`.
Tradeoff: pricing logic stays in one place. Trade Action Service doesn't need to know about PnL.

**Option C — Store realized PnL in Valuations at close time via Trade Action Service**
Trade Action Service triggers a valuation write when closing. Complex, crosses service boundaries.

**Recommended:** Option B. Pricing logic belongs in Pricing Service.
The Trade record already has `close_price` — Pricing Service can compute realized PnL
without Trade Action Service knowing anything about pricing.

---

### 5. Blotter cache rebuild on restart

**Problem:** Blotter Service restarts and its in-memory valuation cache is empty.
Until Pricing Service sends new valuation events, `GET /trades` shows no PnL.

**Option A — Accept cold start, wait for stream to fill cache**
Simple. Cache fills within seconds once pricing events arrive.
Tradeoff: brief window after restart where PnL shows null.

**Option B — On startup, query DB for latest valuation per trade, pre-fill cache**
`SELECT DISTINCT ON (trade_id) * FROM valuations ORDER BY trade_id, valuation_time DESC`
Pre-fills cache before the service accepts requests.
Tradeoff: slightly more complex startup, one extra DB query.
Benefit: no cold-start gap.
This is the "Extension 4" from the requirements (replay last valuations).

**Option C — Persist cache to DB before shutdown**
Complex, fragile, not worth it for this scope.

**Recommended:** Option B. One query at startup is cheap and eliminates the cold-start problem.
This is explicitly mentioned in the requirements as a bonus extension.

---

### 6. Trade Generation Service — where to get book list

**Problem:** When generating an OPEN_TRADE, the service needs a list of active books
to pick one at random.

**Option A — HTTP call to Books Service**
`GET http://books-service:8004/books`
Tradeoff: network dependency. If Books Service is down, generation stops.
Decoupled from DB, follows microservice principles.

**Option B — Direct DB query**
Query `books` table directly with SQLAlchemy.
Tradeoff: tight coupling to DB schema, but no network dependency.
Simpler, faster, no single point of failure via HTTP.

**Option C — Cache from Books Service, refresh periodically**
Call Books Service on startup and every N minutes.
Tradeoff: eventually consistent, but resilient to Books Service restarts.

**Recommended:** Option B for simplicity given shared DB. Document it as a known coupling.
Option A is architecturally cleaner for a real microservices deployment.

---

### 7. SSE client reconnection strategy

**Problem:** Both Pricing Service (to market-data) and Blotter Service (to pricing) connect
via SSE and must handle disconnections gracefully.

**Pattern (already used in pricing-service):**
```
while True:
    try:
        connect and iterate events
    except (ConnectionError, URLError):
        log reconnect attempt
        sleep(5)
        continue
```

**Tradeoff considerations:**
- Fixed sleep (5s): simple, predictable. May miss many ticks during outage.
- Exponential backoff: better under sustained outage, more complex.
- For this project: fixed 5s sleep is sufficient.

**State during disconnection:**
Pricing Service should set `market_data_connection = "RECONNECTING"` immediately on error.
Health endpoint reflects this — monitoring service sees the degraded state.
In-memory market state stays at last known values (stale but not wrong).

---

### 8. queue.Queue backpressure in Trade Action Service

**Problem:** If Trade Generation Service sends faster than workers can process,
the queue grows without bound.

**Option A — Unbounded queue**
Simple. Memory grows under load.
Acceptable for this simulation since generation rate is controlled (500ms interval).

**Option B — Bounded queue with rejection**
`queue.Queue(maxsize=N)`. `put_nowait` raises `queue.Full` if full.
Return 503 Service Unavailable to the caller.
Tradeoff: clear backpressure signal, but caller must handle 503.

**Option C — Bounded queue with blocking**
`queue.put(item, timeout=5)`. Blocks the HTTP thread for up to 5 seconds.
Tradeoff: HTTP clients wait rather than getting rejected. Ties up HTTP threads.

**Recommended:** Option B with a generous bound (e.g. 1000). Return 503 if full.
Prevents memory issues and signals the caller. Generation interval (500ms) makes
queue overflow unlikely in normal operation.

---

### 9. Alembic autogenerate vs manual migrations

**Problem:** As you add new services and potentially new columns, how do you create migrations?

**Autogenerate (`alembic revision --autogenerate`):**
Compares current DB state to `Base.metadata` (your models).
Generates migration code automatically.
Tradeoff: convenient but can miss: rename detection, custom constraints, partial indexes,
computed columns. Always review generated migrations before applying.

**Manual (`alembic revision`):**
Write `op.create_table`, `op.add_column` etc. by hand.
Full control, no surprises.
Tradeoff: more work, but you understand exactly what runs.

**Recommended:** Autogenerate for initial schema creation and simple additions.
Always review before committing. For complex changes (renames, data migrations),
write manually. The `target_metadata = Base.metadata` in `db/env.py` is already
configured for autogenerate.

---

### 10. structlog configuration approaches

**Option A — Minimal setup: JSON output**
```python
structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```
Output: one JSON object per line, machine-readable. Good for log aggregation.

**Option B — Human-readable for development**
```python
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()
    ]
)
```
Coloured, indented output. Hard to parse programmatically.

**Option C — Environment-based switch**
Use JSON in production (Docker), console renderer in development.
Switch based on `LOG_LEVEL` or `ENV` environment variable.

**Recommended:** Option A (JSON) always. You're running in Docker — container logs
go to stdout and are consumed by the container runtime. JSON is parseable by any
log aggregation tool. `LOG_LEVEL=INFO` env var is already in `.env`.

---

### 11. Pricing when no active trades exist

**Problem:** Pricing Service starts and queries active trades — finds none (empty DB
or all trades closed). What should it do?

**Option A — Skip repricing silently, wait for next tick**
No trades = nothing to price. Log at DEBUG level. Service stays healthy.
SSE stream stays open but publishes nothing.
Correct behaviour.

**Option B — Return empty list from /valuations**
No active trades → empty list. 200 OK. Not an error.

**Both apply simultaneously.** The service is healthy, stream is open, valuations list
is empty. This is the expected state before any trades are created.

---

### 12. Monitoring Service: when a service is not yet deployed

**Problem:** Monitoring Service starts and tries to health-check Books Service
which doesn't exist yet.

**Option A — Connection error marks service as DOWN**
Current behaviour. Simple. Monitoring just reports what it finds.

**Option B — Configurable list of services to monitor**
Only monitor services listed in env vars.
Add new services to monitoring config as they are built.

**Recommended:** Option A. Monitoring reporting DOWN for an undeployed service is
correct — it IS down. Add the services to monitoring config when adding to docker-compose.

---

## Key concepts to understand before starting

| Concept | Why it matters |
|---------|----------------|
| SQLAlchemy session lifecycle | One session per operation, never shared between threads |
| `SELECT ... FOR UPDATE` | Row-level lock for concurrent position closing |
| `queue.Queue` as internal broker | Thread-safe, in-process, lost on restart — document this limitation |
| structlog vs AuditLogs | Console observability vs business event history — both required |
| SSE named events | `event: name\ndata: {}\n\n` — Blotter needs to parse event type |
| `Decimal` serialization | NUMERIC from DB → Decimal → must convert before json.dumps |
| Idempotency keys | UNIQUE on `client_request_id` handles duplicate requests |
| Append-only Valuations | Never update, always insert; latest = max(valuation_time) |
| Soft delete | `is_active=False` on Books — trades reference them via FK |
| Inter-container DNS | Use docker-compose service names, not localhost |
| PnL sign convention | BUY and SELL have opposite signs — most common domain bug |
| Blotter: stream vs DB | Live PnL from cache, history from DB — explicit distinction |

| Concept | Why it matters |
|---------|----------------|
| SQLAlchemy session lifecycle | One session per operation, never shared between threads |
| `SELECT ... FOR UPDATE` | Row-level lock for concurrent position closing |
| `queue.Queue` as internal broker | Thread-safe, in-process, lost on restart — document this limitation |
| structlog vs AuditLogs | Console observability vs business event history — both required |
| SSE named events | `event: name\ndata: {}\n\n` — Blotter needs to parse event type |
| `Decimal` serialization | NUMERIC from DB → Decimal → must convert before json.dumps |
| Idempotency keys | UNIQUE on `client_request_id` handles duplicate requests |
| Append-only Valuations | Never update, always insert; latest = max(valuation_time) |
| Soft delete | `is_active=False` on Books — trades reference them via FK |
| Inter-container DNS | Use docker-compose service names, not localhost |
| PnL sign convention | BUY and SELL have opposite signs — most common domain bug |
| Blotter: stream vs DB | Live PnL from cache, history from DB — explicit distinction |
