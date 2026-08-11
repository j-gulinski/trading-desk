# Performance notes

The measured behavior behind the README's performance summary: how frontend ingestion is
throttled, which optimizations exist and what they trade away, where the bottlenecks were
observed, and which optimization is planned for each growth symptom.

## Frontend scheduling details

One 500 ms interval drives both frontend cadences. Feed drains subscribe to every scheduler tick;
`useElapsedTime` subscribes to every second tick. With continuous updates, the first half-second
tick can publish feed state alone and the second publishes feed state plus freshness in one batched
React task. With empty buffers, only the one-second freshness update renders.

The Valuations screen retains the complete client collection:

```text
all valuations in context
-> add LIVE / STALE / CLOSED status
-> class, book, state, and text filters
-> captured-value sort
-> render matchingRows.slice(0, 250)
```

The 250 limit is a DOM boundary, not data eviction. PnL summaries and filters still use the complete
collection, and searching can bring an older closed trade into the visible window. Market
sparklines are memoized so unchanged instruments do not rebuild their SVG geometry.

The Trades & PnL screen uses a different ownership split:

```text
five-second Blotter snapshot
-> durable trade membership, terms, lifecycle and recent closed history
-> overlay newest Pricing-context valuation by trade ID
-> Open/Closed, book, class and text filters
-> captured sort
-> render at most 250 matching rows
-> load valuation history and audits only for the selected trade
```

This keeps historical investigation out of app-lifetime feed state. Closed realized PnL falls back
to the persisted Blotter valuation, so it does not depend on Pricing's process-local cache.

Captured sorting retains each trade's comparison value, not the previous sorted array. A feed flush
creates a fresh filtered array, so sorting must run again to reconstruct the selected order before
the 250-row cap. A sorted-ID cache would need reconciliation for new trades, closures, snapshots,
reconnects, filter changes, and sort recaptures. Five complete 1,197-row sorts took about 0.8 ms in
the domain measurement, so that extra ordering state is not currently justified.

## Current optimizations and their tradeoffs

| Choice | Benefit | Deliberate tradeoff |
| --- | --- | --- |
| Generated open-book equilibrium around 300 tracked trades | Prevents pricing demand from growing forever | Shapes demonstration load; it does not increase Pricing throughput |
| Pricing queue of 5,000 events per client | Absorbs a large valuation burst with bounded memory | Cannot fix sustained calculation or database-write overload |
| Market Data queue of 500 events per client | Bounds the smaller market stream | A persistently slow client can still lose intermediate events and rely on snapshot repair |
| Latest-per-identity browser `Map` with a 500 ms flush | Collapses repeated live updates and limits React publication to twice per second | Every delivered event is still parsed and normalized; intermediate display states are intentionally skipped |
| One shared scheduler for feed flushes and the one-second freshness clock | Avoids independent timers and lets React batch coincident work | A live update can wait up to one half-second before publication |
| Filter all rows, then sort all matches on each render | Keeps one simple, deterministic pipeline for flushes and user interactions | Costs O(n) filtering plus O(m log m) sorting instead of maintaining incremental indexes |
| Sort before taking the first 250 matches | Guarantees that the visible window is the correct top 250 for the selected order | Sorting still sees every matching row even though only 250 reach the table |
| Render only the first 250 matching valuations | Bounds React element, DOM-cell, and paint work without discarding data | Full context, summaries, filters, and sorting still scale with all retained valuations |
| Poll Blotter membership and overlay the shared valuation feed | Keeps durable trade facts separate from changing values without another live cache | A new trade can wait up to five seconds to enter the table |
| Load trade valuation/audit history only in the selected-trade dialog | Keeps history out of every live table render | Investigation data refreshes on a slower poll and currently returns bounded recent history |
| Memoized sparklines and bounded instrument history | Avoids rebuilding unchanged SVG geometry and bounds history memory | Market events still have to update the affected instrument and its bounded history |

These bounds are protection, not throughput optimization.

## Current bottleneck order

The first end-to-end scaling limit is Pricing persistence:

```text
receive one market tick
-> find affected open trades
-> for each trade:
     calculate one valuation
     open a database session
     INSERT and commit one valuation
-> publish the completed valuation events
-> process the next market tick
```

This work is sequential in the market-stream consumer. At roughly 2,100 open trades, Pricing had
to calculate and persist about 1,000 valuations per second, and rows became stale before browser
rendering was the primary constraint. The 5,000-entry client queue is downstream of calculation and
persistence: it absorbs a publication burst but cannot accelerate the producer. The highest-value
server optimization at that scale is inserting all valuations affected by one tick in one database
transaction.

The observed limits, in order, are:

1. **System throughput:** per-valuation database transactions in Pricing.
2. **Frontend work:** React reconciliation, DOM updates, and paint for many simultaneously changing
   visible rows.
3. **Lifetime-history growth:** snapshots, context, summaries, statuses, and filtering still process
   every retained valuation.
4. **Sorting:** currently negligible compared with the preceding work.

The frontend evidence supports that ordering. Removing row flash eliminated measured long tasks at
447 rows. Rendering 1,197 rows produced 361–472 ms tasks; limiting the table to 250 reduced them to
102–192 ms. In contrast, five complete 1,197-row domain sorts took about 0.8 ms in total. The
remaining capped tasks include per-event ingestion, full-context derivation, React reconciliation,
and DOM work; the long-task observer does not isolate those costs further.

## Options when valuation volume grows

Choose the optimization from the observed bottleneck rather than adding all of them:

| Symptom | Next option | Why |
| --- | --- | --- |
| Pricing falls behind while open trades grow | Batch valuation inserts once per market tick | Removes transaction/round-trip overhead from the hottest server path |
| Closed history makes snapshots and context grow | Keep live/open valuations in context; load closed history on demand | Stops inactive history from participating in every clock render |
| Users need large closed-history searches | Server-side filtering and cursor pagination | Bounds response size, browser memory, filtering, and sorting |
| Client summaries must cover data no longer loaded | Publish/query server-side aggregates | Avoids downloading history only to calculate totals |
| DOM commit dominates with hundreds of visible rows | Virtualize the table | Renders only viewport rows while preserving navigation through all matches |
| EventSource dispatch/JSON parsing dominates | Publish valuation batches per tick | Reduces message and parse overhead without discarding latest values |
| Same trade is updated repeatedly inside one window | Coalesce raw updates before normalization | Avoids normalizing values that will be overwritten |
| Final events must be lossless across disconnects | Add event identity, durable replay, and resume cursors | Snapshot repair gives eventual state, not an auditable event stream |
| Book-risk sampling slows as retained valuation history grows | Maintain incremental per-book PnL totals updated at valuation-write time | The per-tick snapshot currently walks every retained valuation under the cache lock; running totals make it O(books) |
| Book-risk regression cost grows with window size or book count | Rolling sums or an EWMA covariance instead of full-window recompute | The stateless O(books × window) recompute is drift-free and unmeasurable at 7 books × 100 samples, so it stays until the scale changes |

A practical production shape would separate two workloads:

```text
live risk:
GET /valuations?state=open
+ valuation SSE
+ compact server aggregates

historical investigation:
GET /valuations?state=closed&cursor=...&limit=...
+ server-side search/filter/sort
+ per-trade valuation history on demand
```

At the current 300-open-trade demonstration target, the existing half-second coalescing and 250-row
window remain intentionally simpler. Server pagination or on-demand closed valuations become the
right next step when lifetime history, rather than live risk, is what grows.
