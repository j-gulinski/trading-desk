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

---

## Part 2: the desk's core flows

Does FastAPI handle the desk's core flows better or cheaper than gunicorn?

### Variants

| Variant | Server | Provider calls | Database |
| --- | --- | --- | --- |
| gunicorn (today) | Bottle, 1 worker, 40 threads + 1 per open stream | `httpx.Client`, 1 250 threads | sync, 15 connections |
| FastAPI | uvicorn, 1 worker, all async | `httpx.AsyncClient`, 1 250 at once | async, 15 connections |

- Same test app in both, built on `desk_pricing`; 10 000 instruments, 1 000 000 positions.
- 1 250 calls in flight = top level (5 000/s × 0.2 s) + 25 %: the limit never decides.

### Flows

| Flow | Service | Load | Levels | Target | Budget |
| --- | --- | --- | --- | --- | --- |
| Market data in | market-data | each instrument refreshed every T s; provider answers in 200 ms | T = 10 / 5 / 2 s | T = 5 s | ≥ 98 % refreshes on time; quote age p95 ≤ T + 1 s |
| Order entry | trade-action | insert trade + update position, one transaction | 10 / 50 / 200 orders at once | 50 | p95 ≤ 500 ms |
| Valuation stream | pricing | K subscribers, 50 updates/s each | K = 50 / 200 / 500 | 200 | delivery p95 ≤ 1 s |

- **On time**: a refresh not started before its next due time is missed.
- **Subscribers**: a test program, not the UI; delay read on 5 of the K streams.

### Measurement

- 10 s warm-up; measured 60 s (market data) or 30 s; 3 runs, variants interleaved.
- Median of 3; a difference counts only beyond the larger spread (max − min).
- More than 1 % errors → the variant misses the point.
- CPU per operation = server cores ÷ operations per second.
- Revaluation: one sizing number, cores to revalue 1 000 000 positions per minute.

### Rule

Per flow, at its target:

| Result | Decision |
| --- | --- |
| FastAPI within budget, gunicorn not | GO |
| Both within budget, FastAPI ≥ 30 % less CPU per operation | GO |
| Otherwise | NO-GO |
| Neither within budget | NO-GO: the fix is more processes, not the framework |

- **30 %**: more threads alone gave 10–20 % in Part 1.
- **Every GO** also needs FastAPI's order p95 at 50 ≤ 110 % of gunicorn's (beyond the spread).
- **Scope**: services whose flow passes.
- **Limitation**: flows measured one at a time; in production they share a process.
