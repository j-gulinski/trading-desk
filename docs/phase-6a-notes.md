---
phase: 6a
status: complete
reviewed: 2026-07-30
revised: 2026-08-03
tags:
  - frontend
  - generator
  - trade-action
  - monitoring
  - audits
  - observability
---

# Phase 6a — Generator & Trade Actions (teaching notes)

Two read-only screens built on data that already existed, plus the three small backend additions
needed to make them honest. This is the "how we got there" version: decisions, the deviations from
the approved plan, and the exact path a config change and an audit row take. The 2026-08-03
revision pass is folded in below — its decisions extend the list, its deletions sit with the
deviations that caused them, and its measurements sit in the verification section.

## Phase outcome in one line

Phase 6a turns the two remaining SYSTEM placeholders into working screens without inventing a new
feed: **the generator becomes controllable at runtime**, and **both event feeds read from the audit
trail that already records every action**.

## Why Phase 6 was split

Phase 6 as planned bundled Books CRUD, Generator, Trade Actions, New Trade, states polish and config
persistence — roughly four screens. Phases 4 and 5 had each grown three revision passes past their
one-line goal, and in both cases the extra passes edited an earlier phase's screens, pulled a slice
of a later phase forward, and changed a backend service. Splitting into 6a / 6b / 6c puts a review
gate between those, so each phase's scope stays legible.

- **6a (this phase)** — read-only screens over existing data.
- **6b** — Books CRUD + New Trade: the first real write forms.
- **6c** — UI states sweep, global streams badge, config persistence, doc fixes.

## What was decided and why

Decisions 1–5 are from the build; 6–12 came out of the review pass, which looked for machinery
that had outlived the decision that created it. They are one list because they are one phase's
story — a decision made while re-reading the code is still a decision.

### 1) The feeds read audits, not new per-service endpoints

The mockups show a `LIVE INTENT FEED` on Generator and an `ACTION FEED` on Trade Actions. Neither
service exposes an events endpoint, so the options were a per-service in-memory ring buffer or the
existing audit trail.

Audits won because the data is already there: `trade-action-service` writes `TRADE_CREATED`,
`TRADE_CLOSED` and `ACTION_REJECTED` with `entity_id` (the trade) and `correlation_id` (the
`client_request_id`). `GET /audits` already existed on monitoring with a `/api/monitoring` proxy from
Phase 2. The cost is a per-row latency column the audit trail cannot answer — recorded as an honest
gap rather than estimated.

This is the audit experiment's **"Slice 2"**, listed in `frontend-plan.md` since Phase 2 and unticked
until now.

### 2) The generator's own audits are not the intent feed

A false start worth recording. The obvious filter for a *generator* screen is
`service=trade-generation-service` — but the generator writes no per-intent audit at all. Its
`generate_once()` only logs to stdout; the audit rows for created and closed trades are written by
**trade-action-service**, downstream.

So the Generator feed filters `service=trade-action-service` and then narrows to generated intents
client-side, using the `gen-` prefix the generator puts on every `client_request_id`
(`gen-open-{uuid}` / `gen-close-{uuid}`). Trade Actions shows the same rows unfiltered, so manual
closes from Phase 5 appear there too — labelled `MANUAL` against the generator's `GENERATED`.

One filter, two screens, no new event catalogue.

### 3) Runtime config replaces two import-time constants

The mockup's `FREQUENCY` and `MAX ACTIVE POSITIONS` sliders were dead on arrival: both values were
read once at import from `.env`, and Phase 4 had already replaced the mockup's fixed
`TRADE-OUT PROBABILITY 30%` with a derived policy.

Rather than render three read-only values, the two that shape the book became mutable module state
behind the generator's existing `_lock`, with `POST /config` to set them and `status()` echoing the
effective values. Close probability stays derived and read-only, displayed with its formula so the
screen explains itself:

```text
p_close = min(0.9, 0.5 × open / target)
```

**The consequence to remember:** `TARGET_OPEN_TRADES=300` in `.env` is now a *startup default*, not
the guaranteed live value. Phase 4's performance measurements were taken at 300, so the screen always
shows the effective config read back from the service, never the env value.

`run_loop()` also had to change. It computed its sleep interval once before the loop, so a config
change would never have taken effect; it now reads the interval each iteration.

### 4) Queue depth is not an observability signal

`queue/status` reports `queued` from `queue.Queue.qsize()`, and the worker pulls from that queue in a
tight loop. In practice, most samples are `0`; a "headline zero" card looked wrong fast enough that
it was removed from the screen.

The cumulative counters carry the activity signal instead: `processed` on the ACCEPTED card and
the opened/closed split on WRITTEN only grow, so sustained activity is visible even when queue
depth reads zero. (A derived per-minute throughput tile existed between the build and the final
revision — decision 6 records why it went.)

### 5) Counts are labelled by the population they come from

The feed is bounded by **row count**, not by time — old rows are fine and are what make the screen
readable when nothing recent has happened. That makes a `REJECTED · LAST 5 MIN` tile a lie waiting to
happen: over a count-limited window it would understate whenever five minutes are busier than the
limit.

The tile is `REJECTED · IN FEED`, with `of 50 shown · N this process` beneath it — a count over the
rows on screen, plus the cumulative number from `queue/status` which *is* process-wide. This is the
same rule Phase 5 arrived at when it replaced the `250+` closed label.

### 6) The rate tiles went from two mechanisms to one to none

The RATE tile first derived intents/min from the count-limited audit feed and needed a `≥`
saturation marker to stay honest whenever 40 rows covered less than a minute. The review pass
consolidated it onto `useCounterRate` (built for Trade Actions' throughput), which samples the
generator's monotonic `opened`/`closed` counters with no window cap to compensate for. The final
revision then removed the mechanism entirely — the RATE and THROUGHPUT tiles and the hook.

Per-minute velocity was instrumentation without an operational consumer: the cumulative counters
and the live intent feed already show whether the system is moving, while the rate cost a hook
with sampling windows, restart detection and a two-poll warm-up state. And the generator it
instrumented is slated for replacement by real-data strategies in homework 5 — its velocity is a
property of the simulator, not of the system being graded.

**Rules:** a count-limited feed is never a rate source — if a rate is ever needed, derive it from
cumulative counters. And don't polish instrumentation on machinery scheduled for removal.

### 7) Writes reconcile by refetching, not by optimistic state

`POST /start`, `/stop` and `/config` all return authoritative state, but the screen discarded it
and waited up to 2 s for the next poll — a gap bridged by ~40 lines of compensation: the
`runningOverride` state with its reset effect, and a draft-reconcile effect diffing draft against
server on every poll. `usePolling` gained `refetch()`, one out-of-cycle poll run immediately after
a successful write; `commitConfig` awaits it, then prunes only the draft entries that still equal
what was committed. The override and both effects are deleted; behavior is the same, just faster
and with less to explain.

**Rule 6b inherits:** write forms reconcile by refetching server truth, not by optimistic client
state. This stack answers in milliseconds; guessing buys nothing and costs a rollback path.

### 8) `set_config` validates both fields, then applies

It used to clamp-and-write one field at a time, so `{"interval_ms": 5000,
"target_open_trades": "abc"}` applied the interval and *then* raised — a 400 response hiding a
half-applied change, with no audit row and no loop wake-up. Both fields are now converted and
clamped before either is written under the lock: an invalid request applies nothing.

### 9) One sync path for open-trade tracking

`seed_open_trades` (startup, merge via `setdefault`) and `_sync_open_trades_from_blotter` (every
10 s, wholesale replace) were the same job written twice. Both are now one `sync_open_trades()`:
fetch active trades from the blotter, catalog-filter, replace the map. `main.py` retries it at
startup; the loop calls it when due. Replacement is idempotent, which is precisely why seeding and
steady-state sync can be the same function.

### 10) Bounds are one range, clamped at the boundaries

Frontend `TARGET_BOUNDS.max` said 5000, the backend said 10000, and this document said both at
different points. Now `[1, 10000]` on both sides (the backend floor rose from 0 to 1 to match
the UI and to kill a divide-by-zero in the p_close formula at the source), and env values are
clamped once at import through the same `_clamp_*` helpers `set_config` uses. The defensive
re-clamp inside `_interval_seconds()` is gone — invalid values can no longer enter, so they need
not be re-checked on the way out.

### 11) Reverted: `FLUSH_INTERVAL_MS` stays 500

An uncommitted working-tree edit had moved the shared UI scheduler from 500 ms to 1000 ms,
contradicting the Phase 4 contract ("one 500 ms scheduler; two flush opportunities per freshness
tick") with no recorded decision. Reverted. If 1000 ms is wanted, that is a real decision with a
measurement behind it, and it belongs in a phase note first.

### 12) Dead-export sweep joins the verification step

Build and lint pass on unused exports, so every mid-build reversal in this phase left the losing
option's code behind and nothing ever flagged it. `npm run deadcode` (knip, zero config) joins
lint and build in the workflow checklist — it catches exactly that class of leftover mechanically.
Its first run also flagged, and this phase deliberately left alone: `positionsOf` (written and
tested for 6b Books), `apiPut` / `apiDelete` (6b CRUD verbs), `ApiError` and a handful of
internal-only exports from Phases 3–5 (`mergeInstrument`, `compareValues`, `tradeOf`,
`valuationHistoryOf`, `mergeValuation`, `styles/global.scss`) — to be reviewed against real usage
in 6b/6c rather than deleted blind.

## What changed during the build (deviations from the approved plan)

Five, all found by running the thing.

1. **Asset classes came from the wrong source.** The plan said to derive the instrument list from the
   live market feed rather than duplicating `shared/catalog.py`. On screen that produced
   `COMMODITY EQUITY FUTURES FX INDEX` — wrong in both directions. `INDEX` is `MARKET_INDEX`, a
   benchmark that is never traded; `BOND` was missing because bonds are priced off the curve and never
   ticked. The books are the authoritative answer — the generator opens into one book per asset class
   — so the source is now `/books/summary`, which returns exactly
   `BOND COMMODITY EQUITY FUTURES FX`. The screen also stopped consuming the market feed entirely, so
   it no longer re-renders on every tick.

2. **`endpoints.blotter.booksSummary` had been deleted.** Phase 5's final shape consolidated Trades
   onto a single `/trades/overview` aggregate and dropped the `booksSummary` entry from the registry.
   The backend route was never removed. It is re-added here rather than reusing `/trades/overview`,
   which would pull ~140 trades to read five book names.

3. **The rejected tile was relabelled** — see decision 5.

4. **The queue-depth card did not survive contact with the data** — see decision 4. The plan
   assumed queue depth would carry the screen; the built replacement (a derived throughput rate
   via `useCounterRate`) was itself removed in the final revision (decision 6), leaving
   cumulative counters as the activity signal.

5. **Open-trade tracking now re-synchronizes against blotter active trades every 10s.** The first
   version only dropped IDs that had closed elsewhere, so any manual open after startup was invisible.
   The current behavior replaces the in-memory map from active blotter rows each sync (catalog-only)
   so `OPEN TRADES` stays aligned and close probability has the right denominator.

The review pass then collected what these reversals left behind — **every mid-build reversal above
orphaned the losing option's code**, and build and lint pass on unused exports, so nothing flagged
it (hence decision 12):

| Deleted | The reversal that orphaned it |
|---|---|
| `FEED_SERVICE` / `FEED_EVENT_TYPES` in `config/generator.js` | the false start in decision 2: the generator's own audits are not the intent feed |
| `REJECTED_WINDOW_MS` in `config/tradeActions.js` | decision 5: the "LAST 5 MIN" tile became "IN FEED" |
| `queued` / `backlog` / `duplicates` / `level` in `queueStatusOf`, plus `queueLevelOf` and `QUEUE_DEPTH_WARN` | decision 4: the queue-depth card was removed as a false idle signal |
| `countRejected` | duplicated what `summarizeIntents().rejected` already computes |
| `intentRateOf` + `RATE_WINDOW_MS` | decision 6, first step: one rate mechanism, not two |
| `useCounterRate` + the RATE / THROUGHPUT tiles | decision 6, final step: no client-side rate derivation at all |
| `runningOverride` + reset effect + draft-reconcile effect | decision 7: writes reconcile by refetching |

## Mental model: what owns what

```text
 Generator screen                       Trade Actions screen
 ├─ usePolling(2s)  /trade-generation/status     ├─ usePolling(2s)  /trade-action/queue/status
 │    -> running, counters, effective config     │    -> cumulative counters
 ├─ usePolling(3s)  /monitoring/audits           ├─ usePolling(3s)  /monitoring/audits
 │    ?service=trade-action-service              │    ?service=trade-action-service
 │    -> filtered to gen- correlation ids        │    -> all rows, GENERATED vs MANUAL
 │                                               │
 └─ usePolling(30s) /blotter/books/summary       └─ (no feed provider, no stream)
      -> asset classes the generator can open
```

Neither screen touches `FeedProvider`. They are polling screens over slow-moving state, so nothing
here subscribes to the 500 ms stream scheduler — a deliberate contrast with Phases 3–5.

## Process flow: a config change, end to end

```text
user types 120 into MAX ACTIVE POSITIONS, presses Enter
 └─ onKeyDown Enter -> blur -> onBlur fires
    └─ handleTargetBlur() clamps into [1, 10000]
    └─ commitConfig({ target_open_trades: 120 })
       └─ POST /api/trade-generation/config
          └─ generator.set_config()
             ├─ validates and clamps BOTH fields to [1, 10000] / [100, 60000]
             │  before writing anything — an invalid field applies nothing
             ├─ writes _config under _lock
             └─ write_audit(CONFIG_CHANGED, payload=applied)
          <- 200 { interval_ms, target_open_trades }
       └─ await status.refetch() -> out-of-cycle /status poll, server truth now
       └─ draft.target_open_trades pruned iff it still equals what was committed
          └─ display returns to server truth; p_close recomputes

user drags INTERVAL slider to 750 and releases
 └─ onChange updates local draft immediately (`draft.interval_ms = 750`)
    └─ 120ms debounce timer fires without blocking UI
       └─ commitConfig({ interval_ms: 750 }) -> same path as above
```

The draft/server split is the important part. `draft` holds the in-flight edit and is displayed in
preference to the polled value (`draft.target ?? server.target`, `draft.interval_ms ?? server.interval_ms`).
After a successful commit, `refetch()` fetches server truth immediately and the draft entry is
pruned only if it still equals the committed value — an edit made while the request was in flight
survives. On failure the draft is kept and the error shown, so the user's input is never silently
discarded by an incoming poll.

Measured: typing 120 moved the backend to 120 and `p_close` from 0.252 to 0.658
(`0.5 × 158/120`), with a `CONFIG_CHANGED` audit row written.

## Process flow: one audit row to a feed line

```text
generator._build_open()  -> client_request_id = "gen-open-{uuid}"
 └─ action_client.submit -> POST /trade-actions      (202, trade_id assigned)
    └─ action_queue.enqueue -> worker picks it up
       └─ trade_processor._open()
          └─ repository.insert_trade + _audit("TRADE_CREATED", correlation_id=crid)
             └─ audit_logs row  { event_type, entity_id, correlation_id, created_at }

browser, 3s later
 └─ GET /audits?service=trade-action-service&event_type=TRADE_CREATED,...&limit=40
    └─ normalizeAuditEvents()   -> { id, createdAtMs, eventType, entityId, correlationId }
       └─ intentRowsOf(rows, { generatedOnly: true })
          ├─ DIRECTION_BY_EVENT maps event_type -> TRADE_IN / TRADE_OUT / REJECTED
          ├─ isGeneratedIntent() -> correlationId.startsWith('gen-')
          └─ row { direction, label, tone, tradeId, source }
             └─ IntentFeed renders one <li>
```

`intentRowsOf` is shared by both screens; `generatedOnly` is the only difference between them.

## Reading the tiles: close probability vs capacity — in plain terms

The two derived numbers on the Generator screen answer different questions, and at a nearly full
book they look confusingly unlike each other:

- **CLOSE PROBABILITY** is a close *intention* probability, not an open-capacity ratio. At
  `981/1000` open trades it reads `0.5 × 981/1000 = 49.0%` — by design (the Phase 4 policy), not
  a math regression. It only approaches its 90% cap when the book is far *over* target.
- **CAPACITY** is `open / target` and answers "how near the active target are we?" — `98.10%` for
  the same numbers. It renders with two decimals so small settings stay readable
  (`target 10000, open 1 => 0.01%`), and it is deliberately not capped at 100%: if config drift
  puts the book over target, the tile shows that as-is.

## Honest gaps (rendered as gaps, not estimates)

| Mockup element | Why it is unavailable | What the screen shows |
|---|---|---|
| Per-row `20ms` latency | Audits record when an action was written, not how long it took | `n/a` with a tooltip |
| Queue depth card | `qsize()` stays near zero in an always-draining queue | Card removed to avoid false "idle" signal |
| Book / side / quantity on feed rows | Audit rows carry `entity_id` and `correlation_id` only | Omitted, with a note under the feed |
| Editable asset classes | Driven by `shared/catalog.py` and the books | Read-only chips |

Closing the first three means writing timing into `trade_processor` and widening the audit payload —
a backend change in a service this phase was not scoped to touch, so it is recorded as a follow-up
rather than smuggled in.

## Verification performed

Two passes against a live stack, generator running: the build verification (2026-07-30) and the
revision re-verification (2026-08-03).

- **`/audits` regression** — `severity=WARNING,ERROR,CRITICAL` with no new params returns what it did
  before; a `POST /debug/audit` WARNING appeared in System Overview's Errors & Warnings panel within
  one poll. The panel is the reason both new params default to today's behaviour.
- **New filters** — `service=` returns one service; `service=&event_type=` returned 36 rows of exactly
  two types; an unknown `event_type` returns **0 rows, not everything** (the filter list is not
  validated against the enum, because a valid-but-unenumerated type silently falling back to
  "no filter" would be a wrong answer rather than an empty one).
- **`POST /config` clamps** — `interval_ms` 1 → 100; `target_open_trades` 99999 → 10000 and
  0 → 1 (the revised floor); rejects an empty body with 400.
- **Atomicity** — `{"interval_ms": 5000, "target_open_trades": "abc"}` → 400, `GET /config`
  unchanged, no audit row. Exactly one `CONFIG_CHANGED` row per successful POST.
- **Restart seeding** — restarted `trade-generation-service` mid-run twice across the two passes:
  `open_trades: 24` then `open_trades: 33` against `opened: 0` — trades adopted from the blotter
  that this process did not open. Before seeding existed, those were permanent orphans the
  generator could never close.
- **Browser flows** — toggle flipped to RUNNING within one refetch (no override state left to fake
  it); typing 120 into MAX ACTIVE POSITIONS moved p_close to 18.3% (`0.5 × 44/120`) and capacity
  to 36.67% in the same poll; zero console errors. (While the rate mechanism existed it was also
  validated — 40.5/min measured against the 1500 ms interval, ≈40 expected — before decision 6
  retired it.)
- **Screens** — both render; Trades, Valuations and System Overview unchanged.
- `npm run lint`, `npm run build`, `npm run deadcode` clean (modulo the recorded 6b items in
  decision 12).

## Concepts seen for the first time in this phase

The backend patterns here are small but canonical — worth having names for.

**Module state behind a lock (`threading.Lock`).** This service has two kinds of threads touching
the same dicts: bottle's request handlers (`/config`, `/status`) and the generation loop.
`_lock` makes each compound read-modify-write atomic. The shape to remember from `set_config`:
validate *outside* the lock, mutate *inside*, and copy out (`dict(_config)`) so no reference to
guarded state escapes to code running unlocked.

**`threading.Event`, used two ways.** `_running.wait()` parks the loop thread at zero CPU until
`start()` sets the flag — an on/off gate. `_config_wait.wait(interval)` is the subtler use: a
plain `time.sleep(60)` would ignore a config change for up to a minute, but `Event.wait(timeout)`
returns the moment `set_config` fires it. An interruptible sleep is why the sliders feel
immediate even at long intervals.

**Rates from counters, not gauges.** `queued` is a gauge — a value that goes up and down — and in
an always-draining queue it reads 0 regardless of load, so sampling it says nothing. `processed`
and `opened` are counters — they only grow — so two timestamped samples give a true average rate,
and a counter that *shrinks* means the process restarted (a reset signal, not a negative rate).
The `useCounterRate` hook that applied all this was retired in the final revision (decision 6) —
the lesson outlives the code.

**The draft/server split for editable polled values.** Bind an input directly to polled data and
a poll landing mid-edit overwrites the user's keystrokes. The screen renders
`draft.value ?? server.value`: draft while an edit is in flight, server truth otherwise, and the
draft key is pruned only when the committed value has come back. This is the smallest honest
version of what form libraries call dirty-field tracking.

**Refetch-after-write vs optimistic updates.** Optimistic UI answers "how do I show the result
before the server confirms?" — by guessing, and by maintaining a rollback path for wrong guesses.
The alternative used here makes the server confirm sooner instead: one out-of-cycle `refetch()`
after the 2xx. One source of truth, no rollback machinery. Optimistic state earns its complexity
only when the backend is genuinely slow.

**Debounced commits.** The slider updates local state on every pixel of drag; the network commit
fires 120 ms after the last change. The UI stays instant while the backend — and the audit trail —
see one `CONFIG_CHANGED`, not fifty.

**Sync by replacement.** `_open_trades` is rebuilt wholesale from the blotter rather than
incrementally patched. Incremental tracking drifts — the pre-6a orphan bug was exactly that drift —
while replacement from the source of truth is idempotent: running it twice changes nothing, which
is what let startup seeding and steady-state sync collapse into one function.

**Label a number by its population.** `REJECTED · IN FEED` counts over the rows on screen;
`N this process` comes from a process-wide counter; they sit on one card, each labelled by where
it was computed. Same rule Phase 5 reached with `250+`, applied prospectively this time.

**Deliberate non-validation.** `/audits?event_type=UNKNOWN` returns zero rows, not everything.
Services write raw event-type strings, so validating the filter against the enum would turn
"valid but unenumerated" into "no filter" — a wrong answer instead of an empty one. Validate only
where the validator owns the vocabulary (severity does; event type does not).

## Files for first-pass review (phase-6a relevant)

1. `services/monitoring-service/app/api.py` + `repository.py` — the two new filters
2. `services/trade-generation-service/app/generator.py` — mutable config, clamps, unified sync, derived p_close
3. `services/trade-generation-service/app/api.py` — `GET`/`POST /config`
4. `services/trade-generation-service/app/blotter_client.py` + `main.py` — startup seeding
5. `frontend/src/hooks/usePolling.js` — the `refetch()` contract writes reconcile through
6. `frontend/src/domain/generator.js` — status normalization, intent rows, feed summaries
7. `frontend/src/domain/tradeActions.js` — queue normalization, feed-scoped counts
8. `frontend/src/views/Generator/Generator.jsx` — draft/server config split, debounced commits
9. `frontend/src/views/TradeActions/TradeActions.jsx` — honest-gap presentation
10. `frontend/src/components/generator/IntentFeed.jsx` — shared feed row
11. `frontend/src/config/{generator,tradeActions}.js` — bounds and poll cadences

## Known limits (what belongs to a later phase)

- Per-action processing latency and a richer audit payload (book, side, quantity) — needs
  `trade_processor` changes and a wider `_to_dict` on monitoring's repository.
- `interval_ms` and `target_open_trades` are process state: they reset to the `.env` defaults on
  restart. Persisting them is a separate decision about where generator config lives.
- The generator's asset-class set is still fixed by `shared/catalog.py`; the mockup's editable chips
  would need the generator to accept a per-class allowlist.
- Startup seeding is best-effort with five retries. If blotter is slow to warm its cache the
  generator starts with an empty tracking map and logs `open_trades_seed_skipped` — it never blocks
  startup.
