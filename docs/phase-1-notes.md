# Phase 1 notes — App shell

## Suggested inspection order

Read the files in this order — it goes entry point → styling → routing → composition →
content, which mirrors how the app is implemented.

1. **Boot** — `index.html` → `src/main.jsx`
2. **Styles** — `styles/_variables.scss` → `styles/_layout.scss` → `styles/main.scss`
3. **Routing foundation** — `routes/routes.js` → `hooks/useHashRoute.js`
4. **The shell** — `App.jsx` → `layout/AppShell.jsx` → `layout/Sidebar.jsx` → `layout/TopBar.jsx`
5. **The pages** — `components/PagePlaceholder.jsx` → `views/*/*.jsx`

---

## 1. Boot

**`index.html` — the single entry point**
One empty `<div id="root">` and a script tag loading `main.jsx`. A React app is a
single-page app: the browser loads one HTML file and everything else is JavaScript
rendering into that one div.

**`src/main.jsx` — React boot**
`createRoot(document.getElementById('root')).render(<App/>)` is the handoff from HTML to
React — it mounts `App` into the root div. `import './styles/main.scss'` once here applies
global styles to the whole document. `<StrictMode>` is a dev-only wrapper that
double-invokes effects to help catch bugs. This is the top of the execution flow.

## 2. Styles

**`styles/_variables.scss` — design tokens**
The dark theme as CSS custom properties (`--bg-app`, `--accent`, `--pos`, spacing, fonts,
`--sidebar-width`). Change a color here and it ripples everywhere. Read this first among
the styles — everything else references these `var(--…)`.

**`styles/_layout.scss` — the shell layout**
Structural CSS only. `.app-shell { display:flex }` puts sidebar and content side by side;
`.sidebar` is `position: sticky` so it stays while `.content` (`flex:1; min-width:0`)
scrolls. `min-width:0` is the subtle one — it lets wide tables scroll later instead of
blowing out the layout. Active-link styling lives here (`.sidebar__link--active`).

**`styles/main.scss` — style entry**
`@use "variables"` then `@use "layout"` pulls the partials in, then base resets
(`box-sizing`, body background/font, scrollbars). Underscore-prefixed files are SCSS
*partials* — they only compile when `@use`d from here.

## 3. Routing foundation

**`routes/routes.js` — the route registry (the spine)**
The single source of truth: an array of `{ path, label, subtitle, group, component }`.
Both the sidebar and the router read it, so the menu and routing can never disagree (DRY).
`findRoute(path)` looks up a route and falls back to the first (home) view for unknown
paths. Read this before the components — they all depend on it.

**`hooks/useHashRoute.js` — the router mechanism**
A custom hook. `readPath()` strips `#/` off `window.location.hash` (`#/market-data` →
`"market-data"`). The `useEffect` subscribes to the browser's `hashchange` event and
updates state so React re-renders on navigation; the cleanup removes the listener.
Changing the hash never reloads the page, yet back/forward/refresh still work. This is the
whole "router engine."

## 4. The shell

**`App.jsx` — wiring it together**
Three lines of logic: `useHashRoute()` gives the current path → `findRoute()` maps it to a
route → render `route.component` inside `<AppShell route={route}>`. This is the
`path → route → component` pipeline. Everything above feeds into here.

**`layout/AppShell.jsx` — the frame**
Composition in action: renders `<Sidebar>` + `<TopBar>` + `{children}`. It doesn't know
*which* page shows — `App` passes the page as `children` and the active `route` as a prop.
Data flows *down* via props. Reusable frame; routing logic stays in `App`.

**`layout/Sidebar.jsx` — navigation rendering**
Loops `GROUP_ORDER`, filters `ROUTES` by group, renders each as `<a href="#/path">`.
`isActive = route.path === activePath` drives the highlight class. The links are plain
anchors to hashes — that's what triggers `useHashRoute`. The `sidebar__spacer` div will
later push the "streams connected" badge to the bottom.

**`layout/TopBar.jsx` — header from route data**
Pure presentation: reads `route.label` + `route.subtitle` for the title, plus the
"New trade" button (styled placeholder, no handler yet). Shows one data source (the route)
feeding multiple parts of the UI.

## 5. The pages

**`components/PagePlaceholder.jsx` + `views/*/*.jsx`**
`PagePlaceholder` takes a `note` prop and renders it — write markup once, reuse with
different data (props). Each of the 8 view files is a stub rendering `<PagePlaceholder>`
with its own text. These are the real files we fill in phase by phase.
