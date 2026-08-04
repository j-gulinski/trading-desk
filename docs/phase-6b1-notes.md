---
phase: 6b-1
status: complete
reviewed: 2026-08-03
tags:
  - frontend
  - books
  - trade-action
  - write-path
---

# Phase 6b-1 — Books screen & New Trade (teaching notes)

The first phase where the browser writes. Everything before this read data and rendered it
honestly; a form introduces failure modes reads never had.

## Phase outcome in one line

Books becomes the authoritative roster of trading books, and **New Trade** submits real
`OPEN_TRADE` intents from any screen — establishing the write-path pattern (validate → submit with
a deadline → honest result → refetch server truth) that 6b-2 and 6c reuse.

## What was decided and why

### 1. Two data sources on one screen, deliberately

The card grid polls `/blotter/books/summary` every 5 s: it is the only endpoint that already
carries name, asset class, active/closed counts and realized/unrealized PnL in one row. The
drill-down instead derives from the **valuation stream** through `positionsOf`.

Neither source can do both jobs. The blotter summary has no per-symbol breakdown; the stream has no
rows for a book whose trades are not yet valued — and no rows at all for a book with no trades.

**The consequence a reviewer will notice:** the card's UNREALIZED (blotter, up to 5 s old) and the
drill-down's UNREALIZED (stream, up to 0.5 s old) are sampled at different instants and will differ
slightly on a moving market. That is deliberate. They are labelled by different sources rather than
being averaged into one number that is true of neither.

### 2. Books does not get a Delete button

The backend `DELETE /books/{id}` deactivates a book with no check for open trades — it would
silently orphan live positions. Delete waits for 6b-2, where the guard is built. Shipping the button first would be exactly the kind of UI that lies about what the
system can do.

### 3. The instrument list comes from the market feed, and the book fixes the asset class

Selecting a book determines the asset class; the tradeable instruments for that class are filtered
from the live feed rather than from `shared/catalog.py`. One source for "what is quotable right
now", and an instrument the feed has never sent cannot be traded — which is honest, because the
form quotes a price from that same feed.

This also reuses 6a's lesson in the other direction: **books are the authority for tradeable asset
classes**, so `INDEX` (a benchmark, never traded) and `BOND` (priced off the curve, never ticked as
a spot) cannot be picked by accident.

The submitted price is the price on screen — the mockup's subtitle, *"intent at displayed snapshot
price"*, is literal. The trade is an *intent*: pricing revalues it on the next tick regardless.

### 4. Writes carry a deadline; reads already did

`usePolling` has aborted stuck reads at 4 s since Phase 2, but `apiPost`/`apiPut` had no timeout at
all. A write that never answers left the form on "Saving…" permanently, with no way out but a
reload. `apiClient` now takes `timeoutMs` and reports a timeout distinctly from a network error, so
the user learns which happened. Writes get 6 s — longer than reads, because nothing retries a write
automatically.

**The deadline is a default in `apiClient`, not a per-caller argument.** `apiPost`/`apiPut`/
`apiDelete` apply `WRITE_TIMEOUT_MS` (`config/api.js`) unless a caller overrides it, so a future
write cannot silently forget it — which is exactly how this defect existed unnoticed through
Phases 4–6a. The Phase 4/5/6a write paths (generator control, close trade) inherit it for free.

Related: the dialog closes on the **write's** result and fires the roster refetch without waiting
for it. Awaiting the refetch made a slow read look like a failed write. The 6a rule still holds —
reconcile with server truth, never with optimistic client state — but reconciliation is not a
precondition for dismissing the form.

**A failed write names the service and states what did not happen.** `describeApiError` turns an
`ApiError` into copy like *"Books service unavailable — the book was not saved."* rather than
`Request failed (502)`. The status code is a diagnostic for us, not an answer to the only question
the user has, which is whether their work was lost. The one case that reads the status is a `500`
on book create, where the unique-name constraint is the likely cause and the hint is worth showing.

### 5. Idempotency is per intent, not per click

Each submission carries `client_request_id` = `manual-open-<uuid>`, and a fresh one is minted only
**after** a successful accept. A retry of a hung submit reuses the id and the backend dedupes it
(`IntegrityError` → `duplicates`); a deliberate second trade gets a new id and is genuinely new.
The `manual-` prefix also separates these from the generator's `gen-` rows in the audit trail,
extending the 6a convention.

### 6. New Trade lives in the top bar, on every screen

It matches the design, and it reflects what the action is: opening a position is not a
Books-screen feature, it is something a trader does while looking at market data or the blotter. So
the dialog is owned by `AppShell` and fetches its own book list once when opened, rather than being
handed one by whichever screen hosts it. Books keeps only `+ Create book`, which genuinely belongs
to that screen.

### 7. Valuations stays stream-only, and now says so

Settled in the plan review as option (a). A book with no valued open trade emits no valuation
events, so it is invisible on Valuations. Adding a second data path there to show zeroed cards was
not worth it. Books is the authoritative roster instead, and the Valuations header now reads
*"N books with open valuations"* so it states its own population.

### 8. The drill-down expands in place, and the connection budget it revealed

The positions view first spanned the full grid row so a six-column table would fit. That reflowed
every other card, which reads as the page jumping under the user. It is now a compact block per
symbol inside the card, so expanding changes one card's height and nothing else moves.

Separately, and more importantly for review: **each open browser tab of this app permanently holds
two of the browser's six connections per origin** — the market-data stream and the pricing stream,
both opened for the lifetime of the page. Measured in a clean browser: one tab responds in ~10 ms,
two tabs still ~8 ms, **three tabs and every other request queues forever** — polls, form
submissions, and even loading the page. This is a property of the SSE-per-service design over
HTTP/1.1, not of this phase, and it affects a production build identically. The fix belongs to 6c:
close the streams while a tab is hidden and reopen on `visibilitychange`, so only the visible tab
spends connections.

## Mental model: what owns what

```
  books-service ──────── POST /books, PUT /books/{id} ───────┐  (writes: name, class, description)
                                                             │
  blotter-service ────── GET /books/summary (poll 5s) ───────┼──> Books card grid
                          name · class · counts · PnL        │    (roster + durable facts)
                                                             │
  pricing SSE ────────── valuation_update (flush 500ms) ─────┴──> positionsOf → drill-down
                          per-trade fair value & PnL              (net exposure per symbol)

  trade-action-service ─ POST /trade-actions (OPEN_TRADE) <────── New Trade (top bar, any screen)
                          ack: {status, trade_id}                 price from market SSE
```

Books owns *which books exist*; blotter owns *durable per-book facts*; pricing owns *changing
values*; trade-action owns *every trade mutation*. The screen never writes to the blotter and never
invents a row for a trade it just submitted.

## Process flow: submitting a trade

Pick a book (this fixes the asset class) → the instrument list is filtered from the live feed and
auto-selects when there is exactly one → quantity → the panel shows LAST PRICE with a LIVE/STALE
pill and EST. NOTIONAL → submit builds an `OPEN_TRADE` intent with `client_request_id`, the side,
and the displayed price at 4 dp → trade-action answers `202` with a `trade_id` and enqueues it →
the worker validates book and asset class (`ACTION_REJECTED` if they disagree), inserts the trade
and writes `TRADE_CREATED` → the ack shows the short trade id → the trade appears in the blotter
within one 5 s poll and carries a fair value within one pricing tick.

## Honest gaps

- **No Delete on the cards** — 6b-2, with the backend guard that makes it safe.
- **Cards show a short UUID, not a `BOOK-EQ-01` code.** No such column exists on `books`; the
  mockup's codes are cosmetic, and inventing a scheme would be fiction.
- **`EST. NOTIONAL` ignores contract multipliers** (futures `multiplier: 50`). It is labelled
  `QTY × LAST PRICE`, which is what it computes; pricing's valued notional is authoritative and
  appears on Trades a tick later.

## Verification performed

Against the live stack, on a freshly recreated database:

- Create, edit and duplicate-name rejection round-trip; a rename propagated to the Trades row for a
  trade in that book, proving the blotter's join rather than a client cache.
- Both forms render the validation-error state and send nothing; a valid create closes the dialog
  and the card arrives via refetch, with no optimistic row.
- New Trade from a non-Books screen: loaded its own book list, auto-selected `ACME` for an EQUITY
  book, showed `LAST PRICE 100.90 LIVE`, and returned
  `Accepted — BUY 25 × ACME as trade 31F5CB66`.
- End to end: `TRADE_CREATED` audit with a `manual-open-…` correlation id, and the trade on the
  Trades screen with a live fair value and PnL.
- Idempotency: one `client_request_id` posted twice → two `202` acks, one trade,
  `duplicates: 1`.
- Write timeout verified in the browser: an unanswered POST resolved to
  `Request timed out — the service did not answer` with the button re-enabled.
- **Service down** (`docker compose stop books-service`): the roster keeps rendering from the
  blotter (books-service owns writes only), create shows
  *"Books service unavailable — the book was not saved."* with the dialog left open and the typed
  values intact, and edit shows *"Books service unavailable — this book could not be loaded."*
  Restarting the service restores both without a reload.
- Expanding a card leaves every other card's position unchanged; no horizontal scrolling anywhere.
- `npm run lint` / `build` / `deadcode` clean. `positionsOf` and `apiPut` came off the accepted-knip
  list; `apiDelete` stays for 6b-2.

## Concepts seen for the first time in this phase

- **Validation before transport.** The cheapest error never leaves the browser. Validation returns a
  `field → message` map and the transport layer is not reached while it is non-empty. Letting the
  server reject instead costs a round trip and yields a message written for a developer.
- **Timeouts belong to writes.** A hung read is covered by the next poll; a hung write has no next
  anything. `AbortSignal.any` lets one request honour both a caller's cancel signal and a deadline,
  so `apiClient` keeps its existing `signal` contract and gains `timeoutMs` beside it.
- **The browser's connection budget is a design constraint.** Six connections per origin on
  HTTP/1.1 is a hard ceiling, and every app-lifetime SSE stream spends one of them per tab
  permanently. Any architecture with a stream per service has to decide what happens at the third
  tab.

## Files for first-pass review

`config/api.js` + `config/books.js` → `domain/books.js` → `domain/apiErrors.js` →
`domain/tradeActions.js` (instrument filtering, validation, `buildOpenTradeIntent`) →
`services/apiClient.js` (`timeoutMs` and the write default) → `views/Books/Books.jsx` →
`components/books/{BookCard,BookFormDialog}.jsx` → `components/trades/NewTradeDialog.jsx` →
`layout/AppShell.jsx` + `TopBar.jsx` (global New Trade).

## Known limits

- Delete and reassignment are 6b-2.
- Both dialogs are `<dialog showModal()>` overlays that close on backdrop click. 6c replaces all
  three drawers (trade detail plus these two) with one shared push-aside panel that slides the page
  content left instead of covering it.
- The multi-tab connection ceiling above is 6c work.
- Book cards show no alpha/beta; that remains E4.
