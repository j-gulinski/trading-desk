# Decision criteria: Bottle (WSGI) → FastAPI (ASGI)

Committed before the first benchmark run. Sample and scenarios: report, section 2.

## Decision

- **GO**: migrate all six services to FastAPI, API contract unchanged.
- **NO-GO**: stay on Bottle and implement the first item of an alternative plan.

GO requires all four gates.

## Variants

| Variant | Server | Handlers |
| --- | --- | --- |
| `bottle-sync` | gunicorn, sync worker | One request at a time |
| `bottle-threads` | gunicorn, `gthread`, 40 threads | 40 at a time, the size of FastAPI's thread pool |
| `fastapi-async` | uvicorn | `async def` with non-blocking I/O (`httpx.AsyncClient`, async database driver) |
| `fastapi-sync` | uvicorn | `def`, run in FastAPI's thread pool |

- One process per variant (N = 1): five of the six services keep live state in memory and
  cannot run as more than one.
- Production mode on both sides: no reload, no debug, no access log.
- Today's `wsgiref` server is not measured: it is a development server.

## Measurement

| | |
| --- | --- |
| Concurrency | c = 1, 10, 50, 200. Target load: c = 50. Stress: c = 200 |
| S5 | 10, 50 and 200 open streams, `/health` at c = 10 beside them. Only `bottle-threads` and `fastapi-async`: `bottle-sync` serves nothing else while it holds a stream, and `fastapi-sync` holds a pool thread per stream like `bottle-threads` |
| Runs | 10 s warm-up (discarded), then 30 s measured. 3 runs per point, variants interleaved. Client timeout 10 s |
| Metrics | Throughput; p50, p95, p99; errors and timeouts; server CPU and RSS |
| CPU | The server has its own core; the load generator, stub and database use the others |

## Rules

- Each point is the median of 3 runs. Spread = max − min.
- A difference counts only if it is larger than the larger spread.
- More than 1 % errors or timeouts: the variant loses the point.
- Latency budget: p95 ≤ 100 ms, the limit below which a response feels immediate. S3 has no
  budget.

## Gates

**Bottle** and **FastAPI** mean the better variant of that framework at each point. (Threads
in Bottle cost one flag; a migration would choose `def` or `async def` per endpoint.)

| Gate | Question it answers | Passes when |
| --- | --- | --- |
| 1. No regression | Is FastAPI no worse on computation and database work? | S3 and S4 at c = 10 and 50: FastAPI throughput ≥ 90 % and p95 ≤ 110 % of Bottle's |
| 2. Real gain | Is FastAPI clearly better where requests wait? | S2 at c = 50 or S5 at 50 streams: FastAPI p95 at least 30 % lower, or throughput 2× |
| 3. Cost | Is the migration affordable? | ≤ 3 h per service with an AI agent, contract tests included |
| 4. Need | Does the migration solve a real problem? | At the target load (c = 50 / 50 streams) in S2, S4 or S5: Bottle misses the latency budget and FastAPI meets it |

Why these values:

- **10 %**: run-to-run noise on one laptop.
- **30 % / 2×**: more threads alone can give 10–20 %; a migration must clearly beat that.
- **c = 50 / 50 streams**: the target load and the first level above 40 threads, where the two
  models can differ.
- **3 h**: estimated from the inventory, checked against the time the FastAPI sample takes.
- **S1 is not gated**: the frameworks differ by microseconds per request; if that mattered, S4
  would show it.

## Not measurable here

Weighed in the decision record:

| For FastAPI | Against |
| --- | --- |
| Pydantic validation, OpenAPI | Learning `asyncio`; the risk of a blocking call among 54 synchronous database call sites; Bottle's simplicity |

## Revisit when

- load on any service approaches c = 50;
- requests often call external APIs inside the handler;
- WebSocket or many concurrent stream clients are needed;
- a service has to run as more than one process;
- an async database driver is adopted.
