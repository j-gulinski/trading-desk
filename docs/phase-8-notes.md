---
phase: 8
status: complete
revised: 2026-08-12
tags:
  - logging
  - observability
  - sweeper
  - correlation
  - sse
---

# Phase 8 — logging, step by step

This phase gave the system a working application-log pipeline: from a log statement in a service
to a live, filterable Logs view in the frontend. This document walks the phase in the order it
was built. Every step answers the same three questions: **what was needed**, **what was chosen**
(and what was rejected), and **what code was added**.

## 1. The idea in 60 seconds

Before this phase, every service already logged structured JSON — but only to stdout. The lines
were visible in `docker compose logs` and nowhere else: nothing collected them, nothing served
them, and the System Overview had a placeholder panel saying "Central log stream not published by
the backend yet."

What was needed was a path from a log statement to a screen:

```text
STEP 1                 STEP 4                    STEP 5                 STEP 6
service writes    ──►  monitoring collects  ──►  API serves        ──►  UI shows
one JSON line          the files into            GET /logs             Logs view:
to its own file        in-memory buffers         GET /logs/stream      filters, search,
(plus stdout,          (the "sweeper")           (snapshot + live      live tail
as before)                                        SSE tail)
```

Steps 2 and 3 are about the *content* of the lines (keeping files readable; tying one action's
lines together with a correlation id), and steps 7–8 build the showcase features on top.

One distinction runs through everything, so it comes first. The system now has **two trails**:

| | audit trail (existed) | application logs (this phase) |
| --- | --- | --- |
| Records | business moments: trade created, action rejected | technical events: retries, connections, failures with reasons |
| Written | deliberately, one row per event | freely, wherever code finds it useful |
| Stored | Postgres `audit_logs`, forever | rotating files + memory buffers, recent window only |
| Asks | "what happened to this trade?" | "why did it happen / what was the system doing?" |

They stay separate mechanisms and meet in exactly one place: both kinds of record can carry the
same `correlation_id`, which is what makes the story view (§8) possible.

## 2. The shape decision — files and a sweeper

Before any code, one decision shaped the whole phase: *where do log lines go?* Three candidate
designs:

1. **A `logs` table in Postgres** (like `audit_logs`). Rejected for two reasons. Volume:
   technical logs are orders of magnitude chattier than audits and would bloat the database for
   no query benefit. Bootstrap: a database-connection failure *cannot be logged to the
   database* — the moment you most need the log is the moment that design cannot record it.
2. **Services push logs to monitoring** (`POST /logs`). Rejected because it inverts the
   dependency: a service should never block, fail, or slow down because the *observer* is down.
   Observability must cost the observed system nothing.
3. **Services write local files; monitoring tails them.** Chosen. Writing one line to a local
   file is the service's entire obligation — everything downstream (collecting, buffering,
   serving, displaying) is the collector's problem. Files survive a monitoring restart. And it
   is the minimal honest version of how real log shipping works (Filebeat/Fluentd tailing files
   a process wrote locally), with the three concerns — transport (files), aggregation (sweeper),
   storage policy (bounded buffers) — kept separate.

Both rejections were later demonstrated live, not just argued (§11): with postgres stopped, the
files kept collecting the very errors the database could not record.

## 3. Step 1 — every service writes its log to a file

**What was needed.** A file per service that a collector can read, without changing what the
logs look like or breaking `docker compose logs`.

**What was chosen.** Keep stdout exactly as it was, and *additionally* append the identical JSON
lines to `/var/log/trading/<service>.log`, size-rotated, on a `./logs` bind mount shared by all
services. A bind mount (not a named volume) keeps the files browsable on the host. Rotation is
by size (`.log`, `.log.1`, …), not by date — every line already carries an ISO timestamp, so
dating lives *in the line*, and stdlib has no combined size+date handler anyway.

**What was added.** The one real obstacle lived in `shared/logging_config.py`. The old config
used `structlog.PrintLoggerFactory()`, which writes rendered lines straight to stdout and
bypasses Python's `logging` machinery entirely — you can attach any number of file handlers and
they will never see a line. The fix is the factory swap:

```python
logger_factory=structlog.stdlib.LoggerFactory(),   # was: structlog.PrintLoggerFactory()
```

With the stdlib factory, structlog still does all the work it did before (merge context
variables → add level → add ISO timestamp → render to JSON), but then hands the finished line to
a standard `logging.Logger`, and stdlib fans it out to every configured handler. Two handlers
are configured: a `StreamHandler` (stdout, unchanged behavior) and — only when `LOG_DIR` is
set — a `RotatingFileHandler(LOG_DIR/<service>.log)`. The format string is just `"%(message)s"`:
the line is already-rendered JSON, handlers only move bytes.

The rest of the step is wiring:

- `configure_logging()` grew a parameter: `configure_logging(SERVICE_NAME)` in every service's
  `main.py` — the service name becomes the filename, and the filename later becomes the
  service's identity in the whole pipeline (§6).
- **Fail-open rule:** if `LOG_DIR` is set but unwritable, the service logs one
  `log_file_sink_unavailable` warning and continues stdout-only. Logging must never take a
  service down.
- Config, in the established env pattern: `LOG_DIR=/var/log/trading`,
  `LOG_FILE_MAX_BYTES=5000000`, `LOG_FILE_BACKUP_COUNT=3` (`shared/config.py`, `.env`,
  `.env.example`).
- `docker-compose.yml`: the bind mount `./logs:/var/log/trading` on all seven Python services.
  `./logs` is gitignored (root-only pattern — see the trap in §12).

## 4. Step 2 — keep the files worth reading

**What was needed.** Market data ticks continuously; pricing revalues on every tick. One
careless `log.info` on a per-tick path and the files grow by megabytes per minute — unreadable,
and rotation would eat history in minutes. At the same time, the *interesting* moments (a trade
being created, a rejection and its reason) were barely logged at all.

**What was chosen.** An editorial policy, applied as a pass over existing statements and a set
of new ones:

- **Per-tick events log at DEBUG** — `tick_generated` (market-data), `valuation_computed`
  (pricing). They still exist: flip one service to `LOG_LEVEL=DEBUG` and only that service's
  file floods. Compose keeps `LOG_LEVEL=INFO`.
- **Business moments log at INFO, one line each** — the trade lifecycle now narrates itself
  across services: `generated` (trade-generation) → `intent_dequeued` → `trade_created`
  (trade-action) → `trade_entered_active_set` (pricing) → … → `trade_closed` →
  `trade_finalized` with realized PnL. Plus `price_preview` on quote, `book_created`/
  `book_updated` on CRUD, `books_synced` when the generator's book set actually changes.
- **Failures log at WARNING/ERROR with the precise reason** — `open_rejected` carries the
  validation message; `stream_failed`, `dependency_down`, `audit_write_failed` carry theirs.
- **Entity ids are always kwargs, never baked into the message string** — `trade_id=…`,
  `book_id=…`, `symbol=…`, `correlation_id=…`. Structured keys are what search and the UI
  features key on (§8); a message string is where ids go to be unfindable.

**What was added.** Log statements across the services (no new machinery): the worker narration
and rejection reasons in `trade-action-service/app/trade_processor.py`; active-set entry and
finalization in `pricing-service/app/cache.py` (with an `active_set_bootstrapped` summary line
at startup instead of ~300 individual "entered" lines); `price_preview` in
`pricing-service/app/api.py`; book CRUD in `books-service/app/repository.py`; sync logging in
`trade-generation-service/app/generator.py`. Measured result in steady state: market-data wrote
4 lines in ten minutes of continuous ticking.

## 5. Step 3 — one id ties an action's lines together

**What was needed.** "Show me everything about *this* trade action" — across four services and
across both trails. The audit rows already carried `correlation_id` (the intent's
`client_request_id`); the log lines did not.

**What was chosen.** structlog's contextvars. The processor chain already began with
`merge_contextvars`, so anything bound into context appears on every line logged under that call
stack — no function signature changes anywhere. The trade-action worker binds the id around each
intent it processes:

```python
structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
try:
    _process(intent)          # every log line in here carries the id automatically
finally:
    structlog.contextvars.unbind_contextvars("correlation_id")
```

The id is minted at the *source* of the intent — the generator names its intents
`gen-open-<uuid>` / `gen-close-<uuid>`, the New Trade ticket sends `manual-open-<uuid>` — and
everything downstream just carries it. Pricing does not bind (it has no intent in scope); its
per-trade lines carry `trade_id` as a kwarg instead, which is enough to join the story.

**What was added.** The bind/unbind in `worker_loop`, and one fix the verification pass caught:
trade-generation's `generated` line logged the id under a kwarg named `crid` — a name nothing
searches for. Renamed to `correlation_id` (plus `trade_id`, `symbol`), the intent's birth line
joined its own story. That is the hygiene rule of §4 enforcing itself.

## 6. Step 4 — the sweeper collects the files

**What was needed.** One place that reads all the files continuously and can answer "the last N
lines, filtered" without anyone grepping containers.

**What was chosen.** A single daemon thread in monitoring-service that *tails* the files:

| Decision | Alternative rejected | Why |
| --- | --- | --- |
| Lives in monitoring-service | A separate shipper container (Filebeat/Fluentd) | Monitoring is already the observer, and the Vite proxy already routes `/api/monitoring` — zero new containers, zero routing |
| A plain thread | asyncio | The work is blocking local-file `stat`/`read`; there is no real async file I/O to await, so async would add a scheduler in front of the same blocking calls |
| One `deque(maxlen=1000)` **per service** | One shared buffer for all services | The fairness bound: a service flipped to DEBUG floods only its own 1000 slots and cannot evict anyone else's history |
| Memory only | A `logs` table | The storage policy is "a bounded recent window", which is exactly what `maxlen` is — O(1) eviction, no cleanup job (§2) |

**The concepts it rests on.** The module is short, but it uses a handful of ideas that are worth
naming before reading it:

| Concept | What it means | Why it appears here |
| --- | --- | --- |
| **Tailing** | Repeatedly reading only the bytes appended since last time (what `tail -f` does) | The whole job: re-reading each file from the top every second would not scale |
| **Offset** | How many bytes of a file have already been consumed — a resume point | Read position for the next scan; stored per file |
| **inode** | The filesystem's internal id for a file. The *name* is just a pointer to it: renaming keeps the inode, recreating makes a new one | The only reliable way to notice that `x.log` is now a *different* file (rotation) |
| **Rotation** | When a file hits the size cap, `RotatingFileHandler` renames `x.log` → `x.log.1` and creates a fresh empty `x.log` | Without detecting it, the sweeper would sit at a stale offset past the end of a new, tiny file and read nothing forever |
| **Partial line** | The writer may be halfway through appending when the sweeper reads | Consuming half a line would corrupt it; the fix is to stop at the last `\n` |
| **Binary mode** | Reading raw bytes rather than decoded text | Offsets are byte counts; text mode's decoding and newline translation would desynchronize the cursor |
| **`deque(maxlen=N)`** | A fixed-size double-ended queue (ring buffer): appending to a full one drops the oldest, in O(1) | Bounded memory with no eviction logic to write |
| **Daemon thread** | A background thread that does not keep the process alive | The sweeper should die with monitoring, not block its shutdown |
| **Lock (critical section)** | A mutex making a block of code run one-thread-at-a-time | Flask request threads read the buffers while the sweeper writes them |
| **Monotonic id** | A counter that only ever increases | One number used as React key, dedup key, and `since_id` cursor |
| **Page cache** | The OS keeps recently written file data in RAM | The sweeper reads bytes written milliseconds ago, so reads hit memory, not disk |

**What was added.** `monitoring-service/app/log_collector.py`. Module state is four objects
guarded by one lock:

| State | Shape | Holds |
| --- | --- | --- |
| `_buffers` | service → `deque(maxlen=1000)` | the log lines |
| `_tails` | file path → `{inode, offset}` | where to resume reading — the bookmark |
| `_minutes` | service → `deque(maxlen=15)` | per-minute counts by level |
| `_ids` | `itertools.count(1)` | the monotonic id source |

*At boot* (`_collector_loop`), in order:

1. **One seeding scan** — `_scan(seed=True)`. Every file is new to `_tails`, so each gets a
   warm-start bookmark near its end rather than at byte 0.
2. **Clear `_minutes`.** The seeding scan filled the buffers *and* counted those lines into
   minute buckets. Wiping the buckets is what makes warm-start lines history rather than current
   pulse — the alternative was threading a "don't count this one" flag down through every layer.
3. Log `log_collector_started` with the seeded line count.
4. Enter the loop: sleep one second, `_scan()`, repeat.

*Each scan* lists `LOG_DIR/*.log` and runs `_scan_file` per file. Per file, in order:

1. **`stat()` the file** — one syscall, returning size and inode together.
2. **Find the bookmark** in `_tails`. Four cases:

   | Case | Test | Bookmark set to |
   | --- | --- | --- |
   | First sight, at boot | not in `_tails`, `seed=True` | `_seed_offset(…)` — near the end |
   | First sight, at runtime | not in `_tails`, `seed=False` | `0` — a service that just started; read it all |
   | Rotated | `st_ino` changed **or** `st_size < offset` | `0` — this is a different or emptied file |
   | Normal | neither branch fires | unchanged — resume where the last scan stopped |

   Rotation needs both tests because there are two ways to rotate. `RotatingFileHandler` renames
   `svc.log` → `svc.log.1` and creates a fresh one: same name, **new inode**. Other tools
   truncate in place: same inode, but the file is now **shorter than the bookmark**. Either way
   the old position is meaningless.
3. **Early out** — `st_size <= offset` means nothing was appended. Return without opening the
   file. This is the common case for most files most seconds, and it is why a scan costs one
   `stat()` per file and nothing more.
4. **Read the new bytes** — open `"rb"`, `seek(offset)`, read to EOF. Binary mode is required:
   the bookmark is a *byte* count, and text mode's decoding and newline translation would make
   the position drift.
5. **Cut at the last newline** — `end = data.rfind(b"\n")`. If there is none, return with the
   bookmark untouched: no complete line has arrived yet.
6. **Advance the bookmark** to `end + 1`, just past that newline — so any half-written trailing
   line stays unread until the next scan, when the writer has finished it.
7. **Ingest** each non-blank line of `data[:end]`, decoded with `errors="replace"` so one mangled
   byte cannot kill the sweeper. Service name = `path.stem`.

Step 6 is the whole concurrency story. The reader never consumes past the last newline it can
see, so appending and tailing need no lock, no signal, and nothing the observed service has to do
or even know about. The invariant: **the bookmark only ever advances past bytes already ingested
as complete lines.** Every early return leaves it untouched, so the worst case is re-reading the
same bytes next second — never skipping a line, never duplicating one.

*Per line* (`_ingest`), in order: parse JSON with a `{"event": raw_line}` fallback → normalize
the level to a known name → copy the parsed dict and stamp `level`/`service` → **under the
lock**, take the next id, append to the service's buffer, bump the minute bucket → **outside the
lock**, publish to SSE clients. Publishing outside matters: the fan-out walks every connected
client's queue, and doing that while holding the collector lock would let a slow reader stall
ingestion for everyone.

Four details around that core:

- **Warm start is aligned once, at boot.** `_seed_offset` starts `64 KB` from the end and then
  moves forward to the next line boundary, so the first line read is whole. Doing it here rather
  than in the scan path keeps a once-per-file concern out of the once-per-second one — and it
  handles the degenerate case correctly: a 64 KB window containing *no* newline means one
  enormous unterminated line, so the bookmark jumps to EOF and waits for a real line rather than
  guessing. Effect: a monitoring restart shows history immediately (verified: 294 lines).
- **Discovery is the filesystem.** Service name = filename stem, no registry. A future service
  appears in the Logs view by merely writing `/var/log/trading/<name>.log`.
- **The id is collector-global, not per service.** That is what lets the merged feed sort on one
  integer and the client hold one scalar cursor. Caveat: ids order lines by when the *sweeper*
  saw them, so two services interleave within a one-second window rather than by their own
  timestamps.
- **Minute buckets are sparse.** A bucket is appended only when a line arrives, so a quiet
  service's 15 buckets can span an hour. Safe because the consumer densifies it —
  `minuteSeriesOf` (`domain/logLines.js`) re-projects them onto a wall-clock timeline and
  zero-fills the silent minutes.

Failures are contained at three levels: a non-JSON line becomes `{"event": raw_line}`; a file
that vanishes mid-scan (`OSError`) is skipped and re-stat'd next cycle; any other per-file error
is logged and the remaining files still scan. A related constraint: the sweeper reads
monitoring's *own* file, so per-line or per-scan logging here would feed itself.

**What it costs.**

| | Steady state | Bound |
| --- | --- | --- |
| Syscalls / second | 1 readdir + 7 `stat` + ~1 read | + 6 more reads |
| Bytes read / second | a few hundred, from page cache | the services' write rate |
| Memory | ~7 × 1000 parsed dicts ≈ single-digit MB | fixed — `maxlen` caps it |
| Cost to each observed service | one local `write()` per line | unchanged when monitoring is down |

That last row is the point of the pull model: services do not know the sweeper exists. The price
is **latency** — up to one scan interval (~500 ms average) before a line reaches the UI. inotify
would make that milliseconds; at 8 syscalls a second the poll is not worth a dependency to
remove.

Queries are linear on purpose. `snapshot()` copies the matching buffers under the lock (a shallow
pointer copy) and filters and sorts *outside* it, so a slow query never blocks ingestion — O(n)
over at most 7000 records, sub-millisecond. `since_id` cannot binary-search, because a deque has
O(n) random access; linear is the correct algorithm for the structure, not a shortcut. The one
real inefficiency is `services_meta()` recounting levels across every buffer on each request —
invisible at a 5-second poll, and the first thing to make incremental if the buffers grew
tenfold.

The design's boundary, which §12 declines to cross: buffers are per-process, so a second
monitoring replica would hold a disjoint view, and nothing survives a restart beyond the 64 KB
tail. That is where the answer becomes a real log store rather than a bigger deque.

## 7. Step 5 — two endpoints serve the buffers

**What was needed.** The UI needs both a snapshot ("what happened recently, filtered") and a
live tail ("what is happening now").

**What was chosen.** Copy, don't invent. `GET /logs` speaks the exact filter dialect `/audits`
already established — CSV lists, validated enums (a garbage level → 400), a clamped limit
(default 200, max 500) — plus `since_id` (the monotonic cursor) and `q` (case-insensitive
substring over `event`, `message`, and `correlation_id`). `GET /logs/stream` is a line-for-line
clone of the market-data SSE fan-out: per-client `queue.Queue(maxsize=500)`, `put_nowait`, drop
on full — a slow client loses lines, never stability.

**What was added.** `log_publisher.py` (the clone) and two routes in
`monitoring-service/app/api.py`. One design point worth noticing: the `/logs` response carries a
`meta.services` block — per service: buffered count, `last_at`, level counts, minute buckets —
so the service chips, sparklines, and pulse number all come from the same call that fetches
lines. No second "stats" endpoint. And one deliberate omission: the publisher does not log
drops — the sweeper reads monitoring's *own* file, and a publisher that logs while publishing is
a feedback loop waiting to happen.

## 8. Step 6 — the Logs view (and the showcase features)

**What was needed.** A `/logs` route that makes the pipeline visible: browse, filter, search,
and watch live — plus the demo-layer features that make logs a navigation surface instead of a
text dump.

**What was chosen.** Assemble from parts the app already had. The feed is the app's signature
*seed + stream* idiom (`useStreamSeed` + `useSseStream`), deduped by collector id — seed and
stream overlap by design, and the id makes the union exact. It is the first *per-view* stream in
the app (all others are app-root singletons) — acceptable because it is cheap and closes on
unmount. Rows reuse the `AuditEventList` `<details>` shape; chips reuse `FilterBar` /
`FilterChipGroup`; sparklines reuse `Sparkline`; the story panel reuses `SidePanel`.

**What was added.**

- `hooks/useLogsFeed.js` — seed + stream, capped at 500 newest-first, stream events batched
  through `useBufferedUpdates` (a DEBUG flood re-renders at the app's flush cadence, not per
  line). **Pause** diverts incoming lines to a pending buffer; the button becomes
  "Resume · N new" — standard live-tail ergonomics, no scroll-jumping.
- `domain/logLines.js` — the normalizer (mirror of `normalizeAuditEvents`), plus the minute-
  bucket → sparkline series math and the client-side filter (service, minimum level, text).
- `views/Logs/Logs.jsx` + `components/logs/LogLineList.jsx` — service chips with buffered
  counts and **F2** error-pulse sparklines (a `trailing` slot added to `FilterChipGroup`
  options); minimum-level chips (`WARNING+` isolates a failure cascade in one click); search;
  expandable rows showing the pretty-printed JSON payload.
- **F3 — entity links.** The normalizer recognizes `trade_id`, `book_id`, `symbol` in any line
  and renders them as links into Trades / Books / Market Data. Honest limitation: links land on
  the target *view*, not a specific row — the hash router has no query-param deep links, and
  building them was out of scope.
- **System Overview.** The placeholder panel became **Recent errors**: the last 10 WARNING+
  lines (polled, like the overview's other panels), the pulse number ("N warn+ · last 5 min")
  computed from the minute buckets, and a link to `/logs`. Browsing stays out of the overview.

## 9. Step 7 — the correlation story panel (F1)

**What was needed.** Steps 3–6 made "search by correlation id" possible; the story panel makes
it one click: follow a single intent through the system, across services *and* across both
trails.

**What was chosen.** A `SidePanel` fed by two requests — `GET /logs?q=<id>` (already specced)
and `GET /audits?correlation_id=<id>` (the one backend addition this feature needed: an equality
filter in the audits repository) — merged into one chronological timeline, each entry tagged
`log` or `audit` plus its service. Clicking a correlation id anywhere — a log line's expanded
row, an audit row on the Overview — opens it.

**What was added.** `components/logs/CorrelationStoryPanel.jsx`, the `correlation_id` filter in
`monitoring-service/app/repository.py` + `api.py`, and an optional `onCorrelationClick` prop on
`AuditEventList`. The verified result reads like distributed tracing built from parts the app
already had: `generated` (log) → `intent_dequeued` (log) → `TRADE_CREATED` (audit) →
`trade_created` (log), in order, with service tags.

## 10. Step 8 — audit-trail gaps closed on the way

Four small items that the logging work exposed, fixed in the same pack:

- **Dependency transitions.** Monitoring's health pollers now remember the previous up/down
  verdict per target and write `DEPENDENCY_DOWN` (ERROR) / `DEPENDENCY_RECOVERED` (INFO) audits
  only on the *crossing* — a state change is a business event; the 5-second poll result is not.
- **Worker failure state.** The trade-action worker audits `WORKER_FAILED` on the first failing
  intent and `WORKER_RECOVERED` on the next success — a two-state machine, not per-error spam.
- **Processing latency.** The worker times dequeue→commit per intent (last-50 window);
  `/queue/status` serves `avg_processing_ms` / `last_processing_ms`, and the Trade Actions
  view's AVG PROCESSING card finally shows numbers (~8 ms live) instead of n/a.
- **Fail-open audits.** Standalone `write_audit` (no session) now catches its own database
  failure and *logs* `audit_write_failed` instead of raising — the audit call must never take
  down the code path it observes. Session-bound audits stay strict on purpose: they are part of
  the caller's business transaction and must fail with it.

## 11. What the live verification proved

The phase plan shipped with a runbook; running it against the live stack proved each design
argument rather than asserting it:

- **Cold start** — seven `./logs/<service>.log` files, each starting with its `starting` line;
  every service chip present in the UI with no registration anywhere.
- **Steady state** — file growth per business event, not per tick (hygiene, §4).
- **Trade lifecycle** — one generated intent's id selected its full story across both trails in
  the story panel (§9).
- **Failure cascade** — stopping market-data: pricing `stream_failed` WARNINGs per ~5 s retry,
  exactly one `DEPENDENCY_DOWN` audit, rising pulse; restart → reconnect lines, `RECOVERED`,
  decay. This doubles as the README's demo script.
- **Database down** — the design's core argument, live: services kept running and kept logging
  to files; `audit_write_failed` ERROR lines captured precisely the writes Postgres could not
  record; `WORKER_FAILED` fired once and `WORKER_RECOVERED` on return; no service needed a
  restart.
- **Collector restart** — the Logs view re-seeded from file tails, not empty (§6).
- **Filters** — every `/logs` parameter behaved per spec, including the 400 on a garbage level.
- **Rotation and backpressure** — verified at the unit level (rotation with contiguous ids;
  drop-on-full queues are the same mechanism every other stream already uses).

## 12. Deliberately not built, and one trap worth remembering

Not built, on purpose: log persistence beyond the rotating files (no table, no search index),
external log stacks (ELK/Loki — over-scope; the dependency set is still structlog + stdlib),
runtime log-level switching from the UI (config is env-owned), hour-scale volume charts (the
buffer is minutes-deep; a chart would overstate what the system retains), and log-based alerting
(alerts belong to monitoring state). Each is one "known limitation" line in the README instead
of a half-feature.

The trap: both `.gitignore` files contained a bare `logs` pattern, which matches a directory
named `logs` *anywhere* — including the brand-new `frontend/src/components/logs/` and (macOS
being case-insensitive) `views/Logs/`. The new source files were silently invisible to git until
the pattern was scoped to the repo-root runtime directory (`/logs/`). If a new file ever fails
to show up in `git status`, `git check-ignore -v <path>` names the pattern responsible.

## 13. Map of the code

New files:

| File | Role |
| --- | --- |
| `services/monitoring-service/app/log_collector.py` | the sweeper: tail, parse, buffer, buckets (§6) |
| `services/monitoring-service/app/log_publisher.py` | SSE fan-out clone (§7) |
| `frontend/src/hooks/useLogsFeed.js` | seed + stream + pause (§8) |
| `frontend/src/domain/logLines.js` | normalizer, filters, sparkline series (§8) |
| `frontend/src/views/Logs/Logs.jsx` | the Logs view (§8) |
| `frontend/src/components/logs/LogLineList.jsx` | row list with JSON payload + links (§8) |
| `frontend/src/components/logs/CorrelationStoryPanel.jsx` | the F1 story panel (§9) |
| `frontend/src/config/logs.js`, `styles/components/_logs.scss` | constants and styles (§8) |

Changed, by step: `shared/logging_config.py` + every `main.py` + compose/env (§3); log
statements across all services (§4); `trade_processor.py` bind/unbind (§5); monitoring
`api.py`/`config.py`/`main.py` (§6–§7); `monitor.py` transitions, `action_queue.py` latency,
`shared/audit.py` fail-open (§10); routes/endpoints/`SystemOverview`/`TradeActions`/
`AuditEventList`/`FilterChipGroup` on the frontend (§8–§9).
