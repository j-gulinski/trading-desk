---
phase: 5
status: complete
reviewed: 2026-07-30
tags:
  - frontend
  - blotter
  - trades
  - pnl
  - trade-action
  - valuations
  - pagination
---

# Phase 5 — Trades & PnL (teaching notes)

This is the “how we got there” version: decisions, trade-offs, and the exact path for one trade row.

## Phase outcome in one line

Phase 5 builds a practical operational blotter for discovery + close:
- membership and lifecycle are owned by Blotter,
- live marks are owned by the existing valuation stream from Phase 4,
- per-trade investigation (history + audit + close action) is on-demand and polling.

Net result: one screen that is fast, bounded, and consistent without adding duplicate stream infrastructure.

## What was decided and why

### 1) Stream is kept at app scope, polling at route scope

There is only one valuation SSE connection in the app-wide provider (`FeedProvider`).  
Trades screen adds route-local polling (`/trades/overview`) every 5 seconds.

Why:
- SSE is great for “fast moving values.”
- Blotter row membership (`open/closed history`, lifecycle, close details) is authoritative in Blotter and is not a good fit for stream events.
- Polling for one service and stream for another gives clear ownership; there is no event fan-in from two producers for the same membership state.

### 2) Keep three freshness sources, not a second cache

For a trade row, the app uses:
- `row` data from Blotter poll (`tradeOf` projection),
- valuation from live stream when available,
- fallback valuation from Blotter snapshot when stream has no newer value.

Why:
- Live-only valuation would lose a value for rows not currently fed or during reconnect.
- Snapshot-only valuation would never feel “live.”
- Combined ownership preserves both correctness and responsiveness.

### 3) Keep `Open / Both / Closed` as the lifecycle model

Trade states are normalized to `OPEN` / `CLOSED` for display logic:
- `CLOSED` means not-`ACTIVE` (includes `CANCELLED` for counting/presentation where intended).
- `tradeRowsOf` computes `lifecycle` from poll state plus valuation terminal flags.

Decision points:
- Default is **Both**, because this aligns with the “blotter” mental model and the tab count usage in the header.
- `Both` is valid and intentionally included because `Closed` in this phase means non-open history, not only final close events.

### 4) Honest total counts are solved with `books/summary`

`/trades?limit=250` is a window, not the full closed set.

Count decision:
- `open`: exact from loaded rows.
- `closed`: `Math.max(summary.closed, closedTradeCountOf(books))`.

Why this exists:
- Prevents incorrect `250+` style labels.
- Makes the `Closed` and `Both` tabs truthful while still keeping response size bounded.

### 5) Close only in this phase; open/reopen deferred

UI currently supports manual close:
- `Close price` is taken from current row valuation price (not hand-entered).
- `close_reason` is fixed to `MANUAL_CLOSE`.
- close action uses `POST /api/trade-action/trade-actions` and waits for downstream state changes.

Open/reopen requires extra workflow and permission semantics, so it is intentionally deferred.

## Mental model: what owns what

```text
App shell:
FeedProvider
 ├─ useValuationFeed -> ValuationFeedContext (tradeId -> live valuation)
 └─ useMarketFeed   -> MarketFeedContext (not used in Trades.jsx)

Trades screen:
 ├─ usePolling(5s)   -> /blotter/trades/overview
 │                      -> members, status, counts, fallback valuation
 ├─ useElapsedTime(1s) -> freshness labeling only
 └─ useTableState     -> sorting, visible columns, captured snapshots

Trade details (selected row):
 └─ usePolling(5s) -> /blotter/trades/{id}
                        -> valuation history + audit for that one trade
```

## `useTableState` process flow (how sorting/states stay stable)

`Trades.jsx` passes two key inputs into `useTableState`:
- columns schema (`TRADE_COLUMNS`)
- `defaultVisibleColumns` for the compact default layout.

Flow inside `useTableState`:

1. **Initial visible columns**
   - `readStoredPreference()` loads previous preference from localStorage if present.
   - Current defaults are:
     - required columns: always visible,
     - optional columns: visible only if they are in `DEFAULT_TRADE_COLUMNS` or explicitly enabled by the user.
   - Practical simplification for this phase: if you want a full reset on process restart, this migration branch can be removed in a follow-up; it remains mainly for backward-compatible preference preservation.
   - New columns only appear when frontend schema/config changes and the bundle reloads (not from API payload changes).

2. **Initial sort**
   - Starts from configured default sort (`pnl desc`) if the column is visible; otherwise fallback sort.
   - A snapshot field (`MARK/Fair/PNL/Return/Updated/Valuation`) starts with `snapshot: null`.

3. **Snapshot capture**
   - `sortTradeRows()` gets values from either `structuralValueOf` (trade fields) or `snapshotValueOf(row, sort.column)`.
   - On first render with rows, if the current sort column is snapshot-based, `applySort()` captures one full-value snapshot map:
     - `captureTradeSnapshot(rows, column)` stores row-by-row comparable values for that column.
   - That snapshot becomes the basis for future order while the value keeps changing live.
   - Result: if marks stream in and out, snapshot-driven columns keep deterministic ordering and avoid row jumping every tick.

4. **User sort/visibility actions**
   - Clicking header calls `toggleSort(column)`:
     - flips direction or establishes default direction for that column,
     - re-captures snapshot when needed.
   - Hiding current sort column calls `applyDefaultSort(next)`.
   - Reorder/toggle/reset only touch local column state, not trade data state.

In short: `useTableState` only owns table projection settings (columns + sort config), not business data. That separation is what keeps stream churn and polling churn out of the sorting logic.

## Trades pipeline (screen-level process flow)

```text
usePolling poll callback
 └─ GET /blotter/trades/overview?limit=250
      ├─ derive books + rows
         └─ tradeRowsOf(rows, valuations, now)
            ├─ value selection (stream vs snapshot)
            ├─ lifecycle, valuationStatus, pnl
            └─ returns trade rows
               └─ summarizeTradeRows(rows) -> open/closed counts
                  └─ closedTotal = max(summary.closed, closedTradeCountOf(books))
                     └─ table tabs render counts
               └─ matchesTradeFilters(...) across book/class/search
               └─ sortTradeRows(..., table.sort)
                  └─ visibleRows = page slice
                     └─ TradeTable -> DataTable render
```

## One row path (the most important flow)

For each `/trades` poll row:

1. `tradesFromSnapshot()` turns backend snake_case into frontend row objects.
2. `tradeRowsOf(trades, valuations, now)`:
   - choose value source:
     - if stream valuation exists and is newer/equal-or-more-authoritative than snapshot, use it;
     - else use snapshot value.
   - compute lifecycle:
     - not active => closed.
   - compute valuation status:
     - `CLOSED`/`CANCELLED` are terminal.
     - otherwise `LIVE`/`STALE` by time rules, `PENDING` when missing value.
   - pick `pnl`:
     - open => unrealized,
     - closed => realized.
3. Table filters/sort/page derive from projected rows and visible settings.
4. Selection triggers side-panel with `key=trade.id` so detail state remounts cleanly.

## Trade detail flow (drawer + detail endpoint)

```text
user clicks trade row/button
 └─ Trades.jsx maps selectedTradeId and derives selectedRow from rows
    └─ renders <TradeDetail key={selectedRow.trade.id} ... />
       └─ TradeDetail poll starts immediately: GET /blotter/trades/{id} every 5s
          ├─ tradeDetailOf(...) -> detail trade + valuationHistory
          ├─ normalizeAuditEvents(...) -> events
          ├─ buildCloseTradeIntent(...) when closing
          └─ close action state:
             - closeTrade() -> POST /api/trade-action/trade-actions
             - close spinner + 15s stall timer
             - clears automatically only when detail.trade.status changes from ACTIVE
       └─ TradeDetailDialog consumes:
          - current row fields (instant availability)
          - detail snapshot fields (if available)
          - row valuation for live mark display
          - on close:
             - detail panel closes => component unmounts
             - polling is automatically aborted by effect cleanup
```

One subtle but important pattern:
- `TradeDetail` is recreated with `key={trade.id}` on selection changes.  
  That guarantees poll timing and closing state are fresh for each trade, and stale status/spinner state cannot bleed across rows.

## Value selection rule (stream vs snapshot) — in plain terms

The row does not mutate the stream cache. It derives value at render time:
- if stream has a value and snapshot has none → use stream
- if snapshot has value and stream missing → use snapshot
- if both have values → choose based on terminal flags and timestamps
- tie case on equal valuation timestamps favors stream (it has browser receipt timing for freshness display)

This is the same principle as Phase 4’s stream merge discipline but applied to list rows.

## What refreshes what in list vs detail

### Trades list

Re-renders when:
- 5-second Blotter poll resolves (`trades`, `books`),
- 500 ms/1-second stream clock updates valuation freshness and merged values,
- local filter/sort/page/column selections change.

What is **not** in list state:
- valuation history,
- audit logs,
- one-trade detail payload.

### Trade detail drawer

Re-renders (and fetches) when:
- selected trade changes (new `key` => remount),
- `/trades/{id}` poll returns,
- close action state changes (`closing`, `closeNote`).

It merges:
- row identity from list (`row`) for instant UI,
- detail payload for history/audit/closed_at/close price if available,
- live metric display is still pulled from row, so mark/fair value updates stay current even while history is polling 5s.

## Close action sequence (what you see and why)

1. User confirms in panel.
2. Frontend sends intent payload with:
   - `action_type: CLOSE_TRADE`,
   - `trade_id`,
   - `close_price` (current mark from row),
   - `client_request_id` for idempotency metadata.
3. Trade-action service returns `202`; no immediate close in DB.
4. Worker closes trade and emits audit (`TRADE_CLOSED`) or rejection.
5. Pricing finalization turns that into final valuation (`final: true`) and publishes it.
6. Blotter consumes the final valuation and drops cached active row for that id.
7. Poll lists + detail catch the new status; close spinner clears only when detail confirms non-active status.

Why `close_price` came up in review:
- without a price, close would use the fallback branch intended for “close all” automation and could compute realized PnL from stale/unrelated values.

## Conversation-based decisions (directly from your questions)

- **“Why not use only polling in trades?”**  
  Polling remains for membership and lifecycle; stream remains for per-trade mark updates. Using only polling would make mark behavior laggy; using only stream would lose closed history and lifecycle accuracy.

- **“Why isn’t valuation table same as trades table?”**  
  Different task shape: valuations is a fixed open-book ranking; trades is a paged operational table with open/closed history and close action.

- **“Should we remove stream from trade screen?”**  
  Removing stream would remove live marks. The chosen compromise is: keep stream for marks, do not add any second stream or extra feed service.

- **“Why both open/closed/defaults?”**  
  `Both` is a valid filter for operational workflows and is kept as default so users can switch to context instantly.

- **“Are open/closed tabs not working because both can be unselected?”**  
  This implementation uses `aria-pressed` toggle style, not checkbox semantics. One tab is always active by current value and drives filtering.

## Performance and scale boundary to remember

- List is paged (50 rows/page), not full historical dump.
- `/trades` closed branch is still windowed by backend limit.
- Search and filters apply to loaded window only.
- Detail fetch happens only on selection.
- Poll and stream intervals are reused; no extra high-frequency loop added for this screen.

## Files for first-pass review (phase-5 relevant)

1. `frontend/src/views/Trades/Trades.jsx`
2. `frontend/src/views/Trades/TradeDetail.jsx`
3. `frontend/src/components/trades/TradeDetailDialog.jsx`
4. `frontend/src/components/trades/TradeStatusTabs.jsx`
5. `frontend/src/domain/trades.js`
6. `frontend/src/components/trades/TradeCell.jsx`
7. `frontend/src/config/trades.js`
8. `services/blotter-service/app/service.py`
9. `services/blotter-service/app/repository.py`
10. `services/trade-action-service/app/trade_processor.py`
11. `services/pricing-service/app/cache.py` (for close finalization behavior)

## Known limits (what belongs to next phase)

- Full historical closed archive navigation is still server-side work.
- Open/reopen flow is still out of scope in Phase 5.
- Close reason, audit review depth, and optional price override are intentionally deferred.
