# Migrating the Trading Desk backend from WSGI (Bottle) to ASGI (FastAPI)

| | |
| --- | --- |
| Repository | `trading-desk`, branch `hw-5.5-asgi-migration` |
| Machine | Apple M3, 8 cores, 16 GB |
| Versions | Docker 29.5.0, Python 3.14 (`python:3.14-slim`), Bottle 0.13.4, SQLAlchemy 2.0.52, psycopg 3.3.4, PostgreSQL 18.6 |

---

## 1. Summary

*Written last, after Stage 2 (go / no-go decision).*

---

## 2. System inventory (Stage 0)

Six Bottle services in Docker Compose, one PostgreSQL database and a React frontend. The
browser reaches the services through the Vite development server, which proxies
`/api/<service>/…` to each of them. All endpoints: appendix A.

### 2.1 Shared runtime

All six start through `desk_runtime.service_runtime.run_service`.

| | |
| --- | --- |
| Server | `wsgiref` (standard library) with `ThreadingMixIn`: a new thread per connection, no limit on their number. HTTP/1.0, so every request opens a new TCP connection. Listen queue of 5 (the `socketserver` default). A development server, not a production one: no gunicorn, no waitress |
| Processes | One per container. Start-up hooks and background threads run in the same process as the request handlers. Five services keep live data only in their own memory, so each can run as one process only: a second copy would hold different data. books-service is the exception |
| Database | SQLAlchemy 2.0 ORM, synchronous sessions (`session_scope()`, 54 call sites), psycopg 3, default pool of 5 + 10 connections per process. psycopg 3 also has an asynchronous API; nothing uses it |
| Other services | Standard-library `urllib`: blocking, with explicit timeouts |
| Framework coupling | Bottle is imported only in each service's `api.py` and in `desk_runtime` (`http.py`, `service_runtime.py`). Domain logic and repositories do not depend on it |
| Errors | JSON `{"error": "…"}` for every status, including unknown routes and 500 (`desk_runtime.http`) |
| Tests | None. Behaviour is checked by hand in the UI |
| Containers | One image (`docker/service.Dockerfile`), a Compose healthcheck per service |

### 2.2 Services

Endpoint counts include `/health`.

| Service | Port | Endpoints | Does | Depends on |
| --- | --- | --- | --- | --- |
| market-data-service | 8001 | 19 | Polls seven external market-data APIs, stores quotes and curves, streams updates | PostgreSQL; Finnhub, Twelve Data, FRED, NBP, ECB, EIOPA, Alpha Vantage |
| pricing-service | 8002 | 7 | Revalues active trades on every market update; serves and streams valuations and book risk | PostgreSQL; market-data-service (`/stream` held open, `/snapshot` on reconnect) |
| monitoring-service | 8003 | 5 | Checks every service and the database, collects the log files, streams log lines | PostgreSQL; `/health` of the five other services; the shared log directory |
| books-service | 8004 | 6 | Stores trading books; refuses to deactivate a book that still has open trades | PostgreSQL only |
| trade-action-service | 8008 | 6 | Validates trade orders, acknowledges them, executes them from a queue | PostgreSQL only |
| blotter-service | 8006 | 7 | Lists trades with their latest valuations, book summaries and audit history | PostgreSQL; pricing-service (`/valuation-stream` held open, `/valuations` on reconnect) |

### 2.3 Load character

All six services are **I/O-bound**.

| Service | Request handlers | In the background |
| --- | --- | --- |
| market-data-service | Most read the database. Symbol search and the two manual refreshes call external APIs | A polling thread per provider loop, a retention sweep; stream subscribers in memory |
| pricing-service | Mostly memory reads. `POST /price` and `POST /scenario` compute, one instrument at a time: the only computation in any handler | A stream consumer, a trade refresh loop; prices and valuations in memory |
| monitoring-service | Read memory or the database | A poller per target every 5 s, a database poller, a log collector every 1 s |
| books-service | One or two queries per request | Nothing; nothing in memory |
| trade-action-service | Validation queries the database; the write happens on the worker | One worker thread; the order queue in memory |
| blotter-service | Several queries per request, joined with the valuation cache | A stream consumer, an active-trades refresh loop; trades and valuations in memory |

- **Request handlers** wait on the database: short waits.
- **Background threads** hold the long waits: external APIs, other services' streams, health
  polling. The framework does not change them; under FastAPI the threads would do the same work.
- **The only handlers that wait on external APIs** inside a request are market-data's symbol
  search and two manual refreshes (`GET /symbols/search`, `POST /refresh`,
  `POST /curves/refresh`). External APIs answer in 83–378 ms at the median and up to 1.8 s at
  p95 (61 000 calls in market-data's logs).

So a migration can change only the waits inside requests: database access in most handlers,
the three streams served to the UI, and market-data's in-request provider calls.

**Today's load is small**: one UI polling every 2–10 s and holding two streams (three on the Logs view), health
checks every 5 s, two internal streams. No service has a performance problem at this load, so
the benchmark asks how the backend scales beyond it.

### 2.4 Benchmark sample

**books-service**, plus a stub standing in for another service.

- **Can be kept identical** in Bottle and FastAPI: no background threads, nothing in memory,
  only the database. Every other service needs its streams, caches, providers or log collector
  running.
- **Representative**: request → synchronous database access → JSON is what nearly every
  handler here does.
- **The stub adds what it lacks**: a handler that waits on another service (S2).

### 2.5 Scenarios

| # | Request | Does | Shows |
| --- | --- | --- | --- |
| S1 | `GET /health` | Small JSON, no I/O | Framework and server overhead |
| S2 | `GET /io` | Calls the stub, which waits 50 ms | Waiting on another service — where ASGI should help |
| S3 | `GET /cpu` | 20 000 rounds of SHA-256 | Computation — where ASGI cannot help (control) |
| S4 | Create and read a book | Inserts a book, then reads it back by id, through books-service's repository | This system's typical work: synchronous database writes and reads |
| S5 | `GET /health` beside open streams | 10, 50 or 200 clients hold an SSE stream (one message a second) while 10 others call `/health` | Whether open streams block other requests — in Bottle each holds a thread |

In this system:

- **S2** is market-data's symbol search and manual refreshes. It stands for any remote call,
  to a microservice or a third-party API: only the wait matters, not who answers. Real
  third-party APIs are not called: rate limits, variable latency and API keys would make runs
  neither comparable nor reproducible.
- **S4** is the database wait most handlers have. Each request inserts a book with a unique
  name and reads it back by id, so its cost does not grow with the table. `fastapi-async` runs
  the same two queries over the async driver. The database is dedicated to the benchmark, and
  its books and audit rows are emptied before each point.
- **S5** is the streams three services serve. Every open UI holds two, so their number grows
  with the number of users. The sample gets a minimal `/stream` for it.

Variants, parameters and thresholds: `docs/decision_criteria.md`.

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
