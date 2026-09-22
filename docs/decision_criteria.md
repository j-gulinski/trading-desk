# Decision criteria: Bottle (WSGI) to FastAPI (ASGI)

Stage 2 of the plan, written in Stage 0 and committed before the first benchmark run
(Stage 1). The sample and scenarios S1–S5 are defined in the report, section 2.

## 1. The decision

**GO** — migrate all six services to FastAPI, API contract unchanged.
**NO-GO** — stay on Bottle and implement one item of an alternative plan.

Both are valid outcomes. The benchmark results pass through four gates, in order. Failing
any gate means NO-GO.

## 2. Terms

| Term | Meaning |
| --- | --- |
| **c** | Concurrency — how many clients send requests at the same time. c = 1 is one client waiting for each answer; c = 200 is two hundred at once. Each scenario runs at c = 1, 10, 50 and 200 |
| **N** | How many copies of the service process run behind one port. N = 4 is the PDF's default; N = 1 is how every service here runs today |
| **p95** | The response time that 95 % of requests beat. Says how slow the slow requests are; an average would hide them |
| **throughput** | Requests completed per second |
| **spread** | The gap between the fastest and slowest of the three repeated runs of one measurement |

## 3. What counts as a result

**Setup.** Bottle behind gunicorn (N processes) against FastAPI on uvicorn (N workers,
`async def` handlers). Same machine, same N, production mode, no reload, no console
logging, versions pinned. Bottle's built-in development server is never measured — it is
single-purpose and would make any comparison unfair.

**Repetition.** Every point is measured three times per variant, alternating A, B, A, B, so
that a busy moment on the machine hits both variants equally.

**Uncertainty rule.** A difference counts only if the gap between the two medians is larger
than the larger of the two spreads. Anything smaller is recorded as *no difference*.

## 4. The four gates

**Gate 1 — nothing gets worse.** Any one of these is NO-GO.

| Scenario | Point | Blocker | Why this limit |
| --- | --- | --- | --- |
| S3 `/cpu` | c = 10 | FastAPI slower by more than 10 % | 10 % is about the run-to-run noise on one machine |
| S4 `/books` | c = 50 | FastAPI slower by more than 10 % | same |
| S1 `/health` | c = 1 | FastAPI slower by more than 20 % | no I/O to hide behind — a loss here means the port is wrong |

**Gate 2 — it helps where it should.** Both must pass.

| Scenario | Point | Required | Why this scenario |
| --- | --- | --- | --- |
| S2 `/io` | c = 50, at both N = 4 and N = 1 | p95 down by 30 % **or** throughput doubled | the one case where async can help at all: waiting for another service |
| S5 held SSE clients | 200 clients, N = 1 | p95 of a plain GET down by 30 % | the one such case this system has: clients holding a stream, each on a thread |

The 30 % and 2x limits are the PDF's example criterion; c = 50 is far above today's traffic,
so a gain must be large to mean anything.

S4 is not in this gate. With a synchronous database driver no gain is expected there; a gain
larger than the spread means the measurement is wrong, not that the migration helps.

**Gate 3 — the change is manageable.** The books-service pilot in Stage 2 produces a list of
what actually had to change: routing, request validation, error format, database access,
start-up, Docker. That list is applied on paper to the other five services. GO requires that
nothing on it lacks a known solution — in particular the three SSE streams, the background
threads and the in-memory state that books-service does not have.

**Gate 4 — there is a reason beyond the numbers.** The inventory found no performance
problem: the system serves one browser and its own health checks. Gates 1–3 show the
migration is safe, effective and manageable — not that it is needed. GO also requires a
reason the numbers cannot give.

For:

- FastAPI checks incoming request data automatically. Today every service does it by hand.
- FastAPI generates API documentation. Of little value here — the only client is our own
  frontend.

Against:

- FastAPI code is written as `async`. One wrong call inside it — a blocking one — slows every
  other request in the process. Every database call in this codebase is blocking today.
- Bottle is simpler to read and to teach.

GO needs at least one *for* judged decisive by the owner. Both *against* always count.

## 5. Revisit when

- traffic grows well beyond one browser plus health checks;
- WebSocket or many concurrent SSE clients are required;
- any service needs more than one process;
- an asynchronous database driver is adopted.
