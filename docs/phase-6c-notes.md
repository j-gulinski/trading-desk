---
phase: 6c
status: complete
reviewed: 2026-08-04
tags:
  - frontend
  - layout
  - streams
  - ui-states
---

# Phase 6c — UI states, streams badge, config persistence (teaching notes)

Three independent units, built in the plan's fixed order, each verified before the next started:
the detail-panel rework, sidebar collapse plus the streams badge, and releasing the SSE connections
while a tab is hidden. Then the states sweep and the storage-key decision.

## Phase outcome in one line

Every overlay in the app became **one push-aside panel** that slides the page left instead of
covering it, the sidebar collapses to icons with the long-deferred `2 / 2 streams` badge, and a
hidden tab now gives its two SSE connections back — the fix for the connection ceiling 6b-1
measured.

## What was decided and why

### 1. CSS decides the push; a small coordinator decides exclusivity

The panel had to shrink the page content, but the panel is rendered deep inside a view (Trades
renders the trade detail; Books renders its forms) while the thing that must shrink is the app
shell's `.content`. The layout does not need a React state bridge: it only needs to know that a
panel exists in its subtree.

Instead: the panel is `position: fixed` on the right, and `.content:has(.side-panel)` adds
`padding-right: var(--panel-width)`. The layout follows the DOM, which is what the DOM is for.
`:has()` is the same generation of CSS as the container queries and `@starting-style` already in
this codebase.

**The trade-off, stated plainly:** the layout is now coupled to a class name rather than to a prop.
If a future panel forgets `.side-panel`, nothing shifts. That is the price of not building a
registration protocol for a boolean.

The interaction rule is different: two panels must never remain mounted together. A global **New
Trade** click can otherwise cover a Book edit/move panel while both document-level focus traps stay
active. `layout/panelContext.js` therefore gives `AppShell` one `activePanel` value. The three
callers claim their id when opening and release it when closing; changing the id unmounts the prior
panel and clears its local selection/dialog state. The coordinator is deliberately only an
exclusivity protocol — CSS still owns the push.

### 2. Losing `showModal()` means re-implementing three things by hand

The native `<dialog>` gave modality for free: a backdrop, a focus trap, Escape-to-close and focus
restoration. Push-aside is *not* modal — that is the whole point — so all four had to be re-decided,
not just re-implemented. `usePanelChrome` now owns them:

- **Escape closes.** A document-level `keydown`, not a panel-level one, because focus can legitimately
  be on the panel's own controls.
- **Focus enters the panel on open and returns to the trigger on close.** The trigger is whatever
  had focus at mount.
- **Tab is trapped inside the panel.** This is the one that deserves scrutiny — see below.

**The trap is a deliberate deviation from ARIA, kept because the review checklist asked for it.**
Strictly, a non-modal panel should let you tab out; trapping keyboard focus while leaving the mouse
free is a hybrid. The argument for keeping it: the value of push-aside here is *watching* the book
while inspecting a position, not interacting with two things at once, and an untrapped panel over a
250-row table means a Tab key that disappears into the table. Removing the trap is the four lines
that handle `event.key === 'Tab'` — a one-commit change if that reading turns out to be wrong.

**`onClose` had to be held in a ref.** Every caller passes an inline arrow, so a naive dependency
array re-runs the effect on every render — which would re-focus the first field on every keystroke.
The listener is registered once and reads the current callback through the ref.

### 3. Table rows became focusable, because "focus returns to the trigger" needs a trigger

The first implementation returned focus to `<body>`. Not a bug in the panel: the trade table's rows
were `<tr onClick>` with no `tabIndex`, so nothing was focused when the panel opened and there was
nothing to restore. Rows now take `tabIndex={0}` and respond to Enter/Space.

This is the useful part of the accessibility requirement: it did not just fix focus restoration, it
made the blotter keyboard-operable at all, which it had not been since Phase 5.

### 4. Tabs replace the long scroll, and the audit trail is now two interactions away

Details / Valuation history / Audit, with counts on the tabs. Audit events used to sit below a
100-row valuation history — reachable only by scrolling past everything else, which is how they
became invisible. Tabs are a `role="tablist"` with roving `tabIndex` and arrow-key navigation; only
the selected panel is mounted, so the valuation-history table costs nothing while you are reading
the details.

### 5. `form-dialog` became `panel-form`, and one stylesheet died

The four write forms kept their internals and lost their shells. The old `_form-dialog.scss` held
both — a drawer shell (`.form-dialog`, `__surface`, `__head`, `__close`, `__body`) and form controls
(`__input`, `__select`, `__submit`, …). The shell rules were duplicated almost exactly in
`.trade-detail`. Both shells are now `SidePanel`, and the surviving form-control rules are
`panel-form__*`, which is what they always described.

Renaming was the point: a class called `form-dialog__input` inside something that is not a dialog is
the kind of drift that makes a codebase hard to read a phase later.

### 6. A hidden tab releases its streams — the 6b-1 ceiling, fixed at the source

6b-1 measured it: each tab permanently holds 2 of the browser's 6 HTTP/1.1 connections per origin,
and **at three tabs every request in every tab queues forever**. `useSseStream` now closes its
`EventSource` on `visibilitychange` → hidden, and reconnects when visible.

This is not only a workaround for a browser limit — it is correct behaviour. A dashboard nobody is
looking at has no reason to hold a feed open, and the server stops fanning events at it.

Two consequences had to be handled honestly rather than hidden:

- **A suspended stream is a fourth status, not a disguised fourth.** `SUSPENDED` sits beside
  `CONNECTING`/`CONNECTED`/`RECONNECTING`. Calling it "reconnecting" would have been a lie, and
  calling it "connected" a worse one.
- **Resuming re-seeds.** `useStreamSeed` re-ran its snapshot load on `RECONNECTING → CONNECTED`; it
  now also does on `SUSPENDED → CONNECTED`. Without that, a tab returning from the background would
  render whatever it had before it was hidden and quietly wait for the next tick to correct it.

### 7. One storage-key scheme, in one file

Six keys existed across four files, already following `<area>.<thing>` by convention but nowhere
written down. They now live in `config/storage.js` as `STORAGE_KEYS`, which is what "one agreed
scheme" has to mean to be checkable — a convention nobody can see is a convention that drifts.

**What persists, and the rule behind it:** durable *view preferences* (column visibility and order
per table, sidebar collapsed) go in `localStorage`; *transient session state* (the market snapshot
and tick count, which exist to survive a reload, not a week) stays in `sessionStorage`. Filters,
tab selection and page size were considered and **deliberately left unpersisted** — a filter that
survives a reload is a filter the user forgot they set, and the next thing they report is missing
data. Column layout is a workspace choice; a filter is part of the question being asked right now.

## What changed during the build

- **`DataTable` gained keyboard row activation** (decision 3) — not in the plan, forced by the focus
  requirement.
- **Three views gained a `SUSPENDED` empty state.** Only reachable when the app is *loaded* in a
  background tab, which the release-on-hidden change makes possible for the first time. Without it
  those views would have said "No instruments published yet" while the stream was simply paused.
- **`streamStatusLabel`** exists so the status pill reads `PRICING PAUSED` rather than
  `PRICING SUSPENDED`. Internal names and user-facing words diverged, so the mapping is explicit.
- **Follow-up cleanup:** the two hooks used only by the retired native dialogs were deleted, and the
  move form no longer directs users to the deliberately dropped per-book Flatten flow. The SSE error
  handler also ignores closed or hidden sources, so a late error cannot revive a suspended stream.

## Mental model: what owns what

```
  AppShell ── collapsed flag (localStorage) ──> Sidebar ── RouteIcon · StreamsBadge
      │                                                        │ reads both feed contexts
      ├── activePanel ──> one of New Trade · Books · Trade detail
      └── .content ──┬── TopBar · view                         ▼
                     │                              2 / 2 streams · connected
                     └── <SidePanel>  (position: fixed, right)
                              ▲
        .content:has(.side-panel) { padding-right: --panel-width }   ← the push, in CSS

  usePanelChrome ── Escape · focus in · focus trap · focus back to trigger

  useSseStream ── visibilitychange ──> hidden: close(), status = SUSPENDED
                                       visible: connect(), status = CONNECTING → CONNECTED
                                                      └─> useStreamSeed re-seeds
```

Five callers, one panel: trade detail (wide, tabbed), New Trade, book create/edit, move positions,
and the delete confirmation. The coordinator ensures only one caller is mounted at a time.

## Process flow: opening a trade's audit trail

Tab or click a row (it is focusable now) → `TradeDetail` mounts `TradeDetailPanel` inside the view →
`.content:has(.side-panel)` shifts the page left, the table stays visible and its live PnL keeps
ticking → focus moves to the panel's first control and Tab stays inside → click **Audit** (or arrow
to it) → the audit list mounts, the valuation-history table unmounts → Escape → the panel unmounts,
the page slides back, and focus returns to the exact row you started on.

## The nine states × views matrix

Required deliverable for the sweep. Every cell is handled (how) or N/A (why).

| View | loading | empty | connected | reconnecting | stale | backend-error | validation-error | no-matching-filters | service-down |
|---|---|---|---|---|---|---|---|---|---|
| System Overview | "Loading service health…" | "No warnings or errors in the last 5 minutes." | per-service pill | status pill · `RETRYING` | freshness age per card | "Audit feed unavailable — retrying." | N/A — read-only | "No `<level>` events" | service card renders DOWN |
| Generator | "Loading generator status…" | "No generated intents recorded yet." | control state from `/status` | poll retry note | N/A — counters are cumulative | "Audit feed unavailable — retrying." | config bounds rejected before submit | feed filter chips | "Trade generation service unavailable — retrying." |
| Trade Actions | "Loading recent actions…" | "No trade actions recorded yet." | queue counters live | poll retry note | N/A — cumulative counters | "Audit feed unavailable — retrying." | N/A — read-only | feed filter chips | queue tiles render unavailable |
| Business Overview | "Connecting to the valuation stream…" | "No trades are being valued yet." | `PRICING CONNECTED` | "Valuation stream unavailable — retrying." | LIVE/STALE split tile | "Could not load current valuations…" | N/A — read-only | N/A — no filters | stream status pill |
| Market Data | "Connecting to market data…" | "No instruments published yet." | `MARKET CONNECTED` | "Market data stream unavailable — retrying." | per-instrument STALE pill | "Could not load the market snapshot…" | N/A — read-only | "No market instruments match these filters." | stream status pill · **PAUSED** when hidden |
| Valuations & Risk | "Connecting to the valuation stream…" | "No open positions are being valued right now." | `PRICING CONNECTED` | "Valuation stream unavailable — retrying." | STALE tile + per-row pill | "Could not load current valuations…" | N/A — read-only | "No valuations match these filters." | stream status pill · **PAUSED** when hidden |
| Books | "Loading books…" | "No books yet — create the first one." | 5 s poll + drill-down from stream | "Book list refresh failed — showing the last available data." | drill-down LIVE/STALE per symbol | same refresh-failed notice | per-field on create/edit; 409/503 on delete | "No books match these filters." | "Blotter service unavailable — retrying." |
| Trades & PnL | "Loading the operational blotter…" | "No trades have been recorded yet." | `PRICING CONNECTED` + live overlay | stream pill + snapshot age | per-row valuation status | "Blotter service unavailable — retrying." | close-trade confirm + failure note | "No trades match these filters." | table falls back to blotter rows |
| Trade detail panel | "Loading valuation history…" | "No audit events recorded for this trade." | live PnL from shared feed | "Detail refresh failed — showing the last available data." | valuation status pill in head | same notice | close-trade error note | N/A — no filters | "Valuation history is unavailable." |
| Write panels (new trade · book form · move · confirm) | "Loading books…" / "Loading book…" | "There is no other `<class>` book to move them into." | N/A — not stream-backed | N/A — single request | N/A | `describeApiError` names the service | `field → message` map, `aria-invalid` + `role="alert"` | N/A | "Books service unavailable — the book was not saved." |

Two cells changed in this phase: Market Data and Valuations gained **PAUSED**, and Business
Overview gained the matching empty message.

## Honest gaps

- **The three-tab fix could not be verified end to end in this harness.** Playwright's pages all
  report `visibilityState: 'visible'` regardless of which is foremost, so background tabs never fire
  `visibilitychange` and never release their connections. The mechanism was verified directly
  instead — dispatching `visibilitychange` with `document.hidden` stubbed closes both streams
  (badge: `0 / 2 streams · paused · tab hidden`) and restoring visibility reconnects both
  (`2 / 2 streams · connected`) with a re-seed. **The real-tab measurement from 6b-1 should be
  repeated by hand in Chrome before this is called closed.** Incidentally the harness reproduced the
  original fault: with three pages open and none of them hidden, a fourth page load hung.
- **Books' drill-down says "No open position in this book is being valued right now" while the
  stream is paused.** True but incomplete. It only appears in a tab the user is not looking at, so
  it is not worth a fourth branch.
- **The focus trap is a deliberate ARIA deviation** — see decision 2.
- **The panel is a right-hand overlay below 900 px**, full width, with no push. There is nothing to
  push aside on a phone.

## Verification performed

Against the live stack, in clean Playwright (not the Chrome extension — it starves the page's
sockets):

- **Push-aside:** at 1680 px the trade table stays fully readable with the 620 px panel open, and
  its PnL column keeps updating from the shared feed while the panel is open. At 1200 px the page
  compresses rather than being covered. Books' card grid reflows 3 → 2 columns with a panel open.
- **Escape and focus:** Escape closes the panel; `document.activeElement` afterwards is the exact
  `<tr>` that opened it (`E5D12253COMMODITY_DEFAULT…`), not `<body>`.
- **Tabs:** Audit is two interactions from a row; counts render on the tab labels (`Valuation
  history 21`, `Audit 1`).
- **All five callers** render through `SidePanel`: trade detail, New Trade (from the top bar on
  Books), create/edit book, move positions (including the "no other EQUITY book" branch), and the
  delete confirmation. Opening New Trade while a Books or trade-detail panel is open replaces it;
  no two focus traps remain mounted.
- **Sidebar:** collapses to 60 px icon-only with the active route still marked; `localStorage`
  `layout.sidebar-collapsed = "true"` survives a reload; the badge renders `2 / 2 streams ·
  connected` expanded and `2/2` collapsed.
- **Stream release:** as described in the gaps above.
- `npm run lint` / `build` / `deadcode` clean. Knip's accepted list is unchanged from 6b-2.

## Concepts seen for the first time in this phase

- **`:has()` as layout plumbing.** A parent can react to a descendant's existence without being told
  about it. This replaces a whole category of "lift state up so the shell knows" refactors — at the
  cost of coupling layout to a class name.
- **Modality is a bundle, and giving up one part costs you the rest.** `showModal()` is not just a
  backdrop; it is a backdrop *plus* focus containment *plus* Escape *plus* focus restoration. Drop
  the backdrop and all four become decisions you own.
- **Callbacks in effects belong in refs.** An inline arrow in a dependency array re-runs the effect
  every render. Registering once and reading the latest callback through a ref is the standard shape
  for any effect that installs a listener.
- **Visibility as a resource signal.** `visibilitychange` is usually treated as an analytics hook.
  Here it is the release point for a scarce resource — connections — which is what makes a
  many-tab dashboard viable at all over HTTP/1.1.

## Files for first-pass review

`layout/panelContext.js` → `hooks/usePanelChrome.js` → `components/panel/{SidePanel,PanelTabs}.jsx` → `styles/components/
_side-panel.scss` + the `:has()` rule in `styles/_layout.scss` → `components/trades/
TradeDetailPanel.jsx` (the tabbed caller) → the three converted forms (`NewTradePanel`,
`BookFormPanel`, `MoveTradesPanel`) + `components/panel/ConfirmPanel.jsx` →
`hooks/useSseStream.js` + `hooks/useStreamSeed.js` + `config/stream.js` (the suspend cycle) →
`layout/{Sidebar,StreamsBadge,RouteIcon}.jsx` → `config/storage.js`.

## Known limits

- The stream-release fix needs one manual three-tab confirmation in a real browser.
- Route icons are hand-drawn single-path SVGs, not an icon set; they read as glyphs, not as a
  designed system.
- The panel does not remember which tab was last open — reopening any trade starts on Details.
- Alpha/beta on the book cards is still E4; nothing in this phase touched it.
