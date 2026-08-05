---
phase: 3
status: complete
revised: 2026-08-05
tags:
  - frontend
  - market-data
  - sse
  - realtime
---

# Phase 3 — what you should know

This phase introduced real-time Market Data with a snapshot for current state and Server-Sent
Events (SSE) for incremental updates.

## 1. Snapshot and stream solve different problems

```text
GET /snapshot → complete latest-known market
GET /stream   → new observations as they happen
```

A snapshot makes initial load and reconnect recovery complete. A stream keeps the screen live
without repeatedly downloading the whole universe. The frontend starts both and merges them; it
does not wait for one before opening the other because that would create a larger event gap.

The two requests are not an atomic handoff, so a stream event can arrive before an older snapshot.
Domain ordering rules decide which value wins.

## 2. Event identity protects ordering

Generated observations carry:

- `stream_id`: identifies one backend process lifetime;
- `event_id`: monotonic sequence inside that process;
- `event_time`: when the observation was generated.

For the same process, a higher event ID wins. After a process restart, event time helps decide
whether the new process observation is newer, and accepted history for that instrument resets.
Ordering is evaluated per instrument even though event IDs are global.

The initial hard-coded backend rows still lack complete per-entity identity. A first live event can
therefore briefly lose to a late cold-start snapshot until recurring ticks correct it. A lossless
contract would require versioned initial rows plus durable cursor/replay support.

## 3. What SSE and `EventSource` mean

SSE is a long-lived HTTP response containing records such as:

```text
event: market_tick
data: {"symbol":"ACME","mid":101.03}

```

`new EventSource(url)` returns a connection object, not a Promise. The browser parses the framing
and dispatches named events.

`useSseStream` owns only transport concerns:

- create and close `EventSource`;
- register named events and parse JSON;
- report `CONNECTING`, `CONNECTED`, and `RECONNECTING`;
- retry after a fixed delay;
- remove listeners, timers, and connections during cleanup.

It does not know instruments, valuations, history, or screen policy. A ref holds the latest event
callback so React renders do not restart a healthy connection.

The current Phase 6c contract keeps streams connected across routes and while the document is
hidden. A real reconnect triggers snapshot re-seeding through `useStreamSeed`.

## 4. Feed ownership is above routing

`FeedProvider` mounts once around the application and owns `useMarketFeed`. Market Data, System
Overview, and later consumers read the same context instead of opening duplicate streams.

```text
FeedProvider
  └── useMarketFeed
      ├── useSseStream
      ├── useStreamSeed
      ├── ordered merge
      └── MarketFeedContext
```

Provider lifetime is connection lifetime. Route changes replace only the page component, so market
history and tick counts continue accumulating.

## 5. Buffering bounds React work

Wire events are processed immediately, but React state is not published for every event.
`useBufferedUpdates` keeps a mutable Map keyed by instrument; the newest update for each key wins
until the shared 500 ms clock flushes it.

```text
many wire events
→ normalize each
→ latest-per-instrument Map
→ one batch every 500 ms
→ one React state update
```

This separates arrival rate from render rate. It is coalescing, not durable history: intermediate
updates inside one window may be omitted from React state, while each instrument's bounded accepted
history keeps its latest 100 displayed observations.

## 6. Freshness and connection are separate

CONNECTED means the HTTP stream is open. LIVE/STALE describes the age of each instrument's last
browser-received value. A connected feed can contain a stale instrument, and a reconnecting feed
can still display useful last-known values.

`useElapsedTime` advances the UI clock so an instrument can become STALE even when no new event
arrives.

## 7. Market screen derivation and stable sorting

```text
context instruments → view rows → filter → captured sort → table
```

Spot/listed instruments and government-curve tenors use separate tables because their units and
sorting rules differ. `MARKET_INDEX` is a non-tradable benchmark card, not a table row.

Live sorting on a changing price would make rows jump continuously. For volatile columns,
`useTableState` captures comparison values when the user sorts. Cells keep updating, but row order
stays stable until the next explicit sort action. Structural columns such as Symbol can sort
normally.

Column visibility and order are persisted. Required columns are restored if stored preferences are
invalid, and missing/unknown IDs safely fall back to current defaults.

## 8. Responsive and visual rules

- Container queries react to the content column's width, not the whole viewport.
- Wide tables scroll horizontally instead of compressing numeric data.
- Sparklines are small inline SVGs with a fixed history cap.
- Price direction uses positive/negative color; LIVE uses a separate freshness color.
- Reduced-motion preferences disable row/panel animations.

## Backend delivery boundary

The market service keeps current state in memory and persists event history separately. A lock
protects event-ID allocation and coherent snapshot copies; database work happens after releasing
the lock so slow persistence does not freeze generation.

Each SSE client has a bounded queue. A slow client cannot block the publisher; overflow drops an
incoming event and preserves the memory bound. This is suitable for current-state recovery because
a later tick/snapshot repairs the latest value, but it is not an auditable tick tape.

## Mental model

```text
generator → current state + event identity
   ├── GET /snapshot ─────────────────────┐
   └── bounded SSE client queue → /stream ├──> useMarketFeed
                                         │      ├── ordered merge
                                         │      ├── bounded history
                                         │      └── MarketFeedContext
                                         └──> Market Data + System Overview
```

## Limits to remember

- SSE/current snapshots do not provide exactly-once history or replay.
- Cold-start rows still need complete per-entity identity for a perfect snapshot/stream handoff.
- Queue drops are bounded but not yet exposed as strong operational metrics.
- Three simultaneous HTTP/1.1 app tabs can exhaust the connection budget; transport multiplexing
  or HTTP/2 is the future fix.

## Main files

- `frontend/src/hooks/useSseStream.js`, `useMarketFeed.js`, and `useStreamSeed.js`.
- `frontend/src/providers/FeedProvider.jsx` and `feedContext.js`.
- `frontend/src/domain/marketData.js` and `marketFormat.js`.
- `frontend/src/hooks/useTableState.js` and `components/tables/DataTable.jsx`.
- `frontend/src/views/MarketData/MarketData.jsx`.
- `services/market-data-service/app/` — generator, persistence, publisher, and API.
