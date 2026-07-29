---
phase: 4
scope: prompted implementation notes
updated: 2026-07-29
---

# Phase 4 — Valuation stream and frontend flow

This is a focused learning note for the questions raised during the valuation performance review.
It is not a full phase audit.

## What changed

| Area | Current behavior | Reason |
| --- | --- | --- |
| Pricing client queue | 5,000 events per connected client | Absorb full-book valuation bursts larger than the old 500-event Market Data queue |
| Market Data client queue | Still 500 events | It has different event cardinality and did not need the valuation-specific increase |
| Frontend scheduler | One shared 500 ms timer | Flush live feeds twice per second and refresh freshness on every second scheduler tick |
| Valuation table | At most 250 matching rows rendered | Bound React and DOM work without deleting data |
| Valuation state filter | `ALL / LIVE / STALE / CLOSED` select | Inspect each exact state instead of conflating LIVE and STALE as “active” |
| Final valuations | Published only while current and applied immediately in the browser | A closed trade must become CLOSED and must never age into STALE |
| Row flash | Disabled | It caused expensive remount/reconciliation work during live updates |
| Market sparklines | Memoized and slightly larger | Skip unchanged charts and make the trend easier to read |
| Generated open-book target | 300 open trades | Exercise the bounded frontend with more live valuations without returning to unbounded growth |

The half-second feed cadence permits up to roughly 500 ms of buffered display latency, about 250 ms
on average. Freshness still changes only once per second. This reduces React publication frequency
relative to the wire stream; it does not reduce the number of events arriving from the server.

## Allowing more open trades without unbounded growth

The configured target is now 300 open trades. It is an equilibrium target, not a hard cap:

```text
p_close = min(0.9, 0.5 * trackedOpenTrades / 300)
```

At zero tracked trades the generator opens. At 150 it chooses a close roughly 25% of the time. At
300, open and close each have roughly 50% probability, so expected growth is zero. Random movement
around the target is normal, while counts above the target receive a stronger downward bias.

This source-side bound is the most valuable scale control because it prevents the pricing workload
from growing forever. The generator still emits only one open-or-close action per configured
1,500 ms interval; raising the target permits a larger live book but does not create a sudden
300-trade burst.

The generator currently tracks its managed open IDs in process memory. The running service was
recreated to load the new target, so the approximately 42 database trades left by the prior process
are not in the new process's tracking Map. This run can therefore settle somewhat above 300 total
database-open trades. Seeding generator state from the active blotter is a separate correctness
improvement; it was not added to this focused performance change.

## First mental model: ownership from the application down

```text
main.jsx
└─ FeedProvider
   ├─ useMarketFeed()
   │  └─ MarketFeedContext
   └─ useValuationFeed()
      └─ ValuationFeedContext

route screen
└─ useMarketFeedContext() or useValuationFeedContext()
```

The feed hooks own long-lived transport and state. The provider mounts them above the router, so
changing screens does not create a new SSE connection. Screens consume already-prepared context;
they do not open streams themselves.

The published context values are:

```text
MarketFeedContext:
{ instruments, tickCount, status, seedStatus }

ValuationFeedContext:
{ valuations, status, seedStatus }
```

`instruments` and `valuations` are keyed objects, not arrays:

```text
instruments[instrumentId] = latest instrument
valuations[tradeId]       = latest valuation
```

There is no third curve-object collection in context. A curve event is normalized into one RATE
instrument per configured tenor and stored inside `instruments`. The Market Data screen later
separates RATE instruments from spot/listed instruments for presentation.

## The hook contract: pass the flush implementation in, get the push function out

The most useful way to read the buffering hook is:

```text
useBufferedUpdates(onFlush) -> pushUpdate
```

The valuation feed passes the operation that is specific to valuation state:

```js
const pushUpdate = useBufferedUpdates((pending) => {
  setValuations((previous) => mergeValuations(previous, pending))
})
```

Two callbacks travel in opposite directions:

```text
useValuationFeed
    |
    | passes onFlush(pending)
    v
useBufferedUpdates
    |
    | returns pushUpdate(key, update)
    v
useValuationFeed's SSE handler
```

The feed is saying:

> When the generic buffer decides to drain, merge the pending valuations into my React state.

For ordinary live updates, the generic hook replies:

> Call this `pushUpdate(key, update)` function whenever one bufferable stream update arrives.

The same generic hook works for Market Data because that feed supplies a different concrete flush:

```js
const pushUpdate = useBufferedUpdates((pending) => {
  setInstruments((previous) => mergeInstruments(previous, pending))
  setTickCount(receivedTicksRef.current)
  storeTickCount(receivedTicksRef.current)
})
```

The buffer owns timing and latest-per-key coalescing. Each feed owns normalization, identity, merge
rules, state setters, and any feed-specific side effects.

## Complete valuation-stream flow

```text
1. FeedProvider mounts useValuationFeed.
2. useValuationFeed passes its valuation onFlush callback to useBufferedUpdates.
3. useBufferedUpdates stores the latest callback in onFlushRef.
4. useBufferedUpdates subscribes an internal drain callback to streamClock.
5. useBufferedUpdates returns pushUpdate(tradeId, update).
6. useSseStream opens EventSource and parses a valuation_update message.
7. valuationOf(data) validates and normalizes the wire payload.
8. The SSE handler branches:
   a. a final valuation runs mergeValuations + setValuations immediately;
   b. an ordinary live valuation calls pushUpdate(tradeId, valuation).
9. For a live valuation, the buffer Map stores it under tradeId.
10. Another live event for the same tradeId replaces that Map entry.
11. The next shared 500 ms scheduler tick calls the drain callback.
12. For buffered live updates, the drain:
    a. does nothing if the Map is empty;
    b. copies distinct pending values into an array;
    c. replaces the Map with a new empty Map;
    d. calls the latest onFlushRef.current(pending).
13. The valuation callback runs mergeValuations and setValuations.
14. ValuationFeedContext publishes the new keyed object.
15. Mounted context consumers render from the new state.
```

The Map changes without setting React state, so individual live events do not render the
application. Within one clock window it performs work per distinct trade ID at flush time, rather
than per event. It still has to dispatch, JSON-parse, normalize, and write every live wire event
before coalescing.

Final valuations deliberately bypass that throttle. They are rare, terminal business events, and
must immediately change the row from LIVE/STALE to CLOSED. A later buffered live value cannot undo
the transition because `mergeValuation` treats an existing final valuation as terminal.

### Why `onFlushRef` exists: one subscription, current behavior

A React function component is not one function invocation that remains alive forever. React calls
`useValuationFeed()` again on every feed render. Each invocation executes this expression again and
creates a new function object:

```js
(pending) => {
  setValuations((previous) => mergeValuations(previous, pending))
}
```

Think of those separate function objects as `onFlush1`, `onFlush2`, and `onFlush3`:

```text
feed render 1 creates onFlush1
feed render 2 creates onFlush2
feed render 3 creates onFlush3
```

Meanwhile, the clock subscription is deliberately installed by an effect with an empty dependency
array:

```js
useEffect(() => subscribeToStreamClock(drain), [])
```

That means:

```text
mount feed      -> subscribe drain once
rerender feed   -> keep the same subscription
rerender again  -> keep the same subscription
unmount feed    -> unsubscribe drain
```

If `drain` directly captured `onFlush1` when the effect first mounted, it would keep calling
`onFlush1` forever. That is a **stale closure**: the long-lived subscriber remembers the variables
from the render in which it was created.

Putting `onFlush` in the effect dependency array would avoid the stale closure, but the inline
function has a new identity on every render. React would therefore unsubscribe and resubscribe the
clock callback after every feed render. That is unnecessary subscription churn.

`useRef` separates the two lifetimes:

```js
const onFlushRef = useRef(onFlush)
onFlushRef.current = onFlush
```

The ref object itself has stable identity across renders, while its `.current` field can point at a
different function:

```text
render 1: sameRef.current = onFlush1
render 2: sameRef.current = onFlush2
render 3: sameRef.current = onFlush3

clock tick:
drain reads sameRef.current now
-> calls onFlush3
```

The subscribed `drain` function closes over `sameRef`, whose identity never changes. It does **not**
permanently copy the value of `sameRef.current`. Reading `.current` inside the clock callback delays
the lookup until the tick actually happens. “Callback from the latest feed render” therefore means
the newest function object assigned during the most recent feed invocation—not the first function
captured when the subscription mounted.

In the current valuation callback, the state update also uses React's functional form:

```js
setValuations((previous) => mergeValuations(previous, pending))
```

`previous` is supplied by React when it processes the update. It is not a `valuations` object
captured from an earlier render. These are two different stale-data protections:

- `onFlushRef.current` selects the current callback implementation;
- `setValuations(previous => ...)` merges into the current React state.

### Why `bufferRef` exists: persistent mutable work that does not render

`bufferRef` solves a different problem:

```js
const bufferRef = useRef(new Map())
```

The same ref container survives every feed render. Stream handlers can mutate its Map:

```js
bufferRef.current.set(tradeId, valuation)
```

React does not observe ref mutations, so this does not schedule a render. That is exactly what the
buffer needs:

```text
event A1 -> Map { A: A1 }       -> no render
event B1 -> Map { A: A1, B: B1 } -> no render
event A2 -> Map { A: A2, B: B1 } -> no render; A1 is coalesced
clock    -> one pending [A2, B1] -> one state publication
```

An ordinary local variable would not work:

```js
const buffer = new Map()
```

Every render would create a new Map, while older event callbacks could still point at the Map from
an earlier render. Making the Map React state would also be wrong for this purpose: every
`set(key, update)` would require publishing state and could render per event, which is the work the
buffer is meant to avoid.

At flush time the hook swaps the Map before calling the feed callback:

```js
const pending = Array.from(bufferRef.current.values())
bufferRef.current = new Map()
onFlushRef.current(pending)
```

The flushed batch is now detached. Any event arriving after the swap writes into the fresh Map and
waits for the next clock tick; it cannot mutate the batch currently being merged.

In one sentence:

```text
onFlushRef keeps the installed subscriber's behavior current;
bufferRef keeps event accumulation persistent but outside rendering.
```

## The shared scheduler: two feed flushes for one freshness tick

`streamClock.js` owns one module-level subscriber set and one 500 ms interval. A subscription states
how often it wants to run:

```text
subscribeToStreamClock(callback, intervalMs)
```

The scheduler converts that interval into a number of base ticks:

```text
feed drain:  500 / 500 = every 1 tick
freshness:  1000 / 500 = every 2 ticks
```

`useBufferedUpdates` uses the default 500 ms interval. A mounted screen's `useElapsedTime` explicitly
requests 1,000 ms:

```js
useEffect(
  () => subscribeToStreamClock(setNow, FRESHNESS_INTERVAL_MS),
  [],
)
```

The timeline is:

```text
0.0 s   buffers collect events

0.5 s   base tick 1
        ├─ drain Market Data if pending
        ├─ drain valuations if pending
        └─ do not update freshness

1.0 s   base tick 2
        ├─ drain Market Data if pending
        ├─ drain valuations if pending
        └─ setNow(the same captured time)

1.5 s   base tick 3 -> feeds only
2.0 s   base tick 4 -> feeds + freshness
```

With continuous data, this permits two feed-state publications for every one freshness update. On
the second tick, feed state and `setNow` enter React from the same timer task and can be batched into
one commit. On the first tick, only a non-empty feed can render. If both buffers are empty, tick 1
does nothing and only the one-second freshness update renders on tick 2.

This uses one timer rather than independent 500 ms and 1,000 ms intervals. Separate timers could
drift and produce a feed render immediately followed by a freshness-only render. The tick divisor
keeps the 2:1 cadence aligned and stops the timer entirely when the last subscriber unmounts.

## Where throttling happens—and where it does not

The browser does not throttle or pause the SSE connection. It continuously consumes every message
the server delivers. The optimization boundary is between event ingestion and React publication:

| Layer | Current behavior |
| --- | --- |
| Trade generator | Targets roughly 300 open trades instead of allowing unlimited open-book growth |
| Pricing publication | Enqueues only the valuation that is still current; a full per-client queue drops rather than blocking |
| `EventSource` / `useSseStream` | No throttle: dispatches and parses every delivered message immediately |
| Feed event handler | Normalizes every message immediately |
| `useBufferedUpdates` Map | Coalesces repeated updates by identity; only the latest value per key survives until flush |
| Live feed React state | Publishes a non-empty pending batch at most once per 500 ms scheduler tick |
| Final valuation React state | Not throttled; terminal close state merges immediately |
| Snapshot | Not throttled; merges immediately when the request completes |
| Connection status | Not throttled; CONNECTED/RECONNECTING changes publish immediately |
| Filters, search, and sort clicks | Not throttled; local user interaction renders immediately |
| Freshness | Updates every second scheduler tick: once per 1,000 ms |
| Monitoring polling | Independent of streams; `usePolling` defaults to one request every five seconds |

This does **not** mean only two network events are processed per second. If 1,000 live events arrive
in a second, all 1,000 are dispatched, parsed, normalized, and written to the Map. The Map is drained
twice, so React receives at most two latest-per-trade batches. Repeated updates for one trade within
one half-second window collapse to that window's latest value. Any final valuation takes the
immediate terminal path instead.

### Efficiency of each stream-consuming screen

Only the active route screen is mounted, but both feed hooks remain mounted in `FeedProvider`. This
keeps one connection per feed while avoiding table/summary derivation for off-screen routes.

The separate Market and Valuation contexts also limit propagation. Both feed results are memoized,
so a valuation update does not change the Market context value and a market update does not change
the Valuation context value. System Overview intentionally consumes both.

| Screen | Work on a shared clock tick | Render boundary |
| --- | --- | --- |
| Market Data | Derive current instrument rows and freshness | Instrument universe is small; unchanged sparklines can skip through `React.memo` |
| Valuations | Derive status for all valuations, summaries, filters, sort matches | At most 250 table rows enter React/DOM |
| Business Overview | Scan all valuations for totals and group by book | DOM scales with books, not trades |
| System Overview | Scan both feeds for compact summaries | DOM stays small; independent monitoring/audit polls can also render |

On every second scheduler tick, pending feed publication and the active screen's freshness update
occur in the same timer task and can be one React commit. The intervening tick can publish feed
state alone. With no pending data, the screen still renders only once per second for freshness.
Snapshot completion, connection changes, polling responses, and user interactions can render
between scheduler ticks because they are deliberately not delayed.

The Valuations screen is therefore bounded for DOM work but not for all CPU or memory work. Its
full-context O(n) derivations remain simple and measured sorting is cheap, but closed-history growth
eventually calls for server-side pagination or on-demand history rather than more client-side
throttling.

## Snapshot flow and how it meets the stream

Each feed starts two independent activities after mounting:

```text
useValuationFeed
├─ useSseStream(GET /valuation-stream)
└─ useStreamSeed(GET /valuations)

useMarketFeed
├─ useSseStream(GET /stream)
└─ useStreamSeed(GET /snapshot)
```

The stream provides changes. The snapshot provides current state for initial load and repairs state
after a reconnect. `useStreamSeed` loads on mount and again on a
`RECONNECTING -> CONNECTED` transition.

Snapshots do not use `useBufferedUpdates`. They merge directly into state and may cause an
immediate render because they are rare reconciliations, not continuous traffic.

Snapshot and SSE can arrive in either order. Domain merge rules decide which value wins:

- a final valuation is terminal;
- otherwise, a strictly newer valuation timestamp wins;
- Market Data compares its stream/event identity and time rules.

This prevents a slower snapshot response from blindly overwriting a newer stream value.

## What happens after valuation context reaches the screen

The Valuations JSX pipeline is:

```text
valuations keyed object
-> Object.values(valuations)
-> valuationRowsOf(values, now)
-> apply class/book/state/search filters
-> sortValuationRows(filteredRows, capturedSort)
-> matchingRows.slice(0, 250)
-> ValuationTable
-> DataTable
```

### `valuationRowsOf`

`valuationRowsOf` is a view adapter. It does not aggregate or copy all valuation fields. It wraps
each valuation reference:

```js
{
  valuation,
  status
}
```

Status is:

- `CLOSED` when the valuation is final;
- otherwise `LIVE` when browser receipt age is at most ten seconds;
- otherwise `STALE`.

The order is intentional: CLOSED is decided before age. A final valuation can never be STALE.

The status depends on `now`, which explains why the screen needs a clock render even if valuation
state did not change.

### Why `0C20C6C1` and `F3C1F86D` incorrectly appeared STALE

Pricing held final valuations for both trades, but the browser held the live valuations immediately
before them. For example, `F3C1F86D` displayed the live value at `22:22:14.165`, while pricing held
the final value at `22:22:14.167`.

The pricing market thread can finish recording a live batch, then the refresh thread can record and
publish a close before the market thread finishes publishing its already-created batch. The old
publisher could therefore enqueue the superseded live value after the final value. In the browser's
latest-per-trade Map, that late live arrival replaced the final before the scheduled flush.

The repair has two parts:

1. Pricing holds its valuation-state lock while confirming the object is still the current cached
   valuation and enqueueing it. A superseded live object is not published.
2. The browser applies a received final valuation immediately. It does not wait in the live-update
   Map, and the terminal merge rule rejects any older live update already pending.

After pricing reconnected and the snapshot reconciled existing browser state, both IDs rendered as
CLOSED and the screen showed zero stale rows.

### Filtering and search

Class, book, exact valuation state, and search selections are local React state in the screen. The
state select offers All states, LIVE, STALE, and CLOSED with full-collection counts. A feed flush
does not clear these selections. The new context value makes the component run the same pipeline
again with the current filter values.

There is no incremental filtering or second filtered-state collection:

```text
new context or filter value
-> run the predicates over all rows
-> produce a new matching array
```

Search trims and lowercases the query once, then checks trade reference, book name, and symbol for
each row. Filtering is O(n), which is simple and efficient for this dashboard scale. Maintaining
indexes would add synchronization paths for updates, closes, snapshots, and reconnects.

The buffer is unaware of filters. A hidden valuation continues to receive and merge updates, so it
is current as soon as the filter is removed.

### Sorting

Filtering runs before sorting. If a search leaves 30 matches, only those 30 rows are sorted.
JavaScript array sorting is normally O(m log m) for `m` matching rows.

Captured sorting freezes comparator values for live-changing columns:

```text
sort selection/capture
-> { tradeId: valueAtCapture }
-> later flush uses those captured values
-> cell values change while visible row order remains stable
```

Captured sorting freezes **the comparison value for each trade**, not a previously sorted array.
That distinction is why a flush still needs to sort.

Each Valuations render rebuilds the candidates:

```text
valuation object in context
-> Object.values(...)
-> derived row objects
-> current filter predicates
-> new matchingRows array
-> sort with the captured comparison values
```

The previous render's `matchingRows` is only a local variable. React does not retain it for the next
render, and the feed context is keyed by trade ID rather than stored in the selected display order.
The filter also creates a fresh array whose order is inherited from that keyed source, not from the
last table render. `sortRows` therefore clones that fresh array with `[...rows]` and reapplies the
selected order.

For example, suppose the source enumeration produces `[B, C, A]`, while captured unrealized PnL is:

```text
A = 900
B = 500
C = -100
```

Sorting descending produces `[A, B, C]`. After a flush, the cell values may have changed and the
component again receives a newly derived `[B, C, A]`; the captured map still supplies `900`, `500`,
and `-100`, so `Array.sort` reconstructs `[A, B, C]`. The order looks unchanged to the user, but it
was recalculated from a new array.

Skipping that sort would have two correctness effects:

1. The table would fall back to object insertion order instead of the order selected in the header.
2. `slice(0, 250)` could select the wrong 250 trades. Sorting must happen before the display cap so
   the visible rows are the top 250 **under the current filters and selected sort**.

Re-sorting is also what deterministically incorporates a newly opened trade, removes a trade that
no longer matches a filter, and restores matching trades after a search or state filter is cleared.
Equal values use the trade reference as a tie-breaker, so repeated sorts remain stable.

It would be possible to retain a sorted-ID list, but that cache would need reconciliation for new
trades, status changes, snapshots, reconnects, filter membership, and every new sort capture. That
would create a second ordering state for very little saved work. The measured domain work was
small: five complete 1,197-row sorts took about 0.8 ms, so the simpler full sort is justified.

### Summaries and the 250-row cap

PnL summaries, LIVE/STALE counts, book risk, filter counts, and matching-row count use the complete
row collection. Only the table receives the first 250 sorted matches:

```text
all rows -> summaries
all rows -> filters -> sort -> first 250 -> table
```

The cap is non-destructive. For example:

```text
1,197 valuations remain in context
-> STATE = CLOSED selects only final valuations
-> sort the closed matches
-> render at most 250
```

When STATE returns to All states, the screen derives rows again from all 1,197 context entries. An
older closed row may fall beyond the first 250 under the current filters and sort, but it was not
deleted. Selecting CLOSED or searching its trade, book, or symbol can bring it into the visible 250
immediately.

This models a real blotter distinction between the complete working set and the visible window:
filters/search operate on the complete set before selecting what is rendered. This screen is the
dashboard-sized version of that pattern. A full production blotter would add pagination or row
virtualization so the user can navigate every match; this implementation instead discloses
“250 of N” and asks the user to narrow the result.

## Valuation performance findings

Observed in the development application:

| Table behavior | Rows rendered | Long tasks |
| --- | ---: | --- |
| Flash on | 447 | 5 at 137–224 ms |
| Flash off | 447 | None |
| Flash off | 1,197 | 8 at 361–472 ms |
| Flash off, capped | 250 | 4 at 102–192 ms |

Removing flash was clearly worthwhile. The cap also materially reduced the worst tasks, but it did
not eliminate them because there are three distinct workloads.

### Per wire event

- EventSource dispatch;
- JSON parsing;
- normalization;
- one Map write.

The table cap and Map coalescing do not remove this work.

### Per non-empty flush

- copy distinct Map values to `pending`;
- apply valuation merge rules;
- clone the keyed state once when the first update is accepted;
- publish the new context value.

### Per Valuations-screen render

- create status rows for the complete context collection;
- compute summaries, books, and filter options;
- filter and sort;
- construct React elements for at most 250 table rows;
- reconcile and update DOM cells.

The browser long-task observer measures the whole main-thread task, so it does not identify which
category owns each millisecond. The cap reducing 361–472 ms tasks to 102–192 ms proves rendering is
material. The tasks remaining after the cap show that total event and collection size also matter.

### Is 250 viable?

Yes, as a dashboard safety boundary. The 447-row flash-off result had no observed long tasks, and
the open book is now bounded. The Compose environment and source fallback now target about 300 open
trades.

The cap is not a complete production-blotter scaling strategy. Closed valuations accumulate, so
the snapshot, context collection, summaries, and filters continue growing even though only 250 rows
render. With continuous live data those full-context derivations can run on both half-second feed
flushes; without data, freshness still traverses them once per second.

Before adding more frontend machinery, profile a production build:

- if React render/commit dominates, a lower disclosed cap is the simplest next lever;
- if users must browse hundreds of matches, use virtualization or pagination;
- if EventSource/JSON work dominates, batch multiple valuations into one stream event;
- if overwritten same-trade events dominate, consider buffering raw events and normalizing only
  the latest event per trade at flush;
- if lifetime closed history dominates, move filtering/pagination to the server and load closed
  history on demand.

`React.memo` on valuation rows is unlikely to help the high-live-traffic case because nearly every
visible open trade receives a new valuation object each flush. `useMemo` around the full pipeline
also misses whenever valuation state or `now` changes. Incremental PnL totals would save cheap
arithmetic while adding subtract-old/add-new correctness paths. These were intentionally not added.

## Pricing queue: what 5,000 fixes and what it does not

Each pricing-stream client now receives a bounded 5,000-entry FIFO. `put_nowait` prevents a slow
client from blocking the pricing publisher. The larger capacity can absorb more than two complete
2,100-trade publication bursts, whereas 500 was too small for one.

The queue is after the expensive work:

```text
market tick
-> find matching open trades
-> value every matching trade
-> persist each valuation
-> build the completed event batch
-> publish events to each client queue
```

Increasing the queue provides burst headroom; it does not make valuation or persistence faster. If
events enter the queue faster than the client drains them for long enough, 5,000 will also fill and
events will be dropped.

A dropped open-trade valuation normally self-heals on a later market tick. A final closed valuation
is a one-shot event, so a dropped final event is repaired by the next snapshot/reconnect rather
than another live valuation.

The current-object publication check solves a different problem from queue capacity. It prevents an
already-built live event from being enqueued after a newer final event. It does not turn the queue
into durable delivery.

If thousands of simultaneously open trades become a real requirement, the first server-side
optimization is batching valuation persistence per market tick. Queue depth/drop metrics and
separating latest-state publication from historical persistence would then be more valuable than
repeatedly increasing queue capacity.

## Sparkline optimization

`Sparkline` is wrapped in `React.memo`. When the Market Data screen rerenders but an instrument's
`values` array and other props retain their references, React skips recalculating that SVG.

The chart is also slightly larger, uses internal padding, centers a flat series, rounds line joins,
and has a larger endpoint. Its accessible description now says whether the observed trend is
rising, falling, or flat.

This optimization applies to Market Data. It does not affect Valuation table performance.

## Navigation affordances reviewed

The Business Overview `OPEN TRADES` stat is now a real link to `#/valuations`; the entire card is
keyboard-focusable and clickable. The existing “alpha/beta in Valuations & Risk →” panel link was
already a real anchor and remains unchanged.

The global `New trade` control was a button with no handler or implemented creation destination. It
was removed instead of presenting a false action. Other reviewed arrows, sidebar entries, table
sort controls, filters, and column controls already have matching behavior.

## What `positionsOf` means

`positionsOf(rows)` is an unused domain projection equivalent to:

```text
GROUP BY book_id, symbol
```

It combines open trade tickets into a position containing net and gross quantity, weighted entry,
signed market value, unrealized PnL, notional, latest price, and worst-case freshness.

It is not a hook, not context state, and not executed by the current Valuations screen. It remains
available for a future position- or book-oriented view.

## Focused reading order

1. `frontend/src/hooks/streamClock.js`
2. `frontend/src/hooks/useBufferedUpdates.js`
3. `frontend/src/hooks/useSseStream.js`
4. `frontend/src/hooks/useStreamSeed.js`
5. `frontend/src/hooks/useValuationFeed.js`
6. `frontend/src/hooks/useMarketFeed.js`
7. `services/pricing-service/app/valuation_publisher.py`
8. `frontend/src/providers/FeedProvider.jsx`
9. `frontend/src/providers/feedContext.js`
10. `frontend/src/domain/valuations.js`
11. `frontend/src/views/Valuations/Valuations.jsx`
12. `frontend/src/views/BusinessOverview/BusinessOverview.jsx`
13. `frontend/src/components/cards/StatCard.jsx`
14. `frontend/src/components/charts/Sparkline.jsx`
