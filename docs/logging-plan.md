# Logging plan — file sink, sweeper, live feed

2026-08-11 · Standalone implementation plan for application-log management: how services write
logs, how they are collected, and how the frontend shows them. Application logs are the
*technical* trail; the existing `audit_logs` table remains the *business* trail. The two stay
separate mechanisms and meet only through `correlation_id`.

## The shape in one paragraph

Every service keeps logging structlog JSON to stdout **and additionally** appends the same lines
to a size-rotated file per service on a shared `./logs` bind mount. monitoring-service grows a
**sweeper thread** that tails those files into bounded in-memory ring buffers (one per service,
no database writes) and exposes two endpoints: `GET /logs` (filtered snapshot) and
`GET /logs/stream` (SSE live tail). The frontend gets a **Logs view** — service and level
filters, text/correlation-id search, live tail — built from existing building blocks
(`useSseStream` + `useStreamSeed`, `FilterBar`, `StatusPill`, the `AuditEventList` row shape).

```text
service (structlog JSON) ──► stdout                      (docker logs — unchanged)
                        └──► /var/log/trading/<svc>.log  (RotatingFileHandler, shared volume)
                                        │
monitoring-service sweeper thread ──── tails all files, parses JSON lines
                                        │
                    per-service ring buffers (deque, bounded, in-memory)
                                        │
              GET /logs (snapshot+filters)   GET /logs/stream (SSE log_line)
                                        │
frontend useLogsFeed = seed + stream ──► Logs view (filters, search, live tail)
                                    └──► System Overview "Recent errors" strip
```

## Design decisions

- **Files + sweeper, not a logs table.** High-volume technical logs would bloat Postgres for no
  query benefit, and there is a bootstrap problem: a database-connection failure cannot be
  logged to the database. Files also survive a monitoring-service restart, and the pattern is
  the minimal version of real log shipping (Filebeat/Fluentd tailing files a process wrote
  locally): transport (files), aggregation (sweeper), and storage policy (bounded buffer) are
  deliberately separate concerns.
- **Services never push logs anywhere.** No `POST /logs` from services to monitoring: a service
  must never block, fail, or slow down because the observer is down. Writing a local file is the
  only obligation; everything downstream is the collector's problem. (Same reasoning as trades:
  the database row is the handoff, nobody calls anybody.)
- **monitoring-service hosts the collector.** It is already the system's observer (health polls,
  `/audits` with the exact filter idiom `/logs` needs), and the Vite proxy already maps
  `/api/monitoring` — zero routing changes.
- **Snapshot + SSE tail, not either/or.** `GET /logs` alone would work with `usePolling`, but the
  app's signature pattern is *seed + stream* (`useStreamSeed` exists precisely for this) and a
  live tail is what makes logs feel real-time. The SSE fan-out is a line-for-line copy of
  `market-data/app/publisher.py` (per-client `queue.Queue`, drop on full).
- **stdout stays.** `docker compose logs` keeps working; the file handler is additive. Both
  sinks render the identical JSON line.
- **Bounded everything.** Ring buffers are `deque(maxlen=…)` *per service* — one chatty service
  cannot evict another's history. SSE client queues are bounded and drop-on-full, like every
  other stream in the app.
- **No new dependencies.** structlog + stdlib only (`logging.handlers`, `queue`, `threading`,
  `collections.deque`).

## 1. File sink (`shared/logging_config.py`)

The one real obstacle: the current config uses `structlog.PrintLoggerFactory()`, which writes
straight to stdout and **bypasses stdlib handlers entirely** — a rotating file handler would
never see a line. The fix is a deliberate factory swap:

- `logger_factory=structlog.stdlib.LoggerFactory()` so rendered lines flow through stdlib
  `logging`; processors (contextvars merge, level, ISO timestamp, `JSONRenderer`) unchanged.
- Handlers built in `configure_logging()`: always a `StreamHandler` (stdout); plus a
  `RotatingFileHandler(LOG_DIR/<service>.log, maxBytes=LOG_FILE_MAX_BYTES,
  backupCount=LOG_FILE_BACKUP_COUNT)` when `LOG_DIR` is set. `format="%(message)s"` — the line
  is already-rendered JSON, handlers just move bytes.
- **Fail-open:** if `LOG_DIR` is unwritable, log one warning and continue stdout-only. Logging
  must never take a service down.
- **Rotation choice:** size-rotated (`<svc>.log`, `.log.1…`), not dated filenames — stdlib has no
  size+date combined handler and every line already carries an ISO timestamp, so dating lives in
  the line.
- Config (all env, `shared/config.py` pattern): `LOG_DIR=/var/log/trading`,
  `LOG_FILE_MAX_BYTES=5000000`, `LOG_FILE_BACKUP_COUNT=3`.
- Compose: bind mount `./logs:/var/log/trading` on **all seven services + monitoring** (it reads
  the same mount). `./logs` is already gitignored. A bind mount (vs named volume) keeps the
  files browsable on the host.

**Correlation IDs (in scope).** `merge_contextvars` is already in the processor chain;
`structlog.contextvars.bind_contextvars(correlation_id=…)` in the trade-action worker (intents
already carry `client_request_id`) stamps every log line of an action's processing with the same
id its audit rows carry — that is what makes correlation-id search and the story view (F1)
work. Bind/unbind per dequeued intent; add the same in pricing where a `trade_id` is naturally
in scope.

**Log-hygiene pass (same change set).** At `TICK_INTERVAL_MS=100`, per-tick logs would dominate
every file and the feed. Rule: per-tick events (`tick_generated`, `valuation_computed`) drop to
**DEBUG**; lifecycle, connections, worker start/stop, rejections, and every WARNING+ stay at
INFO+. Compose keeps `LOG_LEVEL=INFO`. The events remain observable (switch the level to DEBUG
to see them); files stay readable for weeks, not minutes.

## 2. Sweeper/collector (monitoring-service)

New module `app/log_collector.py`, one daemon thread (same shape as `monitor.py` pollers):

- Every `LOG_SCAN_INTERVAL_SECONDS=1.0`: list `LOG_DIR/*.log`, for each file track
  `(inode, offset)`; read appended bytes, split lines. **Rotation detection:** inode change or
  size < offset → reopen from start. New files are picked up automatically: service name =
  filename stem, no registry to maintain — a future service joins the Logs view by merely
  writing its file.
- Each line: `json.loads` with a defensive fallback (`{"event": raw_line}`) — a corrupt or
  non-JSON line must never kill the sweeper. Assign a **monotonic id** (collector-global
  counter) — React key, dedup key, and `since`-cursor in one.
- Storage: `deque(maxlen=LOG_BUFFER_LINES=1000)` per service under one `Lock`. No DB writes,
  ever. **Warm start:** on boot, seed each buffer from the tail of each file (last ~64 KB) so a
  monitoring restart doesn't show an empty view.
- **Minute buckets (feeds F2):** per service, a ring of the last 15 one-minute buckets counting
  lines by level. Two counters in the scan loop, exposed in `GET /logs` meta.
- Fan-out: `log_publisher.py` cloned from `market-data/app/publisher.py` — every parsed line is
  published as a `log_line` SSE event to per-client bounded queues (maxsize 500, drop on full).

**Endpoints** (filter conventions copied from `/audits` — CSV lists, ISO `since`, clamped
limit):

```text
GET /logs?service=&level=&since_id=&q=&limit=
    → { "lines": [ …newest first… ],
        "meta": { "services": { "<name>": { "buffered": 412, "last_at": "…",
                                             "counts": {"info": 390, "warning": 20, "error": 2},
                                             "minutes": [ {"t": "…", "info": 40, "error": 1}, … ] } } } }
    limit default 200, max 500; level validated against debug/info/warning/error/critical;
    q = case-insensitive substring over event, message fields and correlation_id.

GET /logs/stream        → SSE, event: log_line, data: the parsed line (with id, service)
```

The `meta.services` block is what the UI's service chips, sparklines, and the Overview error
count read — no second endpoint needed.

## 3. UI — Logs view

**New route `/logs`** ("Logs", group SYSTEM — 3-line change in `routes.js` + one icon path).
Per-service browsing is served by the service filter being the view's primary control.

- `useLogsFeed` hook: `useSseStream('/api/monitoring/logs/stream', ['log_line'])` +
  `useStreamSeed` fetching `GET /logs`; state is a bounded array (cap 500, newest first),
  deduped by collector id where seed and stream overlap; a **Pause** toggle stops appending
  (buffer continues, "N new lines" badge) — standard live-tail ergonomics. First per-view
  stream in the app (all others are app-root singletons) — acceptable: it is cheap and closes
  on unmount.
- Components, all existing: `FilterBar` + `FilterChipGroup` for service chips (with counts from
  `meta`) and level chips; the search input for `q` / correlation id; row list forked from
  `AuditEventList` (`<details>` rows: time · level `StatusPill` · service · event) with the
  expanded body showing the full JSON payload; `domain/logLines.js` normalizer copied from
  `normalizeAuditEvents`.
- **System Overview:** the placeholder panel ("Central log stream not published by the backend
  yet.") becomes **Recent errors** — last ~10 WARNING+ lines across all services from the same
  feed, linking to `/logs`. Browsing stays out of the overview.

## 4. Related audit-trail gaps (same pack)

Small items that make the observability story complete: `DEPENDENCY_DOWN`/`RECOVERED` audits on
monitoring health-state transitions; `WORKER_FAILED`/`RECOVERED` in the trade-action worker;
per-action processing latency (dequeue→commit ms) recorded in the worker and surfaced in
`/queue/status` so the Trade Actions view's "avg processing time" and per-row `ms` stop
rendering `n/a`.

## Showcase features (the demo layer)

Sections 1–3 make logs *work*; these make them *show*. Each reuses an existing component and
demonstrates a capability recognizable from real systems. Ordered by demo value.

- **F1 — Correlation story view ("follow one intent through the system").** Clicking a
  `correlation_id` anywhere — a log line, an audit row, a trade's audit trail — opens a
  `SidePanel` timeline that merges, chronologically, every **log line** (from the sweeper
  buffers) and every **audit row** (from Postgres) carrying that id, each entry tagged with its
  service and trail (log vs audit). One trade intent, traced across four services and two
  observability trails — distributed-tracing-lite built from parts the app already has.
  Backend cost: add a `correlation_id` filter to `GET /audits`; `q=<id>` on `GET /logs` is
  already specced. Frontend cost: one panel built on `SidePanel` + the same row components as
  the Logs view.
- **F2 — Error pulse (per-service, per-minute).** The collector's minute buckets rendered with
  the existing `Sparkline` inside each service chip on the Logs view, and as the headline
  **"errors, last 5 min"** number on System Overview. Cost: sparkline wiring — the data comes
  from `meta.services.minutes`.
- **F3 — Entity deep-links.** The `logLines` normalizer recognizes well-known payload keys
  (`trade_id`, `book_id`, `symbol`, `correlation_id`) and renders them as links: trade → Trade
  detail, book → Books, symbol → Market Data, correlation id → F1 panel. Logs stop being a
  dead-end text dump and become a navigation surface into the rest of the app. Cost: a
  key→route map in the normalizer plus link rendering in the expanded row.
- **F4 — Failure-cascade demo (choreography, not code).** A documented demo script in the
  README: open the Logs view, run `docker compose stop pricing-service`, and narrate what
  appears live — blotter's `stream_failed` WARNINGs, monitoring's `DEPENDENCY_DOWN` transition
  audit, the Overview error pulse rising; then `docker compose start pricing-service` and watch
  `STREAM_CONNECTED` / `RECOVERED` flow back. Zero code beyond sections 2 and 4.

Deliberately *not* in the showcase: charts of log volume over hours (the buffer is minutes-deep —
the chart would overstate what the system retains), runtime log-level toggles from the UI
(config is env-owned, one owner), and log-based alerting (alerts belong to monitoring state, not
the log trail).

## Future readiness — external market-data phase

Nothing provider-specific is built now; the design's only obligation is that the coming
real-data phase lands on this stack without changes:

- Provider fetch failures and rate-limit hits at 30–60 s polling cadence become *routine*
  WARNING/ERROR log lines: they land in `market-data-service.log`, the sweeper picks them up,
  the level filter makes them one click away. New audit events are just new `write_audit` call
  sites + enum values.
- Provider *health state* (last success/error/poll, error counters) is service state exposed by
  market-data-service itself, **not** logs — the Logs view deliberately does not try to be the
  provider-health view.
- A future service starts appearing in the Logs view by merely writing
  `/var/log/trading/<name>.log` — the sweeper discovers files, not services.

## Verification — how the logs act on the app's current workflows

A manual runbook executed after items 1–4 land (and re-run after 5–6). Each scenario is a
workflow the app already performs; the check is what the logging stack must show for it. File
checks look at `./logs/` on the host; API checks use `/api/monitoring/logs`; UI checks use the
Logs view.

**The runbook doubles as a polish worklist.** Where a scenario's expected line is missing,
misnamed, or missing the fields that make it useful, fix the log statement as part of the pass —
the goal is that each workflow *narrates itself* in the logs. Polish rules: snake_case event
names stating what happened (`trade_entered_active_set`, not `refresh done`); entity ids
(`trade_id`, `book_id`, `symbol`, `correlation_id`) always as kwargs, never baked into the
message string — that is what F3 deep-links and F1 search key on; one line per business moment,
no multi-line narration; and nothing new at INFO on a per-tick path — polish adds clarity, not
volume.

**A. Startup and steady state**

1. **Cold start** — `docker compose up --build`. Expect: `./logs/` gains one `<service>.log`
   per service (8 files incl. monitoring); each begins with that service's `starting` line;
   `GET /logs` meta lists every service with `last_at` fresh; the Logs view shows all service
   chips without any manual registration.
2. **Steady state at INFO** — let the system run 10 minutes with the generator on. Expect: no
   per-tick lines in any file (hygiene pass working — market-data and pricing files grow only
   on lifecycle/worker events, WARNING+, and trade activity); file growth is KB/minute, not
   MB/minute; the live tail is readable, not a blur.
3. **DEBUG opt-in** — set `LOG_LEVEL=DEBUG` on market-data-service only, restart it. Expect:
   `tick_generated` lines flood only that file; other services' buffers are untouched
   (per-service deques — the fairness property, verified directly); revert.

**B. Business workflows**

4. **Generated trade lifecycle** — let the generator open a trade. Expect, in order:
   trade-generation logs the intent; trade-action worker lines all carry the intent's
   `correlation_id` (dequeue → validation → insert); pricing logs the trade entering its active
   set within ~2 s (its refresh loop); filtering the Logs view by `q=<correlation_id>` returns
   the trade-action lines, and the same id on `GET /audits` returns `TRADE_CREATED` — the F1
   story view shows both trails merged in chronological order.
5. **Manual trade via New Trade ticket** — open an OTC option from the UI. Expect: pricing logs
   the preview quote (`POST /price`); the open intent's `manual-open-<uuid>` correlation id
   appears on every worker line; a validation failure (e.g. terms out of bounds) logs the
   rejection at WARNING with the precise reason and pairs with an `ACTION_REJECTED` audit row
   under the same id.
6. **Close and finalization** — close an active trade. Expect: worker lines for the close under
   its correlation id; pricing logs the finalization (realized PnL written, terminal
   valuation); nothing further for that trade after finalization (closed trades leave the
   active set silently — absence is the check).
7. **Book creation** — create a book from the Books view. Expect: books-service logs the CRUD;
   within ~10 s trade-generation logs its book re-sync picking the new book up; the new book
   subsequently appears in generated-trade lines.

**C. Failure modes (the design's core arguments, demonstrated)**

8. **Upstream stream loss** — `docker compose stop market-data-service`. Expect: pricing logs
   `stream_failed` WARNING on each ~5 s retry; monitoring writes the `DEPENDENCY_DOWN`
   transition audit once (not per poll); the Overview error pulse rises; the Logs view level
   filter `warning+` isolates the cascade. Restart → one reconnect line per consumer,
   `RECOVERED` audit, pulse decays. (Same script as the F4 demo — this scenario *is* the
   rehearsal.)
9. **Database down** — `docker compose stop postgres`. Expect: services keep running and keep
   **logging to files** (DB errors at ERROR level, retries visible); audit writes fail and are
   themselves logged (`audit_write_failed`) — the bootstrap argument (a DB failure cannot be
   audited to the DB, but the file trail captures it) verified live. Restart postgres → retry
   lines stop, no service needed a restart.
10. **Collector restart** — restart monitoring-service mid-run. Expect: the Logs view is not
    empty after reload (warm start from file tails); the live tail resumes; the frontend seed
    refetch on reconnect dedups the overlap (no visibly duplicated lines).
11. **Fail-open sink** — unset `LOG_DIR` (or make it unwritable) for one service. Expect: the
    service boots and serves traffic normally, stdout logging intact, one warning about the
    file sink; the sweeper simply sees no file for it — degraded observability, zero
    functional impact.

**D. Mechanics**

12. **Rotation under load** — set `LOG_FILE_MAX_BYTES=100000` + `LOG_LEVEL=DEBUG` on one
    service. Expect: `.log.1` appears and rolls; the sweeper follows the rotation (inode
    change) with no gap and no replayed duplicates in the buffer — verify by watching the
    monotonic ids stay contiguous for that service.
13. **Endpoint filters** — with mixed traffic present, exercise `service=` (CSV), `level=`
    (validated; garbage value → 400), `q=` (event text and correlation id, case-insensitive),
    `since_id=` (returns only newer lines), `limit=` (default 200, clamped at 500). Expect
    each to behave per spec and compose with the others.
14. **Stream backpressure** — open the Logs view in several tabs, flip one service to DEBUG.
    Expect: slow clients drop excess events (bounded queues) but connections stay alive; no
    service-side errors; the UI's Pause toggle accumulates a "N new lines" badge instead of
    scroll-jumping.

The pass criterion for the whole runbook: every scenario observable **without reading any
service's stdout** — the files, the endpoints, and the Logs view alone tell the full story.

## Order and sizing

| # | Item | Size |
|---|------|------|
| 1 | File sink: factory swap + file handler + compose mounts + env | S |
| 2 | Log-hygiene pass (per-tick → DEBUG) + correlation-id binding in trade-action | S |
| 3 | Sweeper + ring buffers + `GET /logs` + `GET /logs/stream` (incl. F2 minute buckets) | M |
| 4 | Logs view + Overview "Recent errors" panel (incl. F2 sparklines, F3 deep-links) | M |
| 5 | Audit-trail gaps: transition audits + processing latency | S |
| 6 | F1 correlation story view (+ `correlation_id` filter on `/audits`) | S/M |
| 7 | Verification runbook pass + workflow log-narration polish (fixing gaps it finds) | S/M |
| 8 | README: logging architecture section + F4 demo script | S |

F2 and F3 ride inside items 3–4 (they touch the same files); F1 is its own item because it
adds a backend filter and a new panel; F4 is documentation only. Item 7 is where existing log
statements across services get their polish — driven by what the runbook scenarios expose, not
by a speculative sweep.

The README section covers: technical logs vs audit trail (one paragraph), the sweeper rationale
(files not database — both arguments), rotation policy, buffer bounds and what is *not* promised
(no long-term retention, no cross-restart search), correlation-id flow, and the demo script.

## Deliberately out of scope

Log persistence beyond the rotating files (no database table, no search index), external log
stacks (ELK/Loki — over-scope and outside the dependency set), a metrics endpoint (separate,
smaller feature), runtime log-level switching from the UI, and multi-line/stack-trace folding
beyond what `log.exception` already renders into a single JSON line. Each is one "known
limitation" line in the README — honest limits over half-features.
