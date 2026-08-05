---
phase: 6c
status: complete
reviewed: 2026-08-05
tags:
  - frontend
  - layout
  - streams
  - ui-states
---

# Phase 6c — what you should know

This phase added one shared side-panel pattern, the collapsible sidebar and stream badge, consistent
UI states, and centralized browser-storage keys. It did not change backend business behavior.

## 1. The side panel

`SidePanel` is the shared shell used by trade details, New Trade, book create/edit, Move, and Delete.
It renders an `<aside>` because the content supplements the current page. The HTML element supplies
meaning; CSS supplies its right-hand position and motion.

The panel is fixed to the right and enters from outside the viewport:

```scss
.side-panel { animation: side-panel-in 0.2s ease; }
.content:has(.side-panel) { padding-right: var(--panel-width); }
```

`:has()` lets `.content` react when a panel exists below it in the DOM. The panel slides in while
the page gains matching right padding, which creates the push-aside effect. On screens below 900 px,
the panel uses the full width instead of pushing a page that no longer has enough space.

`SidePanel` owns the common heading, Close button, body, optional tabs and footer. Feature components
own their actual fields and data. This is React **composition**: one reusable shell receives content
through props and `children` instead of knowing every feature.

## 2. Opening, switching and closing

`PanelProvider` in `AppShell` coordinates the distant panel owners without passing props through the
whole component tree. This use of React context avoids **prop drilling**.

The coordinator exposes:

- `activePanel`: which owner may render a panel;
- `openPanel()` and `closePanel()`: the shared exclusivity protocol;
- `switchingPanel`: a short-lived signal saying that one panel is replacing another.

The interaction rules are:

| Action | Result |
|---|---|
| Open from a closed state | Panel and page animate into the open layout. |
| Click another trade row or panel action | Content changes directly; the panel does not slide out and back. |
| Click ordinary page content outside | Panel closes and the original click still happens. |
| Press Escape or Close | Panel closes. |

Panel-opening controls carry `data-panel-trigger`. `usePanelChrome` does not treat those controls as
outside-dismiss clicks. When a panel is already open, the replacement receives
`side-panel--no-enter`, so only its content changes visually.

## 3. `usePanelChrome` stays small

This hook only handles the two convenient ways to dismiss a panel that are not buttons: Escape and
clicking ordinary page content outside the panel. It adds those document listeners while the panel
exists and removes them when it goes away.

It does not move focus, restore focus, trap Tab, or keep a callback in a ref. Browser keyboard
behavior is otherwise untouched.

## 4. React identity fixed the Book form bug

React normally preserves a component when its type and tree position stay the same. Edit and Create
both rendered `BookFormPanel`, so changing `bookId` alone reused the old form state.

The caller now defines each form session explicitly:

```jsx
<BookFormPanel key={`${panel.type}:${panel.bookId ?? 'new'}`} />
```

A changed `key` unmounts the old session and mounts a clean one. That resets its `useState` values,
aborts the previous edit request through effect cleanup, and starts the correct Create or Edit
session. The key controls state identity; `switchingPanel` separately prevents a visible close/open
animation. State reset and visual motion are different decisions.

## 5. The detail tabs are just view switching

Details / Valuation history / Audit replace one long panel scroll, so Audit is immediately available.
They are ordinary buttons that set the local `tab` state; there is no custom Tab-key or Arrow-key
logic. Clicking a trade row remains mouse-driven.

## 6. The live streams stay global and continuous

`FeedProvider` is mounted above routing and owns both `EventSource` connections. Changing pages does
not unmount the provider, so market ticks and live valuations continue while viewing any route.
They also remain connected while the browser document is hidden.

`useSseStream` reports only real transport states:

```text
CONNECTING → CONNECTED
     failure ↓
RECONNECTING → CONNECTED → useStreamSeed refreshes the snapshot
```

There is no `SUSPENDED`, `PAUSED`, or `visibilitychange` lifecycle. Closing hidden-tab streams was
removed because the latest snapshot cannot reconstruct the intermediate market ticks that were
missed.

The accepted limitation is that three app tabs may exhaust the six HTTP/1.1 per-origin connections.
The eventual solution is HTTP/2 or one multiplexed SSE endpoint, not discarding live observations.

## 7. The badge and storage are derived, not duplicated

`StreamsBadge` reads the two existing feed contexts. It does not open streams or store another copy
of their state. It calculates the connected count and weakest status during render. This is
**derived state**: calculate what can be calculated from authoritative inputs.

`STORAGE_KEYS` centralizes browser-storage names:

- `localStorage`: durable view preferences such as sidebar collapse and table columns;
- `sessionStorage`: market snapshot/tick recovery for the current tab session;
- not persisted: filters, page size, and selected detail tab.

The rule is simple: remember workspace preferences, but do not silently preserve the user's current
question or filter.

## Mental model

```text
FeedProvider (above routing)
  ├── Market EventSource ──> market context ──┐
  └── Pricing EventSource ─> valuation context├──> StreamsBadge
                                              └──> page consumers

AppShell
  ├── PanelProvider ──> activePanel + switchingPanel
  └── .content:has(.side-panel) ──> reserves the panel width
          └── SidePanel
                ├── usePanelChrome: outside close · Escape
                └── feature content: trade detail or a write form
```

## Current verification and limits

- Opening from closed plays `side-panel-in`.
- Trade A → Trade B and Book Edit → Move keep exactly one panel and use no entry animation.
- An ordinary outside click closes the panel.
- Escape closes the panel.
- Both streams remain mounted across route changes.
- Lint, production build and dead-code checks pass.
- Below 900 px the panel is a full-width overlay.
- Three simultaneous HTTP/1.1 app tabs remain unsupported with two continuous streams per tab.

## Main files

- `components/panel/SidePanel.jsx` — shared semantic shell.
- `hooks/usePanelChrome.js` — outside click and Escape.
- `layout/AppShell.jsx` and `layout/panelContext.js` — exclusivity and switch coordination.
- `styles/components/_side-panel.scss` and `styles/_layout.scss` — slide and push-aside layout.
- `providers/FeedProvider.jsx` and `hooks/useSseStream.js` — continuous feed ownership.
- `layout/StreamsBadge.jsx` and `config/storage.js` — derived status and persistence policy.
