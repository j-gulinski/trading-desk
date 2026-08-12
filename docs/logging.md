# Logging — from a log statement to a live screen

Every service writes structured JSON logs. This document explains how those lines get collected,
served, and displayed, why the pipeline is shaped this way, and what it deliberately does not
promise.

The companion trail — the durable `audit_logs` table — is described in
[architecture.md §5](architecture.md). The two meet only through `correlation_id`, and §7 below
is the feature built on that.

## 1. The whole pipeline in six steps

The collector ("the sweeper") is the heart of it. In plain language:

```text
1. seed    — on boot, bookmark each log file near its end (last 64 KB, or all of it if smaller)
2. scan    — every second, list the *.log files and stat each one
3. rotate  — if a file's inode changed or it shrank below the bookmark, reset the bookmark to 0
4. read    — read the bytes after the bookmark, but keep only up to the LAST complete line
5. buffer  — stamp each line with an id and append it to that service's ring buffer
6. publish — push the same line to every connected SSE client
```

Four details in that list are the ones that actually matter, and each is a step below:

- the seed is **not** "end of file" — it deliberately replays the last 64 KB so a restart shows
  history instead of a blank screen (§5);
- rotation has **two** signatures, not one, and detecting it late loses lines (§5);
- "until the last full line" is what makes concurrent reading and writing safe with no lock
  between the writer and the reader (§5);
- buffering happens **before** publishing, which is why a client that reacts to a streamed line
  can always find it via the API (§5).

And around that core, three steps come before (getting the lines into files, keeping them worth
reading, tying them together) and three after (serving them, showing them, navigating them).

## 2. The shape decision — files and a sweeper

Before any code: *where do log lines go?* Three candidate designs, one chosen.

1. **A `logs` table in Postgres**, like `audit_logs`. Rejected for two reasons. **Volume:**
   technical logs are orders of magnitude chattier than business audits and would bloat the
   database for no query benefit. **Bootstrap:** a database-connection failure *cannot be logged
   to the database* — the moment you most need the record is the moment that design cannot
   produce it.
2. **Services push to monitoring** (`POST /logs`). Rejected because it inverts the dependency: a
   service must never block, fail, or slow down because the *observer* is down. Observability
   must cost the observed system nothing.
3. **Services write local files; monitoring tails them.** Chosen. Writing one line to a local
   file is the service's entire obligation — collecting, buffering, serving, and displaying are
   all the collector's problem. Files survive a monitoring restart. And it is the minimal honest
   version of how real log shipping works (Filebeat/Fluentd tailing files a process wrote
   locally), with the three concerns kept separate: **transport** (files), **aggregation**
   (sweeper), **storage policy** (bounded buffers).

Both rejections were later demonstrated live rather than argued (§10): with Postgres stopped,
the files kept collecting the very errors the database could not record.

## 3. Step 1 — every service writes its log to a file

**What was needed.** A file per service that a collector can read, without changing what the
logs look like or breaking `docker compose logs`.

**What was chosen.** Keep stdout exactly as it was and *additionally* append the identical JSON
lines to `/var/log/trading/<service>.log`, size-rotated, on a `./logs` bind mount shared by all
services. A bind mount (not a named volume) keeps the files browsable on the host. Rotation is
by size (`.log`, `.log.1`, …) rather than by date: every line already carries an ISO timestamp,
so dating lives *in the line*, and stdlib has no combined size+date handler anyway.

**What was added.** The one real obstacle lived in `shared/logging_config.py`. The original
config used `structlog.PrintLoggerFactory()`, which writes rendered lines straight to stdout and
bypasses Python's `logging` machinery entirely — you can attach any number of file handlers and
they will never see a line. The fix is a factory swap:

```python
logger_factory=structlog.stdlib.LoggerFactory(),   # was: structlog.PrintLoggerFactory()
```

structlog still does all the work it did before (merge context variables → add level → add ISO
timestamp → render JSON), then hands the finished line to a standard `logging.Logger`, and
stdlib fans it out to every configured handler: a `StreamHandler` (stdout, unchanged) and — only
when `LOG_DIR` is set — a `RotatingFileHandler`. The format string is `"%(message)s"`: the line
is already-rendered JSON, handlers only move bytes.

**Exceptions need one more processor.** `log.exception(...)` sets `exc_info=True`, but
`JSONRenderer` does not know how to render an exception tuple — it serialized the flag and
produced this:

```json
{"event": "process_failed", "exc_info": true, "level": "error"}
```

The traceback was gone: not in the file, not in stdout, nowhere. Adding
`structlog.processors.format_exc_info` before the renderer turns it into a real field:

```json
{"event": "process_failed", "exception": "Traceback (most recent call last):\n  ...\nZeroDivisionError: division by zero"}
```

The detail block in the Logs view renders that value with `white-space: pre-wrap`, so a
multi-line traceback reads as a traceback. The rule worth keeping: **a log line that says an
error happened without saying what it was is not a log line, it is a rumour.**

**Fail-open rule.** If `LOG_DIR` is set but unwritable, the service logs one
`log_file_sink_unavailable` warning and continues stdout-only. Logging must never take a service
down.

Config, in the established env pattern: `LOG_DIR=/var/log/trading`,
`LOG_FILE_MAX_BYTES=5000000`, `LOG_FILE_BACKUP_COUNT=3`.

## 4. Step 2 — keep the files worth reading, and the ids findable

**What was needed.** Market data ticks continuously and pricing revalues on every tick. One
careless `log.info` on a per-tick path and the files grow by megabytes per minute — unreadable,
and rotation would eat the history in minutes. Meanwhile the *interesting* moments (a trade
created, a rejection and its reason) were barely logged at all.

**What was chosen** — an editorial policy, applied as a pass over every existing statement:

- **Per-tick events log at DEBUG** — `tick_generated`, `valuation_computed`. They still exist:
  flip one service to `LOG_LEVEL=DEBUG` and only that service's file floods. Compose keeps
  `LOG_LEVEL=INFO`.
- **Business moments log at INFO, one line each.** The trade lifecycle now narrates itself
  across services: `generated` → `intent_dequeued` → `trade_created` →
  `trade_entered_active_set` → … → `trade_closed` → `trade_finalized` with realized PnL.
- **Failures log at WARNING/ERROR with the precise reason** — `open_rejected` carries the
  validation message; `stream_failed`, `dependency_down`, `audit_write_failed` carry theirs.
- **Entity ids are always kwargs, never baked into the message string** — `trade_id=…`,
  `book_id=…`, `symbol=…`, `correlation_id=…`. Structured keys are what search and the story
  panels key on (§7); a message string is where ids go to be unfindable.

Measured result in steady state: market-data wrote **4 lines in ten minutes** of continuous
ticking.

## 5. Step 3 — one id ties an action's lines together

**What was needed.** "Show me everything about *this* trade action", across four services and
both trails. Audit rows already carried `correlation_id` (the intent's `client_request_id`); log
lines did not.

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
`gen-open-<uuid>` / `gen-close-<uuid>`, the New Trade ticket sends a `manual-open-<uuid>`, a
book move sends `manual-move-<uuid>` — and everything downstream just carries it. Pricing does
not bind (it has no intent in scope); its per-trade lines carry `trade_id` as a kwarg instead,
which is enough to join the story a different way (§7).

One fix the verification pass caught: trade-generation logged the id under a kwarg named `crid`
— a name nothing searches for. Renaming it to `correlation_id` made the intent's own birth line
join its story. That is the hygiene rule of §4 enforcing itself.

## 6. Step 4 — the sweeper collects the files

**What was needed.** One place that reads all the files continuously and can answer "the last N
lines, filtered" without anyone grepping containers.

**What was chosen** — a single daemon thread in monitoring-service that *tails* the files:

| Decision | Alternative rejected | Why |
| --- | --- | --- |
| Lives in monitoring-service | A separate shipper container (Filebeat/Fluentd) | Monitoring is already the observer and the proxy already routes `/api/monitoring` — zero new containers, zero routing |
| A plain thread | asyncio | The work is blocking local-file `stat`/`read`; there is no real async file I/O to await, so async would put a scheduler in front of the same blocking calls |
| One `deque(maxlen=10_000)` **per service** | One shared buffer for all services | The fairness bound: a service flipped to DEBUG floods only its own slots and cannot evict anyone else's history |
| Memory only | A `logs` table | The storage policy is "a bounded recent window", which is exactly what `maxlen` is — O(1) eviction, no cleanup job (§2) |

### The concepts it rests on

The module is short but leans on a handful of ideas worth naming before reading it:

| Concept | What it means | Why it appears here |
| --- | --- | --- |
| **Tailing** | Repeatedly reading only the bytes appended since last time (what `tail -f` does) | The whole job: re-reading each file from the top every second would not scale |
| **Offset** | How many bytes of a file have already been consumed — a resume point | The read position for the next scan, stored per file |
| **inode** | The filesystem's id for a file; the *name* is just a pointer to it. Renaming keeps the inode, recreating makes a new one | The only reliable way to notice that `x.log` is now a *different* file |
| **Rotation** | At the size cap, `RotatingFileHandler` renames `x.log` → `x.log.1` and creates a fresh empty `x.log` | Undetected, the sweeper would sit at a stale offset past the end of a new, tiny file and read nothing forever |
| **Partial line** | The writer may be halfway through appending when the sweeper reads | Consuming half a line corrupts it; the fix is to stop at the last `\n` |
| **Binary mode** | Reading raw bytes rather than decoded text | Offsets are byte counts; text mode's decoding and newline translation would desynchronize the cursor |
| **`deque(maxlen=N)`** | A fixed-size ring buffer: appending to a full one drops the oldest, in O(1) | Bounded memory with no eviction logic to write |
| **Daemon thread** | A background thread that does not keep the process alive | The sweeper should die with monitoring, not block its shutdown |
| **Lock** | A mutex making a block run one-thread-at-a-time | Request threads read the buffers while the sweeper writes them |
| **Monotonic id** | A counter that only ever increases | One number used as React key, dedup key, and `since_id` cursor |
| **Page cache** | The OS keeps recently written file data in RAM | The sweeper reads bytes written milliseconds ago, so reads hit memory, not disk |

### The state it keeps

Five module-level objects in `log_collector.py`, four of them guarded by one lock:

| State | Shape | Holds |
| --- | --- | --- |
| `_buffers` | service → `deque(maxlen=10_000)` | the log lines |
| `_tails` | file path → `{inode, offset}` | where to resume reading — the bookmark |
| `_minutes` | service → `deque(maxlen=15)` | per-minute counts by level |
| `_ids` | `itertools.count(seed)` | the monotonic id source |
| `RUN_ID` | a random hex string | identifies this collector process (§5.4) |

### Step 1 — seed (what "0 if empty" really is)

At boot, `_collector_loop` runs one scan with `seed=True`. Every file is new to `_tails`, so
each gets a warm-start bookmark from `_seed_offset`:

- file **≤ 64 KB** (`LOG_WARM_START_TAIL_BYTES`) → offset `0`, the whole file;
- file **larger** → `size − 64_000`, then moved forward past the next `\n` so the first line
  read is whole;
- a 64 KB window containing *no* newline at all → jump to EOF and wait for a real line, rather
  than guessing where one starts.

So the seed is "the last 64 KB", not "the end of file", and offset 0 happens for *small* files,
not empty ones. That is deliberate: a monitoring restart shows history immediately instead of a
blank screen (verified: 294 lines on a restart).

Two consequences worth knowing:

- **Warm-started lines are history, not pulse.** The seeding scan also counted those lines into
  the per-minute buckets, which would draw a fake spike on every sparkline. `_collector_loop`
  therefore clears `_minutes` right after the seed pass — cheaper than threading a "don't count
  this one" flag through every layer.
- **A file discovered *later* is read in full.** The `seed=True` flag applies only to the first
  pass, so a service that starts after the collector gets offset `0` and its whole file.

### Step 2 — scan

Every `LOG_SCAN_INTERVAL_SECONDS` (1.0), list `LOG_DIR/*.log` and `_scan_file` each one.
Discovery *is* the filesystem: service name = filename stem, no registry anywhere. A future
service appears in the Logs view by merely writing `/var/log/trading/<name>.log`.

Per file, the first move is one `stat()` — one syscall returning size and inode together — and
then an early out: `st_size <= offset` means nothing was appended, so return without opening the
file. That is the common case for most files most seconds, and it is why a scan costs one
`stat()` per file and nothing more.

### Step 3 — rotation ("swap files if there is new")

Two tests, because there are two ways a file can be replaced:

| Case | Test | Bookmark set to |
| --- | --- | --- |
| First sight, at boot | not in `_tails`, `seed=True` | `_seed_offset(…)` — near the end |
| First sight, at runtime | not in `_tails`, `seed=False` | `0` — read it all |
| Rotated | `st_ino` changed | `0` — same name, different file |
| Truncated | `st_size < offset` | `0` — same file, emptied |
| Normal | neither fires | unchanged — resume where the last scan stopped |

`RotatingFileHandler` renames and recreates, so the inode changes; other tools truncate in
place, so the size collapses. Either way the old position is meaningless.

**The honest gap:** nothing ever reads the tail of the file that rotated away. Lines written
between the last scan and the rotation are lost. At a 1 s scan interval and a 5 MB rotation
threshold this is rare, and the fix (following `.log.1` after a rotation) costs more complexity
than the loss justifies — but it is a real hole, not an absent one.

### Step 4 — read "until the last full line"

Open `"rb"`, `seek(offset)`, read to EOF. Then:

```python
end = data.rfind(b"\n")     # the LAST newline in what we just read
if end < 0:
    return                  # no complete line yet — bookmark untouched
tail["offset"] += end + 1   # advance only past that newline
for raw in data[:end].split(b"\n"):
    ...
```

A half-written trailing line stays unread until the next scan, by which time the writer has
finished it.

**Failure is contained at three widths, because a collector that dies on bad input is worse than
no collector.** One bad *byte* is absorbed by decoding with `errors="replace"`; one bad *line*
that is not JSON becomes `{"event": raw_line}` rather than an exception (§5); and one bad *file*
is skipped by the scan loop — an `OSError` (the file rotated away between the `glob` and the
`open`) is retried on the next pass, any other per-file error is logged with its filename, and
**either way the remaining six services still scan.** The blast radius of a problem is one file
for one second.

**This step is the entire concurrency story.** The reader never consumes past the last newline
it can see, so appending and tailing need no lock, no signal, and nothing the observed service
has to do or even know about. The invariant: **the bookmark only ever advances past bytes
already ingested as complete lines.** Every early return leaves it untouched, so the worst case
is re-reading the same bytes next second — never skipping a line, never duplicating one.

### Step 5 — buffer, then publish

Per line, `_ingest` in order: parse JSON with a `{"event": raw_line}` fallback → normalize the
level to a known name → copy the dict and stamp `level`/`service` → **under the lock**, take the
next id, append to the service's buffer, bump the minute bucket → **outside the lock**, publish
to SSE clients.

Two orderings in that sentence are load-bearing:

- **Buffer before publish.** A client that receives a streamed line and immediately queries
  `/logs` will always find it. The reverse order would produce a line that exists on the wire
  but not yet in the API.
- **Publish outside the lock.** The fan-out walks every connected client's queue; doing that
  while holding the collector lock would let one slow reader stall ingestion for everyone.

**Minute buckets are sparse.** A bucket is appended only when a line arrives, so a quiet
service's 15 buckets can span an hour. That is safe because the consumer densifies them —
`minuteSeriesOf` re-projects them onto a wall-clock timeline and zero-fills the silent minutes.

### Step 6 — ids that survive a restart

The id serves three roles at once: React key, dedup key when the seed and the stream overlap,
and the `since_id` cursor. All three break if ids restart.

The first implementation was `itertools.count(1)`. Everything inside the process was consistent
— buffers reset together with the counter — but state held *outside* the process was not:

- a browser tab open across a monitoring restart still held lines with pre-restart ids. New
  lines arrived numbered from 1, sorted *below* the retained ones, and fell off the end of the
  client's cap: the tail looked frozen until the counter climbed past the old maximum. If the
  previous process had been short-lived, low ids **collided** instead and silently replaced
  unrelated rows;
- a client polling with `since_id=8000` got an empty result forever, because every new id was
  smaller.

Two changes fix it, one cheap and one explicit:

```python
RUN_ID = uuid.uuid4().hex[:12]
_ids = itertools.count(int(time.time() * 1_000_000))
```

1. **Clock-seeded ids.** Ids keep rising across restarts, so client-side merging and `since_id`
   both keep working with no protocol at all. (The assumption: never more than one line per
   microsecond of uptime — several orders of magnitude away here.) They stay plain integers,
   well inside JavaScript's exact-integer range.
2. **A run id.** `GET /logs` returns it in `meta.run_id`, and `/logs/stream` sends it as its
   first event. When the browser sees a run id it has not seen before, it drops its buffer and
   re-seeds — a restart is observable rather than inferred. If a client sends `since_id` with a
   stale `run_id`, the server ignores the cursor and serves a full snapshot.

Verified across two restarts: run id changed, ids kept rising, a stale cursor still returned
lines, and a stale `run_id` made the server ignore an absurdly high cursor.

### Step 7 — what it costs

| | Steady state | Bound |
| --- | --- | --- |
| Syscalls / second | 1 readdir + 7 `stat` + ~1 read | + 6 more reads |
| Bytes read / second | a few hundred, from page cache | the services' write rate |
| Memory | 7 × 10,000 parsed dicts ≈ tens of MB | fixed — `maxlen` caps it |
| Cost to each observed service | one local `write()` per line | unchanged when monitoring is down |

That last row is the point of the pull model: services do not know the sweeper exists. The price
is **latency** — up to one scan interval (~500 ms average) before a line reaches the UI. inotify
would make that milliseconds; at 8 syscalls a second the poll is not worth a dependency to
remove.

**Queries stay cheap by exiting early.** `snapshot()` copies the matching buffers under the lock
(a shallow pointer copy) and filters *outside* it, so a slow query never blocks ingestion. It
walks each buffer **newest-first** and abandons it as soon as `limit` matches are collected —
which is correct because the newest `limit` lines overall are always a subset of the newest
`limit` lines per service. The `since_id` filter can `break` rather than `continue` for the same
reason: ids ascend within a buffer, so the first line at or below the cursor means every
remaining one is older.

Measured with all seven buffers full (70,000 records):

| Query | Time |
| --- | --- |
| meta poll (`limit=1`) | 0.7 ms |
| seed (`limit=2000`) | 1.8 ms |
| search matching a trade id | 1.2 ms |
| search matching nothing (full scan — worst case) | 18.6 ms |

Without the early exit, even `limit=1` sorted all 70,000 records on every poll.

**The one inefficiency left, and the condition that would make it matter.** The `meta` block is
not incremental: `services_meta()` recounts levels by walking every record in every buffer, under
the lock, on each request. At a 5-second poll it is invisible, and it was written when the buffers
held 1,000 lines each. They now hold 10,000 — the tenfold growth that was the stated trigger for
making it incremental — so it is the first thing to change if the meta poll ever shows up in a
profile. Kept as-is deliberately: it is a known cost with a known fix, not an unexamined one.

**The design's boundary,** which §12 declines to cross: buffers are per-process, so a second
monitoring replica would hold a disjoint view, and nothing survives a restart beyond the 64 KB
tail. Past that, the answer is a real log store rather than a bigger deque.

**One caveat to know:** ids order lines by when the *sweeper* saw them, and each scan walks
files in alphabetical order. So within any one-second window, all of blotter's new lines get
lower ids than books', regardless of their own timestamps — and the UI sorts by id. That is why
the live tail can show `20:20:37.767 TRADE GENERATION` above `20:20:38.087 PRICING`. Sorting
each scan pass's lines by timestamp before assigning ids would fix it and keep ids monotonic;
it has not been done.

## 7. Step 5 — two endpoints serve the buffers

**What was needed.** The UI needs both a snapshot ("what happened recently, filtered") and a
live tail ("what is happening now").

**What was chosen.** Copy, don't invent. `GET /logs` speaks the exact filter dialect `/audits`
already established — CSV lists, validated enums (a garbage level → 400), a clamped limit — plus
`since_id` (the cursor), `run_id` (the staleness guard), and `q`, a case-insensitive substring
match over `event`, `message`, `msg`, `correlation_id`, `trade_id`, `book_id`, and `symbol`.
`GET /logs/stream` is a line-for-line clone of the market-data SSE fan-out: per-client
`queue.Queue(maxsize=500)`, `put_nowait`, drop on full — a slow client loses lines, never
stability.

The response carries a `meta` block — `run_id` plus, per service, buffered count, `last_at`,
level counts, and minute buckets — so the service chips, sparklines, and the pulse number all
come from the same call that fetches lines. No second "stats" endpoint.

One deliberate omission: the publisher does not log its drops. The sweeper reads monitoring's
*own* file, and a publisher that logs while publishing is a feedback loop waiting to happen.

## 8. Step 6 — the Logs view

**What was chosen.** Assemble from parts the app already had. The feed is the app's signature
*seed + stream* idiom (`useStreamSeed` + `useSseStream`, see
[frontend/README.md](frontend/README.md)), deduped by collector id — seed and stream overlap by design,
and the id makes the union exact. It is the first *per-view* stream in the app (all others are
app-root singletons), acceptable because it is cheap and closes on unmount.

What the view does:

- **Service chips** with buffered counts and per-minute error-pulse sparklines; **minimum-level
  chips** (`WARNING+` isolates a failure cascade in one click); **search** across every field.
- **Pause** diverts incoming lines to a pending buffer and the button becomes "Resume · N new" —
  standard live-tail ergonomics, no scroll-jumping.
- **Timestamps carry the day** (`08-12 20:08:52.925`). The buffer holds hours of history and
  warm-starts across restarts, so a bare clock time silently invites reading yesterday's
  shutdown cascade as if it were happening now.
- **Expanded rows show a key/value detail block**, not a raw JSON dump: fields already in the
  row header (`event`, `level`, `service`, `id`, `timestamp`) are filtered out, so a
  `trade_closed` line expands to the three fields that actually differ. A line with nothing left
  to show renders no expander at all.
- **`trade_id` and `correlation_id` are buttons** inside that block, each opening the matching
  story panel (§9).

**Three caps, three different jobs** — worth keeping straight, because they are easy to confuse:

| Cap | Value | What it protects |
| --- | --- | --- |
| `LOG_BUFFER_LINES` (server) | 10,000 / service | collector memory |
| `LOG_FEED_CAP` (client) | 10,000 | what the browser holds and can filter/search locally |
| `LOG_RENDER_LIMIT` (client) | 500 | how many rows reach the DOM |

The render limit is the important one: filters and search run over all 10,000 lines, but only
the newest 500 matches are rendered, because re-reconciling 10,000 `<li>` elements on every
stream flush stutters. The panel says so out loud — `newest 500 of 1,021 matching · 1,021
buffered` — rather than quietly truncating.

**System Overview** carries the summary view: the last 10 WARNING+ lines, the pulse number
("N warn+ · last 5 min") computed from the minute buckets, and a link to `/logs`. Browsing stays
out of the overview.

## 9. Step 7 — the story panels: two ways to ask a question

Steps 3–6 made search possible; the story panel makes it one click. It merges two sources into
one chronological timeline, each entry tagged `log` or `audit` plus its service:

```text
GET /logs?q=<id>            the sweeper's buffers   (technical trail)
GET /audits?<key>=<id>      Postgres                (business trail)
```

The panel has two modes, and understanding **why both exist** is the interesting part.

| | correlation story | trade story |
| --- | --- | --- |
| Keys on | `correlation_id` = the intent's `client_request_id` | `trade_id` |
| Answers | "what happened to this **request**?" | "what happened to this **thing**?" |
| Audit query | `correlation_id=` | `entity_id=` |
| Scope | one intent, end to end | the entity's whole life, across intents and services |

**Neither is a superset of the other.** Where `trade_id` cannot reach:

- **Book-level actions.** A rejected `REASSIGN_TRADES` writes `ACTION_REJECTED` with
  `entity_type=BOOK` — no trade exists anywhere in that story.
- **Lines with no entity.** `intent_dequeued` for a reassign, `close_all_processed`,
  `trades_reassigned`, `WORKER_FAILED`/`WORKER_RECOVERED` — all stamped with the correlation id
  by the contextvar, none carrying a trade.
- Measured on 400 recent audit rows: **311 had no `entity_id` at all.**

Where `correlation_id` cannot reach:

- **pricing-service.** `trade_entered_active_set` and `trade_finalized` carry no correlation id
   — pricing works from the database and never sees the request. They appear only in the trade
  story.
- **Anything spanning two intents.** The open is `gen-open-…`, the close is `gen-close-…`: one
  trade, two correlation ids. Only the trade story shows open→close as one thing.
- Of those same 400 rows, **323 had no `correlation_id`.**

So the trade story is the better demo — a real one spans three services and both trails:

```text
20:08:52.902  LOG   TRADE ACTION      intent_dequeued
20:08:52.904  LOG   TRADE GENERATION  generated
20:08:52.920  AUDIT TRADE ACTION      TRADE_CREATED — Trade created
20:08:52.925  LOG   TRADE ACTION      trade_created
20:08:53.879  LOG   PRICING           trade_entered_active_set
20:08:57.744  LOG   TRADE ACTION      intent_dequeued
20:08:57.756  AUDIT TRADE ACTION      TRADE_CLOSED — Trade closed
20:08:57.758  LOG   TRADE ACTION      trade_closed
20:08:57.900  LOG   PRICING           trade_finalized
```

— while the correlation story is the one that still works when the trade was never created. The
panels cross-link: an id inside an open story opens that story instead, so you can land on a
trade and drill into the single intent that failed. The id currently being viewed renders as
plain text rather than a dead link.

**One known gap:** `_close_all` writes its `TRADE_CLOSED` audit rows without a `correlation_id`,
so a CLOSE_ALL correlation story shows log lines and no audit rows.

## 10. Step 8 — audit-trail gaps closed on the way

Four items the logging work exposed:

- **Dependency transitions.** Monitoring's health pollers remember the previous up/down verdict
  per target and write `DEPENDENCY_DOWN` (ERROR) / `DEPENDENCY_RECOVERED` (INFO) audits only on
  the *crossing* — a state change is a business event; a 5-second poll result is not.
- **Worker failure state.** The trade-action worker audits `WORKER_FAILED` on the first failing
  intent and `WORKER_RECOVERED` on the next success — a two-state machine, not per-error spam.
- **Processing latency.** The worker times dequeue→commit per intent (last-50 window);
  `/queue/status` serves `avg_processing_ms`, so the Trade Actions view shows real numbers
  (~8 ms) instead of `n/a`.
- **Fail-open audits.** A standalone `write_audit` (no session) catches its own database failure
  and *logs* `audit_write_failed` instead of raising — the audit call must never take down the
  code path it observes. Session-bound audits stay strict on purpose: they are part of the
  caller's business transaction and must fail with it.

## 11. What the live verification proved

One criterion decided whether this feature was done: **every scenario had to be observable without
reading any service's stdout** — the files, the endpoints, and the Logs view alone had to tell the
whole story. An observability feature that still needs `docker compose logs` to explain itself has
not replaced anything.

Running the runbook against the live stack proved each design argument rather than asserting it:

- **Cold start** — seven `./logs/<service>.log` files, each starting with its `starting` line;
  every service chip present in the UI with no registration anywhere.
- **Steady state** — file growth per business event, not per tick (§4).
- **Trade lifecycle** — one generated intent's id selected its full story across both trails.
- **Failure cascade** — stopping market-data: pricing `stream_failed` WARNINGs per ~5 s retry,
  exactly one `DEPENDENCY_DOWN` audit, rising pulse; restart → reconnect lines, `RECOVERED`,
  decay. This doubles as the README's demo script.
- **Database down** — the design's core argument, live: services kept running and kept logging
  to files; `audit_write_failed` ERROR lines captured precisely the writes Postgres could not
  record; `WORKER_FAILED` fired once and `WORKER_RECOVERED` on return; no service needed a
  restart.
- **Collector restart** — the Logs view re-seeded from file tails, not empty.
- **Filters** — every `/logs` parameter behaved per spec, including the 400 on a garbage level.

A worked example of reading the result: an error burst dated `2026-08-11T21:52–21:54Z` showed
DNS failures across services, then `OperationalError` everywhere, then `process_failed` on every
intent and `audit_write_failed` in three services. That is not a bug — it is the signature of the
stack being shut down, read backwards from the files the next morning. Which is exactly the
point of having them.

## 12. Deliberately not built

Log persistence beyond the rotating files (no table, no search index), external log stacks
(ELK/Loki — over-scope; the dependency set is still structlog + stdlib), runtime log-level
switching from the UI (config is env-owned), hour-scale volume charts (the buffer is a bounded
window; a chart would overstate what the system retains), and log-based alerting (alerts belong
to monitoring state). Each is one "known limitation" line rather than a half-feature.

**A trap worth remembering.** Both `.gitignore` files contained a bare `logs` pattern, which
matches a directory named `logs` *anywhere* — including the new `frontend/src/components/logs/`
and, macOS being case-insensitive, `views/Logs/`. Those source files were silently invisible to
git until the pattern was scoped to the runtime directory (`/logs/`). If a new file ever fails
to appear in `git status`, `git check-ignore -v <path>` names the pattern responsible.

## 13. Map of the code

| File | Role |
| --- | --- |
| `shared/logging_config.py` | structlog config: stdlib factory, file handler, `format_exc_info` (§3) |
| `services/monitoring-service/app/log_collector.py` | the sweeper: seed, scan, tail, buffer, buckets (§6) |
| `services/monitoring-service/app/log_publisher.py` | SSE fan-out (§7) |
| `services/monitoring-service/app/api.py` | `GET /logs`, `GET /logs/stream`, `/audits` filters (§7, §9) |
| `services/trade-action-service/app/trade_processor.py` | correlation-id bind/unbind (§5) |
| `frontend/src/hooks/useLogsFeed.js` | seed + stream, pause, run-id reset (§8) |
| `frontend/src/domain/logLines.js` | normalizer, filters, sparkline series, payload filtering (§8) |
| `frontend/src/views/Logs/Logs.jsx` | the view, filters, render cap (§8) |
| `frontend/src/components/logs/` | `LogLineList`, `LogPayload`, `StoryPanel` (§8, §9) |
| `frontend/src/config/logs.js` | the three caps and poll cadences (§8) |
