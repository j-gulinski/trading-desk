# Migrating the Trading Desk backend from WSGI (Bottle) to ASGI (FastAPI)

| | |
| --- | --- |
| Repository | `trading-desk`, branch `hw-5.5-asgi-migration` |
| Hardware | Apple M3, 8 cores, 16 GB, Docker Desktop 29.4.3 |
| Versions | Python 3.14.7, Bottle 0.13.4, SQLAlchemy 2.0.52, psycopg 3.3.4, PostgreSQL 18.6 |

---

## 1. Summary

*Written last, after Stage 2 (go / no-go decision).*

---

## 2. System inventory (Stage 0)

Six Bottle services in Docker Compose, one PostgreSQL database, one React frontend. Each
service is one process in one container, served by a small threaded server from `desk-runtime`
(`wsgiref` with one thread per connection, `service_runtime.py`), using a synchronous
database driver (SQLAlchemy + psycopg). There are no automated tests.

Every service is **I/O-bound**: handlers wait on the database or on another service, never
on computation. Endpoint details are in appendix A.

The load is small. One browser polls a few endpoints every 2–10 s and holds three SSE streams;
monitoring calls every `/health` every 5 s; pricing and blotter each hold one internal stream.
No service has more than about five requests in flight at once.

### 2.1 Services

**market-data-service** · 8001

| | |
| --- | --- |
| Does | Polls 7 external providers, stores quotes and curves, streams updates to clients |
| Endpoints | 19 — quotes, curves, watchlist, FX, search, providers, `/snapshot`, `/stream` |
| Depends on | PostgreSQL, 7 external APIs |
| Load | Handlers read the DB. Provider calls — the slow part — run in background threads |
| Runs as | 1 process, polling threads, SSE subscribers in memory |

**pricing-service** · 8002

| | |
| --- | --- |
| Does | Revalues active trades from the market stream, streams valuations to clients |
| Endpoints | 7 — `/valuations`, `/book-risk`, `POST /price`, `POST /scenario`, `/valuation-stream` |
| Depends on | PostgreSQL, market-data-service (stream + snapshot) |
| Load | Reads serve memory. The work is the incoming stream and a periodic DB refresh |
| Runs as | 1 process, stream consumer thread, prices and valuations in memory |

**monitoring-service** · 8003

| | |
| --- | --- |
| Does | Checks the health of every service and the DB, tails the log files |
| Endpoints | 5 — `/status`, `/audits`, `/logs`, `/logs/stream` |
| Depends on | PostgreSQL, all five other services (`/health` every 5 s), log files |
| Load | Its own health polling is most of its work |
| Runs as | 1 process, six polling threads, log buffers in memory |

**books-service** · 8004

| | |
| --- | --- |
| Does | Stores trading books; refuses to close a book that still has open trades |
| Endpoints | 6 — `GET/POST /books`, `GET/PUT/DELETE /books/<id>` |
| Depends on | PostgreSQL only |
| Load | One or two DB queries per request, nothing else |
| Runs as | 1 process, **no background threads, nothing in memory** |

**trade-action-service** · 8008

| | |
| --- | --- |
| Does | Validates trade orders, acknowledges them, executes them from a queue |
| Endpoints | 6 — `POST /trade-actions` (+ `/batch`, `/close-all`), `/queue/status`, `/instruments/term-schemas` |
| Depends on | PostgreSQL only |
| Load | Validation queries the DB in the request; the write happens on a worker thread |
| Runs as | 1 process, one worker thread, queue in memory |

**blotter-service** · 8006

| | |
| --- | --- |
| Does | Shows trades with their latest valuations, book summaries, audit history |
| Endpoints | 7 — `/trades`, `/trades/overview`, `/trades/<id>` (+ valuations, audit), `/books/summary` |
| Depends on | PostgreSQL, pricing-service (stream + snapshot) |
| Load | Several DB queries per request, joined with a valuation cache |
| Runs as | 1 process, stream consumer thread, trades and valuations in memory |

Five services keep live data only in their own memory: pricing holds the latest valuations,
trade-action holds its order queue, and so on. Running two copies of such a service would
split that data between them — a request to one copy would not see what the other holds. So
these five can only ever run as one copy each. books-service keeps nothing in memory; several
copies of it would behave exactly like one. That matters for the benchmark, which the PDF
runs with several worker processes: for books-service that setup is real, for the others it
could not exist.

### 2.2 Benchmark sample: books-service

A benchmark builds the same thing twice, in Bottle and in FastAPI. Everything except the
framework must be identical, or the comparison measures something else. books-service is
the easiest service to hold identical:

- **No background threads** — nothing runs beside the handlers to add noise.
- **Nothing in memory** — no cache or queue to fake before measuring.
- **No other services** — only the database is needed to run it.

What remains is what every service here does: take a request, run one or two synchronous
database queries, return JSON.

The others fail one of these tests. blotter and pricing serve caches that only exist while
their streams run; market-data's `/snapshot` pulls in most of the domain library;
monitoring's `/logs` needs the log collector.

### 2.3 Scenarios

The PDF prescribes a small sample app, built in both frameworks, with a few endpoints. Three
are artificial on purpose — each isolates one property — and one uses the real books code.

| # | Endpoint | Does | Answers |
| --- | --- | --- | --- |
| S1 | `GET /health` | Returns tiny JSON, no I/O | Bare cost of the framework and server |
| S2 | `GET /io` | Calls a stub service that waits 50 ms | Waiting for another service — where ASGI should win |
| S3 | `GET /cpu` | 20 000 rounds of SHA-256 | Pure computation — where ASGI cannot help. A control |
| S4 | `GET /books` | Real books-service code: one query, 20 books as JSON | What migration does to *this* system. No gain expected; shows nothing breaks |

Each scenario runs at c = 1, 10, 50 and 200 against three variants: Bottle on sync workers,
Bottle on threaded workers and FastAPI. The variants, the thresholds and the reason the
threaded Bottle variant is included are in `docs/decision_criteria.md`.

Held SSE connections are not measured. One browser and two internal consumers hold five
streams in total — a load no server here notices.

---

## 3. Benchmark method

*Stage 1 (benchmark on a small sample). Starts only after `docs/decision_criteria.md` is
committed.*

## 4. Results

*Stage 1 (benchmark on a small sample).*

## 5. Interpretation

*Stage 1 (benchmark on a small sample).*

## 6. Criteria and decision (ADR)

*Stage 2 (go / no-go decision), against the thresholds in `docs/decision_criteria.md`.*

## 7. Risk analysis

*Stage 3 (risk matrix).*

## 8. Refactor (GO) or alternative plan (NO-GO)

*Stage 4A after GO, Stage 4B after NO-GO.*

## 9. Conclusions and lessons

*Written last.*

---

## 10. Appendices

### A. Endpoints

All responses are JSON. Errors are `{"error": "..."}` with the HTTP status — also for
unknown routes (404), wrong methods (405) and unhandled exceptions (500). SSE endpoints
return `text/event-stream`.

**market-data-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/stream`, `/stream/<provider>` | — | 200, 404 | SSE: `market_tick`, `curve_tick`, `market_remove` |
| GET | `/snapshot` | — | 200 | `{stream_id, event_id, spots, curves}` |
| GET | `/curves`, `/curves/<provider>` | `raw` | 200, 404 | list of curves |
| GET | `/curves/<provider>/<curve>/<as_of>` | `raw` | 200, 400, 404 | one curve |
| POST | `/curves/refresh` | `curve`, `provider` | 200, 404 | `{refreshed, skipped}` |
| GET | `/quotes` | `symbol`, `asset_class`, `provider` | 200 | list of quotes |
| GET | `/quotes/<provider>/<symbol>` | — | 200, 404 | one quote |
| GET | `/quotes/<provider>/<symbol>/history` | `limit` 1–200, `raw` | 200, 400, 404 | list of snapshots |
| GET | `/watchlist` | — | 200 | list of items |
| POST | `/watchlist` | JSON body | 201, 400, 404, 409, 422 | item |
| DELETE | `/watchlist/<symbol>` | `provider` | 200, 404, 409 | removal result |
| GET | `/fx/rates` | `to` | 200, 400 | `{to, rates}` |
| GET | `/symbols/search` | `q` (≥ 2 chars) | 200, 400, 503 | `{query, results, provider_errors}` |
| GET | `/providers`, `/providers/<name>/health` | — | 200, 404 | provider status |
| POST | `/refresh` | `symbol`, `provider` | 200, 404, 422 | tick |
| GET | `/health` | — | 200 | `{service, status}` |

**pricing-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/valuations` | — | 200 | list of valuations |
| GET | `/valuations/<trade_id>` | — | 200, 404 | one valuation |
| GET | `/book-risk` | — | 200 | list of book-risk records |
| POST | `/price` | JSON body | 200, 400, 404, 409, 503 | priced instrument |
| POST | `/scenario` | JSON body | 200, 400, 404 | scenario result |
| GET | `/valuation-stream` | — | 200 | SSE: `valuation_update`, `book_risk_update` |
| GET | `/health` | — | 200 | `{service, status, …}` |

**monitoring-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/status` | — | 200 | health of every target |
| GET | `/audits` | `limit`, `since`, `severity`, `service`, `event_type`, `correlation_id`, `entity_id` | 200 | list of audit rows |
| GET | `/logs` | `level`, `since_id`, `run_id`, `service`, `q`, `limit` | 200, 400 | `{lines, meta}` |
| GET | `/logs/stream` | — | 200 | SSE: `run`, `log_line` |
| GET | `/health` | — | 200 | `{service, status}` |

**books-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/books` | — | 200 | list of books |
| GET | `/books/<book_id>` | — | 200, 404 | one book |
| POST | `/books` | `name`, `expected_asset_class`, `description` | 201, 400, 409 | created book |
| PUT | `/books/<book_id>` | partial body | 200, 400, 404, 409 | updated book |
| DELETE | `/books/<book_id>` | — | 200, 404, 409 | deactivated book |
| GET | `/health` | — | 200 | `{service, status}` |

**trade-action-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/instruments/term-schemas` | — | 200 | `{instruments, schemas, curves}` |
| POST | `/trade-actions` | JSON intent | 202, 400, 422, 503 | acknowledgement |
| POST | `/trade-actions/batch` | JSON array | 202, 400, 413, 422, 503 | `{accepted, rejected}` |
| POST | `/trade-actions/close-all` | optional body | 202, 400, 503 | acknowledgement |
| GET | `/queue/status` | — | 200 | counters |
| GET | `/health` | — | 200 | `{service, status}` |

**blotter-service**

| Method | Path | Params | Codes | Body |
| --- | --- | --- | --- | --- |
| GET | `/trades`, `/trades/overview` | `limit` 1–500, `offset`, `book_id`, `asset_class`, `status`, `symbol` | 200, 400 | list of trades / `{trades, books}` |
| GET | `/trades/<trade_id>` | — | 200, 404 | `{trade, latest_valuation, valuation_history, audit_logs}` |
| GET | `/trades/<trade_id>/valuations`, `…/audit-logs` | — | 200, 404 | list |
| GET | `/books/summary` | — | 200 | list of book summaries |
| GET | `/health` | — | 200 | `{service, status, …}` |
