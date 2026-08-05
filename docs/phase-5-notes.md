---
phase: 5
status: complete
revised: 2026-08-05
tags:
  - frontend
  - blotter
  - trades
  - pnl
  - trade-action
---

# Phase 5 — what you should know

This phase built the operational Trades & PnL blotter. It combines authoritative trade lifecycle
data with live valuations and adds the first asynchronous write: closing a trade.

## 1. Different sources keep different authority

The screen intentionally uses both polling and streaming:

```text
Blotter poll (5 s)     → membership, lifecycle, books, closed history, fallback values
Valuation SSE context → current mark, fair value, live PnL
```

Polling alone would make marks lag. Streaming alone would not provide complete membership and
closed history. The screen derives rows from both without mutating either source.

For a value present in both places, terminal flags and valuation timestamps decide which wins. A
stream value wins equal-time ties because it includes browser receipt time for freshness.

## 2. The row pipeline is derived at render time

```text
/trades/overview snapshot + valuation context + current time
→ normalize trades
→ choose stream or snapshot value
→ derive OPEN/CLOSED and valuation freshness
→ filters
→ captured sort
→ 50-row page
→ DataTable
```

Open rows display unrealized PnL; closed rows display realized PnL. Missing valuations become
PENDING rather than fabricated zeroes.

`Open / Both / Closed` is the lifecycle filter, with Both as the default operational view. Closed
counts use the book summary because the loaded trade response is only a bounded window. The page
distinguishes total counts from currently loaded rows.

## 3. `useTableState` owns presentation, not business data

`useTableState` manages:

- visible and ordered columns;
- persisted column preferences;
- active sort and direction;
- captured comparison values for live-changing columns;
- fallback sort when the active column is hidden.

The trade objects and valuations stay outside the hook. Snapshot sorting keeps row order stable
while marks and PnL continue changing inside cells.

## 4. Detail data is loaded only when selected

Selecting a trade opens the shared Phase 6c `SidePanel`. The list row is available immediately;
`TradeDetail` separately polls `/trades/{id}` for valuation history and audit events.

```text
selected list row
  ├── immediate identity + live metrics
  └── detail poll (5 s)
      ├── persisted valuation history
      └── audit trail
```

Keying the detail session by trade ID resets its polling and close-action state when another trade
is selected. Phase 6c suppresses the replacement entry animation, so switching rows changes content
without visually closing and reopening the panel.

## 5. Closing is accepted first and confirmed later

The frontend submits a `CLOSE_TRADE` intent with the current mark as `close_price` and a unique
`client_request_id`.

```text
click Confirm
→ POST trade action
→ 202 Accepted: queued, not completed
→ worker closes the trade and writes audit
→ pricing publishes terminal valuation
→ blotter/detail poll observes non-ACTIVE status
→ pending UI clears
```

The UI does not pretend a `202` means the trade is already closed. It waits for authoritative state
to change. A 15-second note reports a slow workflow without declaring failure.

`client_request_id` is idempotency/correlation metadata: retries can be recognized and the action
can be traced across services.

## 6. A window is not an archive

- The overview loads a bounded recent trade set.
- Pagination shows 50 rows at a time.
- Search and filters operate on the loaded window.
- Detail history is fetched only for the selected trade.
- Summary endpoints provide totals the list window cannot know.

This keeps the dashboard responsive while being honest about what is loaded. Full historical
navigation requires server-side pagination.

## Mental model

```text
FeedProvider → ValuationFeedContext ───────────────┐
                                                   ├── tradeRowsOf → Trades table
Blotter /trades/overview poll ─────────────────────┘

selected trade → /trades/{id} poll → SidePanel history + audit

Close button → trade-action queue → pricing finalization → blotter truth → UI confirmation
```

## Concepts to keep

- **Source ownership:** poll lifecycle, stream live values, and derive the display from both.
- **Confirmation by observation:** an asynchronous acknowledgement is not completion.
- **Remount by key:** use identity to prevent state from leaking between selected records.
- **On-demand detail:** keep expensive one-record history outside list state.
- **Label populations honestly:** totals and loaded-window counts are different numbers.

## Current limits

- Full closed-history navigation is not implemented.
- Search and filters cover the loaded trade window, not the entire archive.
- Manual close exists; reopen does not.
- Close reason is fixed to `MANUAL_CLOSE`; optional price override is not exposed.

## Main files

- `frontend/src/views/Trades/Trades.jsx` and `TradeDetail.jsx`.
- `frontend/src/components/trades/TradeDetailPanel.jsx` and `TradeTable.jsx`.
- `frontend/src/domain/trades.js` and `config/trades.js`.
- `services/blotter-service/app/` — trade read model and detail aggregation.
- `services/trade-action-service/app/trade_processor.py` — close processing.
- `services/pricing-service/app/cache.py` — terminal valuation behavior.
