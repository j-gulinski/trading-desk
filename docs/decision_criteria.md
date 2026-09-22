# Decision criteria: Bottle (WSGI) to FastAPI (ASGI)

Written in Stage 0 and committed on its own before the first benchmark run (Stage 1). The
sample and the scenarios S1–S4 are described in the report, section 2.

## 1. The decision

**GO** — migrate all six services to FastAPI, API contract unchanged.
**NO-GO** — stay on Bottle and implement one item of an alternative plan.

Both are valid outcomes. GO requires all four gates below. Failing any gate means NO-GO.

## 2. What is compared

| Variant | Server | Handlers |
| --- | --- | --- |
| **A** Bottle | gunicorn, N sync workers (`-w N`) | plain functions — the PDF's reference point |
| **A′** Bottle + threads | gunicorn, N workers × 40 threads (`-w N --threads 40`) | the same code; 40 = FastAPI's default thread pool, so both sides can run the same number of blocking calls at once |
| **B** FastAPI | uvicorn, N workers (`--workers N`) | `async def` where the I/O is non-blocking (S1, S2 via `httpx.AsyncClient`); `def` where it blocks (S3 computation, S4 synchronous database driver) |

**WSGI** in the gates means the better of A and A′ at that point. Switching Bottle to
threaded workers costs one flag, so that is what the migration has to beat.

Same machine, same N, same Python and pinned versions, production mode, no reload, no
access log. Bottle's development server is never measured.

## 3. Terms

| Term | Meaning |
| --- | --- |
| **c** | Concurrency — how many clients send requests at the same time: 1, 10, 50, 200 |
| **N** | Worker processes behind one port, the same for every variant |
| **throughput** | Requests completed per second |
| **p95** | The response time that 95 % of requests beat |
| **spread** | Max − min of one measurement over its three runs |

## 4. What counts as a result

- Each point is run three times, alternating A, A′, B, and reported as the median.
- A difference counts only when the gap between medians is larger than the larger of the two
  spreads. Anything smaller is *no difference*.
- A variant that returns more than 1 % errors or timeouts at a point loses that point,
  whatever its latency — failed requests do not appear in the percentiles.

## 5. The four gates

**Gate 1 — nothing gets worse.** At c = 10, B's throughput is no more than 10 % below WSGI in
S1 (framework overhead), S3 (computation) and S4 (the real books code).

**Gate 2 — it helps where it should.** In S2 (waiting 50 ms on another service) at c = 50,
B cuts p95 by at least 30 % **or** at least doubles throughput against WSGI. This is the
PDF's example criterion, applied to the only scenario where async can help at all.

**Gate 3 — the cost fits.** The Stage 2 estimate of the full migration is at most **40 hours**,
including contract tests, which do not exist yet and are required before migrating. The
estimate is built per service from the inventory: endpoints, background threads, SSE streams,
in-memory state. 40 hours is one working week, the share of this assignment set aside for
Stage 4.

**Gate 4 — the system needs it.** The Gate 2 gain must also appear in S2 at c = 10. That is
the measured point nearest twice today's peak: one browser, the monitoring health checks and
two internal stream consumers keep at most about five requests in flight per service. A gain
that appears only at c = 50 or 200 answers a load this system does not have.

Pydantic validation, OpenAPI and the cost of learning `asyncio` are weighed in the decision
record (report, section 6). They are not gates, because they cannot be measured here.

## 6. Revisit when

- peak concurrency on any service grows past about ten requests in flight;
- WebSocket or many concurrent SSE clients become a requirement;
- a service needs more than one process;
- an asynchronous database driver is adopted.
