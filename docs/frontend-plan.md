# Frontend build plan & phase context

Living document for the Praca domowa nr 4 frontend (React + SCSS + Vite, hand-rolled
hash routing). It records **how we work**, the **conventions** we follow, and a
**per-phase context block** so any phase can be picked up without re-deriving decisions.

---

## How we work

- We build **one small phase at a time**. For each phase: I propose the plan + the
  concepts it teaches → you accept → I implement → you review.
- Order (your call): shell first, then pages one by one, then details (e.g. the
  bottom-left "streams connected" badge) last.
- Teaching style: I write the files and narrate the concepts so you can take notes.

## Backend-gap strategy

Some views need backend that doesn't exist yet. Rule:

- **Big domain features from `praca_domowa_04` are built LAST** (after the whole UI
  is wired). Until then the UI shows an **honest placeholder / "unavailable" state**,
  never a fake value. This matches the homework: *"if Pricing Service doesn't publish
  a valuation stream, the Blotter must not look like everything works."*
- **Small additions** (one endpoint, one extra field, a proxy entry) are done **inline**
  in the phase that needs them.

## Conventions (apply to every phase)

- **Routing:** hash-based (`#/market-data`). One registry `src/routes/routes.js` feeds
  both the Sidebar and the router. `useHashRoute` reads `location.hash`.
- **Styles:** design tokens as CSS custom properties in `src/styles/_variables.scss`
  (dark theme from the mockups). Structural CSS in `_layout.scss`. Entry `main.scss`.
  Prefer tokens (`var(--...)`) over hard-coded colours.
- **Data flow:** data down via props; each view owns its own data fetching/stream.
- **Proxy:** browser can't see Docker container names, so the browser calls **relative
  paths** and Vite proxies them. We add a `/api/<service>` proxy entry **per phase** as
  each page starts talking to its service. (See `vite.config.js`.)
- **Performance rule (real-time):** frequent ticks must **not** re-render the whole app.
  Cap buffered events, and keep stream state local to the view that needs it.
- **UI states:** every data view should handle loading / empty / connected /
  reconnecting / stale / backend-error / no-matching-filters / service-down.

---

## Backend inventory (as of Phase 1)

| Service | Exists today | SSE? |
|---|---|---|
| market-data | `GET /stream`, `GET /snapshot`, `GET /health` | ✅ `/stream` |
| pricing | `GET /valuations`, `GET /valuations/{id}`, `GET /valuation-stream`, `POST /scenario`, `GET /health` | ✅ `/valuation-stream` |
| books | `GET/POST /books`, `GET/PUT/DELETE /books/{id}`, `GET /health` | — (poll) |
| blotter | `GET /books/summary`, `GET /trades`, `GET /trades/{id}`, `/trades/{id}/valuations`, `/trades/{id}/audit-logs`, `GET /health` | — (poll) |
| monitoring | `GET /status`, `GET /health` | — (poll; allowed by homework) |
| trade-generation | `POST /generate-once`, `POST /start`, `POST /stop`, `GET /status`, `GET /health` | — (poll) |
| trade-action | `POST /trade-actions`, `/batch`, `/close-all`, `GET /queue/status`, `GET /health` | — (poll) |

**Known gaps** (resolved later per the strategy above):

- **Big / end-of-project (domain, from praca_domowa Part 1):**
  - European option (Black–Scholes) pricing — *verify if present in pricing engine.*
  - IRS pricing + rate curve in market data (`MarketDataCurves`).
  - **alpha / beta per book** (rolling window vs `MARKET_INDEX` benchmark) in the
    valuation stream. → Valuations & Risk + Business Overview show a placeholder for
    alpha/beta until this exists.
  - Alembic migrations for the new instruments/metrics.
- **Small / inline additions:**
  - trade-generation **`GET /events`** (recent generated intents) — Generator view.
  - trade-action **`GET /events`** + a **`GET /status`** summary (throughput, errors,
    last actions) — Trade Actions view. Only `queue/status` exists today.
  - Design decision: **Monitoring has no separate sidebar page**; System Overview
    doubles as the monitoring view (matches the mockups). Document in README.

---

## Phases

### Phase 1 — App shell ✅ (done, in review)
- **Goal:** sidebar + top bar + navigation + base styles; placeholder pages.
- **Concepts:** component composition (`App → AppShell → Sidebar/TopBar/page`); route
  registry (single source of truth / DRY); hash routing mechanics + active link;
  SCSS design tokens + flexbox shell.
- **Files:** `routes/routes.js`, `hooks/useHashRoute.js`, `layout/{AppShell,Sidebar,TopBar}.jsx`,
  `components/PagePlaceholder.jsx`, `views/*/*.jsx` (8 placeholders),
  `styles/{_variables,_layout,main}.scss`, rewired `App.jsx` + `main.jsx`.
- **Backend deps:** none.
- **Review checklist:** sidebar groups + links match the mockups; clicking navigates
  without reload; active link highlights; refresh keeps the view; dark theme reads
  cleanly.

### Phase 2 — Data layer + System Overview ✅ (done, in review)
- **Goal:** shared data layer, then the System Overview page for real.
- **Built:** `services/apiClient.js` (+ `ApiError`), `services/endpoints.js`,
  `domain/serviceStatus.js` (normalize + POC DEGRADED>6ms rule + freshness + summary),
  `domain/formatting.js` (`formatElapsedTime`), cancellable `hooks/usePolling.js`,
  `hooks/useElapsedTime.js`, `components/{status/StatusPill, filters/FilterChipGroup,
  cards/ServiceCard, Panel, EmptyState}.jsx`, real
  `SystemOverview.jsx`, `styles/_components.scss`, proxy → `/api/monitoring`.
- **Deferred (honest placeholders):** SSE-connections panel (Phase 3), logs & errors
  panels (no backend feed yet).
- **Concepts:** `apiClient` (fetch wrapper, errors), `endpoints.js`, domain models
  (`ServiceStatus`, later `Book/Trade/Valuation`), a timeout-aware `usePolling` hook,
  reusable filter chips, and presentational components (StatusPill, service cards).
- **Backend deps:** `monitoring GET /status` (exists). Logs/errors panels: derive from
  what monitoring/health expose; if not available → placeholder panel.
- **Proxy to add:** `/api/monitoring` (rename from the current `/monitoring`).
- **Phase 3 hand-off:** the former "SSE connections" placeholder is now the live Market
  Data Stream panel with connection status, received ticks, instrument freshness, and last
  update.

### Audit feed experiment — after Phase 2

Use the existing audit mechanism to prove the System Overview event panels before expanding
the event catalogue. Split in two slices: **errors first** (now), the full operational-events
feed later. Errors-first sidesteps the volume question (`TRADE_CREATED`/`TRADE_CLOSED` arrive
~5/s while the generator runs) because the severity filter excludes INFO rows entirely.

**Slice 1 — Errors & Warnings panel (now):**

- [x] Read-only recent-audits endpoint on **monitoring-service** (`GET /audits`) with
  `limit`, `since`, and `severity` filters. Monitoring owns it: it already has DB access
  and the `/api/monitoring` proxy exists since Phase 2 — no new proxy entry.
  (`app/repository.py` + `/audits` route; response is a bare newest-first list.)
- [x] Alembic migration: partial index on `audit_logs(created_at)`
  `WHERE severity IN ('WARNING','ERROR','CRITICAL')` — tiny, and the only index this
  slice needs. (Deliberate exception to the end-of-project Alembic deferral.)
  (`b7e2f1a9c3d4_audit_severity_index`, mirrored in `AuditLog.__table_args__`.)
- [x] Panel: **“ERRORS & WARNINGS · LAST 5 MIN”** from recent `WARNING`/`ERROR`/`CRITICAL`
  rows, polled via `usePolling`. Including WARNING (small departure from the mockup —
  note in README) means the panel shows real data in normal demos: disabling a stream
  produces `STREAM_DISCONNECTED` warnings. Keep honest empty and unavailable states.
  (`domain/auditEvents.js`, `components/audit/AuditEventList.jsx`, wired in `SystemOverview`.)
- [x] Sync `AuditEventType`: add `ACTION_REJECTED` (written today as a raw string),
  drop unused `ACTION_ACCEPTED`.
- [x] Testing via `scenarios/errors.http`:
  - `POST /trade-actions` with a nonexistent `book_id` → `ACTION_REJECTED` (WARNING),
    deterministic, one request;
  - `GET /audits?severity=...` to read it back;
  - comment with `docker compose stop market-data-service` → pricing writes
    `STREAM_DISCONNECTED` (WARNING), and `docker compose stop postgres && sleep 5 &&
    docker compose start postgres` → real `DB_WRITE_ERROR` (ERROR). ERROR rows share the
    exact code path as WARNING — only the filter value differs.

**Slice 2 — Operational Events feed (later):**

- [ ] Extend `GET /audits` with `service` and `event_type` filters; decide how the panel
  handles per-trade noise (default to excluding `TRADE_CREATED`/`TRADE_CLOSED`, or an
  exclude-list). Add composite indexes only if the query needs them.
- [ ] Render audit rows as **Operational Events** (repurposes the “LOGS · ALL SERVICES”
  placeholder).

This experiment is not a full technical-log viewer. High-volume request/debug output and
stack traces remain structured stdout logs.

### Phase 3 — SSE + Market Data ✅ (done, in review)
- **Goal:** an app-lifetime `useSseStream` connection shared by System Overview and a live
  Market Data view.
- **Built:** `hooks/useSseStream.js` (EventSource lifecycle, named-event listeners, ref-held
  handler, CONNECTING/CONNECTED/RECONNECTING, cleanup close), `config/marketData.js`
  (stale threshold, history length, flush interval, event names, class order),
  `domain/marketData.js` (normalize ticks/curve → instrument rows, previous-tick delta,
  LIVE/STALE, pair symbols and market-level units), `views/MarketData/useMarketFeed.js`
  (snapshot seed + ref-buffer + throttled flush + tick counter),
  `providers/MarketFeedProvider.jsx` (app-lifetime stream shared by
  Market Data and System Overview, preserving state across routes), `sessionStorage`
  persistence for the received-tick count across same-tab refreshes,
  `components/charts/Sparkline.jsx` (dependency-free SVG),
  `components/cards/StatCard.jsx`, `components/marketdata/InstrumentTable.jsx`, real
  `MarketData.jsx`, `styles/components/_market-data.scss`, proxy → `/api/market-data`,
  `marketData` endpoints, and the System Overview Market Data Stream panel.
- **Concepts:** `EventSource` + named events, connection status
  (CONNECTING/CONNECTED/RECONNECTING), cleanup in `useEffect`, buffering + LIVE/STALE, throttling
  renders (ref buffer + interval flush → bounded re-renders), mini price history (sparkline).
- **Backend deps:** `market-data GET /stream` (named `market_tick`/`curve_tick` events) and
  `GET /snapshot` (both exist).
- **Proxy added:** `/api/market-data` → `market-data-service:8001` (Vite streams
  `text/event-stream` through unbuffered).
- **Deferred (honest):** per-row **Buy/Sell** actions → Phase 6 (New Trade / trade-action);
  bottom-left global **"streams connected"** badge → shell detail, done last. Market Data
  shows its own per-view connection pill meanwhile.

### Phase 4 — Valuations & Risk (+ Business Overview PnL)
- **Goal:** valuation stream view; PnL cards; alpha/beta.
- **Concepts:** merging a stream into a keyed map (latest per trade), realized vs
  unrealized PnL, money/percent formatting, freshness (LIVE/STALE) per valuation.
- **Backend deps:** `pricing GET /valuation-stream` + `/valuations` (exist).
  **alpha/beta:** likely a big gap → **placeholder** in the alpha/beta cells until the
  end-of-project backend work lands.
- **Proxy to add:** `/api/pricing`.

### Phase 5 — Trades & PnL (Blotter) + configurability
- **Goal:** the main operational table + trade drill-down.
- **Concepts:** configurable table (column pick, sort, filter), controlled inputs,
  live valuations from the stream (not just DB), trade details + valuation history +
  audit logs, `useLocalViewConfig` (localStorage).
- **Backend deps:** `blotter GET /books/summary`, `/trades`, `/trades/{id}`,
  `/trades/{id}/valuations`, `/trades/{id}/audit-logs` (exist); live prices reuse the
  pricing stream from Phase 4.
- **Proxy to add:** `/api/blotter`.

### Phase 6 — Books CRUD + Generator + Trade Actions + states polish
- **Goal:** remaining views + finish UI states + config persistence.
- **Concepts:** forms (create/edit/delete), optimistic vs refetch, POST/PUT/DELETE,
  polling status views, consistent empty/error/service-down states.
- **Backend deps:** books CRUD (exists). **Generator `GET /events`** and **Trade
  Action `GET /events`/`GET /status`** — *small additions* to add here, else placeholder.
- **Proxy to add:** `/api/books`, `/api/trade-generation`, `/api/trade-action`.

### End-of-project — deferred big backend features
Build **after** the UI is complete; then swap the placeholders for real data.
- [ ] Enrich audits with useful low-frequency technical transitions such as
  `DEPENDENCY_DOWN` / `DEPENDENCY_RECOVERED`, `WORKER_FAILED` / `WORKER_RECOVERED`, and
  persistence failure/recovery. Record state changes, not every retry.
- [ ] European option (Black–Scholes, `math.erf`, no scipy) pricing + fields.
- [ ] IRS pricing + rate curve (`MarketDataCurves`) in market data + stream.
- [ ] alpha/beta per book (rolling window, `MARKET_INDEX` benchmark) in valuation stream.
- [ ] Alembic migrations for the new instruments + metrics.
- [ ] Wire the frontend alpha/beta + option/IRS cells to the new data.

### Also required for submission (not a UI phase)
- [ ] `docs/wireframes/*.png` — the homework requires wireframes. We have full designs
  in `docs/designs/`; export/rename them (or trace simple wireframes) into
  `docs/wireframes/` with the required filenames.
- [ ] README additions: architecture, proxy, SSE streams, live-state approach,
  configurability, options/IRS, alpha/beta, known limitations.
