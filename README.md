# Trading Microservices

A local trading and risk system that exercises the complete path from market movement to a
browser-visible PnL change. Market Data publishes prices and curves, Trade Action owns trade
creation and closing, Pricing continuously values active trades, PostgreSQL stores business
history, Blotter provides read models, and a React frontend consumes snapshots plus SSE streams.

The project is intentionally small enough to inspect end to end, but it preserves the boundaries
that matter in a real system: one writer per business entity, explicit event ordering, terminal
close state, bounded queues, latest-value coalescing, and a distinction between live state and
historical records.

## System at a glance

| Component | Responsibility |
| --- | --- |
| Market Data | Generate and persist spot, futures, FX, index, and curve events; publish snapshot and SSE |
| Trade Action | Validate intents and act as the only writer of trade lifecycle state |
| Trade Generator | Produce simulated opens and closes around a bounded open-book target |
| Pricing | Consume market events, value matching active trades, persist valuations, and publish PnL |
| Blotter | Combine live caches with database history for trade- and book-oriented reads |
| Books | Own trading-book configuration |
| Monitoring | Aggregate service health and important audit events |
| React frontend | Maintain live feed context and present market, valuation, and system views |
| PostgreSQL | Source of truth for trades, valuations, books, and business audit history |

```text
market event -> Market Data publisher -> Pricing consumer
  Pricing: update spot/curve -> compute valuation -> persist valuation -> publish SSE
                                                      └──> React valuation context -> screens
trade intent -> Trade Action -> OPEN trade in DB (+audit)
  -> Pricing loop refreshes active-set from DB cache

CLOSE intent -> Trade Action -> DB close (status=CLOSED, close_price)
             -> Pricing periodic finalization loop (TRADE_REFRESH_SECONDS)
             -> final valuation (final=true, unrealized=0, realized=closed PnL) persisted and published
             -> React valuation context -> screens (terminal row state)
```

## Screen data sources

Two SSE feeds — market data and valuations — are opened once in `FeedProvider` above routing and
shared through React context, so switching screens never reconnects a stream. Everything else is
plain HTTP polling with a per-screen interval. The dividing rule: **streams carry high-frequency
values** (prices, fair value, PnL), **polls carry slow-moving state** (trade membership, config,
queue counters, health). Writes never update the client optimistically — after a successful POST
the owning poll refetches server truth out of cycle (`usePolling().refetch()`).

| Screen | Stream (shared context) | Polls | Writes |
| --- | --- | --- | --- |
| Market Data | market SSE + one-shot snapshot seed (repeated on reconnect) | — | — |
| Valuations | valuation SSE + one-shot seed; stream-only by decision — the UNREALIZED PNL summary derives from stream rows, no summary poll | — | — |
| Business Overview | valuation SSE (same shared context) | — | — |
| Trades & PnL | valuation SSE overlays live fair value / PnL by trade ID | Blotter `/trades/overview` every 5 s (membership, terms, closed history); detail drawer polls `/trades/{id}` only while open | close intent → Trade Action |
| Trade Actions | — | `/queue/status` every 2 s; monitoring audits every 3 s | trade intents → Trade Action |
| Generator | — | generator `/status` every 2 s; monitoring audits (generated intents) every 3 s; books summary every 30 s | start / stop / generate-once / config → Trade Generator |
| System Overview | none of its own — stream health is read from both shared feed contexts | monitoring `/status` every 5 s; monitoring audits (errors) every 5 s | — |
| Books | — | `/blotter/books/summary` every 5 s; `/blotter/trades?book_id&status=ACTIVE` every 5 s while a card is expanded | create / edit / delete book → Books; `REASSIGN_TRADES` → Trade Action |
| New Trade (top bar, every route) | market feed (shared context) for instrument list & quoted price | `/blotter/books/summary` once per open | `OPEN_TRADE` intents → Trade Action |

## Decisions that define the system

### Ownership is explicit

- Trade Action is the only service that changes trade lifecycle state.
- Pricing owns valuation and PnL calculation.
- PostgreSQL owns durable history; streams and caches are delivery/read models.
- Blotter may combine live and historical data, but it does not become a second writer.
- Books owns which books exist; it asks Blotter over HTTP about trades rather than reading the
  `trades` table, and refuses a destructive operation it cannot verify.

Trade closing is guarded in SQL:

```sql
UPDATE trades
SET status = 'CLOSED'
WHERE trade_id = :id AND status = 'ACTIVE'
```

Only `rowcount == 1` means the close won. A unique `client_request_id` makes resubmitting an intent
idempotent.

Retiring a book is guarded the same way, one level up: a book is deactivated only when Blotter
reports zero ACTIVE trades for it. If Blotter cannot answer, the deletion is refused rather than
allowed — `409` means the book still has positions, `503` means we could not tell.

### Tick-to-screen order

| Order | Stage | Ordering and cost |
| ---: | --- | --- |
| 1 | Market Data creates a tick | The event carries `stream_id`, monotonic `event_id`, and canonical `event_time` |
| 2 | Pricing consumes the tick | Spot/curve cache is updated before dependent trades are selected |
| 3 | Pricing selects affected trades | Spot ticks value matching symbols; curve ticks value dependent bonds |
| 4 | Pricing calculates valuations | BUY/SELL sign, multiplier, FX forward, or bond PV is applied centrally |
| 5 | Pricing persists | Each accepted valuation is currently written separately |
| 6 | Pricing checks current identity | An event superseded by a newer/final valuation is not published |
| 7 | Per-client queue receives the event | `put_nowait` prevents one slow browser from blocking Pricing |
| 8 | Browser consumes SSE | Every delivered message is parsed and normalized immediately |
| 9 | Browser applies ordering | Final valuations apply immediately; live updates coalesce latest-per-trade |
| 10 | Shared 500 ms scheduler flushes | Live state can publish twice per second; freshness advances on every second scheduler tick |
| 11 | Valuation screen derives its view | Full context → status → filter → sort → first 250 matching rows |

The expensive backend path finishes before queue publication. Increasing queue capacity can absorb
a burst, but it cannot make calculation or database persistence faster.

### Snapshot and stream are concurrent

Waiting for a snapshot before opening the stream creates a guaranteed gap, so each feed starts both
operations independently:

```text
SSE stream     -> continuous changes
HTTP snapshot  -> current-state seed and reconnect repair
```

They can arrive in either order. Domain merge rules reconcile them:

- Market Data prefers the correct stream identity and newer event sequence/time.
- A final valuation is terminal.
- Otherwise, a strictly newer valuation time wins.
- Snapshot completion merges directly; it does not replace the entire context blindly.
- A reconnect loads another snapshot to repair events missed while disconnected.

Closed trades are never classified by age. A final event immediately changes a row to `CLOSED`;
only non-final open valuations can be `LIVE` or `STALE`.

### Frontend ingestion is continuous; React publication is throttled

| Work | Current behavior |
| --- | --- |
| EventSource delivery and JSON parsing | Not throttled |
| Domain normalization | Runs for every delivered event |
| Repeated live updates for one identity | Latest value replaces the earlier value in a `Map` |
| Live React state publication | At most once per 500 ms scheduler tick |
| Final valuation publication | Immediate; terminal state bypasses the live buffer |
| Snapshot and connection status | Immediate |
| Freshness clock | Once per second, on every second 500 ms scheduler tick |
| Search, filter, and sort interaction | Immediate |

One 500 ms interval drives both cadences. Feed drains subscribe to every scheduler tick;
`useElapsedTime` subscribes to every second tick. With continuous updates, the first half-second
tick can publish feed state alone and the second publishes feed state plus freshness in one batched
React task. With empty buffers, only the one-second freshness update renders.

The feed hooks stay mounted above routing, so changing screens does not create new SSE connections.
Only the active route performs its screen-specific derivations. Market and Valuation contexts are
separate, so an unrelated feed update does not propagate through the other context.

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

Captured sorting retains each trade's comparison value, not the previous sorted array. A feed flush
creates a fresh filtered array, so sorting must run again to reconstruct the selected order before
the 250-row cap. A sorted-ID cache would need reconciliation for new trades, closures, snapshots,
reconnects, filter changes, and sort recaptures. Five complete 1,197-row sorts took about 0.8 ms in
the domain measurement, so that extra ordering state is not currently justified.

These bounds are protection, not throughput optimization.

### Current bottleneck order

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

## Important limitations

- Trade Action uses an in-process, non-durable queue. Idempotency makes retry safe, but in-flight
  work can be lost on restart.
- Trade Generator tracks open-trade IDs in memory, seeded from the Blotter at startup and
  re-synced every 10 seconds. Trades opened or closed outside the generator can take up to one
  sync interval to enter its equilibrium calculation.
- SSE is current-state delivery, not durable replay. Snapshot/reconnect repairs state but does not
  reconstruct every missed event.
- Pricing currently persists valuations one at a time and retains latest closed valuations in its
  in-memory snapshot collection for the process lifetime.
- The Blotter list is a recent working window, not a complete historical archive: active rows are
  not paginated, non-active history is bounded, and exact totals/cursors are not published.

Detailed walkthroughs are in [`docs/phase-4-notes.md`](docs/phase-4-notes.md) for the valuation
feed and performance model, and [`docs/phase-5-notes.md`](docs/phase-5-notes.md) for the operational
Blotter and trade investigation flow.
