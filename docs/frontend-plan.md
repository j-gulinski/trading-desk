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
- **Real-data constraint (homework 5, standing).** The system will later be re-pointed at real
  market data (Yahoo Finance / OpenFin) with signal strategies. Do not design around the
  simulated generator: the snapshot + SSE stream contract is the boundary, and anything
  simulator-specific stays behind it. Phase 7a decides the seams and 7b audits for violations;
  the cheaper path is not to create them.

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
  reconnecting / stale / backend-error / **validation-error** / no-matching-filters /
  service-down. (Nine states — the homework lists all nine; validation-error was missing
  from this list until the 2026-08-03 requirements audit and matters from 6b's first
  write form onward.)

---

## Backend inventory (as of Phase 1)

| Service | Exists today | SSE? |
|---|---|---|
| market-data | `GET /stream`, `GET /snapshot`, `GET /health` | ✅ `/stream` |
| pricing | `GET /valuations`, `GET /valuations/{id}`, `GET /valuation-stream`, `POST /scenario`, `GET /health` | ✅ `/valuation-stream` |
| books | `GET/POST /books`, `GET/PUT/DELETE /books/{id}`, `GET /health` | — (poll) |
| blotter | `GET /trades/overview`, `GET /trades/{id}`, `/trades/{id}/valuations`, `/trades/{id}/audit-logs`, `GET /health` | — (poll) |
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
  findings, including the trace of one price change from the wire to a rendered row.
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
- **Full detail:** `docs/phase-4-notes.md` — a focused note on the valuation performance review,
  organised by topic with the measurements, not a full file-by-file phase audit. This section keeps
  only what later phases need to know.

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

### Phase 5 — Trades & PnL (Blotter) + configurability ✅ (built and verified)

- **Goal:** the main operational table + trade drill-down.
- **Outcome:** one five-second Blotter snapshot poll supplies durable trade membership, terms,
  lifecycle, recent closed history and book names; the Phase 4 valuation context overlays the
  newest live/final value by trade ID. No new feed, provider or backend route was added.
  A same-phase follow-up later added real trade closing (the one exception — it integrates
  trade-action-service, an existing route this screen hadn't used before), a right-side detail
  panel, and a firmer Trades/Valuations split. A final review pass replaced the `250+` closed
  label with an exact backend-supplied total and made every number on Valuations open-scoped.
- **Full detail:** `docs/phase-5-notes.md` follows the implementation in inspection order and
  records the merge, freshness, history-window and verification decisions. It also carries the
  end-to-end close-trade flow across four services, the valuation-selection truth table, and the
  measured request costs.

**Built**

- **Integration:** `/api/blotter` proxy and endpoint registry entries for book summary, filtered
  trades and encoded trade detail.
- **Domain/config:** `config/trades.js` and `domain/trades.js` normalize decimal/timestamp wire
  values, join book names, de-duplicate stale cache/database overlap, select the newest terminal-aware
  valuation, derive `LIVE / STALE / PENDING / CLOSED / CANCELLED`, capture live sort values and
  normalize detail history.
- **Screen/table:** real `Trades.jsx`; controlled book, Open/Closed, asset-class and text filters;
  14 configurable columns with a design-aligned nine-column default; captured PnL sorting;
  Prev/Next paging at 50 rows; `TradeStatusTabs`, `TradeTable` and `TradeCell`.
- **Drill-down:** a native-`<dialog>` right-side drawer, current feed value, full trade/close terms,
  newest-first valuation history and the existing normalized audit list. One aggregate
  `/trades/{id}` request replaces three competing detail requests and polls only while the drawer
  is mounted.
- **Small shared adjustments:** `useTableState(defaultVisibleColumns)` and optional
  `DataTable(onRowClick)`. Existing screens retain their previous behavior.
- **Follow-up (closing, panel, consolidation):** a real close action (`domain/tradeActions.js`,
  wired through `TradeDetail.jsx`/`TradeDetailDialog.jsx` with an honest pending state, no
  optimistic faking); the detail panel restyled from a centered modal into a right-side drawer
  (`showModal()` kept for its native focus/Escape/backdrop-click behavior — only the backdrop's
  CSS and the panel's position changed); Valuations trimmed to an open-only top-100 leaderboard
  (`MAX_RENDERED_ROWS` 250→100, `realized` column and the STATE filter dropped; the review pass
  then made the stat and book-risk cards open-scoped too, and deleted the `REALIZED PNL` card that
  Business Overview already owns); Trades gained real Prev/Next paging
  (`TRADE_PAGE_SIZE = 50`, replacing the old truncate-and-announce pattern) plus two columns
  ported from Valuations (`price`/`return`, reusing fields already present on feed-sourced rows).
- **Review pass (counts and duplication):** `blotter GET /books/summary` gained `closed_trades`
  (per-book exact count of non-active trades) so the Closed tab shows a real total instead of
  `250+`; `MAX_RENDERED_TRADE_ROWS` deleted and `TRADE_HISTORY_FETCH_LIMIT` 251→250; Valuations
  fully open-scoped; six behaviour defects fixed (close-pending guard, duplicate-close window,
  hidden-by-default column migration in `useTableState`, lifecycle-scoped book counts, dated
  `Opened` column, page reset on filter change); duplication removed via shared
  `VALUATION_STATUS_LEVEL`, `groupOptions`, `formatQuantity` and `DataTable` sort defaults.

**Contracts and rules later phases inherit**

- **Blotter owns row membership and durable facts; Pricing context owns changing values.** A feed
  valuation does not create a partial trade row. New trades can wait up to the next five-second
  membership poll; once present, fair value and PnL publish on the shared half-second feed cadence.
- **Fallback remains honest.** Context values use browser-receipt freshness. A Blotter fallback has
  no stream receipt, so it uses server valuation time and can be `STALE`; absence is `PENDING`.
  Closed/final remains terminal.
- **PnL column is lifecycle-aware:** unrealized while Open, realized while Closed. The latter comes
  from persisted Blotter history and survives a Pricing-process restart.
- **The trade table is a working window, not an archive — and it says so.** Active rows remain
  cache-backed and complete, so the open count is exact. The `limit` on `/trades` bounds only the
  database leg, so the closed count comes from `closed_trades` on `/books/summary` (one `GROUP BY`,
  no extra round trip) rather than from the loaded rows. The tab count is therefore every closed
  trade, while the meta line discloses the loaded window (`newest N of M loaded`) whenever it is
  smaller. 50 rows render per page. Archive *search* still needs backend filtering and pagination.
- **A screen must not report on rows it does not show.** Both `250+` and Valuations' old
  `N open · M closed` header failed this in opposite directions. Counts belong to the same
  population as the table, or they are labelled as something else.
- **Details are on demand.** Valuation history and audits do not enter route-level live state or
  participate in every feed render.

- **Backend deps used:** `blotter GET /trades/overview`, `/trades/{id}`; the aggregate
  detail response already contains the same valuation history and audits exposed by the two
  narrower routes. Live values reuse Pricing SSE from Phase 4. The follow-up also uses
  `trade-action-service POST /trade-actions` (`CLOSE_TRADE`) — already built for Phase 6, just not
  previously called from the frontend.
- **Proxy added:** `/api/blotter` → `blotter-service:8006`; the follow-up added
  `/api/trade-action` → `trade-action-service:8008`.
- **Deferred:** New trade, Books CRUD, Generator and the full Trade Actions screen (batch actions,
  close-all, queue status) stay Phase 6 — only single-trade close moved up here. Exact closed totals
  now exist, but server-side closed-history *filtering and pagination* and valuation-history
  pagination remain follow-ups; the client-side Trades pager windows the same already-loaded
  ~250-row set rather than replacing that need.

### Phase 6 — split into 6a / 6b-1 / 6b-2 / 6c

Phase 6 as originally written bundled Books CRUD, Generator, Trade Actions, New Trade, states polish
and config persistence — roughly four screens. Phases 4 and 5 had each run three revision passes past
their one-line goal, and in both cases the extra passes edited an earlier phase's screens, pulled a
slice of a later phase forward, and changed a backend service. The split puts a review gate between
those. 6b was split again in the 2026-08-03 plan review: the book-lifecycle work (delete guard,
trade reassignment) is the heaviest backend feature since Phase 3 and deserves its own gate rather
than riding along with the first write forms.

### Phase 6a — Generator + Trade Actions ✅ (built and verified)

- **Goal:** the two remaining SYSTEM screens, read-only, over data that already exists.
- **Outcome:** both event feeds read the existing audit trail through `GET /audits` — no new
  per-service events endpoint, no new proxy for monitoring. The generator gained runtime config so
  the mockup's sliders are real, and startup seeding so it can close trades it did not open.
- **Full detail:** `docs/phase-6a-notes.md` — decisions, the four build-time deviations, the config
  and audit process flows, and the measured verification.

**Built**

- **Backend (small, inline):** `service` and `event_type` filters on monitoring `GET /audits` (the
  audit experiment's Slice 2, above); `GET`/`POST /config` on trade-generation with `interval_ms` and
  `target_open_trades` as mutable module state guarded by the existing `_lock`, and `status()`
  echoing the effective config plus derived `close_probability`; `blotter_client.py` +
  `BLOTTER_SERVICE_URL` so `_open_trades` seeds from the active book at startup;
  `CONFIG_CHANGED` added to `AuditEventType`.
- **Frontend:** `config/{generator,tradeActions}.js`, `domain/generator.js`, extended
  `domain/tradeActions.js`, `components/generator/IntentFeed.jsx`, real
  `Generator.jsx` and `TradeActions.jsx`, three style partials, `.page__note`.
- **Proxy added:** `/api/trade-generation` → `trade-generation-service:8007`.
  `endpoints.blotter.booksSummary` re-added (Phase 5 dropped it when Trades consolidated onto
  `/trades/overview`; the backend route was never removed).

**Contracts and rules later phases inherit**

- **Env is a startup default where runtime config exists.** `TARGET_OPEN_TRADES` and
  `TRADE_GENERATION_INTERVAL_MS` are now mutable at runtime, so any screen must show the *effective*
  config read back from the service, never the env value. Values reset on restart.
- **The generator writes no per-intent audit.** Its intents are visible only through
  trade-action-service's `TRADE_CREATED` / `TRADE_CLOSED` / `ACTION_REJECTED` rows; generated ones are
  identified by the `gen-` prefix on `correlation_id`.
- **`/audits` filters are not enum-validated.** Services write raw event-type strings, so validating
  against `AuditEventType` would turn an unrecognised filter into "no filter" and return everything.
  An unknown `event_type` correctly returns zero rows.
- **Trade-actions queue depth is usually uninformative in this phase.** The trade-action queue drains on
  arrival, so `queued` is usually zero. The cumulative counters (`processed`, `created`, `closed`)
  carry the activity signal instead.
- **Feeds are bounded by row count, not time.** A tile counting over a count-limited feed must be
  labelled by that population (`REJECTED · IN FEED`, `of N shown`), never as a time window.
- **Books are the authority for tradeable asset classes**, not the market feed — the feed carries
  `INDEX` (a benchmark, never traded) and omits `BOND` (priced off the curve, never ticked).

- **Deferred (honest):** per-action processing latency and the `ms` column render `n/a` with the
  reason — audits record when an action was written, not how long it took; feed rows omit book, side
  and quantity for the same reason. Both need `trade_processor` timing plus a wider audit payload.

**Review pass (simplification sweep, 2026-08-03).** Full detail in `phase-6a-notes.md`
(decisions 6–12). Every mid-build reversal had left the losing option's code behind; the sweep
removed five dead units (`FEED_SERVICE`/`FEED_EVENT_TYPES` on generator config,
`REJECTED_WINDOW_MS`, `queueLevelOf`/`QUEUE_DEPTH_WARN` and the unused `queueStatusOf` fields,
`countRejected`, `intentRateOf`), unified startup seeding and the 10 s blotter sync into one
`sync_open_trades()`, made `set_config` validate both fields before applying either, aligned the
target bounds to `[1, 10000]` on both sides with env values clamped at import, and reverted an
undocumented `FLUSH_INTERVAL_MS` 500 → 1000 drift back to the Phase 4 contract. A later same-day
pass removed the rate mechanism entirely (Generator RATE tile, Trade Actions THROUGHPUT tile,
`useCounterRate`). Verified against the live stack: clamps (1 → 100, 99999 → 10000, 0 → 1),
atomic 400 on mixed valid/invalid config, restart adoption of 33 blotter trades at `opened: 0`.

**Contracts added by the review pass (6b/6c inherit):**

- **`usePolling` exposes `refetch()`; write flows reconcile by refetching server truth**, never by
  optimistic client state — this deleted Generator's `runningOverride` and draft-reconcile
  effects. 6b's Books CRUD and New Trade forms must use the same pattern.
- **No client-side rate derivation.** The per-minute velocity tiles (Generator RATE, Trade
  Actions THROUGHPUT) and the `useCounterRate` hook were removed in a later 2026-08-03 pass:
  sampling windows, restart detection and a two-poll warm-up state existed to answer a question
  nothing operational consumed, and the generator they instrumented is slated for replacement by
  real-data strategies in homework 5. Cumulative counters stay on screen; if a rate is ever
  genuinely needed, derive it from monotonic counters — never from a count-limited feed.
- **`npm run deadcode` (knip) joins lint/build in every phase's verification.** Known accepted
  flags awaiting 6b/6c: `positionsOf` (Books), `apiPut`/`apiDelete` (CRUD), `ApiError`, and a few
  internal-only exports from Phases 3–5 listed in the notes.

### Phase 6b-1 — Books screen + New Trade (the first write forms) ✅ (built and verified)

- **Outcome:** Books is now the authoritative roster (card grid from `/blotter/books/summary`, net
  exposure per symbol on drill-down from the Phase 4 `positionsOf`), and New Trade submits real
  `OPEN_TRADE` intents. No backend changes, as planned — one proxy entry and the books endpoints
  were the whole integration.
- **Full detail:** `docs/phase-6b1-notes.md`.

**Contracts and rules later phases inherit**

- **Writes carry a timeout, by default.** `apiClient.request` takes `timeoutMs` (`AbortSignal.any`
  combines it with any caller signal) and reports a timeout distinctly from a network error.
  `apiPost`/`apiPut`/`apiDelete` apply `WRITE_TIMEOUT_MS` (6 s, `config/api.js`) unless overridden,
  so no future write can forget it; reads keep `usePolling`'s 4 s abort. Before this, a write that
  never answered wedged its form permanently.
- **`NewTradeDialog` is a trade-domain component** (`components/trades/`), owned by `AppShell` —
  not a Books component, because it is reachable from every route.
- **Refetch after a write, but never block the dialog on it.** The 6a no-optimistic-state rule
  stands; what changed is that the form closes on the write's own result and fires the refetch,
  rather than awaiting the roster read before dismissing.
- **Validation runs before transport.** `field → message` maps rendered per field with
  `aria-invalid`/`role="alert"`; nothing is sent while the map is non-empty. Native constraint
  validation is bypassed (`noValidate`) so the presentation is ours.
- **A failed write names the service and says what did not happen.** `domain/apiErrors.js`
  (`describeApiError`) replaces raw `Request failed (502)` with copy like *"Books service
  unavailable — the book was not saved."*; the dialog stays open with the user's input intact.
  Status codes stay diagnostic, not user-facing.
- **Manual intents are labelled.** `client_request_id` is `manual-open-<uuid>`, minted fresh only
  after a successful accept — so a retry of a hung submit dedupes while a deliberate second trade
  is genuinely new. Extends 6a's `gen-` convention.
- **Two sources on one screen, labelled by source.** The card PnL is blotter-sourced (≤5 s) and the
  drill-down PnL is stream-sourced (≤0.5 s); they are sampled at different instants and are not
  reconciled into a single false number. **Superseded in 6b-2:** the drill-down now reads the
  blotter too, so the screen has one source.
- **New Trade is a global action, not a screen feature.** It lives in the top bar on every route
  (matching the designs) and is owned by `AppShell`, fetching its own book list when opened rather
  than being handed one by the host screen. `+ Create book` stays on Books, where it belongs.
- **Connection budget is now a known constraint.** Each open tab permanently holds 2 of the
  browser's 6 per-origin HTTP/1.1 connections (one SSE stream per feed). Measured: 1 tab ~10 ms,
  2 tabs ~8 ms, **3 tabs deadlocks every request including page loads**. Applies to production
  builds too. 6c fix: release the streams while a tab is hidden, reconnect on `visibilitychange`.

**Deferred (honest):** no Delete on the cards until 6b-2's backend guard exists;
`apiDelete` stays on the accepted-knip list one more phase. `positionsOf` and `apiPut` came off it
here. Book cards show a short UUID rather than the mockup's `BOOK-EQ-01` codes — no such column
exists. `EST. NOTIONAL` is labelled `QTY × LAST PRICE` and ignores contract multipliers.

#### Original plan (as approved)

- **Inherited from the Phase 4 revision:** `positionsOf` in `domain/valuations.js` is written,
  tested against live data and **unwired** — net exposure per book × symbol is the natural content
  of the **Books** screen. It nets signed market value (so offsetting trades net rather than sum
  gross), weights entry by |quantity|, and propagates worst-case freshness.
- **Goal:** the Books screen (list, create, edit) and the New Trade dialog — the first real write
  forms, establishing the write-path patterns everything later reuses.
- **Concepts:** forms (create/edit), POST/PUT, the **validation-error state** (first of the nine
  UI states to appear on a write path), refetch-after-write in a form context (rule inherited
  from 6a — no optimistic client state).
- **Decided:** Books renders the mockup's card grid from `/blotter/books/summary` (which already
  returns name, asset class, active/closed counts and realized/unrealized PnL), expanding to
  `positionsOf` net exposure per symbol on drill-down. New Trade derives its instrument list and last
  price from the live market feed rather than duplicating `shared/catalog.py`.
- **From review (2026-08-03): a new book does not appear on Valuations — explained, settled.**
  This is a designed consequence, not a bug: Valuations consumes exactly one source, the valuation
  stream (`useValuationFeedContext`), and both the book-risk cards (`bookRisksOf`) and the book
  filter (`bookOptionsOf`) derive from `bookId`/`bookName` carried on each valuation event. A book
  with no valued open trade emits no events, so it is invisible until its first trade is priced.
  **Settled (2026-08-03): option (a) — Valuations stays stream-only.** The alternative, **(b)**,
  would have added a `/blotter/books/summary` poll whose only contribution to this screen is a
  PnL sum and zeroed cards for valuation-less books — a second data path is not worth that.
  Everything the screen shows, including the UNREALIZED PNL summary card, keeps deriving from
  stream rows (`summarizeValuations` over the open valuation set): one source, nothing to
  reconcile, no extra request cycle. The new Books screen becomes the authoritative roster and
  Valuations states its population explicitly ("books with open valuations").
- **Backend deps:** books CRUD (exists), trade-action `POST /trade-actions` for New Trade
  (exists). No backend changes in this phase — delete/close guards belong to 6b-2, so the Books
  screen ships without a delete button rather than with an unguarded one.
- **Proxy to add:** `/api/books` → `books-service:8004`.
- **Review checklist:** create/edit a book round-trips and the roster refetches (no optimistic
  rows); New Trade validates before submitting (validation-error state renders, nothing is sent);
  a successful New Trade appears in Trades within one blotter poll and values within one pricing
  tick; a duplicate submit is idempotent via `client_request_id`; service-down on books renders
  the honest unavailable state; `npm run lint/build/deadcode` clean (`positionsOf` and
  `apiPut`/`apiDelete` come off the accepted-knip-flags list here).

### Phase 6b-2 — Book lifecycle: delete guard and trade reassignment ✅ (built and verified)

- **Outcome:** `Delete` is real and safe. books-service refuses to deactivate a book with open
  positions (asking the blotter over HTTP, and refusing when it cannot ask); `REASSIGN_TRADES` joins
  the trade-action queue so a book can be emptied first; deactivated books stay reachable behind an
  **Include deactivated** filter.
- **Full detail:** `docs/phase-6b2-notes.md`.

**Contracts and rules later phases inherit**

- **The guard is on ACTIVE trades, not any trade.** `DELETE /books/{id}` is a soft delete, and
  closed trades stay attributed to the book they happened in — so "any trade" would make every book
  that ever traded permanently undeletable. Deleting means *stops accepting trades, leaves the
  roster*, never *never existed*.
- **Guard the state transition, not the route.** `PUT /books/{id}` also accepts `is_active`, so the
  same guard fronts both endpoints. A rule attached to one URL is bypassable by the next one.
- **Cross-service reads fail closed.** books-service reaches the blotter through `blotter_client.py`
  (the 6a trade-generation precedent, not a new pattern) rather than querying `trades` directly, and
  a destructive operation that cannot verify its precondition is **refused with 503** — distinct
  from the `409` that means the precondition genuinely failed.
- **The blotter re-indexes on disagreement.** Its ACTIVE-trade cache is keyed by `book_id` and was
  never updated after load, so a reassignment would have been invisible until restart. It now
  corrects itself when a streamed valuation's `book_id` disagrees with the cached one — pricing
  re-reads its active set every 2 s, so the truth is already on the wire. `IndexedStore.update_field`
  does the remove-mutate-add atomically; doing it from the caller corrupts the index.
- **`202 accepted` cannot be chained.** Trade-action enqueues; the effect lands later. The move →
  delete flow reports the acknowledgement and lets the 5 s roster poll reconcile, rather than
  auto-continuing into the guard it would race.
- **`ApiError` carries the response body.** Status codes stay diagnostic and the copy stays ours,
  but a server-supplied *reason* (the open-trade count on a 409) is not a status code.
- **A new trade mutation must be added to the Trade Actions feed list.** `FEED_EVENT_TYPES` is an
  explicit allow-list; a mutation missing from it is invisible on the screen whose job is showing
  every mutation.
- **A soft-deleted book is hidden, not gone.** It still owns its closed trades and their realized
  PnL, so the roster hides it by default, says how many are hidden, and brings them back — marked
  `DEACTIVATED`, without actions — behind **Include deactivated**. Deactivated books are never
  offered as move targets.
- **One button, one action; the guard is the only copy of the rule.** `Move` is its own control on
  any book with open positions; `Delete` always opens the confirm and surfaces the backend's
  refusal (*"Refused — this book still has 3 open positions."*). The first cut had Delete open the
  move form when positions remained — a client-side branch duplicating a rule the backend already
  enforces.
- **A screen reads one source.** Books is blotter-only: the roster from `/blotter/books/summary`,
  the expanded card's per-symbol netting from `/blotter/trades?book_id=…&status=ACTIVE`. This
  supersedes 6b-1's "two sources on one screen, labelled by source" — same cache behind both calls,
  so the card total and the drill-down agree when sampled together. It required the blotter's
  `latest_valuation` to project `current_price` and `multiplier`: `MARK` is the price of one unit,
  not the value of the position.

**Dropped from the approved scope: per-book Flatten** (and the `book_id` filter on close-all it
needed). Move already empties a book, so Flatten was a second route to the same outcome that
additionally required scoping the most destructive query in the system. `close_all_trades` stays
global and unreachable from the UI.

**One fix beyond the approved scope, caused by this phase:** the blotter re-index above — without it
a reassignment looks like it silently failed until the service restarts.

#### Original plan (as approved)

- **Goal:** make destructive book operations safe — the heaviest backend feature since Phase 3,
  which is why it has its own gate.
- **From review (2026-08-03):** deleting or closing a book that still has trades must be refused
  by the backend, not just hidden in the UI. Closing a book is a *move operation*: reassign its
  transactions to another book, then close the empty book.
- **Settled (2026-08-03, plan review):**
  - **Reassignment lives in trade-action-service** as a new action type (it mutates trades, and
    trade lifecycle state has exactly one writer — the same ownership rule as every other trade
    mutation), with an audit row per moved trade and the blotter picking the change up through
    its normal read path.
  - **Closed-trade history stays attributed to the original book; only active positions move.**
    History is a record of what happened, and what happened happened in the original book.
- **Scope:** a guard on books `DELETE /books/{id}` (refuse when the blotter shows any trades for
  the book); the reassignment action type end to end; the UI flow — pick target book → move →
  confirm close. The approved scope also listed an optional `book_id` on
  `POST /trade-actions/close-all` for a per-book **Flatten**; that was dropped at build time as a
  duplicate route to an outcome move already produces (see the outcome section above).
- **Review checklist:** DELETE on a book with trades is refused with a clear error surfaced in
  the UI (and allowed once empty); reassigning N active trades writes N audit rows with the
  original and target book recorded; reassigned trades keep valuing without interruption (the
  pricing active-set survives the move); closed trades stay under the original book after a
  move; the close-book flow refuses to close while active trades remain.
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
  - ✅ **Resolved in 6a:** `_open_trades` was in-memory, so after a restart the generator could not
    close trades it did not open and orphans accumulated. It now seeds from the active book at
    startup via `blotter_client.active_trades()` — verified at 24 adopted trades against
    `opened: 0` on a fresh process.
  - The **market tick** generator needs no change: it is already a mean-reverting Gaussian walk at
    ~0.065%/tick with realistic tick sizes and spreads. The prices were never the unrealistic part.

### Phase 6c — UI states, streams badge, config persistence
- **Goal:** finish the UI-state sweep, add the global streams badge, settle config persistence.
- **Scope:** the bottom-left `2 / 2 streams · connected` badge (deferred since Phase 3, present in
  every mockup); every view checked against the nine states listed in the conventions above;
  a decision on what persists beyond column preferences (filters, tabs, page size) and one storage-key
  scheme.
- **Build order (fixed, 2026-08-03 plan review):** the three units below are independent, so each
  lands and verifies before the next starts — the drawer rework is the structurally hardest UI
  change in the plan and must not share a debugging surface with the rest.
  1. **Detail panel rework** — push-aside layout + tabs together (they are the same component;
     doing them separately means restyling the panel twice). **Extended after 6b-1 review:** the
     same push-aside treatment covers the two Books write drawers (New Trade, Create/Edit book).
     All three become the one shared right-hand panel that slides the page content left instead of
     covering it, so this is one layout mechanism built once and used by three callers — not a
     drawer pattern per screen. Both 6b-1 dialogs ship today as `<dialog showModal()>` overlays
     that close on backdrop click (matching the Phase 5 trade-detail behaviour); that is the
     stop-gap this item replaces, and the `showModal()` question below applies to them equally.
  2. **Sidebar collapse + streams badge** — one layout unit (the badge lives in the sidebar and
     must render in icon-only mode).
  3. **Release SSE connections while a tab is hidden** (added after 6b-1). Each tab permanently
     spends 2 of the browser's 6 per-origin connections on the two feeds, so a third open tab
     deadlocks every request in every tab — polls, form submits, even page loads. Closing the
     streams on `visibilitychange` and reseeding when visible fits `useSseStream`'s existing
     cleanup and is the right behaviour anyway: a hidden dashboard has no reason to hold a feed.
  4. **States sweep + config persistence** — the sweep's required deliverable is a
     **nine-states × views matrix in the phase notes**, every cell either "handled (how)" or
     "N/A (why)". Without the matrix, "checked every view" is unverifiable at review.
- **Review checklist:** drawer open/close keeps the table visible and its live PnL updating;
  Escape and focus behavior survive the loss of `showModal()` (focus returns to the triggering
  row, Escape closes, focus cannot tab behind the panel); audit tab reachable in two
  interactions from a row; sidebar collapse persists across reload and the badge renders in both
  modes; the state matrix is complete; storage keys follow the one agreed scheme;
  `npm run lint/build/deadcode` clean.
- **Accepted in review (2026-08-03) — three UI changes:**
  1. **The trade-detail drawer pushes the table aside instead of covering it.** A trader watching
     the book must not miss a P&L change on another position while inspecting one. This replaces
     the Phase 5 overlay-drawer decision: the panel becomes a layout sibling of the table (grid
     column, not `<dialog>` backdrop), which also means rethinking what `showModal()` provided —
     Escape handling and focus management have to survive the change. **Applies to the Books
     drawers too** (added after the 6b-1 review): New Trade in particular quotes a live price, so
     covering the market it is priced against is the same mistake in a worse place.
  2. **The detail panel gets tabs instead of one long scroll** — Details / Valuation history /
     Audit. Audit events currently sit too low to be found (another student hit the same issue).
  3. **The sidebar collapses to icons** to maximize workspace, with the expanded state
     persisted. Interacts with the streams badge (icon-only rendering) and the Phase 1
     `--sidebar-width` token, which becomes two values.
- **Settled by decision (requirements audit 2026-08-03, confirmed by the project owner):**
  - **System Overview stays as designed — no headline PnL/count tiles.** The homework lists
    total PnL and counts as *example* elements; the deliberate split here is Business Overview
    as the money view and System Overview as the technical view. This is a README justification,
    not UI work.
  - **Configurability scope is what already shipped:** column visibility/order, sorting,
    filters, persisted table prefs, runtime generator config. No density toggle, PnL thresholds
    or pinned books planned — the README describes and argues the shipped scope (the homework
    asks for domain sensibility, not option count).
- **Docs:** ✅ `workflow.md`'s notes format was rewritten in 6a to match what Phases 4–5 actually do
  (decision log → process flows → files for review at the end), and the two dangling
  "implementation artifact" references were removed.

### Phase 7a — real-data seam review (before the end-of-project features)

- **Goal:** make the boundary decisions the end-of-project features will sit on, with the
  homework-5 real-data lens (Yahoo Finance / OpenFin, signal strategies). Output is **recorded
  decisions, not features** — this phase is deliberately cheap so it cannot endanger the
  homework-4 deliverables it precedes.
- **Why before, not after:** the end-of-project work lands directly on these seams. Options and
  IRS add new asset classes, which collides immediately with `SYMBOL_BY_CLASS` (one symbol per
  class) and the static `shared/catalog.py` universe; IRS discounting is built on the curve
  representation the homework grades as a decision — and homework 5's real data will feed that
  same curve; alpha/beta's rolling window is trivial against the simulator's steady ticks but
  must survive real bars with gaps. Deciding first avoids building those features twice.
- **Scope (decisions to record):**
  - **Instrument universe:** how the catalog and `SYMBOL_BY_CLASS` restructure when a class has
    many symbols and instruments carry parameters (strike, maturity, legs) — the options/IRS
    migration design depends on this.
  - **Curve representation** in the database and on the stream — reviewed against both IRS
    discounting and a future real-rates source.
  - **Benchmark series ownership** for alpha/beta: who stores the rolling window, what happens
    on gaps, too-few observations, and zero benchmark variance (all named by the homework).
  - **Market-data adapter boundary:** confirm the snapshot + named-SSE-stream contract is the
    seam a Yahoo/OpenFin producer can stand behind with zero consumer change; list anything
    downstream that assumes simulator internals (tick regularity, tick sizes, mean-reversion).
  - **Strategy plug-in sketch:** strategies as intent producers beside the generator — the
    GENERATED/MANUAL split becomes a strategy label; `gen-` prefixes stop being the only
    automated marker.
- **Constraint in force from now on (6b/6c included):** no new design may deepen simulator
  coupling; anything simulator-specific stays behind the market-data service boundary.

### End-of-project — deferred big backend features (phases E1–E5)

Build **after** the UI is complete. Restructured in the 2026-08-03 plan review from a flat
checklist into phases, because these are the graded deliverables and they deserve the same
loop (propose → accept → implement → verify → notes) as everything else. Two ordering rules:
**Alembic comes first** (options and IRS need schema changes, and migrations are how schema
lands — building instruments first means doing the schema work twice), and **every feature
wires its own frontend cells in the same phase** (big-bang integration at the end is how gaps
survive until review; every prior phase wired UI with its data and caught them early).

All of E1–E5 build on the Phase 7a seam decisions (instrument universe, curve representation,
benchmark ownership) — do not start them with 7a unresolved.

- **E1 — Alembic baseline + instrument-universe migration.** Introduce Alembic over the current
  schema, then land the 7a instrument-universe restructure (catalog / `SYMBOL_BY_CLASS` → a
  representation where a class has many symbols and instruments carry parameters) as the first
  real migration. *Concepts:* migrations as code, autogenerate vs hand-written, baseline-stamping
  an existing database. *Review checklist:* `alembic upgrade head` from an empty database and
  from the current schema both succeed; downgrade of the new migration works; the running stack
  is unaffected (same trades, same valuations).
- **E2 — European options.** Black–Scholes pricing (`math.erf`, no scipy) in pricing-service,
  option instrument fields via an E1-style migration, generator/New Trade able to produce one,
  and the option cells wired on Trades/Valuations in the same phase. *Review checklist:* a known
  BS test vector prices correctly; an option trade values on the stream like any other; the UI
  shows option fields only for options (honest N/A elsewhere).
- **E3 — IRS.** IRS instruments and pricing consuming the curve per the 7a curve-representation
  decision; migration + frontend cells in-phase. *Review checklist:* a par swap prices near zero
  at inception; a curve shift moves the IRS valuation in the expected direction; cells wired.
- **E4 — alpha/beta per book.** Rolling window against `MARKET_INDEX` per the 7a
  benchmark-ownership decision, published on the valuation stream; wires the Valuations
  book-risk cards to real values. *Review checklist:* the homework's named edge cases return
  honest nulls, not numbers — gaps in the series, too few observations, zero benchmark
  variance; beta of the benchmark against itself ≈ 1 as a sanity vector.
- **E5 — observability pack** (smallest; flexes if time runs short). Low-frequency transition
  audits (`DEPENDENCY_DOWN`/`RECOVERED`, `WORKER_FAILED`/`RECOVERED`, persistence
  failure/recovery — state changes, not every retry), rendered as the homework's per-service
  status-change timeline on the monitoring view; per-action processing latency via timing in
  `trade_processor` plus a wider audit payload (book, side, quantity), unblocking the "average
  processing time" stat and the per-row `ms` column that render honest `n/a` today (recorded in
  6a; elevated by the requirements audit). *Review checklist:* stopping a dependency writes one
  DOWN and one RECOVERED row, not a retry storm; the timeline renders them; the `ms` column and
  average replace their `n/a` states.

### Phase 7b — consolidation sweep (after the end-of-project features)

- **Goal:** the project-wide simplification pass over the *complete* codebase, as the last work
  before homework 5. Runs after the end-of-project features precisely so their build debris is
  included — sweeping first and building after would deposit new leftovers on a clean floor
  (the 6a review pass demonstrated that reversals during a build always leave some).
- **Scope:**
  - Project-wide dead-export and duplication sweep (`npm run deadcode` across the app); the
    accepted knip flags carried since 6a get resolved here rather than carried further.
  - Machinery-that-outlived-its-decision review across all phases, 6a-style, now that the
    feature set is final.
  - **Re-verify the performance rules against real-feed behavior:** the 500 ms scheduler,
    buffer bounds and queue sizes were measured against the simulator's steady cadence; real
    feeds burst and gap, so the burst case gets measured before homework 5 relies on it.
    Bursts are produced with the tools already in the stack — drop the generator interval to
    its 100 ms floor for a sustained burst, and use pricing's `POST /scenario` shock for a
    single revaluation spike — since no real feed exists until homework 5. Record the numbers
    the same way Phase 4 did (long tasks, flush sizes, staleness counts).
- **Deadline valve:** if homework-4 time runs short, this phase compresses safely — it improves
  the codebase but gates no graded deliverable. Phase 7a does not have that property, which is
  why the two halves are ordered the way they are.

### Also required for submission (not a UI phase)
- [ ] `docs/wireframes/*.png` — the homework requires wireframes. We have full designs
  in `docs/designs/`; export/rename them (or trace simple wireframes) into
  `docs/wireframes/` with the required filenames.
- [ ] README additions: architecture, proxy, SSE streams, live-state approach,
  configurability, options/IRS, alpha/beta, known limitations. Per the requirements audit also
  cover: which benchmark alpha/beta uses and why (`MARKET_INDEX`); which views poll instead of
  stream and why that is allowed (monitoring explicitly; trade-gen/trade-action use the audits
  endpoint — "stream **lub endpoint**" per the homework); why Monitoring has no separate
  sidebar page (System Overview doubles as it); why top-level PnL lives on Business Overview
  rather than System Overview (deliberate money-view/technical-view split); and the
  WARNING-severity departure from the errors-panel mockup.

### Optional extensions ("zadanie dla chętnych") — tracked, mostly not planned
Status after the 2026-08-03 requirements audit, so the option list is a decision, not an
accident. None are required; revisit only if time remains after Phase 7b.
- **Local view-config persistence — largely done already** (column visibility/order and table
  prefs in localStorage since Phases 3–5; 6c settles what else persists).
- **Simple charts — done in spirit:** dependency-free SVG sparklines (Phase 3) and the benchmark
  card; no charting library, by design.
- **Scenario shock — backend half exists:** pricing already ships `POST /scenario`. A UI view is
  a candidate stretch goal after Phase 7b, and pairs naturally with real data in homework 5.
- **PnL attribution, configurable layouts, operational alerts — not planned** (PnL thresholds
  were declined in 6c, so alerts have no configuration to ride on).
