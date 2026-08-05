---
phase: 6b-2
status: complete
revised: 2026-08-05
tags:
  - backend
  - books
  - trade-action
  - blotter
  - lifecycle
---

# Phase 6b-2 — what you should know

This phase made book retirement safe. A book with open positions cannot be deactivated; positions
can be reassigned to a compatible book first.

## 1. Delete is a guarded soft delete

`DELETE /books/{id}` sets `is_active = false`. It does not remove the historical book or its closed
trades. The precondition is therefore **zero ACTIVE trades**, not zero trades of any kind.

The guard covers every route that can perform the transition, including `PUT` with
`is_active: false`. Guard the state change, not only one HTTP route.

## 2. Destructive checks fail closed

Books-service asks blotter whether the book has active trades instead of reading another service's
tables directly.

```text
books-service → blotter active-trade check
  ├── active trades exist → 409
  ├── blotter unavailable → 503
  └── zero active trades  → deactivate
```

`409` means the precondition failed. `503` means the system could not verify it. An unavailable
dependency must not be interpreted as permission for a destructive action.

## 3. Trade reassignment has one writer

`REASSIGN_TRADES` runs through trade-action-service because that service owns mutations to the
`trades` table.

The worker validates that source and target books exist, the target is active, and both books share
the same asset class. It moves only ACTIVE trades and writes one `TRADE_REASSIGNED` audit per trade,
correlated by the request ID.

Move is a separate action from Delete. Delete never silently changes meaning. The steps are not
automatically chained because `202 Accepted` confirms only queueing; deleting immediately would
race the reassignment worker.

## 4. Denormalized caches need invalidation

Blotter caches active trades and indexes them by `book_id`. Reassignment changes that indexed field,
so leaving the cache untouched would show the old book until restart.

Pricing refreshes active trades from the database and publishes the corrected `book_id`. Blotter
compares the streamed value with its cached value and atomically re-indexes on disagreement.

```text
database reassignment
→ pricing active-set refresh
→ valuation with new book_id
→ blotter detects disagreement
→ atomic cache re-index
```

The correction reuses an existing channel, but a moved trade that never receives another valuation
would not re-index until restart. Current catalog symbols keep ticking, so the limitation does not
occur in normal operation.

## 5. Totals and breakdown must share one snapshot

The book card's unrealized total and its per-symbol breakdown originally came from different
sources/requests, so they represented different instants and could not always add up.

`/books/summary` now calculates both in one pass over the same cached trades and valuations. The
card total is the sum of the returned position rows by construction.

This also makes missing valuations visible: they participate in net positions and make the position
STALE rather than disappearing from a stream-only breakdown.

## 6. Deactivated books preserve history

Active books show by default. “Include deactivated” reveals retired books with a DEACTIVATED label
and no write actions. They remain visible because they still own closed trades and realized PnL.
Deactivated books are never reassignment targets.

## Process flow

```text
Move → choose active same-class target → REASSIGN_TRADES (202)
→ worker moves active trades + writes audits
→ pricing publishes corrected book IDs
→ blotter re-indexes
→ Books poll shows source empty
→ Delete → guarded soft deactivation
```

## Concepts to keep

- **Fail closed:** inability to verify a destructive precondition is a refusal.
- **Guard transitions:** protect every path to the state change.
- **Single writer:** send mutations through the service that owns them.
- **Cache invalidation by disagreement:** a denormalized read model must follow mutable indexed data.
- **One number, one request:** totals and decompositions need the same snapshot.
- **`202` cannot be chained:** observe completion before starting a dependent operation.

## Current limits

- Deactivated books cannot be reactivated from the UI.
- Delete is one book at a time.
- The summary computes positions for every book on every poll, even when cards are collapsed.
- Global `CLOSE_ALL` remains outside the UI and has a known realized-PnL edge case.

## Main files

- `services/books-service/app/blotter_client.py` and API/service modules — delete guard.
- `services/trade-action-service/app/trade_processor.py` and repository — reassignment.
- `services/blotter-service/app/cache.py` and service modules — re-index and summary positions.
- `frontend/src/components/books/MoveTradesPanel.jsx` and `ConfirmPanel.jsx`.
- `frontend/src/views/Books/Books.jsx` and `domain/books.js`.
