# Building a screen — views, domain, tables, forms, panels, states

Every view in this app is assembled from the same six parts in the same order. This document is
that recipe, then each part in detail.

## 1. The anatomy of a view

```text
1. read      feed context and/or usePolling
2. derive    domain functions turn raw payloads into view models
3. filter    local useState for class / book / search
4. arrange   useTableState for columns and sort
5. bound     slice to the rendered window
6. render    StreamHeader · StatCards · FilterBar · DataTable · EmptyState
```

`Valuations.jsx` in full skeleton — every view looks like this:

```jsx
export default function Valuations() {
  const { valuations, bookRisk, status, seedStatus } = useValuationFeedContext()   // 1
  const { now } = useElapsedTime()

  const [activeClass, setActiveClass] = useState(null)                             // 3
  const [activeBook, setActiveBook] = useState(null)
  const [query, setQuery] = useState('')

  const openRows = valuationRowsOf(Object.values(valuations), now)                 // 2
    .filter((row) => !row.valuation.closed)
  const summary = summarizeValuations(openRows)

  const table = useTableState({ columns: VALUATION_COLUMNS, storageKey: …, … })    // 4

  const matchingRows = sortValuationRows(openRows.filter(…), table.sort)
  const visibleRows = matchingRows.slice(0, MAX_RENDERED_ROWS)                     // 5
  …                                                                                // 6
}
```

The state a view owns is only ever *what the user asked for* — three values here. Everything on
screen is derived ([react.md §9](react.md#9-derived-state-if-you-can-compute-it-dont-store-it)).

## 2. The domain layer — where the thinking lives

`domain/` holds pure functions: no React, no fetch, no DOM. They are the reason components stay
readable.

| Kind | Examples | Job |
| --- | --- | --- |
| Normalizers | `normalizeServiceStatus`, `valuationOf`, `normalizeLogLine`, `tradeRowsOf` | Backend payload → stable view model |
| Merge rules | `mergeValuations`, `mergeInstruments`, `mergeLogLines` | Which value wins, and the cap |
| Derivations | `summarizeValuations`, `bookRisksOf`, `minuteSeriesOf` | Totals, groupings, series |
| Filters/sort | `countOptions`, `groupOptions`, `sortRows` | Reusable list mechanics |
| Formatting | `formatAmount`, `formatSignedAmount`, `formatClockTime` | Numbers → strings, one policy |

**Normalizing at the boundary is the highest-leverage habit here.** A component never touches a
raw response, so a backend field rename is one edit in one file rather than a hunt through JSX.
The normalizer is also where defensive coding belongs:

```js
export function normalizeLogLine(raw) {
  if (raw == null || typeof raw !== 'object') return null
  const level = LOG_LEVELS.includes(raw.level) ? raw.level : 'info'
  const atMs = Date.parse(raw.timestamp ?? '')
  return { …, level, atMs: Number.isNaN(atMs) ? null : atMs, payload: raw }
}
```

Unknown level → a safe default. Unparseable timestamp → `null`, which the formatter renders as
`—`. Nothing throws, nothing renders `NaN`, and the raw payload is kept so the detail view can
show exactly what arrived.

**Sorting is one shared function** with a rule most tables get wrong:

```js
const aMissing = aValue == null
if (aMissing !== bMissing) return aMissing ? 1 : -1     // missing always sinks
return comparison === 0 ? tieBreak(a, b) : comparison * directionMultiplier
```

Missing values sink to the bottom in *both* directions — reversing the sort should not promote
rows that have no value — and a stable `tieBreak` (usually the trade reference) keeps equal rows
from shuffling on every flush.

## 3. Tables — `useTableState` and `DataTable`

The split: `useTableState` owns **presentation** (which columns, what order, which sort);
`DataTable` owns **markup**; the view owns **rows**. The hook never sees a row.

A column is declarative config, not JSX:

```js
{ id: 'unrealized', label: 'Unrealized', required: true, sortable: true,
  snapshot: true, defaultDirection: 'desc', numeric: true, headerNote: 'open PnL' }
```

| Flag | Effect |
| --- | --- |
| `required` | Cannot be hidden by the column picker |
| `sortable` / `defaultDirection` | Header becomes a button; first click uses this direction |
| `numeric` | Right-aligned, tabular figures |
| `snapshot` | **The column's values change live — sort must be captured** (§3.2) |
| `headerNote` | A small clarifier under the label ("on notional", "valuation input") |

### 3.1 Column visibility and order, persisted

`readVisibleColumns` merges three inputs: the configured columns, the user's stored preference,
and the defaults. The subtle part is what happens when the *code* changes:

```js
const known = new Set(stored.known)      // columns that existed when the user last chose
for (const column of columns) {
  if (seen.has(column.id)) continue
  if (!column.required && (known.has(column.id) || !defaultColumns.includes(column.id))) continue
  // …otherwise insert it at its configured position
}
```

Storing `known` alongside `visible` is what distinguishes *"the user hid this column"* from
*"this column did not exist yet"*. A newly shipped column appears for existing users (it is not
in their `known` set) while a column they deliberately hid stays hidden. Required columns always
come back. Both read and write are wrapped in try/catch — a broken preference must never stop a
table from rendering.

### 3.2 Captured sort — the live-data problem

Sorting on a column whose values change twice a second means rows reorder while you try to click
one. The fix: when the user sorts a `snapshot` column, capture each row's comparison value at
that moment and sort on the capture.

```js
const applySort = useCallback((column, direction) => {
  const capturedAt = Date.now()
  setSort({ column, direction,
    snapshot: columnById.get(column)?.snapshot ? captureSnapshotRef.current(column, capturedAt) : null,
    capturedAt })
}, [columnById])
```

Cells keep updating — only the *order* is frozen — and `SortCaptureStatus` tells the user
exactly that: `Order captured 14:32 · values live`. Sorting by a structural column (symbol, book)
needs no capture and gets none.

There is one more piece: if the view mounts before any rows exist, there is nothing to capture,
so the hook re-applies the sort once rows arrive (`needsCapture` + `hasRows`). Hiding the sorted
column falls back to a configured `fallbackSort` rather than leaving an invisible sort active.

### 3.3 `DataTable`

Presentational and generic: it maps columns to `<th>`, rows to `<tr>`, and delegates every cell
to the view's `renderCell(column, row)`. Accessibility is built in rather than bolted on —
`scope="col"`, `aria-sort` on the active header, a real `<button>` inside the header (keyboard
focus for free), `aria-disabled` with a reason when sorting is temporarily unavailable, and a
`<caption>` describing what the table contains.

```jsx
const minWidth = Math.max(520, 500 + (columns.length - 2) * 80)
```

The table declares a minimum width and its wrapper scrolls horizontally. Financial tables must
not compress numbers to fit — a squeezed price column is worse than a scrollbar.

## 4. Filters

`FilterBar` composes a chip group, an optional search input, and a `children` slot for
view-specific tools (a book `<select>`, the column picker, a pause button). Options are built by
one of two domain helpers:

```js
countOptions(rows, (row) => row.valuation.assetClass)   // value === label   → EQUITY (12)
groupOptions(rows, (r) => r.bookId, (r) => r.bookName)  // value ≠ label     → Equity Delta One (7)
```

Counts come from the same collection the table renders, so a chip never advertises rows that a
different filter has already removed. `FilterChipGroup` also supports a `trailing` slot — that
is how the Logs view puts an error sparkline inside each service chip.

## 4a. Configurability and persistence

The homework asks for configurability that makes *domain* sense rather than a long options list.
What is adjustable, and where each choice is remembered:

| Setting | Scope | Stored in | Key |
| --- | --- | --- | --- |
| Visible columns and their order | per table (trades, valuations, market, curve) | `localStorage` | `trades.visible-columns`, … |
| Sidebar collapsed | app | `localStorage` | `layout.sidebar-collapsed` |
| Market tick-history depth | Market Data | `localStorage` | `market-data.tick-count` |
| Market snapshot + tick recovery | this tab only | `sessionStorage` | `market-data.feed-state` |
| Filters, search, page, selected tab | — | **not persisted** | — |

Every key lives in `config/storage.js` — one registry, so a rename is one edit and two features
can never collide on a string.

**The rule: remember the workspace, never the question.** Column layout and a collapsed sidebar
are how you like to work; a filter is what you were asking a minute ago. Reopening the app on
yesterday's filter is a bug that looks like a feature — and worse, it hides rows without saying
why.

**`localStorage` vs `sessionStorage` is a deliberate split.** Preferences are durable; recovered
feed state is per tab, because it is a cache of a live stream, not a setting — two tabs must not
fight over one copy of it.

Every read and write is wrapped in try/catch (`useStoredFlag`, `useTableState`,
`useMarketFeed`): storage can be disabled, full, or hold a value from an older version of the
app. A dashboard must never fail to boot over a preference, so a bad value falls back to the
default and is overwritten on the next change.

Two settings are deliberately **not** in the UI. The alpha/beta benchmark is backend config
(`BENCHMARK_SYMBOL`) because changing it invalidates every book's rolling window — that is not a
per-user toggle. Log levels are env-owned for the same reason: one owner per fact.

## 5. Writes — validate, submit, observe

Every write in the app follows one sequence:

```text
validate locally → POST with a deadline → 202 Accepted → refetch authoritative state
```

`NewTradePanel` is the fullest example. Its state is grouped by role, which is worth copying:

```jsx
const [bookId, setBookId] = useState('')        // ── what the user typed
const [side, setSide]     = useState('BUY')
const [errors, setErrors] = useState({})        // ── validation, field → message
const [pending, setPending] = useState(false)   // ── request lifecycle
const [submitError, setSubmitError] = useState(null)
const [ack, setAck]       = useState(null)
const [requestId, setRequestId] = useState(newOpenTradeRequestId)   // ── idempotency
const [catalog, setCatalog] = useState(null)    // ── fetched reference data
const [termSchemas, setTermSchemas] = useState(null)
const [preview, setPreview] = useState(null)    // ── live server quote
```

**Validation returns a map, not a boolean.**

```js
const errors = tradeFormErrorsOf({ bookId, symbol, quantityText, price })
// → { book: 'Pick a book.' }
// → { quantity: 'Quantity must be a whole number between 1 and 1,000,000' }
// → { price: 'Mark rounds to 0.00 — not tradeable at these terms.' }
```

Rendered next to the field it belongs to, with `role="alert"`, `aria-invalid`, and
`aria-describedby` wiring the message to the input. An invalid form never sends a request — but
the server validates independently, because browser validation is a courtesy, never an
authority. (The same `validate_terms` runs server-side; see [pricing.md](../pricing.md).)

**A `202` cannot be chained.** Move-trades-then-delete-the-book is two user actions, not one
automated sequence: the move returns `202`, meaning *queued*, so deleting immediately would race
the reassignment worker and hit the "book still has active trades" guard. When a step's
completion is only observable, the next step waits for the observation — the UI shows the source
book emptying, and *then* Delete becomes the obvious next click.

**`202` is not "done".** Trade-action queues the intent and returns immediately. The panel shows
*accepted*, keeps its pending state, and waits for the blotter poll to observe the real status
change. After 15 seconds it says the workflow is slow — without declaring failure, because the
worker may still be processing.

**Idempotency lives in state.** `requestId` is generated once per form session and reused on
retry, so a double-submit deduplicates on the backend's unique constraint. A deliberately new
trade gets a new id. That same id is the correlation id in both observability trails
([logging.md](../logging.md)).

**Errors name the service and the consequence** — in two layers. The generic mapper turns a
status class into a sentence that always says *who* and *what did not happen*:

```js
describeApiError(err, { service: 'Books service', outcome: 'the book was not deleted.' })
// 502/503/504 or no status → "Books service unavailable — the book was not deleted."
// a timeout                → "Books service did not answer in time — …"
// 5xx                      → "Books service could not process the request — …"
// 4xx                      → "Rejected by Books service — the book was not deleted."
```

Then a view adds specificity wherever the backend returns a structured body — which is why
`ApiError` keeps the parsed `body`:

```js
if (error?.status === 409) {
  const open = Number(error.body?.active_trades)
  return `Refused — this book still has ${formatNumber(open)} open positions.`
}
if (error?.status === 503 && error.body?.error === 'open trades could not be verified') {
  return 'Blotter service unavailable — open positions could not be checked, so nothing was deleted.'
}
```

That second message is the frontend half of the backend's fail-closed rule
([architecture.md](../architecture.md#2-three-rules-that-explain-most-of-the-code)): the user is
told the check could not run, not that the book is protected.

**A form can quote the server while you type.** The New Trade ticket posts `{asset_class, terms}`
to `POST /price` as terms become valid and shows the live model mark, recomputed when the
underlying ticks. That is a read-only preview: nothing is stored, and a mark that rounds to 0.00
blocks the open.

**Closing books the price you were looking at.** A close is a `CLOSE_TRADE` intent carrying the
row's current mark as `close_price` and a fixed `close_reason` of `MANUAL_CLOSE` — the number on
screen is the number that gets executed, rather than one the worker re-derives from a tick that
may have moved since you clicked. The cost of that fixed reason is named in
[decisions.md](../decisions.md#scope): there is no reason picker, no price override, and no
reopen — a closed trade is closed.

### Draft vs server state

The generator's sliders edit values that a 2-second poll is simultaneously overwriting. The rule:

```text
render draft.value ?? server.value
```

A draft protects the in-progress edit; it is cleared **only if it still equals the value that
committed**, so an edit made *during* the request survives. After a successful write the screen
refetches and reconciles with server truth — no optimistic copy, no rollback path.

## 6. Panels

One `SidePanel` shell serves six features. It renders `<aside>` because the content supplements
the page, and it *pushes* the page rather than covering it ([styling.md](styling.md#4-the-panel-push-and-has)).

```jsx
<SidePanel eyebrow="TRADE STORY" title={id} subtitle="…" wide onClose={…}>
  {children}
</SidePanel>
```

Three collaborating pieces:

- **`PanelProvider`** (in `AppShell`) holds `activePanel` so only one panel is open at a time,
  and `switchingPanel` so replacing one panel with another changes content without replaying the
  slide-in animation.
- **`usePanelChrome`** adds exactly two document listeners for the life of the panel: Escape, and
  pointerdown outside. It deliberately does *not* trap focus or manage tab order — native
  keyboard behavior is left alone.
- **`data-panel-trigger`** marks controls that open panels, so clicking one while a panel is open
  is a *switch*, not an outside-click dismiss:

  ```js
  if (event.target.closest('[data-panel-trigger]')) return
  ```

**Detail data loads only when selected.** Clicking a trade row shows the list row's data
immediately, while `TradeDetail` separately polls `/trades/{id}` for valuation history and audit
events. Keying that component by trade id resets its polling and close-action state when another
row is selected ([react.md §7](react.md#7-keys-identity-not-just-a-lint-rule)).

## 7. States are part of the contract

Nine states, all real, all rendered. The ordering of the checks matters as much as the strings:

```jsx
if (visibleRows.length > 0)          tableContent = <ValuationTable … />
else if (openRows.length > 0)        tableContent = <EmptyState message="No valuations match these filters." />
else if (seedStatus === 'error')     tableContent = <EmptyState message="Could not load current valuations — retrying on reconnect." />
else if (seedStatus === 'loading' || status === 'CONNECTING')
                                     tableContent = <EmptyState message="Connecting to the valuation stream…" />
else if (status === 'RECONNECTING')  tableContent = <EmptyState message="Valuation stream unavailable — retrying." />
else                                 tableContent = <EmptyState message="No open positions are being valued right now." />
```

"No rows" has four different meanings and each gets its own sentence: *your filter excluded
everything*, *we could not load*, *we are still connecting*, *there genuinely are none*. A single
"No data" would hide a broken backend behind an empty state.

**Within a row, the status checks have their own precedence: CLOSED is decided before age.**
Freshness is computed from browser receipt time ([data.md §5](data.md#5-step-4--sse-and-what-eventsource-actually-is)),
and a closed trade stops receiving valuations by definition — so if age were checked first, every
closed row would silently drift into `STALE` a minute after it settled. Terminal beats temporal,
in the merge rule and in the status derived from it.

The rest of the catalogue:

| State | How it renders |
| --- | --- |
| Stale value | The row keeps its last value with a `STALE` pill — never blanked |
| Missing valuation | `PENDING`, never `0.00` |
| Warming-up statistic | `12/20 returns` with `n/a` metrics |
| Service down | A `DOWN` pill on the card plus the failing check's error text |
| Validation error | Beside the field, `role="alert"` |
| Write failure | Names the service and what did not happen |
| Slow write | "Still processing — the worker has not confirmed yet" |

**One copy rule holds across all of it:** the UI states facts in desk shorthand
(`Benchmark: MARKET_INDEX`, `12/20 returns`, `Close pending — awaiting confirmation.`) and never
explains concepts. Explanations live in these documents. Tutorial prose inside a trading screen
is the fastest way for a project to read as generated rather than built.

### Service health is a policy, not a field

`normalizeServiceStatus` shows how much thinking a "status" needs. The backend reports what it
observed; the *verdict* is the frontend's, and each rule has a failure it prevents:

| Rule | Prevents |
| --- | --- |
| The known service roster always renders | A service that has never answered silently disappearing from the page |
| Explicit `DOWN` is down | — |
| A slow `UP` becomes `DEGRADED` past `DEGRADED_LATENCY_MS` | "Responding" reading as "healthy" when it takes 3 s |
| An old observation becomes `STALE` | A stale verdict being shown as current |
| Unseen services stay `UNKNOWN` | Guessing about something never observed |
| If **monitoring itself** is unreachable, monitoring is `DOWN` immediately — its targets age into stale/unknown | Reporting seven services as down when the observer is what broke |

That last row is the important one, and it generalizes: **a missing observer is not a failing
system.** The thresholds live in `config/monitoring.js`; the domain function applies them —
policy values and the mechanism that uses them stay separable.

### Counts must say which population they describe

A dashboard shows several different numbers that all look like "how many":

```text
`${visible.length} of ${lines.length} buffered`         rendered vs held in the browser
`${summary.open} open positions · ${summary.books} books`  the whole feed, not the page
`newest 500 of 1,021 matching · 1,021 buffered`         three populations in one line
```

Never let one number stand in for another: a closed-trade count comes from the **book summary**
(the server knows the total) while the table shows a **bounded window** of loaded rows. Labelling
a window as a total is the fastest way to make a dashboard lie. The same rule killed two earlier
tiles: a client-derived "trades per minute" (computed from a count-limited list — a rate inferred
from a truncated population is fiction) and queue depth as a headline (an always-draining queue
reads zero while work is flowing; see [performance.md](../performance.md)).

## 8. Formatting financial data

`domain/formatting.js` is small and opinionated, because inconsistent number formatting is what
makes a financial UI feel amateur:

| Function | Rule |
| --- | --- |
| `formatAmount` | `Intl.NumberFormat` with 0 decimals ≥ 10,000, else 2 — big numbers don't need cents |
| `formatSignedAmount` | Explicit `+` / `−` (U+2212, not a hyphen), and never `-0.00` |
| `formatUnitPrice` | Decimals per asset class — FX gets 5, everything else 2 |
| `formatPercent` | Fixed decimals, sign preserved |
| `formatClockTime(ms, {millis, day})` | `20:08:52.925`, optionally `08-12 20:08:52.925` |
| `formatShortId` | First 8 characters, uppercased — UUIDs are unreadable in a table |
| `directionOf` | `pos` / `neg` / `flat` → the CSS tone class |

Two conventions worth stating: **`—` (em dash) is the universal "no value"** so a missing number
never renders as `0`, `NaN`, or blank; and **every number in a table is monospace and
right-aligned**, so digits line up by place value and a change of magnitude is visible at a
glance.

## 9. Where each view's logic lives

| View | State it owns | Everything else comes from |
| --- | --- | --- |
| System Overview | selected service filter | monitoring polls + `serviceStatus.js` |
| Market Data | filters, tick-history depth | market feed context + `marketData.js` |
| Valuations & Risk | class, book, search | valuation feed + `valuations.js` |
| Books | include-deactivated toggle, panel target | blotter poll + `books.js` |
| Trades & PnL | filters, page, selected trade | blotter poll + valuation feed + `trades.js` |
| Business Overview | — | valuation feed |
| Generator | slider drafts | generation poll + `generator.js` |
| Trade Actions | — | queue poll + `auditEvents.js` |
| Logs | filters, search, pause, story target | logs feed + `logLines.js` |

The pattern to notice: **no view stores data that came from the backend.** It stores what the
user did, and derives the rest.

Two placement decisions inside that table are worth their own line:

- **New Trade lives in the app shell, not on a screen.** Opening a trade is not a Books action or
  a Trades action — it is available from the top bar on every route, and it loads its own books.
  *Put an action where its workflow belongs, not where one of its data sources happens to be
  displayed.*
- **Market Data renders three different things, not one table.** Spot instruments and curve
  tenors get **separate tables** because their units and sort rules differ (a price and a rate do
  not belong in one column), and `MARKET_INDEX` is a **card, not a row**: it is a non-tradable
  benchmark, so putting it in the instrument table would invite filtering and sorting it
  alongside things you can actually trade. Shape follows meaning.
