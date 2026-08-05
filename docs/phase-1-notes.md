---
phase: 1
status: complete
revised: 2026-08-05
tags:
  - frontend
  - shell
  - routing
  - styles
---

# Phase 1 — what you should know

This phase created the React single-page application, its navigation shell, and the styling rules
that later screens reuse.

## 1. How the application starts

`index.html` contains one `<div id="root">`. `main.jsx` calls `createRoot(...).render(<App />)`, so
React owns everything inside that element. Navigation changes React state; it does not load another
HTML page.

`StrictMode` is enabled in development. It deliberately repeats setup and cleanup to expose effects
that leak listeners, timers, or network connections.

## 2. Routing is deliberately small

The application uses hash URLs such as `#/market-data`. `useHashRoute`:

1. reads `window.location.hash`;
2. stores the current path in React state;
3. listens for the browser's `hashchange` event;
4. removes the listener when the hook unmounts.

Hash routing needs no server fallback configuration because the fragment after `#` is handled only
by the browser. Back, forward, and refresh still work. A larger router was unnecessary because the
application does not need nested routes or route loaders.

`routes/routes.js` is the single route registry. Both `App` and `Sidebar` read it, preventing the
menu and rendered pages from drifting apart. Unknown paths fall back to the first route.

## 3. The shell uses composition

```text
App
└── AppShell
    ├── Sidebar
    ├── TopBar
    └── current page through children
```

`App` chooses the route. `AppShell` only provides the frame and renders `{children}`. This is React
**composition**: a reusable component owns structure while callers supply its content.

Data flows down through props. `TopBar` receives route metadata; `Sidebar` receives the active path.
Keeping this direction predictable makes later state bugs easier to locate.

## 4. Styling has a token layer

Theme values such as colors, spacing, widths, and fonts are CSS custom properties:

```css
color: var(--text-primary);
gap: var(--sp-4);
```

The values remain available at browser runtime and can be overridden by a future theme. SCSS is
used only to organize partial files with `@use`.

The shell is a flex layout: Sidebar beside the flexible content column. `min-width: 0` on the
content column is important—it allows later wide tables to scroll inside the page instead of
forcing the entire application wider than the viewport.

## 5. The reusable hook pattern begins here

`useHashRoute` establishes the lifecycle used by later hooks:

```text
read current external value
→ subscribe in useEffect
→ update React state when it changes
→ unsubscribe in effect cleanup
```

Later polling, SSE, clocks, and panel listeners follow the same ownership rule: the effect that
acquires an external resource must release it.

## Mental model

```text
index.html
  └── main.jsx
      └── App: hash path → route registry → page component
          └── AppShell: Sidebar + TopBar + page

styles/main.scss
  └── tokens → layout → component styles
```

## Current limits

- Hash routing is intentionally flat; there are no nested routes or loaders.
- Unknown routes return to the first screen instead of showing a dedicated 404 page.
- Later phases replaced the original placeholder pages but kept this routing and composition model.

## Main files

- `frontend/src/main.jsx` — React boot.
- `frontend/src/App.jsx` — path-to-page selection.
- `frontend/src/routes/routes.js` — route registry.
- `frontend/src/hooks/useHashRoute.js` — browser hash subscription.
- `frontend/src/layout/AppShell.jsx` — shared application frame.
- `frontend/src/styles/_variables.scss` and `_layout.scss` — tokens and shell layout.
