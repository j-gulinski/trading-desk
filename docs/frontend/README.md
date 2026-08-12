# The frontend

React 19 + SCSS + Vite. **Three runtime dependencies** — `react`, `react-dom`, `sass` — and
nothing else: no router, no state library, no UI kit, no chart library, no HTTP client. Nine
views over seven backend services, two of them fed by SSE streams that stay open for the whole
session.

This folder is the frontend documentation. Start here, then read in this order:

| Document | Read it for |
| --- | --- |
| [react.md](react.md) | The React model itself: rendering, state, effects, refs, keys, context — written for a backend developer, with this codebase's code |
| [data.md](data.md) | Getting data in: the HTTP boundary, polling, SSE, snapshot+stream reconciliation, the render throttle |
| [screens.md](screens.md) | Building a view: the domain layer, tables, filters, forms and writes, panels, UI states |
| [styling.md](styling.md) | SCSS architecture, design tokens, layout mechanics, container queries, motion, accessibility |

## 1. The whole frontend in one picture

```text
main.jsx
└── StrictMode
    └── FeedProvider ──────────── 2 EventSource connections, session-long
        └── App ───────────────── hash route → route registry → page component
            └── AppShell ──────── Sidebar · TopBar · PanelProvider · {page}
                └── a view
                     ├── reads   feed context and/or usePolling
                     ├── derives view models via domain/ functions
                     ├── filters with local useState
                     └── renders StreamHeader · StatCards · FilterBar · DataTable · panels
```

Data flows one way down; the only shared state is the two feeds and which panel is open.

## 2. Folder structure and the import rule

```text
src/
  config/      thresholds, caps, poll cadences, storage keys, column definitions
  domain/      pure functions: normalizers, merge rules, derivations, formatting
  hooks/       reusable behavior: polling, SSE, buffering, table state, panel chrome
  providers/   FeedProvider — the two long-lived streams and their contexts
  services/    apiClient (the only fetch) + endpoints (the URL registry)
  routes/      the route registry
  layout/      AppShell, Sidebar, TopBar, StreamsBadge
  views/       one folder per screen
  components/  tables, panels, filters, status, charts, and per-feature components
  styles/      tokens → layout → one partial per component
```

**Imports run one way, and that is the order to read them in:**

```text
config → domain → hooks → providers → views → components
```

Nothing imports upward. A provider never reaches into a view; a component never reaches into
feature config; a domain function never imports React. When you are unsure where something
belongs, ask which layer may import it — that answers it.

## 3. The ten patterns that explain most of the code

| # | Pattern | One line | Where |
| --- | --- | --- | --- |
| 1 | Acquire / release | Every effect that subscribes returns an unsubscribe | [react.md §5](react.md#5-effects-acquire-then-release) |
| 2 | Callback in a ref | Subscribe once, always call the newest callback | [react.md §6](react.md#6-refs--three-different-jobs) |
| 3 | Functional `setState` | The merge must see current state, not the render's closure | [react.md §4](react.md#4-state-and-the-two-ways-to-get-it-wrong) |
| 4 | `key` as identity | A different subject means a fresh component, not reused state | [react.md §7](react.md#7-keys-identity-not-just-a-lint-rule) |
| 5 | Derive, don't store | If it can be computed from the feed, it is not state | [react.md §9](react.md#9-derived-state-if-you-can-compute-it-dont-store-it) |
| 6 | Seed + stream | Snapshot for completeness, stream for currency, domain rules for conflicts | [data.md §5](data.md#5-step-4--sse-and-what-eventsource-actually-is) |
| 7 | Buffer, flush on a clock | Ingest continuously, publish to React twice a second | [data.md §6](data.md#6-steps-56--ingest-continuously-publish-on-a-clock) |
| 8 | Normalize at the boundary | Components never see a raw payload | [screens.md §2](screens.md#2-the-domain-layer--where-the-thinking-lives) |
| 9 | Captured sort | Freeze the order, keep the values live | [screens.md §3.2](screens.md#32-captured-sort--the-live-data-problem) |
| 10 | Honest states | Nine real states; never an invented zero | [screens.md §7](screens.md#7-states-are-part-of-the-contract) |

## 4. Recipe — adding a new view

1. **Route** — add an entry to `routes/routes.js` (`path`, `label`, `subtitle`, `group`,
   `component`) and an icon case in `layout/RouteIcon.jsx`. The sidebar and the top bar both read
   the registry, so nothing else needs touching.
2. **Endpoint** — add the URL to `services/endpoints.js`. If it is a new service, add a proxy
   entry to `vite.config.js` and restart the dev server.
3. **Config** — put caps, poll intervals, and column definitions in `config/<feature>.js`. No
   magic numbers in components.
4. **Domain** — write `normalize…`/`…RowsOf` in `domain/<feature>.js`. Pure functions, no React.
   This is where defensive parsing belongs.
5. **Data** — `usePolling` for slow facts; for a stream, compose `useSseStream` + `useStreamSeed`
   (+ `useBufferedUpdates` if it is chatty) into a `use<Feature>Feed` hook.
6. **View** — `views/<Feature>/<Feature>.jsx`: read, derive, filter with local state, bound, and
   render. Copy the state-check ladder from [screens.md §7](screens.md#7-states-are-part-of-the-contract)
   so every empty case says something true.
7. **Styles** — `styles/components/_<feature>.scss` plus one `@forward` line in
   `_components.scss`.
8. **Check** — `npm run lint && npm run build && npm run deadcode`, then look at it in a browser
   with the backend running.

## 5. Running and checking it

```bash
npm run dev        # Vite dev server (the whole stack: docker compose up --build)
npm run lint       # oxlint
npm run build      # production build — catches what lint doesn't
npm run deadcode   # knip: unused files and exports
```

`npm run deadcode` earns its place: every mid-course reversal leaves an unused export behind, and
lint and build both pass with them. It is the only way this codebase stays free of orphaned
helpers.

There are no unit tests — a deliberate scope decision recorded in
[decisions.md](../decisions.md). Verification is lint + build + dead-code + exercising the real
app against the real backend, including the failure paths (stop a service and watch the UI say
so).

## 6. How the browser reaches the backend

The browser requests same-origin paths; Vite proxies them by container name:

```js
'/api/pricing': { target: 'http://pricing-service:8002', rewrite: p => p.replace('/api/pricing', '') }
```

This is mandatory, not stylistic: **the browser cannot resolve `pricing-service`** — that name
exists only inside the Docker network. It also removes any need for CORS on seven services, and
SSE flows through the same path. Production needs a reverse proxy exposing the same public paths.

## 7. What the frontend deliberately does not do

- **No client-side business logic.** Prices, PnL, alpha and beta all arrive computed; the browser
  formats and arranges them. A second implementation of a valuation would be a second source of
  truth.
- **No optimistic writes.** `202 Accepted` is shown as *accepted*; the row appears when the
  backend says it exists.
- **No fabricated values.** Missing data renders `—`, `PENDING`, `n/a`, or a warming-up count.
- **No full history.** Tables render a bounded window over what is loaded; deep history needs
  server-side pagination, which is named as a limitation rather than faked with client paging.
- **No auth.** Out of scope at this stage of the project.
