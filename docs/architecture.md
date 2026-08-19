# Architecture — the base system

Six Python services, one Postgres, one React frontend, started by `docker compose up --build`.
This is the base the provider build ([hw5-plan-v2.md](hw5-plan-v2.md)) lands on: the synthetic
flows of the forked repo are gone, and market data comes from real providers — Finnhub first
(Phase 2), the rest landing phase by phase per the plan.

## The system in seven steps

```text
1. market-data       external quotes+curves  → publishes ticks + curves (SSE)
2. trade-action      is the only writer      → intents from the ticket → queue → worker → trades table + audit row
3. pricing           reads active trades     → reprices on every tick → publishes valuations (SSE)
4. blotter           reads trades+valuations → serves the operational read model
5. books             owns book metadata      → guarded create/edit/retire
6. monitoring        watches everything      → health, audits, log collection
7. frontend          merges snapshot+stream  → screens that stay live without reloading
```

No message broker, and no service-to-service call about a trade — which is what the three rules
below replace.

## The three design rules

- **The database row is the handoff.** Trade-action inserts a trade; pricing re-queries
  `ACTIVE` trades every `TRADE_REFRESH_SECONDS` and swaps its working set wholesale; blotter
  polls on its own cadence. A restarting service rebuilds its world from one source of truth —
  no replay protocol, no liveness coupling. The cost is ~2 s propagation, invisible in a UI
  that already streams.
- **One writer per table.** Every mutation of `trades` goes through trade-action, even from the
  Books screen; books-service owns `books`; pricing owns `valuations`. When a destructive
  precondition cannot be verified (blotter unreachable during a book delete), the request
  is refused with `503`.
- **Freeze at the boundary.** A trade's economics are validated once at open and frozen into
  its `metadata` JSONB; every later process prices from the frozen terms and never looks
  anything up again. Adding the two OTC classes (options, IRS) required no migration.

## Who owns what

| Service | Port | Owns | Publishes |
| --- | --- | --- | --- |
| market-data | 8001 | provider quotes and curves, provider polling and budgets | `GET /snapshot`, `GET /quotes`, `GET /providers` (+ `/<p>/health`), `POST /refresh`, SSE `/stream` |
| pricing | 8002 | valuations, book alpha/beta, scenario analysis | `GET /valuations`, `GET /book-risk`, SSE `/valuation-stream`, `POST /price`, `POST /scenario` |
| monitoring | 8003 | health polling, audit queries, log collection | `GET /status`, `GET /audits`, `GET /logs`, SSE `/logs/stream` |
| books | 8004 | book metadata and lifecycle | `GET/POST/PUT/DELETE /books` |
| blotter | 8006 | the operational read model over trades | `GET /trades/overview`, `/trades/{id}`, `/books/summary` |
| trade-action | 8008 | **every** mutation of `trades` | `POST /trade-actions` (202), `GET /queue/status`, `GET /instruments`, `GET /instruments/term-schemas` |
| frontend | 3000 | eight views over the above | — |

The browser only requests same-origin `/api/<service>/…` paths; Vite's dev-server proxy
forwards to the containers by name, so no service needs CORS and the frontend's URLs are
deployment-independent.

## Data model

- **`books`** — `book_id`, name, expected asset class, `is_active` (retirement is a soft
  delete).
- **`trades`** — identity, book, side, quantity, prices, lifecycle status, and `metadata JSONB`
  holding the frozen terms; `asset_class` is `TEXT`, not a database enum. Phase 1 added the
  provenance columns (D2): `market_data_provider`, `entry_price_timestamp`,
  `entry_snapshot_id` (FK to the quote-history row used at execution), `client_seen_price`,
  `created_by_service` — present in the schema; nothing writes them at execution yet.
- **`valuations`** — one row per repricing, plus the terminal row written at close; stamped
  with `market_data_provider` + `market_data_timestamp` from Phase 2 on.
- **`audit_logs`** — service, event type, severity, message, entity, `correlation_id`,
  timestamp. The audit trail is the business record; rotating log files plus monitoring's
  bounded in-memory buffers are the technical one.
- **The market store** (reshaped by the Phase 1 migration; details in
  [market-data.md](market-data.md)): `market_data_spot_prices` — the latest quote board,
  unique (provider, symbol), upserted; `market_data_snapshots` — change-only quote history
  with raw payloads; `market_data_curves` / `market_data_curve_points` — curve sets with
  per-point provenance; `watchlist_items` — the symbol master that replaced the static
  instrument catalog.

Migrations live in `db/versions/` (Alembic) and run as the one-shot `db-migrations` container
before any service starts.

## Runtime shape (Phase 0)

- Every service boots through `shared/service_runtime.py`:
  `run_service(name, app, port, startup=…, background=…)` — startup hooks run to completion
  before background daemon threads start and the threaded server begins serving on the
  declared port. A default `/health` is installed unless the service defines a richer one.
- `os.environ` is read only in `shared/config.py` (`env_str` / `env_int` / `env_float` /
  `env_required`); each service's `app/config.py` holds its `SERVICE_NAME`, declared port, and
  service-local knobs. Rationale for every knob: [configuration.md](configuration.md).
- One image per service, all built from the single `docker/service.Dockerfile` template
  (python:3.14-slim, multi-stage, one shared dependency layer from the root
  `requirements.txt`) — the recipe is shared, the images, containers, and processes are not.
  The `db-migrations` compose entry reuses the market-data image for its one-shot
  `alembic upgrade head` job.
- Intents carry a client-minted `client_request_id` (`manual-open-…`, `manual-move-…`); it is
  the idempotency key (unique constraint) and the `correlation_id` that joins audit rows and
  log lines into one correlated trace.

## Conventions

- **No explanatory comments in code** — rationale lives in `docs/`; code carries only
  constraint comments it cannot express itself.
- **Honest UI over fake data** — unavailable values render as real states (`PENDING`, `n/a`,
  `INSUFFICIENT_DATA`), never invented zeros.
- **Bounded everything** — every queue, buffer, and rendered table has an explicit cap.
- **Docs are produced per phase** ([README.md](README.md)) — a document describes the system
  as it is now, or it does not exist.
