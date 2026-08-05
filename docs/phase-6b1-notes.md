---
phase: 6b-1
status: complete
revised: 2026-08-05
tags:
  - frontend
  - books
  - trade-action
  - write-path
---

# Phase 6b-1 — what you should know

This phase added the Books screen, Create/Edit Book, and global New Trade. It established the
frontend write pattern used by later phases.

## 1. Services keep clear ownership

```text
books-service  → create/edit/deactivate book metadata
blotter        → book roster summaries, counts, PnL, and position breakdown
market feed    → currently quotable instruments and displayed prices
trade-action   → every trade mutation
```

The current Books screen polls `/blotter/books/summary` every five seconds. After the 6b-2 revision,
the same response contains card totals and per-symbol positions, so the card and its breakdown are
calculated from one coherent snapshot.

Valuations remains stream-only and shows books with open valuations. Books is the authoritative
roster, including empty books.

## 2. Write forms validate before transport

Book and trade validation returns a `field → message` map. Invalid forms do not send a request.
The server still validates independently; browser validation exists to give immediate, field-level
feedback.

All writes use the shared API client's deadline. Reads naturally retry through polling, but a write
that hangs would otherwise leave the form pending forever. Write errors name the service and state
what did not happen instead of showing only an HTTP code.

Successful writes close from the write result and trigger a roster refetch. The form does not wait
for that read before dismissing, and it does not insert an optimistic card.

```text
validate → submit with timeout → success/failure message → refetch server truth
```

## 3. Book forms have explicit sessions

Create and each Edit target are keyed separately:

```text
create:new
edit:<book-id>
```

This Phase 6c correction prevents Edit values and effects from leaking into Create or another book.
Switching actions keeps the visible side panel open while replacing the form session.

## 4. New Trade belongs to the app shell

Opening a trade is not a Books-only action, so New Trade is available from the top bar on every
route and owns its own book load.

Selecting a book fixes the asset class. The form filters currently quotable instruments from the
market feed for that class and submits the displayed snapshot price.

```text
book → asset class → matching live instruments → side + quantity
→ OPEN_TRADE intent → 202 Accepted → later blotter/valuation confirmation
```

Each intent carries `manual-open-<uuid>` as `client_request_id`. A retry reuses the same ID so the
backend can deduplicate it; a deliberate new trade receives a new ID. The prefix also identifies
manual actions in the audit feed.

## 5. Accepted is not completed

Trade-action returns `202` when the intent is queued. The new trade appears after the worker writes
it, the blotter poll discovers it, and pricing values it. The UI reports acceptance without
inventing an immediate trade row.

## 6. Current panel behavior

Phase 6c converted the original dialogs into the shared non-modal `SidePanel`:

- closed → open slides and pushes desktop content aside;
- an ordinary outside click closes;
- another panel trigger replaces content without a close/reopen animation;
- Escape/Close restores focus; native Tab navigation is not trapped.

## Mental model

```text
Books page → blotter summary poll → cards + positions
     └── Create/Edit → books-service → refetch summary

AppShell New Trade
  ├── books list → valid target and asset class
  ├── market context → instrument and displayed price
  └── trade-action OPEN_TRADE → async processing
```

## Concepts to keep

- **Validation before transport:** reject cheap errors before paying for a request.
- **Write deadlines:** writes need an explicit end state because they are not automatically retried.
- **Idempotency per intent:** correlation identity survives retries and traces work across services.
- **Server reconciliation:** refetch authoritative state instead of manufacturing optimistic rows.
- **Global action ownership:** place an action where its workflow belongs, not where one data source
  happens to be displayed.

## Current limits

- Estimated notional is quantity × displayed price and does not apply futures multipliers.
- Books have UUIDs but no separate human-friendly code column.
- Three HTTP/1.1 app tabs can exhaust the connection budget while both global streams remain live.
- Book alpha/beta remains unavailable.

## Main files

- `frontend/src/views/Books/Books.jsx` and `components/books/BookFormPanel.jsx`.
- `frontend/src/components/trades/NewTradePanel.jsx`.
- `frontend/src/domain/books.js`, `tradeActions.js`, and `apiErrors.js`.
- `frontend/src/services/apiClient.js` and `config/api.js`.
- `frontend/src/layout/AppShell.jsx` and `TopBar.jsx`.
