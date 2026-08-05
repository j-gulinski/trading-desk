---
phase: 4
status: complete
revised: 2026-08-05
tags:
  - frontend
  - valuations
  - realtime
  - performance
---

# Phase 4 — what you should know

This phase added the valuation feed, Valuations & Risk, and live PnL on Business Overview. Its main
lesson is how to process many stream events without rendering for every message.

## 1. Valuations reuse the Market Data transport

`useValuationFeed` reuses `useSseStream` and `useStreamSeed`. Transport stays generic; the feature
hook owns valuation normalization, merge rules, and state.

Both feeds live in `FeedProvider` but publish separate memoized contexts. A valuation update does
not change the market context value, and a market update does not change the valuation context.

```text
FeedProvider
  ├── useMarketFeed    → MarketFeedContext
  └── useValuationFeed → ValuationFeedContext
```

## 2. `useBufferedUpdates` separates arrival from rendering

The reusable contract is:

```text
useBufferedUpdates(onFlush) → pushUpdate(key, update)
```

Each live event is normalized and written to a Map. Repeated values for the same trade replace one
another until the shared clock drains the latest values.

```text
A1 → {A:A1}
B1 → {A:A1, B:B1}
A2 → {A:A2, B:B1}
500 ms clock → publish [A2, B1] once
```

`bufferRef` holds mutable pending work without causing renders. `onFlushRef` lets the long-lived
clock subscription call the newest flush callback without unsubscribing on every React render.

The state setter also uses its functional form:

```js
setValuations(previous => mergeValuations(previous, pending))
```

This ensures the merge uses React's current state rather than a stale render closure.

## 3. One shared clock coordinates feeds and freshness

`streamClock` owns one 500 ms timer. Feed buffers subscribe every base tick; freshness clocks run
every second tick.

```text
0.5 s → flush non-empty market/valuation buffers
1.0 s → flush buffers + update freshness time
```

One aligned scheduler avoids several drifting timers and stops when its final subscriber unmounts.
The browser still parses every network event; only React publication is throttled.

## 4. Final valuations are terminal

Ordinary live valuations use the 500 ms buffer. A final/closed valuation bypasses the buffer and
merges immediately because a business lifecycle transition must not wait behind display throttling.

Merge policy:

- a final valuation cannot be replaced by a later-arriving live value;
- otherwise the strictly newer valuation time wins;
- snapshots and streams both use the same rule.

The server also checks that a valuation object is still current before publishing it. This fixed a
race where a superseded live value could arrive after the closing valuation and make a closed trade
appear stale/open again.

## 5. Snapshot and stream reconciliation

```text
useValuationFeed
  ├── SSE /valuation-stream → changes
  └── GET /valuations       → initial/reconnect current state
```

Both start independently. Snapshot results merge directly because they are rare reconciliation
events. `useStreamSeed` runs at mount and after a real `RECONNECTING → CONNECTED` transition.

## 6. Screen derivation remains simple and bounded

The current Valuations pipeline is:

```text
keyed valuations
→ derive LIVE/STALE/CLOSED status
→ keep open rows
→ summarize all open rows
→ filter by class/book/search
→ captured sort
→ render the top 100 matches
```

The 100-row limit bounds DOM work; it does not delete data. Summaries and filters still use the full
open collection, and changing the filter/sort can bring another row into the visible 100.

Freshness is derived from browser receipt age. CLOSED is decided before age, so terminal values do
not become STALE.

Business Overview consumes the same valuation context for portfolio and per-book PnL. It does not
open another connection or maintain a second cache.

## 7. Performance boundary

The important work layers are different:

| Layer | Cost control |
|---|---|
| Network events | Every delivered event is parsed. |
| Pending updates | Latest value per trade is kept until flush. |
| React feed state | Published at most twice per second when non-empty. |
| Freshness | Updated once per second. |
| Valuation table DOM | Capped at 100 matching rows. |
| Pricing client queue | Bounded at 5,000 for burst headroom. |

The larger pricing queue absorbs bursts but does not make valuation calculation or database writes
faster. If the book becomes much larger, the next useful work is batching persistence, server-side
history pagination, and measured virtualization—not more client caches.

## Mental model

```text
pricing SSE → normalize valuation
  ├── final → immediate terminal merge ───────┐
  └── live  → latest-per-trade buffer         │
                 └── shared 500 ms clock ─────┤
                                              └── ValuationFeedContext
                                                   ├── Valuations & Risk
                                                   └── Business Overview
```

## Concepts to keep

- **Inversion of control:** the buffer owns when; the feed supplies what flushing means.
- **Refs for different jobs:** one stores non-rendering work, another stores current behavior.
- **Terminal state:** lifecycle authority can be stronger than timestamp order.
- **Measure then bound:** cap rendered work without pretending the complete collection vanished.
- **Provider value memoization:** context propagates only when its actual feed changes.

## Current limits

- The top-100 table is a dashboard window, not full historical navigation.
- Full-context summaries/filtering still scale with the number of valuations.
- Pricing's 5,000-event queue is bounded and non-durable.
- Alpha/beta is not published by pricing and remains explicitly unavailable.

## Main files

- `frontend/src/hooks/useBufferedUpdates.js`, `streamClock.js`, and `useValuationFeed.js`.
- `frontend/src/domain/valuations.js` and `config/valuations.js`.
- `frontend/src/views/Valuations/Valuations.jsx`.
- `frontend/src/views/BusinessOverview/BusinessOverview.jsx`.
- `services/pricing-service/app/` — valuation calculation, cache, persistence, and SSE publication.
