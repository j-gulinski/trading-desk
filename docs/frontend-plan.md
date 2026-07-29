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
- **Reuse the mechanism, re-decide the policy.** A pattern proven in one phase is not
  automatically right in the next. Phase 4's fan-out valuation feed reused Phase 3's table and
  transport but had to drop its row flash: what reads as a useful signal on ~10 sparse rows is
  noise — and a real render cost — when one input updates hundreds of rows at once.

## Conventions (apply to every phase)

- **Routing:** hash-based (`#/market-data`). One registry `src/routes/routes.js` feeds
  both the Sidebar and the router. `useHashRoute` reads `location.hash`.
- **Styles:** design tokens as CSS custom properties in `src/styles/_variables.scss`
  (dark theme from the mockups). Structural CSS in `_layout.scss`. Entry `main.scss`.
  Prefer tokens (`var(--...)`) over hard-coded colours.
- **Data flow:** data down via props. A data source lives at its narrowest common owner:
  view-local when one route consumes it, provider-owned when multiple routes need the same
  live connection. Market data is the first provider-owned source because both Market Data
  and System Overview consume it.
- **Proxy:** browser can't see Docker container names, so the browser calls **relative
  paths** and Vite proxies them. We add a `/api/<service>` proxy entry **per phase** as
  each page starts talking to its service. (See `vite.config.js`.)
- **Performance rule (real-time):** frequent ticks must **not** re-render the whole app.
  Bound and coalesce buffered events, publish state on a controlled cadence, and keep the
  provider value limited to consumers that actually need the stream.
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
  - IRS instruments and pricing. The USD government rate curve and its snapshot/SSE
    contract were completed in Phase 3.
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

### Phase 3 — SSE + Market Data ✅ (browser scope complete; backend follow-ups recorded)
- **Goal:** an app-lifetime `useSseStream` connection shared by System Overview and a live
  Market Data view.
- **Built — transport and feed:** `hooks/useSseStream.js` (EventSource lifecycle,
  named-event listeners, ref-held handler, fixed-delay reconnect required by the Vite/Docker
  proxy, CONNECTING/CONNECTED/RECONNECTING, cleanup close);
  `hooks/useMarketFeed.js` (concurrent identity-ordered snapshot seed with the documented
  unversioned cold-start-row exception, bounded latest-per-instrument ref buffer, atomic
  throttled flush, reconnect reconciliation, tick counter);
  `providers/MarketFeedProvider.jsx` + `providers/marketFeedContext.js` (app-lifetime stream
  shared by Market Data and System Overview, preserving state across routes); versioned
  `sessionStorage` persistence for bounded instrument history and the received-tick count
  across same-tab refreshes; proxy → `/api/market-data`; `marketData` endpoints; and the
  System Overview Market Data Stream panel.
- **Built — domain:** `config/marketData.js` (stale threshold, history length, flush
  interval, event names, column descriptors); `domain/marketData.js` (normalize ticks/curve →
  instrument rows, ordered merge, independent last-tick and observed-period deltas,
  LIVE/STALE, row derivation, market sort adapters); `domain/marketFormat.js` (value, delta,
  symbol and unit presentation); `domain/tableSort.js` (nulls-last ordering, direction,
  tie-break — no market knowledge).
- **Built — screen:** `hooks/useTableState.js` (column visibility, order, persistence, sort
  state, snapshot capture — reusable); `components/tables/DataTable.jsx` +
  `ColumnPicker.jsx` (generic table shell and preference UI);
  `components/marketdata/MarketTable.jsx` + `MarketCell.jsx` (market adapters);
  `components/marketdata/MarketIndexCard.jsx`; one dependency-free SVG `Sparkline`, reused at
  row size in the tables and at card size for the benchmark; `components/cards/StatCard.jsx`; real
  `MarketData.jsx`; `styles/components/_table.scss` + `_market-data.scss`, with `.content`
  as a CSS container so breakpoints track the content column rather than the viewport.
- **Concepts:** `EventSource` + named events, connection status
  (CONNECTING/CONNECTED/RECONNECTING), cleanup in `useEffect`, buffering + LIVE/STALE, throttling
  renders (ref buffer + interval flush → bounded re-renders), process/event ordering,
  stable snapshot sorting, independently persistent movable optional columns in the market
  and yield-curve tables, a dedicated yield-curve table, mini price history (sparkline), and
  container queries for a fixed-sidebar layout.
- **Reading order:** the screen reads one way — `instruments → rows → filter → sort → table`
  — and imports run one way: `config → domain → hooks → providers → views → components`.
- **Notes:** `docs/phase-3-notes.md` documents the implemented data flow and review
  findings. The Market Data implementation reference artifact traces one price change from
  the wire to a rendered row.
- **Backend deps:** `market-data GET /stream` (named `market_tick`/`curve_tick` events) and
  `GET /snapshot` (both exist).
- **Proxy added:** `/api/market-data` → `market-data-service:8001` (Vite streams
  `text/event-stream` through unbuffered).
- **Deferred (honest):** per-row **Buy/Sell** actions → Phase 6 (New Trade / trade-action);
  bottom-left global **"streams connected"** badge → shell detail, done last. Market Data
  shows its own per-view connection pill meanwhile.

### Phase 4 — Valuations & Risk (+ Business Overview PnL) ✅ (built, revised against the designs, reviewed)

- **Goal:** valuation stream view; PnL cards; alpha/beta.
- **Outcome:** a second, independent feed beside the market feed with `useSseStream` unchanged.
  Seven Phase 3 units reused as-is; two shared hooks extracted while being used; one input added to
  the generic table hook. Six defects during the build, four more in review.
- **Full detail:** `docs/phase-4-notes.md` (file-by-file, in inspection order, with the
  measurements). The implementation artifact covers the same ground organised by topic. This
  section keeps only what later phases need to know.

**Built**

- **Backend (small, inline):** `/valuation-stream` yields an immediate `: connected` comment and
  sets `Cache-Control: no-cache`; its pricing-specific per-client queue holds 5,000 events;
  `market_data_connection` initialized in the module `/health` reads it from; stream audits isolated
  and recorded on connection **transitions**; `book_name`, `quantity` (signed) and `trade_price`
  joined onto every valuation so the screens need no second data source.
- **Shared layer:** `hooks/useStreamSeed.js`, `hooks/streamClock.js`,
  `hooks/useBufferedUpdates.js`, `domain/filters.js`, `config/stream.js`, consolidated
  `domain/formatting.js`, and shared `StreamHeader` / `FilterBar` / `SortCaptureStatus`.
  `useMarketFeed` was rewritten onto the shared hooks.
- **Feed and screens:** `config/valuations.js`, `domain/valuations.js`, `hooks/useValuationFeed.js`,
  `providers/feedContext.js` + `FeedProvider.jsx` (both app-lifetime streams; the four Phase 3
  provider files collapse to two), `components/valuations/*`, real `Valuations.jsx` and
  `BusinessOverview.jsx`, and one `LIVE STREAMS` panel on System Overview covering both feeds.

**Contracts and rules later phases inherit**

- **Payload:** `quantity` is **signed by the producer** and `side` is not published. The
  static-per-trade fields (`quantity`, `trade_price`, `book_name`) are deliberate denormalization,
  measured at 19% of a 513-byte event; the reference-data alternative needs a client cache and a
  gap-filling path for continuously created trades. `book_name` moves first if that ever matters.
- **Merge policy:** a **final valuation is terminal**, otherwise **strictly newer wins** per trade.
  Both rules are enforced on the server (`record_valuation` returns its decision; rejected
  valuations are neither persisted nor published) *and* in `mergeValuation`, because the server
  cannot guarantee record order against its own transaction boundary. Reconnect re-seeding is
  idempotent as a side effect.
- **Ordering identity is still missing.** The contract has `valuation_time` but no producer epoch or
  event sequence. Timestamps express ordering, not supersession — which is why the terminal rule
  had to be added separately. Durable replay or dedup across clock changes needs explicit identity.
- **One 500 ms UI scheduler for the whole app.** `FLUSH_INTERVAL_MS` and
  `FRESHNESS_INTERVAL_MS` live in `config/stream.js`. Buffered feeds subscribe to every base tick;
  `useElapsedTime` subscribes to every second tick. This gives two flush opportunities per
  one-second freshness update, with the second flush and freshness entering React in one task. Each
  feed hook memoises its returned object, so a screen consuming one feed does not re-render on the
  other. Any new stream should use `useBufferedUpdates` and do the same.
- **Seed state is `'loading' | 'ready' | 'error'`,** named `seedStatus` on every feed, so a failed
  seed is distinguishable from an empty one. Every data view needs the failed-seed branch.
- **`useTableState` takes `hasRows`.** A snapshot default sort has nothing to capture before the
  feed seeds. Inert unless the default sort is a snapshot column.
- **Persisted column state stores `visible` *and* `known`,** so a column shipped later is not
  mistaken for one the user hid. Legacy arrays migrate in place.
- **Time display:** milliseconds only on server-stamped times (per-row `Updated`); seconds on
  anything derived from browser arrival. Freshness belongs to the group header, per-event time to
  the row.

**Revised three times**

1. **Against the designs.** The screen had grown a Positions view, a Positions/Trades toggle and a
   second column configuration the mockup does not contain — ~300 lines, all compensating for an
   unbounded trade generator rather than solving anything. Cause fixed in the generator (see
   Phase 6), machinery removed, `positionsOf` kept unwired for Books. Also fixed here: a
   render-time ref write in `useTableState`, and the FX-decimals consolidation that blanked Market
   Data because the deleted helper had a second caller.
2. **Review pass.** Two flush timers merged into one clock; provider values memoised; the two System
   Overview stream panels merged into one group with a single labelled timestamp; and the
   post-final valuation race fixed properly — the build-time fix had guarded the cache but not the
   publish path, so a stale non-final still reached the browser and re-opened a closed trade
   (measured at 1 of 158 finalized trades).
3. **Performance follow-up.** Pricing's valuation queue increased independently of Market Data;
   feed flushing and `useElapsedTime` joined one shared scheduler at 500 ms and 1,000 ms
   respectively; the shared Sparkline was memoised and clarified; and the complete snapshot →
   stream → buffer callback → context → screen pipeline plus the 250-row performance decision were
   recorded in `phase-4-notes.md`.

- **Backend deps:** `pricing GET /valuation-stream` + `/valuations` (exist).
- **Proxy added:** `/api/pricing` → `pricing-service:8002`.
- **Phase 3's fixed two-second reconnect kept.** Exponential backoff was reconsidered and rejected
  again for the reason `phase-3-notes.md` records: native `EventSource` retry did not resume
  reliably through the Vite/Docker proxy, and backoff adds tuning constants against a stampede
  problem a single-browser demo does not have.
- **Deferred (honest):** alpha/beta shows `n/a` with the reason on each book card until the
  end-of-project backend work lands; realized PnL survives only as long as pricing's in-memory
  cache, so durable realized PnL belongs to the Blotter in Phase 5; pricing never evicts closed
  valuations, so the seed payload grows for the life of the process — a retention window is
  outstanding; the "New trade" button and the global streams badge remain later work.

### Phase 5 — Trades & PnL (Blotter) + configurability
- **Goal:** the main operational table + trade drill-down.
- **Concepts:** configurable table (column pick, sort, filter), controlled inputs,
  live valuations from the stream (not just DB), trade details + valuation history +
  audit logs. Column pick/sort/persistence comes from the Phase 3 `useTableState` +
  `DataTable` + `ColumnPicker` set; only blotter-specific columns and cells are new.
- **Backend deps:** `blotter GET /books/summary`, `/trades`, `/trades/{id}`,
  `/trades/{id}/valuations`, `/trades/{id}/audit-logs` (exist); live prices reuse the
  pricing stream from Phase 4.
- **Inherited from the Phase 4 revision:** the **Qty** and **Entry** columns belong here — the
  `Trades & PnL` mockup shows Side and Qty, `Valuation & Risk` does not. The valuation payload
  already carries `quantity` (signed) and `trade_price`, so no backend work is needed. Expect a
  snapshot-column default sort, which means passing `hasRows` to `useTableState` as Phase 4 did.

- **Proxy to add:** `/api/blotter`.

### Phase 6 — Books CRUD + Generator + Trade Actions + states polish
- **Inherited from the Phase 4 revision:** `positionsOf` in `domain/valuations.js` is written,
  tested against live data and **unwired** — net exposure per book × symbol is the natural content
  of the **Books** screen. It nets signed market value (so offsetting trades net rather than sum
  gross), weights entry by |quantity|, and propagates worst-case freshness.
- **Goal:** remaining views + finish UI states + config persistence.
- **Concepts:** forms (create/edit/delete), optimistic vs refetch, POST/PUT/DELETE,
  polling status views, consistent empty/error/service-down states.
- **Backend deps:** books CRUD (exists). **Generator `GET /events`** and **Trade
  Action `GET /events`/`GET /status`** — *small additions* to add here, else placeholder.
- **Generator realism — ✅ resolved in the Phase 4 revision, not here.** The open book used to grow
  without bound: `TRADE_GENERATION_INTERVAL_MS=200` (five trades/second) with a fixed
  `CLOSE_PROBABILITY=0.3` meant opens permanently outran closes — past 2,000 open trades at ~$1m
  each within a demo session. `CLOSE_PROBABILITY` became a bounded
  `p_close = min(0.9, 0.5 × open/target)` policy, the interval is 1500 ms and
  `TARGET_NOTIONAL` is 250,000. The mechanism was first measured with
  `TARGET_OPEN_TRADES=50`: 20 → 32 → 44 → 46 → 48 → 49 → 45 open trades over five minutes,
  flattening at that target. The current higher-load configuration uses
  `TARGET_OPEN_TRADES=300`. What remains for this phase:
  - Observed consequence at scale, worth keeping as the acceptance test: at ~2,100 open trades the
    Valuations screen showed **198 LIVE against 1,896 STALE**. Pricing must value and persist every
    open trade on every tick of its symbol — roughly 1,000 valuations/second, each with its own
    `save_valuation` insert. The pricing client queue was 500 when this was observed and is now
    5,000, which provides publication-burst headroom but does not accelerate those inserts. The UI
    was reporting the resulting staleness truthfully; the primary fixes are to bound the book
    (above) and batch valuation persistence if this scale becomes a requirement.
  - Also worth handling here: `_open_trades` is in-memory, so after a restart the generator cannot
    close trades it did not open — orphans accumulate. Seeding it from the active book on startup
    belongs with this work.
  - The **market tick** generator needs no change: it is already a mean-reverting Gaussian walk at
    ~0.065%/tick with realistic tick sizes and spreads. The prices were never the unrealistic part.
- **Proxy to add:** `/api/books`, `/api/trade-generation`, `/api/trade-action`.

### End-of-project — deferred big backend features
Build **after** the UI is complete; then swap the placeholders for real data.
- [ ] Enrich audits with useful low-frequency technical transitions such as
  `DEPENDENCY_DOWN` / `DEPENDENCY_RECOVERED`, `WORKER_FAILED` / `WORKER_RECOVERED`, and
  persistence failure/recovery. Record state changes, not every retry.
- [ ] European option (Black–Scholes, `math.erf`, no scipy) pricing + fields.
- [ ] IRS instruments and pricing, consuming the Phase 3 USD government curve.
- [ ] alpha/beta per book (rolling window, `MARKET_INDEX` benchmark) in valuation stream.
- [ ] Alembic migrations for the new instruments + metrics.
- [ ] Wire the frontend alpha/beta + option/IRS cells to the new data.

### Also required for submission (not a UI phase)
- [ ] `docs/wireframes/*.png` — the homework requires wireframes. We have full designs
  in `docs/designs/`; export/rename them (or trace simple wireframes) into
  `docs/wireframes/` with the required filenames.
- [ ] README additions: architecture, proxy, SSE streams, live-state approach,
  configurability, options/IRS, alpha/beta, known limitations.
