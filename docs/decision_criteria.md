# Decision criteria: Bottle (WSGI) → FastAPI (ASGI)

Committed before the first benchmark run. Scenarios: report, section 2.5.

## Decision

- **GO** — migrate all six services to FastAPI, API contract unchanged. Requires all four gates.
- **NO-GO** — stay on Bottle, implement the first item of an alternative plan.

## Variants

| Variant | Server | Handlers |
| --- | --- | --- |
| `bottle-sync` | gunicorn, sync worker | one request at a time |
| `bottle-threads` | gunicorn, 40 threads | 40 at a time, the size of FastAPI's thread pool |
| `fastapi-async` | uvicorn | `async def`, non-blocking I/O (httpx, async database driver) |
| `fastapi-sync` | uvicorn | `def`, in FastAPI's thread pool |

- One process per variant (N = 1): five of the six services keep state in memory.
- Production mode on both sides: no reload, no debug, no access log.
- Today's `wsgiref` server is not measured: it is a development server.

## Measurement

- c = 1, 10, 50, 200. Target load c = 50, stress c = 200.
- S5: 10, 50, 200 open streams, `/health` at c = 10 beside them; only `bottle-threads` and
  `fastapi-async`.
- 10 s warm-up (discarded), 30 s measured, 3 runs per point, variants interleaved, client
  timeout 10 s.
- Metrics: throughput; p50, p95, p99; errors and timeouts; server CPU and RSS.
- The server has its own core; load generator, stub and database use the others.

## Rules

- Each point = median of 3 runs; spread = max − min.
- A difference counts only if it is larger than the larger spread.
- More than 1 % errors or timeouts → the variant loses the point.
- Latency budget: p95 ≤ 100 ms (feels immediate). S3 has no budget.

## Gates

**Bottle** / **FastAPI** = the better variant of that framework at each point.

| Gate | Passes when | Why this value |
| --- | --- | --- |
| 1. No regression | S3 and S4 at c = 10 and 50: FastAPI throughput ≥ 90 % and p95 ≤ 110 % of Bottle's | 10 % = run-to-run noise on one laptop |
| 2. Real gain | S2 at c = 50 or S5 at 50 streams: FastAPI p95 at least 30 % lower, or throughput 2× | more threads alone can give 10–20 % |
| 3. Cost | ≤ 3 h per service with an AI agent, contract tests included | from the inventory, checked against the time the FastAPI sample takes |
| 4. Need | at c = 50 / 50 streams, in S2, S4 or S5: Bottle misses the latency budget and FastAPI meets it | target load, first level above 40 threads |

S1 is not gated: the frameworks differ by microseconds per request.

## Also weighed (not measurable here)

- For FastAPI: Pydantic validation, OpenAPI.
- Against: learning `asyncio`; the risk of a blocking call among 54 synchronous database call
  sites; Bottle's simplicity.

## Revisit when

- load on any service approaches c = 50;
- requests often call external APIs inside the handler;
- WebSocket or many concurrent stream clients are needed;
- a service has to run as more than one process;
- an async database driver is adopted.

## Part 2: the desk core

Added before the first Part 2 run. The business core of the desk under a realistic load: quotes in,
valuations out, trades through. 10 000 instruments refreshed from a provider stub (constant 200 ms),
5 000 open positions. Method: report, Part 2.

### Variants

| # | Variant | Serving |
| --- | --- | --- |
| 1 | `wsgiref` | today's development server (before stage 4B) |
| 2 | gunicorn | gthread, one worker, threads = 40 + open streams (stage 4B) |
| 3 | FastAPI streams | FastAPI serves the market-data and pricing streams; their other routes are the same Bottle app behind `a2wsgi`; the other four services as in variant 2 |

- Same application code in all variants; only the HTTP layer differs.

### Load

- K clients watching: each holds the price stream and the valuation stream. K = 10, 50, 100, 200.
- Trading at a fixed desk rate, independent of K: 0.2 orders opened per second (720 per hour), each
  closed about 60 s later.
- Price previews (`POST /price`, a European option) at 0.2 per second.
- Rates set on 2026-09-28 from the gunicorn desk alone, before any variant comparison: one preview
  costs 120–170 ms of pricing CPU at 10 000 watched instruments, and 1 preview per second already
  pushes valuation freshness past its budget with one client.
- Clients connect at K / 10 per second; then 30 s without dropped streams; then 150 s measured.
  3 runs per point, variants interleaved.

### Budgets (p95)

| Measure | Budget |
| --- | --- |
| Tick delivery: provider response → tick at the client | ≤ 1 s |
| Valuation freshness: provider response → valuation at the client | ≤ 1 s |
| Price preview (`POST /price`) | ≤ 300 ms |
| Position on screen: order confirmed → first valuation of that position | ≤ 3 s |
| Order execution (`POST /trade-actions`) | ≤ 500 ms |
| Errors: timeouts, 5xx, dropped streams | ≤ 1 % |

- Each point = median of 3 runs; spread = max − min; the Part 1 rules apply.
- A run where the clients do not all stay connected for 30 s before the measured window is out of
  budget.

### Decision

- **GO for market-data and pricing** if variant 3, compared with variant 2:
  - (a) stays within the market-data and pricing budgets (tick delivery, freshness, preview, position
    on screen, their errors) at least one K level higher; or
  - (b) at K = 200 has at least 30 % lower p95 in tick delivery, price preview or valuation
    freshness, beyond the larger spread;
  - and in both cases uses at most 10 % more market-data + pricing CPU per client.
- **NO-GO** otherwise.
- Order execution is reported but does not decide: variant 3 does not change trade-action.
