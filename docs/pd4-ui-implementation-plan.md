# PD4 UI implementation plan — aligned to repository designs

## Authority and delivery rules

1. The screen structures, navigation, copy, and component hierarchy in [`docs/designs/`](designs/) are the visual source of truth.
2. The agreed product rules and real backend contracts determine behaviour. Do not ship the example numeric data in the PNGs as believable mock data.
3. When a design asks for data the backend does not yet support, build the visible screen state now and show an honest `N/A`, empty, or unavailable state until the corresponding PD4 backend work is complete.

## Design baseline

- The sidebar contains **System Overview**, **Generator**, **Trade Actions**, **Business Overview**, **Market Data**, **Valuations & Risk**, **Books**, and **Trades & PnL**.
- Reproduce the shared dark trading-console shell: persistent sidebar, page title/subtitle, compact metric panels, monospace values/identifiers/timestamps, purple accent, and semantic health/PnL colours.
- Keep the global **New trade** entry point. It opens the designed modal rather than a sidebar route.
- The shared footer displays `2 / 2 streams · connected` when both actual SSE subscriptions are healthy. System Overview names the two feeds as `market-data /stream` and `pricing /stream`; health is separately polled.
- A manual trade is an intent at the displayed snapshot price. It is neither `@ MKT` nor a guaranteed market fill.
- Business Overview reports **total realized PnL · all books**. Books deactivated after all their positions are closed are excluded from its all-book totals.

## Delivery order

### 1. Shell, navigation, and visual primitives

- [ ] Implement the exact sidebar order and labels from the designs, including the System and Trading groups. Do not create a Monitoring navigation item.
- [ ] Implement the shared desktop shell, page header, global New trade button, footer connection pill, status badges, metric cards, table styling, filters, empty states, error states, and responsive modal treatment.
- [ ] Add routes for the eight sidebar views. Open New Trade and Valuation History as modal/drawer UI state, not sidebar destinations.
- [ ] Centralize financial formatting, semantic colours, timestamps, table columns, and connection states: `connected`, `reconnecting`, `polling`, `stale`, and `unavailable`.

### 2. Data boundary and freshness foundation

- [ ] Call backend services only through relative `/api/...` proxy paths; browser code must not address Docker service hostnames directly.
- [ ] Build a snapshot-plus-update hook: REST snapshot first, keyed SSE merge for `market-data` and `pricing` second, and incremental polling only where streaming is absent.
- [ ] Keep high-frequency state local to the view that consumes it. Retain bounded browser buffers only for visible sparklines/activity lists.
- [ ] Show a last-updated timestamp and stale/fallback state wherever the design says `LIVE`, `STALE`, or `connected`.
- [ ] Use health/status polling with backoff for the seven service cards. Do not represent polling as a third SSE stream.
- [ ] Use cursor/since endpoints for logs, action history, and generator events when added; never repeatedly load or scan raw log history in the browser.

### 3. System Overview

- [ ] Render the seven designed service cards: Market Data, Pricing, Monitoring, Books, Blotter, Trade Generation, and Trade Action.
- [ ] Show the healthy/degraded/down summary, per-service latency, and checked-at age from the monitoring response; retain loading, partial-failure, and unavailable states.
- [ ] Render the two-stream panel with connection badge and event rate for market data and pricing.
- [ ] Add the designed recent-log panel: service filter chips, bounded recent entries, severity styling, and a load-more/history path backed by a monitoring/audit API.
- [ ] Add the five-minute error count and bounded error list. Until monitoring exposes history/errors, show an explicit unavailable state rather than fabricated entries.

### 4. Market Data and New Trade

- [ ] Render the six visible Market Data rows in the design: `MARKET_INDEX · VIEW ONLY`, `ACME`, `EURUSD`, `XAU`, `US_CURVE_10Y`, and `US_CURVE_2Y`—in that order. Remove `GLOBEX`, `GBPUSD`, and `WTI` from UI/demo data.
- [ ] Make the Instruments, Live, Stale, and Last Update metric-card values data-driven; the screenshot values are illustrative.
- [ ] Add the designed class chips, symbol search, price/change columns, small bounded history sparkline, per-row feed badge, and updated timestamp.
- [ ] Map the presentation label `XAU` to the existing backend instrument key `XAUUSD`. Derive the two curve rows from the live `USD_GOV` curve's 10Y and 2Y points; keep that mapping in one market-data adapter.
- [ ] `MARKET_INDEX` has no Buy/Sell action and is rejected server-side if submitted. Curve tenor rows must not submit a trade unless a real catalog instrument/action mapping is introduced; see the design discrepancies below.
- [ ] Implement the New Trade modal exactly as designed: Book, Instrument, Buy/Sell, Quantity, live last-price snapshot, estimated notional, asset-class badge, intent summary, close icon, and `Submit BUY {quantity} {symbol}` button copy.
- [ ] Validate selected book and asset-class eligibility on submit, with server-side validation authoritative. Do not add a visible pre-trade capacity panel that is absent from the design.
- [ ] Submit the displayed snapshot/reference price with an explicit `as_of` timestamp or quote/version identifier, and show a stale/changed-price confirmation if the snapshot has expired.

### 5. Books

- [ ] Render the card grid and controls shown in the design: create book, book name/id, asset-class badge, realized/unrealized PnL, open/closed counts, Flatten, and Delete.
- [ ] Keep the planned card slots for Equity, FX, IRS, Commodity, and Futures, but use honest empty/unsupported states until each backend asset class exists.
- [ ] Implement Flatten as a scoped bulk close of eligible active trades, with confirmation, progress, result summary, and partial-failure handling.
- [ ] Implement Delete as soft deactivation only after `open_positions === 0`; preserve audit history and exclude deactivated books from default/all-book PnL queries.
- [ ] Disable Delete on a card with active positions and explain that the user must close/flatten those positions first. The current visual treatment is ambiguous; this is a required behaviour refinement.

### 6. Valuations & Risk, Trades & PnL, and Valuation History

- [ ] Implement the Valuations & Risk layout: alpha/beta-by-book cards, rolling-100-observation label, benchmark label, per-book unrealized PnL, biggest-mover affordance, and live valuation table.
- [ ] Render the Trades & PnL controls from the design: book selector, Open/Closed tabs with counts, asset-class chips, column chooser, sortable financial table, and row-to-history interaction.
- [ ] Keep IRS and `EUROPEAN_OPTION` filter/chip/card locations visible now. Before PD4 support exists they must show `N/A`/insufficient-data or no matching rows, not specimen values.
- [ ] Implement the Valuation History drawer with trade/book/class header, side/quantity, fair value, realized/unrealized PnL, bounded valuation history, sparkline, audit log, and close control.
- [ ] Keep the visible button copy `Close · realize {unrealized PnL}`. On confirmation, state that this is the latest valuation estimate and submit a close intent against the current displayed valuation/version; never promise that amount as an executable market fill.
- [ ] Load valuation history and audit details on demand by trade id, with pagination/cursors; merge subsequent pricing updates into the current row only.

### 7. Trade Actions

- [ ] Render the designed metric cards: Queue Depth (including max), Avg Processing (rolling last 100), Rejected (5m), and Last Trade (written-to-trades time).
- [ ] Render the accepted/rejected action feed with live/fallback state, action id, book, result text, and per-action processing duration.
- [ ] Record or expose `accepted_at`, `started_at`, `completed_at`, outcome, rejection reason, and trade/action identifier so the average and list are derivable server-side.
- [ ] Fetch a rejection reason through an action/audit endpoint by identifier. Do not make the browser search application logs for it.

### 8. Generator

- [ ] Implement the generator state card: running/stopped badge, toggle, frequency slider, trade-out probability slider, maximum active positions input, and allowed asset-class chips.
- [ ] Persist frequency, probability, maximum positions, and allowed-asset configuration with server-side range/eligibility validation. Keep the generated-this-session and intents-per-minute cards.
- [ ] Implement the designed Live Intent Feed: timestamp, `TRADE_IN`/`TRADE_OUT`, book, asset class, side, and quantity, with a bounded live buffer plus cursor-based history/fallback polling.
- [ ] Render unsupported IRS/options classes as disabled or unavailable until PD4 support arrives; do not generate plausible unsupported intents.
- [ ] Surface generator failures/rejections in the screen itself, without treating browser console/log scraping as the source of truth.

### 9. Business Overview

- [ ] Implement the four designed headline cards: unrealized PnL (all books), total realized PnL (all books), active trades, and books.
- [ ] Implement the per-book unrealized-PnL list and the Valuation Freshness panel with live/stale counts and the link/route to Valuations & Risk.
- [ ] Provide one backend overview read model containing aggregates and an `as_of` timestamp. Calculate totals in the backend/read model, not by downloading and re-aggregating trades in the browser.
- [ ] Refresh the aggregate more slowly than prices/valuations, expose staleness, and exclude deactivated books from the all-book aggregates.

### 10. PD4 advanced pricing — after the core UI above

- [ ] Add IRS and European option support end-to-end: catalogue, validation, books/trades persistence, market-data/pricing dependencies, valuations, and audit/history handling.
- [ ] Add alpha/beta input series, benchmark handling, rolling-window calculation/read model, observation count, `as_of`, and `N/A`/insufficient-data behaviour.
- [ ] Enable real advanced-class entries in generator feeds, Books, Trades & PnL, Valuations & Risk, and filters only after the underlying capability is available.

### 11. Fill remaining UI gaps and release QA

- [ ] Replace temporary unavailable/empty advanced-pricing states with live data only once PD4 services support it.
- [ ] Verify design parity for navigation, titles, metric cards, connection indicators, filters, table columns, modals, and empty/error/stale states against every PNG in `docs/designs/`.
- [ ] Test reconnect, stale data, service loss, duplicate events, cursor expiry, slow clients, manual intent, close, flatten, soft deactivation, rejection, and generator flows.
- [ ] Verify accessibility, keyboard modal close/focus restoration, numeric alignment, responsive layout, lint/build, and Docker deployment.

## Refresh policy

| Screen data | Preferred transport | Fallback | Browser behaviour |
| --- | --- | --- | --- |
| Market prices, curve points, valuations | REST snapshot + SSE | Incremental `since`/cursor poll | Idempotent keyed merge; bounded sparkline buffer |
| Service health and SSE status | HTTP health/status poll | Exponential-backoff poll | Show checked-at age and connection/fallback state |
| Logs, errors, actions, generator intents | Cursor-paginated API or SSE when introduced | Incremental poll | Keep a bounded visible list; load history on demand |
| Books, trades, and overview aggregates | Read-model snapshot | Timed poll after mutations | Refresh slower than prices; show `as_of` and stale state |

## Design discrepancies and required decisions

1. **Market symbols versus backend keys:** the design uses `XAU`, `US_CURVE_10Y`, and `US_CURVE_2Y`; the service exposes `XAUUSD` plus a `USD_GOV` curve. The adapter above makes the design viable without changing the backend names. It must not silently submit `XAU` as an unknown trade symbol.
2. **Curve-row Buy/Sell actions:** the design displays Buy/Sell beside curve tenors, but the current catalogue has bonds (`GOVT_2Y`, `GOVT_5Y`), not tradable `US_CURVE_*` instruments. Disable/remove those actions or define a deliberate tenor-to-instrument workflow before implementing them.
3. **Delete with open positions:** every displayed book has open positions while Delete looks available. The implementation must disable it until the book is flat, or the design needs a clear confirmation/error state.
4. **Advanced sample values:** the designs show IRS, European option, alpha/beta, and advanced generator/activity values. Current services do not support all of them. Until PD4 delivers that work, use visible `N/A`, insufficient-data, disabled, or empty states—not sample values.
5. **Close amount wording:** `Close · realize +9,508.08` can read as guaranteed. Keep the design's concise button label only with an estimate/valuation-version confirmation before the close intent is sent.

This order completes the designed core experience first, preserves truthful freshness behaviour, and then adds the larger IRS/options/alpha/beta implementation before filling the final advanced UI states.
