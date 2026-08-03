---
phase: 3
status: complete-with-follow-ups
reviewed: 2026-07-23
tags:
  - frontend
  - market-data
  - sse
  - real-time-ui
---

# Phase 3 — SSE + Market Data

## Suggested inspection order

1. **Scope and contract**
   - `docs/frontend-plan.md`
   - `services/market-data-service/app/config.py`
   - `services/market-data-service/app/persistence.py`
2. **Generation and delivery**
   - `services/market-data-service/app/generator.py`
   - `services/market-data-service/app/publisher.py`
   - `services/market-data-service/app/api.py`
   - `services/market-data-service/app/health.py`
3. **Browser transport**
   - `frontend/src/services/endpoints.js`
   - `frontend/vite.config.js`
   - `frontend/src/hooks/useSseStream.js`
4. **Domain state and ownership**
   - `frontend/src/config/marketData.js`
   - `frontend/src/domain/marketData.js`
   - `frontend/src/domain/marketFormat.js`
   - `frontend/src/domain/tableSort.js`
   - `frontend/src/hooks/useMarketFeed.js`
   - `frontend/src/providers/MarketFeedProvider.jsx`
   - `frontend/src/providers/marketFeedContext.js`
   - `frontend/src/main.jsx`
5. **Screen and table policy**
   - `frontend/src/views/MarketData/MarketData.jsx`
   - `frontend/src/hooks/useTableState.js`
   - `frontend/src/components/tables/DataTable.jsx`
   - `frontend/src/components/tables/ColumnPicker.jsx`
   - `frontend/src/components/marketdata/MarketTable.jsx`
   - `frontend/src/components/marketdata/MarketCell.jsx`
   - `frontend/src/components/marketdata/MarketIndexCard.jsx`
   - `frontend/src/components/charts/Sparkline.jsx`
   - `frontend/src/components/status/StatusPill.jsx`
6. **Integration and presentation**
   - `frontend/src/views/SystemOverview/SystemOverview.jsx`
   - `frontend/src/styles/_layout.scss`
   - `frontend/src/styles/components/_table.scss`
   - `frontend/src/styles/components/_market-data.scss`
   - `frontend/src/styles/components/_pill.scss`
   - `frontend/src/styles/components/_stat-card.scss`
7. **Verification and durable context**
   - `README.md`
   - this note

## Scope and contract

### Completion verdict

The browser-facing Phase 3 feature set is complete for the current demonstration scale. It
provides a realistic simulated source, identity-aware generated snapshot rows and SSE
events, one browser connection shared across routes, bounded client and server buffers,
reload-safe observed history, independent
observed-period and last-tick deltas, stable production-style sorting, separate curve
presentation, persisted optional-column choices, a reload-safe benchmark trend, and honest
connection and freshness states.

The 2026-07-23 reuse review confirmed that `useSseStream` is small enough to reuse for the
next feed without a stream or state dependency. The complete backend pattern is not yet
copy-ready, however. Before treating it as a production-resilient template, the following
follow-ups should be handled:

- isolate audit failures so a failed database plus a failed audit cannot terminate producer
  or consumer threads;
- audit stream disconnect and recovery transitions rather than every retry attempt;
- make the sparse pricing valuation stream yield an immediate SSE comment and set
  `Cache-Control: no-cache`;
- initialize pricing's shared `market_data_connection` state in the module that health
  reads;
- stamp the hard-coded cold-start market rows with usable per-entity ordering identity, or
  define another snapshot-cut rule, so an early late-arriving snapshot cannot briefly
  overwrite the first live event;
- make downstream Python stream readers isolate malformed records, reconcile current state
  after connection loss where missed sparse events matter, and compare explicit ordering
  metadata;
- report per-producer liveness and observable queue drops if this moves beyond the current
  small demonstration scale;
- either remove periodic database snapshots or define and implement their recovery use.

The remaining Buy/Sell actions and the global shell stream badge are intentionally outside
this phase. IRS instruments and pricing are also later domain work; the USD government
curve they can consume is already implemented here.

### End-to-end mental model

The data path is:

**Generator → current in-memory state → event persistence → per-client SSE queue → Vite
proxy → transport hook → feed hook → app-lifetime provider → Market Data and System
Overview.**

Two delivery paths serve different purposes:

| Path | Purpose | Failure it solves |
| --- | --- | --- |
| `GET /snapshot` | A coherent picture of the latest known market | Initial load, browser reload, reconnect gaps |
| `GET /stream` | Low-latency incremental updates | Keeping values live without polling the full universe |

Neither path blindly replaces the other. Once an entity has produced its first event, its
snapshot row and stream events carry enough ordering metadata for the browser to decide
which is newer. The hard-coded rows visible during the first moments of a fresh backend
process are a documented exception: they have only the snapshot's top-level `stream_id`,
not their own `event_id` or `event_time`.

### The event identity contract

Every generated spot or curve event has three identity fields:

| Field | Meaning | Why it exists |
| --- | --- | --- |
| `stream_id` | UUID created when the market-data process starts | Separates one process lifetime from the next |
| `event_id` | Global monotonic sequence inside that process | Detects duplicates and out-of-order delivery |
| `event_time` | Canonical generation timestamp | Resolves process restarts and records market time separately from database write time |

An `event_id` alone is insufficient because it restarts from zero with the service. A
timestamp alone is also insufficient because two requests can arrive in a different order
from their generation order. The pair of process identity and sequence number provides the
normal fast path; event time is the current single-producer heuristic for deciding whether a
changed process identity is newer. It is not a universal proof across unsynchronized clocks
or overlapping producers.

Ordering is evaluated per instrument. The IDs are global, but ACME does not need to receive
every curve or FX event in between its own observations.

### Why snapshot and stream start together

Waiting for the snapshot before opening the stream creates a larger serial gap: an event can
be generated after the snapshot is taken but before the stream is connected. Starting both
without waiting reduces that window, but two independent HTTP requests do not create an
atomic handoff. A live event may arrive before an older snapshot, and a theoretical event
can still fall between snapshot capture and stream registration.

The frontend deliberately accepts the race and normally resolves it by identity. If a late
snapshot contains an older generated value from the same process, it is ignored for that
instrument. The cold-start rows are the exception: until every entity has generated once,
an unversioned initial row can be accepted after the first live value and briefly move that
entity backward. Recurring ticks quickly converge again, but the backend should stamp
initial rows or expose a defined snapshot cut before this is treated as a complete ordering
contract. A lossless event history would additionally require a durable cursor and a
server-defined snapshot-plus-replay handoff.

## Generation and delivery

### `config.py`

The service-specific configuration only names the service, host, port, and converts shared
tick and snapshot intervals into the units needed by this process. Market behavior remains
in the generator and frontend display policy remains in the frontend configuration; these
concerns are not mixed.

### `persistence.py`

The in-memory dictionaries are the source for the current snapshot. Postgres is the event
history and audit record, not a dependency for reading the latest screen state.

A single lock protects event-ID allocation, generator reads, current-state replacement,
health counters, and snapshot copying. The lock gives each event one coherent position in
the process sequence. Database I/O and SSE publication happen after the lock is released,
so a slow database does not freeze all generators or block `GET /snapshot`.

Spot and curve objects are replaced rather than mutated after insertion. Snapshot copies
therefore remain stable after the lock is released. Each stored database record keeps both:

- `event_time`, when the market observation was generated;
- `created_at`, when persistence happened.

Keeping those clocks separate prevents database latency from rewriting the market timeline.

The initial hard-coded spot and curve records predate event generation and do not contain
per-entity `event_id` or `event_time`. `current_snapshot()` adds the process `stream_id` at
the envelope level, and the frontend uses it as a fallback for those records, but it cannot
prove whether an unversioned row is older than a same-process event that arrived first.
This narrow cold-start race is masked by recurring ticks; it remains a correctness
follow-up rather than a replay guarantee.

The intended availability policy is for persistence failure not to stop the in-memory feed.
The current exception path does not fully meet that policy: after a database insert fails,
it writes `DB_WRITE_ERROR` through the same database-backed audit path without guarding that
second failure. If the audit write also throws, the exception can escape `persist()` and
terminate that instrument's generator thread before publication. `save_snapshot()` has the
same shape, and its writer loop has no outer guard. This is a concrete resilience follow-up,
not a reason to move database I/O under the state lock.

The periodic `MarketDataSnapshot` database rows are also not read during startup or recovery.
The live `GET /snapshot` endpoint correctly reads current memory, but the scheduled database
snapshot writer currently adds writes and `SNAPSHOT_WRITTEN` audits without serving a
consumer. It should be removed for the current scale or completed as a defined recovery
feature.

### `generator.py`

The simulator aims for plausible movement, not exchange-level price discovery. Its key
properties are:

- **Volatility is direct and local.** `PRICE_MODEL` contains one understandable per-tick
  volatility and one source field for each asset. It does not expose annualization,
  simulated-time conversion, activity-state decay, or burst parameters that the screen does
  not need.
- **Gentle mean reversion limits artificial drift.** A pure random walk can wander to
  implausible levels during a long-running demo. One small shared pull toward each asset's
  initial anchor stabilizes the simulation without pinning every move to the starting value.
- **Quotes respect instrument conventions.** Equity uses cents, gold uses ten-cent ticks,
  ES futures use quarter points, FX uses five decimals, and each instrument has a coherent
  two-sided spread.
- **Prices remain positive.** A small lower bound prevents invalid negative values in an
  extreme random draw.

The `MARKET_INDEX` is not an unrelated random series. It is an equal-weighted rebased basket
of ACME, XAUUSD, and ES_FUT, so its movement is connected to visible constituents. It is a
benchmark and is deliberately kept out of the tradable instrument table.

The USD government curve still uses three related sources of movement, all derived from one
base curve-volatility value:

- a common level shock moves all tenors together;
- a slope shock loads short and long tenors in opposite directions;
- a small tenor-specific shock prevents a perfectly rigid curve.

Each tenor also mean-reverts toward the anchor curve. This produces plausible curve motion
and preserves the economic relationship between tenors better than generating every rate
independently, while keeping the model small enough to understand from the file itself.

### `publisher.py` and `api.py`

The endpoint creates one bounded queue for each SSE client; the publisher copies the
registered queue set and never waits for a slow client. If a 500-event queue is full, the
incoming event is dropped and
`client_event_dropped` is logged. This is deliberately only a hard memory bound for the
current small application, not a claim of production-grade coalescing. If queue pressure is
ever observed, the next design step is a measured latest-per-instrument buffer or
server-side subscription—not progressively more queue retry logic. There is currently no
drop counter or client identity in that debug event, so sustained pressure would not be
operationally measurable yet.

The streaming response sets the required `text/event-stream` content type and
`Cache-Control: no-cache`, asking caches to reach the live producer rather than reuse a
stored response. Named `market_tick` and `curve_tick` events keep the wire format explicit.
The generator's `finally` removes its queue once the WSGI iterator resumes or raises after a
disconnect. Because market events are frequent, the blocking queue regularly wakes and
exercises that cleanup path; an indefinitely silent stream would need heartbeat yields for
prompt idle cleanup.

This market endpoint does not emit an immediate `: connected` comment. Its response
generator waits on the client queue, so in the current WSGI/proxy path the browser may
remain CONNECTING until the first market event produces response bytes. Six frequent
generators make that delay short in practice. The pattern should not be copied unchanged to
a sparse stream, where an immediate comment is the minimal way to establish the response
without inventing a business event.

Event-ID allocation is globally monotonic inside the process, but mixed wire delivery is not
guaranteed to be globally ordered. Each generator releases the state lock, persists
independently, and only then publishes, so a later ID from another generator can reach the
queue first. This is safe for the current browser because ordering is evaluated per
instrument and one generator owns each instrument. A future consumer must not interpret gaps
in the mixed stream as proof that every lower global ID was already delivered.

Proxy-specific buffering headers belong in the deployment layer if an Nginx-compatible
reverse proxy is introduced. MIME-sniffing hardening is also outside this small internal
stream's current scope, so neither concern is configured in the application endpoint.

Continuous market events also act as natural connection traffic, so a separate heartbeat is
not needed at the current event cadence.

### `health.py`

Health reads generated-event count and last event time under the same lock as generation.
Those fields describe whether the producer is advancing rather than merely reporting that
the HTTP process is reachable. `stream_id` remains in snapshots and events, where clients
need it; duplicating it in health was removed because no current consumer used it.

The current health response still reports one global count and always reports the process
UP. It does not retain generator thread handles or distinguish ACME, FX, index, and curve
liveness. One dead producer can therefore be hidden while other generators advance, and
all dead producers would still leave the HTTP process reachable. Per-producer last-event
times or a small watchdog become necessary only when health must prove complete feed
liveness rather than service reachability plus aggregate activity.

## Browser transport

### What `EventSource` means here

`EventSource` is the browser's native client for Server-Sent Events. Constructing:

```js
new EventSource('/api/market-data/stream')
```

returns a browser connection object immediately and starts a long-lived HTTP GET in the
background. It is not a Promise. The server sends `text/event-stream` headers once, keeps
the response body open, and writes records such as:

```text
event: market_tick
data: {"symbol":"ACME","mid":101.03}

```

The blank line terminates the SSE record. The browser handles network chunk boundaries,
parses the record, and dispatches a `MessageEvent` named `market_tick`.
`message.data` remains text; the hook parses its JSON.

The concrete lifecycle is:

```text
provider commits
→ effect constructs EventSource
→ browser sends GET through Vite
→ backend registers a client queue
→ streaming response begins
→ browser fires open
→ backend yields a named SSE record
→ browser dispatches MessageEvent
→ hook parses and forwards it
→ feed buffers the normalized update
→ next shared 500 ms scheduler tick flushes React state
→ both routes receive the new provider value
```

An open EventSource proves only that the HTTP transport is established. Per-instrument LIVE
or STALE state is calculated independently from browser receipt time.

Named ready states, named versus default events, authentication constraints, retry
behavior, and cleanup are covered where they are used, in the transport section below.

### `endpoints.js` and `vite.config.js`

The browser calls same-origin `/api/market-data` URLs. Vite proxies them to the Docker
service, and the current development topology has been verified to forward SSE records
incrementally. Components never know container names, ports, or development topology, and
the phase does not require feature-specific CORS configuration. A production proxy must
independently verify response buffering, compression, idle timeout, and stream duration;
`no-cache` does not universally disable proxy buffering.

### `useSseStream.js`

The hook is intentionally a transport boundary. It owns:

- `EventSource` creation;
- named-event registration and JSON decoding;
- `CONNECTING`, `CONNECTED`, and `RECONNECTING` status;
- one fixed two-second reconnect delay;
- timer, listener, and connection cleanup.

It does not own instruments, history, formatting, storage, sorting, or screen policy. A ref
holds the latest event callback, so an ordinary React render does not tear down a healthy
connection. On error the hook closes that source and owns one fixed retry schedule. Native
`EventSource` retry was tested first, but a failed Vite proxy connection did not reliably
resume after the Docker upstream returned. A small explicit loop is therefore required by
the current topology; exponential backoff and multiple tuning constants are not.

Because the explicit loop closes one EventSource and constructs a new object, a future SSE
replay cursor would need an explicit continuity design. A replacement object does not
automatically inherit the former object's internal `lastEventId`.

Malformed JSON is ignored at the transport edge. One bad message therefore cannot stop the
stream or contaminate domain state.

The review verdict is to reuse this hook unchanged as the Phase 4 transport for
`valuation_update`, then build a valuation-specific feature hook and provider around it. No
additional SSE, query, or state dependency is needed. Snapshot shape, entity key, ordering,
buffering, storage, and valuation presentation must remain outside the transport hook.
Extract another generic feed abstraction only after two feature hooks demonstrate identical
behavior.

The important ownership boundary is that this hook reports transport events; it never
decides how market observations merge.

## Domain state and ownership

### Frontend `config/marketData.js`

The frontend keeps the small set of shared display policies in one plain module:

| Constant | Current value | Responsibility |
| --- | --- | --- |
| `STREAM_EVENTS` | `market_tick`, `curve_tick` | Named SSE records registered by the transport hook |
| `MARKET_STALE_AFTER_MS` | 5,000 ms | Browser-receipt age after which an instrument becomes STALE |
| `HISTORY_LENGTH` | 100 accepted values | Maximum retained series used by every sparkline, row and benchmark alike, and by tab storage |
| `FLUSH_INTERVAL_MS` | 500 ms (shared from Phase 4) | Base scheduler and boundary between high-frequency ref updates and React state publication |
| `FRESHNESS_INTERVAL_MS` | 1,000 ms | Freshness runs on every second base tick without creating another timer |
| `BOND_CURVE_TENORS` | 1Y, 2Y, 3Y, 5Y, 10Y | Curve nodes admitted into the current screen model |

The same module declares market and curve columns, their required/sortable properties,
default sort directions, and whether a sort needs captured live values. These are data
descriptions consumed by the view and table rather than branches duplicated across
components.

The two-second reconnect delay remains in `useSseStream.js` because it is transport policy,
not market-display policy. Generator tick timing remains in shared backend configuration.
Keeping those concerns separate avoids a single configuration object whose values only
make sense through hidden dependencies on one another.

### `marketData.js`

The domain module converts transport payloads into one UI model. Spot values consistently
prefer `mid`, then `last`, then `spot`. The USD_GOV payload expands into separate 1Y, 2Y,
3Y, 5Y, and 10Y RATE rows. The full backend curve remains available for future pricing work;
this screen deliberately shows the compact observed-tenor set.

Value presentation lives in `domain/marketFormat.js`, and the direction-agnostic sorting
primitives live in `domain/tableSort.js`. `marketData.js` therefore contains only the
ordering, merge, derivation, freshness, and market-sort-adapter rules.

The ordered merge follows these rules:

| Incoming observation | Decision |
| --- | --- |
| Same `stream_id`, same or lower `event_id` | Ignore as duplicate or stale |
| Same `stream_id`, higher `event_id` | Accept and append an observation |
| Different `stream_id`, older `event_time` | Ignore as a delayed event from the former process |
| Different `stream_id`, same or newer `event_time` | Accept as a restart and reset that instrument's observation window |
| Legacy event without complete identity | Fall back to event-time ordering |

Resetting history on a confirmed process restart is important. Joining two unrelated
simulator lifetimes would create a false observed delta and a misleading sparkline.

The display history and observed-period delta have separate state:

- `history` contains at most 100 values, which bounds storage and sparkline work;
- `observedOpen` retains the first accepted value for the current process window;
- `observationCount` describes the full window even after early sparkline points roll off.
- `previousValue` retains only the accepted value immediately before the latest value.

This separation fixes a subtle bug: using `history[0]` as the delta baseline would silently
change the meaning of **This session** after the 101st update.

The UI exposes both meanings explicitly:

- **This session** compares the first browser-observed value in the current process window
  with the latest value;
- **Last tick Δ** compares the previous accepted value with the latest value.

Last-tick delta is not derived from the sparkline array. It therefore remains correct if the
history cap changes, survives a same-tab reload, and becomes unavailable after a process
restart until a second value from the new process arrives.

Rates show absolute movement in basis points. Other instruments show absolute movement and
percentage movement. Percentage is used for cross-price sorting because a one-point change
in EURUSD, an equity, and an index does not have comparable meaning.

Freshness uses browser receipt time rather than server time. A five-second threshold then
measures “how long since this browser saw the instrument” and cannot be distorted by clock
skew between containers and the user's machine. Server event time remains the value shown
in the Updated column.

### `useMarketFeed.js`

The feed hook is the stateful bridge between transport and domain behavior:

1. Restore bounded state from the current tab's `sessionStorage`.
2. Start the initial snapshot request and SSE connection without serializing them.
3. Normalize all incoming events.
4. Put only the newest pending update for each instrument into a ref-backed `Map`.
5. Flush at most once per shared 500 ms scheduler tick into one atomic market-state update.
6. After a successful reconnect, fetch another snapshot and merge it through the same
   ordering rules.

Its runtime triggers are:

| Trigger | Owner action | Does it render immediately? | Downstream effect |
| --- | --- | --- | --- |
| First render | Lazy state initializers restore feed state and tick count from `sessionStorage` | The restored state is the first render | Cached rows and charts appear without waiting for the network |
| First committed mount | Snapshot effect starts `GET /snapshot`; `useSseStream` opens SSE independently | Not by starting the requests | Whichever response arrives first is merged by identity |
| Named SSE message | Callback normalizes the payload, increments a ref counter, and replaces that instrument in the pending `Map` | No; refs do not schedule React renders | Latest pending values wait for the next flush |
| Shared 500 ms scheduler tick | Pending values are removed from the map and merged with a functional state update; the tick counter is copied into state and storage | Yes, at most once per non-empty tick | Consumers receive one coherent market update; every second tick also carries the one-second freshness update |
| Market state commit | Persistence effect serializes bounded market state | No additional state update | A same-tab reload can restore the chart and delta baselines |
| Status changes from RECONNECTING to CONNECTED | Reconciliation effect requests a new snapshot | Only when accepted snapshot values change state | Missed current values are recovered |
| Effect cleanup | Abort its request or clear its interval | No | Work cannot outlive its owning hook instance |

The pending map is bounded by the number of distinct instruments, not by the number of
events received between renders. Coalescing may omit intermediate visual samples during an
extreme burst, but it never leaves the UI rendering an obsolete backlog. The tick counter
counts one recognized, successfully normalized SSE envelope—not each expanded curve tenor
and not each rendered sample—so transport activity and rendered samples are not confused.

The hook publishes exactly one collection: `instruments`, keyed by instrument ID. An earlier
revision also carried a parallel `universe` array of identity metadata so that filtering and
ordering could keep a stable array reference across ticks. At this scale that reference
stability bought nothing measurable and duplicated state, so the view now derives its rows
from `instruments` directly. Row order stays stable because snapshot sorts compare captured
values and structural sorts are deterministic — not because the source array is memoized.

The initial snapshot is allowed to fail without hiding valid streamed values. Conversely, a
temporary stream loss does not discard the last known state. A reconnect snapshot closes
any gap immediately; later live ticks continue from the reconciled state.

`snapshotSettled` means that the first snapshot attempt has finished, whether successfully or
with an error. It is not a claim that instruments exist. The view combines `snapshotSettled`,
connection status, and the actual entity list to distinguish “connecting,” “retrying with no
cached data,” and “connected but no instruments published.” Stream events can populate the
list before the snapshot attempt settles.

### Persistence choices

Two browser stores have deliberately different lifetimes:

| Data | Store | Semantics |
| --- | --- | --- |
| Bounded instruments, history, observation baseline, tick count | `sessionStorage` | Survives reload and route changes in the same tab; disappears with the tab session |
| Independent ordered market and curve column-ID arrays | `localStorage` | Each table's visibility and order survive future browser sessions |

Stored market state is versioned, validated, limited to 100 instruments, and re-capped to
100 history values on restore. Invalid or old payloads become an empty safe state. Storage
failure never interrupts the live feed.

The received-tick count is updated for every valid SSE envelope in a ref, but it is written
to `sessionStorage` only during the same half-second flush that updates React state. Exact
sub-millisecond durability for an informational counter would add synchronous work to every
event without improving the screen.

Both screens label this as **ticks received · this tab session**. It survives reload and
route navigation in that tab, and it intentionally continues across market-data restarts or
database teardown. It is not a producer-lifetime counter, a database row count, an accepted
instrument count, or a rendered-point count. Closing the tab session gives it a new
lifetime.

Restored rows keep their prior history and delta baseline instead of repainting empty
sparklines. Their prior receipt time is preserved rather than reset by restoration, so a
recent row can remain LIVE briefly while an older row is immediately STALE; either becomes
STALE once its receipt age exceeds five seconds unless a snapshot or live event confirms
freshness. Browser restoration therefore never invents a new receipt time.

### `MarketFeedProvider.jsx`, `marketFeedContext.js`, and `main.jsx`

The provider mounts above routing because Market Data and System Overview need the same
source. This creates one app-lifetime logical subscription owner with at most one active
EventSource at a time and preserves the feed during navigation. Reconnection can replace
the EventSource object, and development Strict Mode intentionally performs an initial
setup-cleanup-setup check. It is narrower than introducing a general global state library:
only market-feed consumers subscribe to this context, and all market rules remain in the
dedicated hook and domain module.

`useMarketFeedContext()` also checks that the context is non-null and throws a direct
ownership error when a consumer is mounted outside `MarketFeedProvider`. That fail-fast
guard makes a component-tree wiring mistake easier to diagnose than allowing later code to
read properties from `null`.

## Screen and table policy

### `MarketData.jsx`

The view composes feed state into a live market-index benchmark, compact feed-health cards,
class and symbol filters, two independent tables, column preferences, and sort state. It
reads in one direction with no branching back:

**instruments → rows → filter → sort → table.**

`marketRowsOf` derives every per-row value once, the class and symbol filters narrow the
list, `sortMarketRows` orders it, and `MarketTable` renders it. The view holds only what is
genuinely screen policy: the active class, the search text, and which sorts require a single
class. Column visibility, column order, their persistence, and sort state are owned by
`useTableState`, which is called twice with different configuration rather than duplicated.

The screen distinguishes transport state from instrument freshness:

- connection status describes whether the EventSource is connected;
- LIVE or STALE describes when each instrument was last received.

A connected stream can temporarily contain a stale instrument, and a reconnecting stream
can still display useful last-known values. Treating these as separate concepts avoids
misleading all-or-nothing status.

`useElapsedTime()` advances a small `now` state once per second. This is intentionally a UI
clock, not polling: it performs no request and changes no quote. Its render lets
`isStale(instrument, now)` cross the five-second threshold even when the feed has gone
silent, so LIVE can become STALE without waiting for another market event.

### Stable snapshot sorting

Re-sorting rows on every tick makes a live table difficult to read, difficult to click, and
expensive at scale. Phase 3 therefore uses two kinds of sort:

| Sort type | Columns | When order changes |
| --- | --- | --- |
| Structural | Symbol, Class, Tenor | User changes sort or the instrument universe changes |
| Snapshot | Market level, This session, Last tick Δ, Bid/Ask, Feed, Updated | User clicks a sortable header |

The non-tradable `MARKET_INDEX` lives only in the top benchmark card, which carries its live
level, session change, last-tick change, freshness, and recent normalized path. It is
excluded from the asset table and class filter, so class sorting and the class selector are
purely alphabetical with symbol as the stable row tie-breaker.

A snapshot sort captures only the comparison values. The cells remain live while row order
stays fixed, and a subtle status shows when the order was captured. Clicking any sortable
header records a fresh capture time; volatile sorts also recapture their comparison values.
Clicking the active header toggles its direction and captures again. The highlighted large
arrow identifies the active direction; muted smaller arrows only indicate that another
column is sortable. Only the active header exposes `aria-sort`.

Market level and relative-spread sorts require a single asset class. Without that filter,
the table would rank unlike units such as FX rates, index points, and equity dollars. Price
instrument deltas sort by percentage, so both observed-period and last-tick movement remain
meaningful across classes. The curve table sorts yield by rate and both deltas by basis
points. Market and curve sorts are independent.

Missing values always appear after real values in either direction. A deterministic
class/tenor/symbol fallback prevents equal values from causing random row movement.

### Separate market and curve tables

The USD government curve is a related set of non-tradable tenors, not a collection of spot
instruments. Keeping it in a dedicated table below the market table provides comparable
Yield and basis-point Delta columns, avoids mixing units, and leaves room for curve-specific
behavior without complicating the generic market table.

Both tables are the same `MarketTable` given different column configuration and its own
`useTableState` instance, so neither table duplicates rendering or preference behavior and
neither can disturb the other's columns or sort.

The backend already publishes 6M and 7Y in addition to the five displayed tenors. Showing
the larger tenor set and adding a curve-shape chart were deliberately deferred as a separate
feature. This phase continues to enforce its five-tenor UI policy when restoring browser
state, so an older or experimental stored instrument set cannot reintroduce removed stale
rows.

### Market benchmark trend

The benchmark belongs in the top `MARKET_INDEX` card because the index is the screen's single
cross-asset benchmark. Plotting ACME dollars, EURUSD, gold, and futures points on one raw axis
would be invalid; introducing several axes would make a small operational screen harder to
read. A future relative-performance comparison would first need time-aligned, normalized
series.

The card reuses the same `Sparkline` component as the table rows, at a larger size. A
dedicated `MarketIndexChart` with its own scale calculation, zero line, and percentage axis
labels existed first and was removed: the axis labels restated the delta already printed
beside the value, and the second SVG component duplicated geometry the sparkline already did.
The card now shows the shape of the session and nothing else, and the numbers are read from
the text where they are exact. Session history is restored from `sessionStorage`, so a reload
does not repaint the trend from an empty path.

Colour follows the same rule as everywhere else: the trend is green or red by direction,
matching the card border tone, rather than a separate contextual blue.

### Columns, filtering, and accessibility

Symbol and Market level are required in the market table. Tenor and Yield are required in
the curve table. The remaining columns in each table are optional. Two `ColumnPicker`
instances share the same disclosure, toggle, drag, keyboard, and reset behavior, while each
`useTableState` instance owns one ordered ID array and one `localStorage` key. A change or
Reset in one table therefore cannot alter the other table.

The same sanitizer validates either stored array, prevents duplicates, ignores unknown
IDs, and restores missing required columns at their configured positions. There is no
pre-release schema migration framework: an invalid or obsolete value falls back to that
table's current defaults. Migration logic should be introduced only after a released
layout becomes real user data that must be preserved.

Visible columns can be reordered from an enlarged grab handle using dependency-free pointer
events. Pointer movement only previews a blue before/after insertion line; it does not move
the list underneath the pointer, and the options area keeps one grabbing cursor throughout
the gesture. Pointer release commits one
`reorderColumn(source, target, position)` operation, which avoids the cursor oscillation
caused by reordering on every move. Focused handles use Arrow Up and Arrow Down through the
same operation. Hidden columns remain available in the selector but become draggable only
after they are shown. Because both pickers contain some identical column IDs, pointer
hit-testing is scoped to the currently open `<details>` element; a drag can never target a
row in the other picker. Distinct accessible labels identify the market and yield controls.
Hiding the active sort column safely returns the market table to its valid default sort or
the curve table to Tenor ascending.

The native Columns `<details>` menu closes on an outside pointer action. Escape also closes
it and returns focus to the Columns summary, while checkbox and movement interactions inside
the menu keep it open.

Class filtering applies only to the market-instrument table. Symbol search applies to both
market and curve rows. Each empty result has a specific explanation rather than rendering a
blank table.

### Visual semantics

The whole row briefly flashes green for an uptick and red for a downtick. This animation is
about price direction. The compact LIVE badge remains blue because it represents feed
freshness, not profit, loss, or price direction. STALE uses the muted stale treatment.

The row key includes an update sequence so a newly accepted value reliably restarts the CSS
flash. Reduced-motion preferences disable the animation. Every trend line is the same small
inline-SVG `Sparkline` with no chart dependency, and the table gains horizontal scrolling at
narrow widths instead of compressing numeric columns into unreadable text. Former 8–9 px
microcopy now has a 10 px minimum, ordinary supporting labels use 11–12 px, and secondary
text uses stronger contrast; dense numeric data remains at 13 px rather than making the
whole screen larger.

## Integration and presentation

### `SystemOverview.jsx`

System Overview reads the same provider to show connection state, received envelopes for
this tab session, instrument count, live/stale split, and last update. It does not open a
second EventSource. This both reduces backend load and ensures the overview and detailed
screen describe the same browser-observed feed.

### Component and style boundaries

`DataTable` owns semantic table rendering, sortable header interaction, `aria-sort`,
disabled-sort messaging, responsive minimum width, and horizontal overflow. It knows nothing
about markets: rows, columns, cell rendering, row keys, and per-cell classes and titles all
arrive as props. `ColumnPicker` owns only preference interaction. Both live in
`components/tables/` and carry `data-table__*` and `table-columns__*` class names so a later
feed can reuse them unchanged.

`MarketTable` is the market-side adapter: it binds `DataTable` to `MarketCell`, the row flash
and stale classes, the delta tone classes, and the observed-window tooltips. `MarketCell`
renders one market cell and nothing else. `MarketIndexCard` owns benchmark-specific
formatting and hands its history to the shared `Sparkline`. `Sparkline`, `StatCard`, and
`StatusPill` stay reusable and presentation-focused.

The SCSS uses existing design tokens. Price-direction colors, status colors, active sort,
stale treatment, and surface hierarchy are separate visual roles rather than one overloaded
green/red convention. Generic table styling lives in `_table.scss`; `_market-data.scss` keeps
only market-specific presentation.

### Responsive behavior

The content column is the sized element, not the window: a fixed 210 px sidebar plus page
padding makes it roughly 274 px narrower than the viewport. Viewport media queries therefore
fired far too late, and the summary row and benchmark card overflowed their containers in any
window narrower than about 1210 px. `.content` now declares `container: page / inline-size`
and the market breakpoints are `@container` queries measured against the content column
itself. Every grid track also has a zero minimum, so a track can never demand more width than
its parent can give. Verified with no overflow from a 1360 px content column down to 430 px.

## Reuse review for later phases

### Browser transport

`useSseStream` is the correct reusable unit. It manages one browser transport resource and
has no market-data knowledge. Phase 4 can call it with the pricing URL and
`valuation_update`, while a separate `useValuationFeed` owns `trade_id` keys, the
`/valuations` seed, valuation freshness, ordering, and any render buffer. Mounting that
feature hook in an app-level provider will share one valuation connection just as the market
provider shares one market connection.

`useMarketFeed` should not be generalized now. Its curve expansion, observed baselines,
sparkline history, tab storage, and instrument identity are real market rules. A
configuration-heavy “universal feed” would hide those rules and still need feature-specific
branches. Compare the two feature hooks after Phase 4 and extract only behavior that is
actually identical.

### Table capabilities

Three units are already feed-agnostic and are the intended Phase 4 starting point:

| Unit | Owns | Knows nothing about |
| --- | --- | --- |
| `hooks/useTableState.js` | Column visibility, column order, `localStorage` persistence and sanitizing, sort column and direction, snapshot capture on header click, fallback when the sorted column is hidden | Instruments, values, formatting, which columns exist |
| `domain/tableSort.js` | Null-last ordering in both directions, direction multiplier, deterministic tie-break | What a row is |
| `components/tables/DataTable.jsx`, `ColumnPicker.jsx` | Semantic markup, header buttons, `aria-sort`, disabled-sort messaging, overflow, drag and keyboard column reordering | Cells, rows, domain classes |

A new table supplies four things: a column descriptor array, a storage key, a default sort,
and `captureSnapshot` plus a cell renderer. Snapshot-value derivation and tie-break stay with
the domain that owns the data — for markets that is `captureMarketSnapshot` and
`sortMarketRows` in `domain/marketData.js`. Valuations should add their own equivalents
rather than widening the generic layer.

The current valuation payload has `valuation_time` but no producer epoch or event sequence.
For the present single-producer latest-value screen, per-trade timestamp comparison is a
reasonable small ordering policy. If deterministic deduplication across clock changes,
multiple producers, or durable replay becomes a requirement, the pricing contract must add
an explicit identity or cursor; the generic transport hook should remain unchanged.

### Python stream readers and producers

The Pricing and Blotter readers use standard-library `urllib` and a small line parser. That
is enough for the controlled one-line JSON SSE format used here; adding an SSE client
dependency would not currently improve the product guarantee. The loop correctly retries
network failure, but its audit calls are not failure-isolated and it records
`STREAM_DISCONNECTED` on every failed connection attempt instead of only on a connection
state transition. Those are lifecycle fixes to make before copying the reader as a
production template.

Their one connection-wide `try` also covers JSON decoding and domain handlers. One malformed
record or handler exception therefore tears down that connection and enters retry rather
than rejecting only the bad event. Neither reader performs a snapshot reconciliation or
uses the producer identity after reconnect. Recurring market values usually converge the
pricing cache, but a sparse final valuation can be missed by Blotter. Those are application
delivery semantics, not reasons to add a general SSE library: add a per-record error
boundary and an explicit snapshot/order policy where the downstream workflow requires
current-state recovery.

The next browser feed also exposes a producer-side issue: `/valuation-stream` waits on its
queue before yielding the first byte. If there is no active valuation, EventSource can stay
in CONNECTING rather than promptly reporting an open stream. The minimal Phase 4
prerequisite is an immediate SSE comment such as `: connected\n\n` plus
`Cache-Control: no-cache`. A periodic heartbeat is separate and is unnecessary unless
measured idle timeouts require it.

No Redux-style store, third-party EventSource client, query library, drag-and-drop package,
or chart library is justified by this phase. The native browser API, React hooks, bounded
maps, context, and inline SVG match the current scale.

## Decisions kept deliberately minimal

| Choice | Why it fits this phase |
| --- | --- |
| SSE instead of WebSocket | The server only pushes data; bidirectional protocol complexity is unnecessary |
| Snapshot plus current-state stream instead of replay | This screen needs the latest quote, not exactly-once processing of every event |
| React context instead of Redux or another store | Two routes share one source, and the state model remains small and cohesive |
| One fixed reconnect delay instead of native-only or exponential policy | Native retry did not recover reliably through the stopped Vite upstream; one measured fixed delay solves the observed failure without a tuning surface |
| Latest-per-instrument coalescing instead of an event array | Bounds memory and render work while preserving the newest state |
| Stable snapshot sorting instead of continuous sorting | Preserves readability and scales independently from tick frequency |
| Direct per-tick volatility instead of annualized and burst parameters | Keeps the demo movement understandable and tunable without pretending to be a calibrated market model |
| SSE content type plus `no-cache`, without proxy-specific headers | Matches the current Vite/Docker topology; deployment hardening is added only when the deployment layer requires it |
| Inline SVG charts instead of a chart library | Bounded sparklines and one benchmark path need only basic SVG geometry and accessible labels |
| Pointer-based column drag instead of a drag-and-drop package | Direct manipulation without a dependency; focused handles retain keyboard reordering |
| One generic instrument table plus a curve wrapper | Reuses rendering without forcing unlike market and rate policies together |

The phase intentionally does not promise exactly-once event history in the browser.
Intermediate samples can be lost during a disconnect or coalesced during a burst. Current
state is reconciled from a snapshot and then kept live. If a later feature requires an
auditable tick tape, it should use durable replay with server event IDs rather than
overloading this screen's UI buffer.

## Concepts seen for the first time in this phase

This is the phase where the app becomes real-time, and nearly every technique below is reused
by Phases 4–6 without change.

**Server-Sent Events and `EventSource`.** A long-lived HTTP GET where the server keeps the
response open and writes `event:`/`data:` records separated by blank lines; the browser parses
the framing and dispatches named `MessageEvent`s. One direction only — which is exactly the
shape of a market feed, and why SSE beat WebSocket here (see the decision table). The key mental
adjustment: `new EventSource(url)` is not a Promise; it is a connection object with a lifecycle.

**An effect that owns a network resource.** Phase 1's cleanup removed an event listener; here the
same `useEffect` pattern creates and tears down a live connection. Get it wrong and every remount
leaks a socket. This is the strongest version of "an effect's cleanup must mirror its setup" in
the project.

**The transport/domain boundary.** `useSseStream` knows how to connect, parse JSON, report
status, and reconnect — and nothing else. It never decides how observations merge; the feed hook
never touches `EventSource`. The proof of the boundary came in Phase 4: a second stream reused
the transport hook unchanged.

**A ref that holds the latest callback.** The connection must survive re-renders, but the handler
closes over fresh state each render. Storing the handler in a ref (`ref.current = handler` each
render, transport calls `ref.current(event)`) decouples the two lifetimes: a healthy connection
never restarts just because React rendered. This "latest ref" idiom recurs in every later hook
that bridges a long-lived resource and React state.

**Buffer, coalesce, flush — bounding render work.** Raw ticks land in a mutable ref keyed by
instrument (latest-per-key wins), and a timer flushes the buffer into React state on a fixed
cadence. Ticks can arrive at any rate; renders happen at most twice a second. The decomposition
matters as much as the throttle: *arrival* (ref write, free) is separated from *publication*
(state write, a render).

**Reconciling a snapshot with a live stream.** Neither alone is correct: the snapshot is complete
but instantly aging; the stream is current but starts mid-flow. Seed from the snapshot, let newer
stream values win through an ordered merge, and re-snapshot on reconnect to fill whatever the
outage dropped. The merge discipline built here becomes the Phase 4 valuation rules and Phase 5's
row-value selection.

**Freshness is derived, not reported.** An open connection proves transport, nothing more.
LIVE/STALE is computed per instrument from browser receipt time against a threshold — which is
why a healthy socket with a silent instrument correctly shows STALE, and why every later screen
computes freshness rather than trusting a flag.

**Versioned browser persistence.** History and tick counts survive a refresh via
`sessionStorage`, written with a version stamp so a shape change invalidates cleanly instead of
crashing on parse. The rule: persisted state is input from an old version of the app — validate
it like any other input.

**Stable snapshot sorting.** Live-sorting a table on a streaming column makes rows jump on every
tick. Capturing the sort key once — a snapshot of values at sort time — keeps order deterministic
while cells keep updating in place. Reused verbatim by Valuations and Trades.

**Container queries.** With a fixed sidebar, viewport-width breakpoints lie about the space a
table actually has. `.content` is a CSS container and component styles query *it* — layout
decisions track the column that contains them.

## Failure behavior and limits

| Condition | Behavior |
| --- | --- |
| Snapshot is slow after entities have generated | Newer SSE values win through ordered merge |
| Cold-start snapshot row lacks per-entity identity | A first live event can be overwritten briefly; recurring ticks converge, but initial rows still need stamping for a complete contract |
| Snapshot fails but SSE works | Streamed instruments still populate the screen |
| SSE disconnects | Last-known values remain, status becomes RECONNECTING, instruments age to STALE |
| SSE reconnects | A fresh snapshot immediately reconciles missed current values |
| Service restarts | New `stream_id` resets each instrument's observed window when the newer process arrives |
| Duplicate or delayed event arrives | Domain merge ignores it |
| Browser storage is corrupt or unavailable | Safe empty/default state; live feed continues |
| Server client queue fills | Incoming event is dropped and logged; memory remains bounded |
| Database write fails | The insert is caught, but a second unguarded database audit can currently terminate that generator; resilience follow-up required |

The current hard bounds are 100 persisted instruments, 100 sparkline points per instrument,
a shared 500 ms browser scheduler with one-second freshness, and 500 queued market events per
client. Only the browser flush and history cap are active behavior at today's event rate; the larger
limits mainly prevent unbounded memory or corrupted storage. A high-cardinality production feed
would need measured queue sizing, latest-state coalescing on both sides, table virtualization,
server-side subscriptions, and durable replay for any workflow that cannot tolerate loss.

## Verification and durable context

The complete verification sequence is:

- from `frontend/`: `npm run lint`, `npm run build`;
- from the repository root: Python compile check for market-data service code;
- Docker rebuild of market-data service and frontend when backend delivery changes;
- browser exercise at desktop and compact widths.

The 2026-07-22 completion review passed lint, the Vite production build, Python compilation,
and `git diff --check`. Live verification confirmed stable delta sorting while values
changed, eight non-empty table sparklines and a restored benchmark chart after reload,
persisted column movement and visibility, no page-level overflow at 820 px or 560 px
viewports, and a clean browser console. The benchmark path changed with live observations
while its card height and the stable asset row order did not move. The four-tenor restore
policy also removed experimentally stored 6M, 7Y, and 10Y rows. The recovery check reached
RECONNECTING and nine STALE instruments after the local service stopped, then returned to
CONNECTED and nine LIVE instruments with a reconciled, new-process history after restart.
Direct snapshot and named-event checks confirmed matching stream identity and populated
ordering fields; health confirmed the generator count and last-event timestamp were
advancing.

The follow-up generator simplification was rebuilt in Docker. The restarted service became
healthy, produced advancing events with a new `stream_id`, returned the same identity from
`/snapshot`, and exposed the expected SSE content type plus the no-cache response header.

The 2026-07-23 minimalism pass again passed frontend lint/build, Python compilation, and
`git diff --check`. Browser checks confirmed that keyboard and pointer column movement share
one operation, the plain ordered-column array survives reload, tick count and the 100-point
benchmark chart restore without repainting from zero, and outside pointer actions close the
column menu. An outage test disproved native-only retry in the current Vite/Docker topology;
the final fixed two-second retry reached RECONNECTING with stale rows and then returned to
CONNECTED with eight live table rows and a reset new-process observation window.

The subsequent reuse review confirmed that the frontend transport has one connection owner,
one retry owner, complete cleanup, bounded rendering, and no unnecessary dependency. It
also found the backend resilience and sparse-stream handshake follow-ups listed in the
completion verdict. Those findings change the phase status from unqualified “complete” to
“browser scope complete with backend follow-ups”; they do not invalidate the current
market-screen behavior.

The same pass completed frontend lint and production build, Python compilation of the three
stream-related services, documentation structure checks, and `git diff --check`. Browser
verification showed **this tab session** on Market Data and System Overview, confirmed the
shared connection remained CONNECTED across navigation, and found no console errors.

The 2026-07-23 yield-column follow-up passed frontend lint and production build. Browser
verification confirmed that the market and yield pickers have independent accessible
labels and preferences, Tenor and Yield remain locked, the other five curve columns can be
hidden or reordered, and hiding the active curve sort returns immediately to Tenor
ascending. A reload preserved a six-of-seven curve selection, Reset restored all seven
without changing the market selection, the menu stayed within the viewport at desktop and
560 px widths, and the console remained clean.

The 2026-07-27 structure pass extracted `useTableState`, `tableSort`, `DataTable`, and
`MarketTable`/`MarketCell`, moved `useMarketFeed` from the view folder to `hooks/`, split
formatting into `marketFormat.js`, removed the duplicated `universe` state, and replaced the
viewport media queries with content-column container queries. Frontend lint and the Vite
production build passed. Browser verification at a 1360 px content column and at simulated
1000, 950, 700, 600, and 430 px columns found no element overflowing its container and no
page-level horizontal scroll. Sorting was re-checked live: a `requiresClass` header stayed
disabled without a class filter and became sortable with one, Symbol toggled ascending and
descending with the capture status updating, clearing the class filter returned the table to
its default sort, and hiding the active sort column fell back to Symbol ascending. Reset
restored all nine market columns without touching the seven curve columns, keyboard
reordering moved a column and persisted it, Escape closed the picker, and a reload restored
the 100-point benchmark chart, the sparklines, the continuing tick counter, and the stored
column selection. System Overview continued to share the one connection. The console stayed
clean throughout.

A follow-up simplification pass replaced the bespoke `MarketIndexChart` with the shared
`Sparkline` at card size, deleting the component, its axis and scale logic, and 66 lines of
chart SCSS. It also removed the dead `history.filter(Number.isFinite)` in `observedChangeOf`:
`mergeInstrument` only ever appends finite values and `restoreInstrument` filters on restore,
so the guard could never fire, and it was the only O(history) work in a function that
otherwise does arithmetic on two numbers. Measured on ten instruments with a hundred points
each, that scan was about eleven times the cost of the calculation it guarded. Lint, build and
a browser pass at content widths of 1000, 700 and 480 px were clean afterwards.

### Manual behavior checklist

1. Confirm snapshot and SSE payloads share process identity and per-event ordering fields.
2. Navigate between System Overview and Market Data; the connection and counter must
   continue rather than restart.
3. Reload the tab; rows, sparklines, and the Market Index chart must restore immediately,
   then reconcile with the snapshot instead of repainting from zero.
4. Sort either table by This session and Last tick Δ; values must continue changing without
   row movement.
5. Click the active sortable header; direction must toggle and the order must be captured again.
6. Filter to one class and verify Market level and Bid/Ask sorting become available.
7. In both tables, hide and move optional columns, reload, verify independent persistence,
   then use each Reset. Confirm Tenor and Yield cannot be hidden and hiding the active curve
   sort returns to Tenor ascending.
8. Stop the market-data service; connection must show RECONNECTING and rows must age to
   STALE after roughly five seconds.
9. Restart the service; the stream must reconnect, reconcile a snapshot, and start a new
   observed window without mixing process histories.
10. Verify a full row flashes red or green on a price move while the LIVE badge stays blue.
11. Observe the Market Index chart across several updates; its path should change without
    changing the card height or continuously reordering the asset table.

### Deferred boundaries

- Per-row Buy/Sell actions belong to the trade-entry phase.
- The global shell-level “streams connected” badge remains a final shell detail.
- IRS instruments and pricing will consume the implemented rate curve in the later backend
  domain phase.
- A yield-curve shape chart and a broader displayed tenor set remain a separate focused UI
  feature; the backend data is already available.
- An auditable tick tape would require durable replay and is not part of this latest-state
  screen.
- Producer/consumer audit failure isolation and transition-based connection audits are
  required before the backend loops are treated as a reusable resilience template.
- The pricing valuation stream needs an immediate comment handshake and `no-cache` before
  Phase 4 reuses the browser transport hook.
- Periodic database snapshot persistence should be removed or connected to a defined
  recovery path.
