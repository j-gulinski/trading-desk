---
phase: 6b-2
status: complete
reviewed: 2026-08-04
tags:
  - backend
  - books
  - trade-action
  - blotter
  - lifecycle
---

# Phase 6b-2 — Book lifecycle: delete guard and trade reassignment (teaching notes)

The first phase where the browser can retire something. It ships two things: books-service refuses
to deactivate a book that still holds open positions, and trades can be moved from one book to
another so that a book *can* be retired.

## What was decided and why

### 1. The guard is on *open* positions, not on *any* trade

`DELETE /books/{id}` is a **soft delete** (`is_active = False`), and closed trades stay attributed
to the book they happened in. So "refuse when the book has trades" would make every book that ever
traded permanently undeletable — its closed history never goes away.

The guard is therefore **no ACTIVE trades**. Deleting a book means *it stops accepting trades and
leaves the roster*, not *it never existed*. A hard delete was never on the table: it would need
`ON DELETE CASCADE` across trades and valuations, which is a data-loss button.

### 2. The guard sits on the state transition, not on the route

`PUT /books/{id}` copies whitelisted fields from the body and `is_active` is one of them —
`deactivate_book` is literally `update_book(book_id, {"is_active": False})`. Guarding only `DELETE`
would have left the same transition reachable through the edit endpoint. Both routes are guarded;
`PUT` whenever the body carries `is_active: false`.

### 3. books-service asks the blotter over HTTP, and fails closed

books-service shares the database, so it *could* read the `trades` table. It doesn't — trade reads
belong to the blotter, the same ownership rule that keeps trade writes inside trade-action-service.
6a set this precedent when trade-generation grew a `blotter_client.py`.

**The consequence that matters:** if the blotter cannot answer, the delete is refused with **503**,
not allowed. A destructive operation that cannot verify its precondition must not proceed. The two
refusals carry different codes so the UI can say different things — `409` is *you can't*, `503` is
*we can't tell*. The cost is honest: books-service now has a runtime dependency on a path that used
to be pure local state.

### 4. Reassignment lives in trade-action-service

`REASSIGN_TRADES` joins `OPEN_TRADE`, `CLOSE_TRADE` and `CLOSE_ALL` in the same queue, worker and
audit path. Moving a trade between books is a write to `trades`, and `trades` has exactly one writer.

Validation reuses the rule that already guards `OPEN_TRADE`: the target book must be active and its
`expected_asset_class` must match the source's. Books are the authority for asset class (a 6a
contract), so the check is book-to-book rather than trade-by-trade — a per-trade filter would move
some trades and leave others, which is worse than refusing. Only ACTIVE trades move; each one gets a
`TRADE_REASSIGNED` audit row carrying `from_book_id`/`to_book_id` and the caller's
`client_request_id`, so a move of N trades is reconstructable from the audit trail alone.

### 5. The blotter would not have noticed the move — the one real find

The blotter serves ACTIVE trades from an in-memory `IndexedStore` **indexed by `book_id`**, filled
once at startup. `handle_valuation` inserts a trade only when it is absent; for one already cached
it just records the valuation. Nothing ever updated a cached field. After a move, `/books/summary`
counts and every `book_id` filter would have kept reporting the old book until restart — the screen
would have shown the move as having silently failed.

The fix rides the stream that already exists: pricing rebuilds its active set from the database
every 2 s, so the corrected `book_id` is already on the wire. The blotter compares the streamed
`book_id` against the cached one and re-indexes on disagreement.

The re-index is one atomic operation (`IndexedStore.update_field`) rather than remove-mutate-add
from the caller. The blotter serves requests on threads, and — subtler — the naive version is simply
wrong: `_add` removes an existing entry by reading the *stored* object's fields, so mutating first
makes the removal look in the **new** book's bucket and leaves a stale entry under the old key.

**Worth keeping:** a denormalised cache is only as correct as its invalidation, and "this field
never changes" is an assumption a later feature can quietly invalidate.

### 6. Move is its own button, and Delete does not pre-empt the guard

The first cut hid Move behind Delete: clicking Delete on a book with open positions opened the move
form instead of the confirm. It was clever and it was worse — the button did two different things
depending on state, and the only way to move positions was to pretend you wanted to delete.

Now each button does one thing. `Move` appears on any book with open positions and reassigns them.
`Delete` always opens the confirm; if positions remain, the backend refuses and the panel shows
*"Refused — this book still has 3 open positions."* The rule lives in exactly one place — the guard
— instead of being duplicated as a client-side branch that decides which dialog to open.

The two steps are deliberately not chained. Trade-action answers `202 accepted` — the trades have
not moved yet when the form closes. Auto-continuing into the delete would race the worker and hit
the guard. The UI reports the acknowledgement and the 5 s roster poll reconciles.

### 7. The Books screen reads one source: the blotter

The screen used to mix two. Card PnL came from `/blotter/books/summary` (5 s poll) while the
drill-down came from the shared valuation SSE stream (sub-second) — two numbers for the same book,
sampled at different instants, that a reviewer would reasonably read as a bug.

Everything now comes from the blotter: the roster from `/books/summary`, and the expanded card's
per-symbol netting from `/trades?book_id=…&status=ACTIVE`, which already carries each trade's latest
valuation. Same cache behind both, so the card total and the drill-down rows agree when sampled
together (measured: −246.20 against −246.20 across two open XAUUSD legs).

This needed one addition: `latest_valuation` projected `fair_value` and PnL but not the per-unit
price, so the blotter now passes `current_price` and `multiplier` through from the valuation
payload. The `MARK` column needs the price of one unit, not the value of the position — for a
futures leg those differ by a factor of 50.

Two consequences worth stating. Staleness is now measured against the mark's own `valuation_time`
rather than against when the browser last heard from the stream, which is the more honest number —
it ages a stale mark even if the connection is healthy. And a trade with no valuation at all is now
visible: it counts into the netting and pushes the position to `STALE`, where the stream-fed version
simply did not know it existed.

The screen no longer touches `useValuationFeedContext`. It does not reduce the connection count —
the streams are opened once by `FeedProvider` for the whole app — it removes a second source of
truth from one screen.

### 8. Deactivated books stay visible behind a filter

A soft-deleted book still owns its closed trades and their realized PnL, so hiding it permanently
would hide history the blotter still reports. The roster shows active books by default and an
**Include deactivated** checkbox brings the rest back, marked `DEACTIVATED` and without Edit or
Delete. The header states what is hidden (`… · 7 deactivated hidden`) rather than silently dropping
rows. Deactivated books are never offered as move targets.

## Scope change during the build

**Per-book Flatten was dropped.** The original plan paired the delete guard with a per-book Flatten
button (and an optional `book_id` on `POST /trade-actions/close-all` to scope it). Move already
empties a book, so Flatten was a second way to do the same thing that additionally needed a filter
on the most destructive query in the system. It is not built; `close_all_trades` is unchanged and
still global, and nothing in the UI calls it. The card therefore carries `Edit` and `Delete` where
`docs/designs/Books.png` shows a third `Flatten` button — a deliberate deviation from the mockup.

## Mental model: what owns what

```
  books-service ─── DELETE /books/{id} ──┐
                    PUT (is_active:false)│ guard: blotter says 0 ACTIVE?
                                         ├──> 409 has open trades
                    blotter_client ──────┘    503 could not verify (fail closed)
                         │ GET /trades?book_id&status=ACTIVE
                         ▼
  blotter-service ── owns trade reads ── IndexedStore[book_id] ──> /books/summary
                         ▲                      ▲
                         │                      │ re-index on book_id change
  pricing SSE ───────────┴──────────────────────┘ (active set re-read every 2s)

  trade-action-service ── the only writer of `trades`
       OPEN_TRADE · CLOSE_TRADE · CLOSE_ALL · REASSIGN_TRADES
                    └─ audit row per affected trade, correlated by client_request_id
```

books owns *which books exist*; the blotter owns *what is in them*; trade-action owns *every trade
mutation*. books-service asks rather than reads, and refuses when it cannot ask.

## Process flow: retiring a book that still holds positions

Move on the card → the target list is filtered to *active books of the same asset class* → submit
posts `REASSIGN_TRADES` → `202 accepted`, the form closes, the page shows the acknowledgement → the
worker validates both books, updates the ACTIVE rows and writes one `TRADE_REASSIGNED` per trade →
pricing's 2 s refresh picks up the new `book_id` and keeps valuing without a gap → the blotter
re-indexes off the next valuation event → the 5 s roster poll shows 0 open on the source and the
Move button disappears → Delete → confirm → `DELETE /books/{id}` passes the guard, and the card
becomes a `DEACTIVATED` tile behind the filter. Deleting before moving is not an error the UI
prevents — it is a refusal the UI reports.

## Honest gaps

- **A moved trade that is never valued never re-indexes.** The blotter learns about the move from
  the valuation stream, so a position whose symbol has no live price would stay in the old book's
  count until restart. Every symbol in the catalog ticks, so this does not occur in practice — but
  the correction path is the stream, not the database.
- **A rejected reassignment is audited against the book, not a trade**, so the Trade Actions feed
  shows a book UUID in a column that otherwise holds trade ids.
- **`GET /audits` does not project `payload`**, so `from_book_id`/`to_book_id` are queryable in the
  database but the feed renders the book names from the message text instead.
- **Found but not fixed here:** `realized_pnl_by_book` computes realized PnL from `close_price` and
  skips trades where it is NULL. Bulk close (`CLOSE_ALL`) writes no `close_price` — pricing records
  the realized number on the final valuation instead — so trades closed that way contribute 0 to a
  book's realized PnL. Nothing in the UI reaches `CLOSE_ALL`, and the fix belongs to whatever phase
  makes it reachable.

## Verification performed

Against the live stack:

- **Delete guard:** `DELETE` on a book with 38 open trades → `409 {"error": "book has open trades",
  "active_trades": 38}`. Unknown book → `404`. A book with 0 open → `200`, `is_active: false`.
- **Bypass closed:** `PUT {"is_active": false}` on that same book → the identical `409`.
- **Fails closed:** with `blotter-service` stopped, `DELETE` on a book with **zero** open trades →
  `503 {"error": "open trades could not be verified"}` in 0.04 s (refused, not hung).
- **Reassignment:** EQUITY → FX target rejected (`rejected` 0 → 1, no rows touched); EQUITY →
  EQUITY moved 3 trades, `reassigned` 0 → 3, three `TRADE_REASSIGNED` rows correlated to the
  request id with `{"from_book_id": …, "to_book_id": …}` confirmed in the database.
- **Blotter follows without a restart:** source `active=3 → 0`, target `active=0 → 3`, three
  `trade_reindexed` log lines; the closed trade stayed on the source. All three moved trades kept
  returning `source: valuation-stream` fair values immediately after the move, and the target card's
  unrealized went on ticking.
- **UI, move:** Move on a book with 3 open positions listed only the active same-class book,
  submitted, and reported *"Accepted — 3 open positions are moving to Move Check."* The roster
  reconciled within one poll — source `3 open → 0` (its Move button disappearing), target
  `0 → 3 open` with unrealized −575.00 — without restarting the blotter. Moving them back restored
  the original book. On a book whose only same-class peers are deactivated the form says so instead
  of offering them.
- **UI, delete:** Delete on a book with 3 open positions reached the guard and rendered
  *"Refused — this book still has 3 open positions."* in the panel. Delete on an empty book
  confirms, reports *"… deleted."*, and the card turns into a `DEACTIVATED` tile with the filter on
  / drops into the `deactivated hidden` count with it off.
- **UI, drill-down from the blotter:** expanding a book renders netted per-symbol rows — 3 FUTURES
  trades netting to `ES_FUT · NET QTY −1 · MARK 5,225.00 · UNREALIZED +875.00`, matching the card's
  +875.00 exactly; `GOVT_5Y +165 @ 1,038.83 / mark 1,038.59 / −38.79` on a bond book. Zero console
  errors on a clean load.
- `npm run lint` / `build` / `deadcode` clean; no new knip findings.

## Concepts seen for the first time in this phase

- **Fail closed.** A precondition that cannot be evaluated is not a precondition that passed. "The
  blotter said no" and "the blotter said nothing" must reach the user as different answers.
- **Guard the transition, not the route.** The same state change was reachable from two endpoints.
- **Cache invalidation by disagreement.** The blotter notices that the stream and its cache disagree
  and corrects itself — no new channel, self-healing after a missed message, but only as timely as
  the stream carrying the truth.
- **`202 accepted` cannot be chained.** A flow whose second step depends on the first step's *effect*
  has to reconcile by polling, not by continuing on the acknowledgement.

## Files for first-pass review

`shared/enums.py` → `services/books-service/app/{config,blotter_client,api}.py` (the guard) →
`services/trade-action-service/app/{repository,trade_processor}.py` (`REASSIGN_TRADES`) →
`services/blotter-service/app/{cache,service}.py` (the re-index and `latest_valuation`) →
`domain/books.js` (`moveTargetsOf`, `bookPositionsOf`) → `components/books/MoveTradesDialog.jsx` →
`views/Books/Books.jsx`.

## Known limits

- Both dialogs are still `<dialog showModal()>` overlays; 6c replaces them with the shared
  push-aside panel.
- Delete is per-book; there is no multi-select.
- A deactivated book cannot be reactivated from the UI (the `PUT` accepts it; no control calls it).
- The card total and the drill-down are two requests at two instants, so they can differ by a tick
  or two while prices move. Same source, same cache — different sample times.
- `positionsOf` in `domain/valuations.js`, the stream-side netting the drill-down used to call, is
  now unreferenced and back on the accepted-knip list. It was left in place rather than deleted;
  Valuations is the screen that would use it.
- `realized_pnl_by_book` still loads every closed trade on each 5 s poll — unchanged in shape from
  before this phase, but the next thing to feel the generator's volume.
