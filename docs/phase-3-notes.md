# Phase 3 notes — SSE + Market Data

## Suggested inspection order

Follow one market-data event from the wire to the screen: proxy in, stream primitive,
domain shaping, the buffering feed, then the presentational pieces and the page.

1. **Proxy & config** — `frontend/vite.config.js` → `config/marketData.js`
2. **Data layer** — `services/endpoints.js`
3. **SSE primitive** — `hooks/useSseStream.js`
4. **Domain** — `domain/marketData.js`
5. **Feed** — `views/MarketData/useMarketFeed.js` → `providers/MarketFeedProvider.jsx`
6. **Components** — `components/charts/Sparkline.jsx` → `components/cards/StatCard.jsx` →
   `components/marketdata/InstrumentTable.jsx`
7. **The page** — `views/MarketData/MarketData.jsx`
8. **Market-data backend** — `services/market-data-service/app/api.py` → `publisher.py` →
   `generator.py`

---

## 1. Proxy & config

### `vite.config.js`

A second proxy entry, `/api/market-data` → `http://market-data-service:8001`, added the
same way as monitoring in Phase 2. The browser opens the relative path
`/api/market-data/stream`; Vite forwards it to the container. Vite's dev proxy streams the
response body without buffering, so `text/event-stream` passes through unchanged — the key
requirement for SSE. No CORS setup is needed because the browser only ever talks to the
Vite origin.

### `config/marketData.js`

The view's tunable policy lives outside the hooks and domain, the same split Phase 2 used
for monitoring. `STREAM_EVENTS` names the two server event types. `MARKET_STALE_AFTER_MS`
is **5 seconds** — the threshold that flips a row from LIVE to STALE. `HISTORY_LENGTH`
(40) bounds the per-instrument sparkline buffer. `FLUSH_INTERVAL_MS` (400ms) sets how often
buffered ticks are committed to React state. `CLASS_ORDER` fixes the table's asset-class
sort and the filter-chip order. These are exactly the "stale threshold" and "event buffer
limit" configurability knobs the homework calls out; a settings UI can bind to them later.

## 2. Data layer

### `services/endpoints.js`

Adds `marketData.stream` and `marketData.snapshot`. As before, views reference logical
endpoint names rather than literal URLs.

## 3. SSE primitive

### `hooks/useSseStream.js`

`useSseStream` is the small transport-level hook that owns the browser's `EventSource`
connection. It knows how to connect, decode an SSE event, report connection status, retry,
and clean up. It deliberately knows nothing about instruments, curves, history, tick counts,
or React batching; those market-data concerns belong to `useMarketFeed`.

```js
useSseStream(url, { events = ['message'], onEvent })  // returns { status }
```

#### What SSE means here

Server-Sent Events is a long-lived, one-way HTTP response from the server to the browser. It
is not polling and it is not a WebSocket: the browser opens one `GET`, the server keeps that
response open, and new text frames are appended whenever data is available. A market event
on the wire is conceptually:

```text
event: market_tick
data: {"symbol":"EURUSD","spot":1.1596}

```

The blank line ends the frame. `EventSource` handles the HTTP stream and SSE framing, then
dispatches a browser `MessageEvent`. Its `data` property is still text; parsing the JSON is
the hook's responsibility. SSE fits this screen because updates flow only from the pricing
service to the UI, while commands and snapshots continue to use ordinary HTTP endpoints.

#### Hook boundary

- `url` identifies the stream to own.
- `events` lists the SSE event names to subscribe to. It defaults to `message`, so the hook
  also works with an unnamed/default SSE stream.
- `onEvent(name, data)` receives an already parsed payload but decides what the payload
  means. For this application, `useMarketFeed` normalises and buffers it.
- `{ status }` is the only returned React state. Tick payloads are intentionally not copied
  into hook state.

This boundary keeps the primitive reusable: another feature can use the same connection
lifecycle without importing market symbols, curve rules, or table state.

#### Lifecycle, line by line

1. **Low-frequency state.** `useState(CONNECTING)` holds only the connection status. An
   `open` event changes it to `CONNECTED`; a connection failure changes it to
   `RECONNECTING`. There is no terminal `ERROR` state because retrying is continuous.
2. **Latest callback without reconnecting.** `onEventRef.current = onEvent` runs on every
   render. Event listeners call the ref, so they always see the newest callback and closed-
   over application state. If `onEvent` itself were an effect dependency, the inline
   callback created by `useMarketFeed` could change identity on a render, tear down a healthy
   connection, and open a new one for no transport-level reason.
3. **Semantic subscription dependency.** `events.join(',')` turns the event-name list into a
   primitive dependency. Passing a newly allocated `['market_tick', 'curve_tick']` array
   with the same contents therefore does not restart the effect. The effect legitimately
   restarts when the URL or the actual event-name list changes.
4. **Effect-local transport state.** The current source, reconnect timer, attempt count, and
   stop flag are ordinary variables inside the effect. They are operational details that
   must survive EventSource callbacks but must not trigger a render, so React state would be
   the wrong storage.
5. **Connect and subscribe.** `connect()` creates one `EventSource`. On `open`, it resets the
   attempt counter and reports `CONNECTED`. One `addEventListener` is registered for every
   requested name because this backend sends named events.
6. **Decode and hand off.** A listener parses `message.data` inside `try/catch`. A malformed
   frame is ignored instead of throwing out of an asynchronous browser callback; a valid
   frame is passed to `onEventRef.current(name, data)`. The generic hook does no domain
   transformation.
7. **Own the retry loop.** On the first `error` from a source, the hook closes that source,
   reports `RECONNECTING`, and schedules a new `connect()` after 1s, 2s, 4s, then at most 5s.
   `settled` prevents several error notifications from the same failed source from creating
   parallel timers. A successful `open` resets the attempt count, so a later outage starts
   again at 1s.
8. **Clean up all asynchronous work.** Effect cleanup sets `stopped`, cancels a pending
   timer, and closes the current source. `stopped` also makes a late error callback a no-op.
   This prevents an unmounted component from reconnecting in the background and makes React
   StrictMode's development-only mount → cleanup → mount check safe.

The status lifecycle is:

```text
CONNECTING ----------------open---------------> CONNECTED
CONNECTING or CONNECTED -----error------------> RECONNECTING
RECONNECTING ----------------retry opens------> CONNECTED
RECONNECTING ----------------retry fails------> RECONNECTING
```

Unmounting can close the source and cancel the retry loop from any state.

#### What changed from the reference example, and why

The assignment's reference is a minimal EventSource-hook pattern. This implementation keeps
that pattern but productionises the parts that differ for this backend and app lifecycle:

| Minimal/reference pattern | This implementation | Why |
| --- | --- | --- |
| Listen with `source.onmessage` | Register `addEventListener` for every requested name | The server emits `market_tick` and `curve_tick`. Named SSE events do not invoke `onmessage`. |
| Put the caller callback directly in the effect/listener and commonly in the dependency array | Keep the latest callback in `onEventRef` | UI renders can create a new callback identity. That should update event handling, not reconnect the network stream. |
| Let native `EventSource` retry | Close the failed source and use capped exponential backoff | Native retry is useful for ordinary disconnects, but a fatal proxy/service 5xx can leave the source `CLOSED`. Explicit retry also gives the UI a reliable `RECONNECTING` state and recovers after the service returns. Closing first prevents native and application retry loops from competing. |
| Handle only the default payload path | Parse JSON behind `try/catch` and forward `(eventName, data)` | Both event type and payload are needed for domain normalisation; one malformed frame must not break later ticks. |
| Often expose received data as hook state | Expose only connection status; deliver ticks through a callback | React must not render for every wire event. `useMarketFeed` buffers events in refs and commits a batch every 400ms. |
| Mount the hook in the market-data page | Mount it through the app-level `MarketFeedProvider` | One stream, history, and tick count continue across route changes and can also be shown in System Overview. |
| Close only the current source on unmount | Also cancel the timer and guard late callbacks | Manual retry introduces asynchronous work that must not survive cleanup; this also avoids duplicate connections under StrictMode. |

The key design is therefore two-stage: `useSseStream` owns a reliable connection and emits
decoded events immediately, while `useMarketFeed` owns their financial meaning and decides
when accumulated updates become React state. The first stage prevents connection churn; the
second prevents render churn.

## 4. Domain

### `domain/marketData.js`

Pure, testable functions that turn raw stream/snapshot JSON into a uniform instrument model
and format it. No React here.

- **Normalisation.** `instrumentsFromEvent(name, data)` and `instrumentsFromSnapshot()`
  both emit the same row shape `{ id, symbol, assetClass, currency, value, unit, tradable,
  tenor?, eventTimeMs }`. A `market_tick` yields one row. The backend also streams a single
  `USD_GOV` yield curve as one `curve_tick` carrying `tenors[]` + `rates[]`; that fans out
  into RATE rows for the 1Y, 2Y, 3Y, and 5Y nodes used to discount the annual cash flows of
  `GOVT_2Y` and `GOVT_5Y`. The 3Y/5Y pair also brackets the interpolated 4Y cash-flow rate.
  Rows are labelled as explicit curve points (`USD_GOV · 2Y`) and marked non-tradable
  (VIEW ONLY). These are points on the curve, not separate instruments.
  `value` is the first present of `mid → last → spot`, so equities use mid,
  FX/commodities/futures/index use their populated field, and rates carry the tenor's rate.
  Class-specific equity `bid`/`ask` fields flow through to the dedicated **Bid / Ask**
  column (`—` for classes without a two-sided quote).
- **History, delta & tick direction.** `mergeInstrument(prev, update)` appends the new value
  to a bounded history array (drops the oldest past `HISTORY_LENGTH`) and records
  `lastDirection` (up/down/flat vs the previous value) plus a monotonic `updateSeq`. The view
  keys each table row by `id:updateSeq`, so an updated row remounts and replays a one-shot
  green/red blink coloured by `lastDirection`. `deltaOf()` subtracts the immediately
  previous history point from the latest one, so the plain **Δ** column means change since
  the last tick. It returns 0 until there are at least two points, so a fresh row never
  shows an invented move.
- **Freshness.** `isStale(instrument, now)` compares `now − receivedAtMs` to the 5s
  threshold. Staleness is keyed off arrival time at the browser, not the server timestamp,
  so clock skew between container and browser can't wrongly mark a live feed stale.
- **Formatting.** `formatValue` prints rates as percentages and prices with class-aware
  decimals (FX to 4dp, others to 2dp with thousands separators). `formatMarketSymbol`
  renders conventional pairs (`EUR/USD`, `XAU/USD`), while `formatValueUnit` makes the
  overloaded market level explicit (`USD per EUR`, `USD/oz`, `pts`, or `yield`).
  `formatDelta` prints rate moves in basis points and price moves with a sign.
  `formatStreamTime` renders the millisecond wall-clock shown in the UPDATED column.
  `summarizeFeed` and `sortInstruments` produce the header counts and the stable
  class-then-symbol ordering.

## 5. Feed

### `views/MarketData/useMarketFeed.js`

The market-data-specific stateful layer stays outside the generic `hooks/` folder. An
app-lifetime `MarketFeedProvider` owns it and exposes the same feed to Market Data and
System Overview, while pages that do not consume the context avoid tick-driven renders.

- **Snapshot seed.** One `/snapshot` GET on mount fills the table with current spots and
  curves before any tick arrives, so the view is never blank on load. Seeded rows are stamped
  with a receive time, so they read LIVE immediately but will still flip to STALE after 5s if
  the stream never delivers.
- **Buffer, then flush.** `onEvent` pushes normalised updates into a plain ref array and
  bumps a tick counter — no `setState` per tick. A 400ms interval drains the buffer into the
  instruments map in one batched update. So however fast ticks arrive, feed consumers
  re-render at most a few times a second. When the buffer is empty the interval does
  nothing, so a dead stream costs no renders.
- **Why 400ms when `TICK_INTERVAL_MS=2000`.** The backend interval applies to each
  independent generator, not to the aggregate stream; spot, index, and curve events can
  therefore arrive close together. `FLUSH_INTERVAL_MS=400` batches those clusters, caps
  feed-driven React updates at 2.5 per second, and adds at most roughly 400ms of display
  latency. Most flush callbacks find an empty buffer and return without a state update, so
  the shorter interval does not mean five renders for every two-second generator cycle.
- **Returns** `{ instruments, tickCount, status, seeded }`.

### `providers/MarketFeedProvider.jsx`

The provider mounts above routing in `main.jsx`. Consequently there is one snapshot seed,
one `EventSource`, one rolling history map, and one received-event counter for the lifetime
of the frontend app. Navigating between pages does not close or recreate the connection.
Market Data consumes the complete feed; System Overview consumes the same status, count,
instrument freshness summary, and last-update time. The counter is mirrored to
`sessionStorage`, so a refresh in the same browser tab restores it; a new tab or closed
browser session starts a new count.

## 6. Components

### `components/charts/Sparkline.jsx`

A dependency-free inline SVG polyline over the value history — the "mini price history" the
brief asks for, without pulling in a charting library. It scales the series into the box and
colours itself by its own first-point→last-point trend: green if the line ends higher than it
started, red if lower, muted if flat.

### `components/cards/StatCard.jsx`

A small generic label/value/sub stat card with an optional tone, used for the four Market
Data summary tiles and the three System Overview stream metrics. Kept generic so the PnL
cards in later phases can reuse it.

### `components/marketdata/InstrumentTable.jsx`

Purely presentational. It receives already-computed rows and renders the columns: symbol
(with a "VIEW ONLY" tag for non-tradable benchmark/rate lines), asset-class chip,
right-aligned mono market level with its class-specific unit, delta, Bid / Ask (populated
per class), the sparkline, a LIVE/STALE pill (reusing `StatusPill`), and the millisecond
timestamp. Stale rows dim via a row modifier class. No data logic lives here.

## 7. The page

### `views/MarketData/MarketData.jsx`

Orchestration only:

1. `useMarketFeedContext()` for the app-scoped instrument map, tick count, and connection
   status;
2. `useElapsedTime()` for a one-second clock that keeps LIVE/STALE current even when no
   ticks are arriving;
3. derive rows (value, delta, direction, live) and the header summary from the map;
4. apply the class filter and the symbol search;
5. render the connection pill, the four stat cards, the controls, and the table.

It covers the required real-time UI states explicitly: connecting (pre-seed), reconnecting
with no data, empty roster, and no-matching-filters, each with its own message rather than a
blank screen. The SSE connection status is always visible as a pill (`CONNECTING` /
`CONNECTED` / `RECONNECTING`) in the header, next to a running
"N ticks received" counter reporting how many stream events the frontend has consumed in
the current browser session. The counter and connection continue across route changes, and
`sessionStorage` preserves the count through a refresh in the same tab.

The asset-class filter reuses Phase 2's `FilterChipGroup`. Its dots are suppressed (the
component only falls back to a value-derived dot colour on a *nullish* tone, so an
empty-string tone renders a plain chip) to match the design's dot-less class chips.

## 8. Deferred (honest, per the plan)

- **Buy / Sell actions** on each row belong to the New-Trade / trade-action flow and land in
  Phase 6. Rather than render dead buttons, the column is omitted for now.
- **The bottom-left "streams connected" badge** is a global shell detail, scheduled for last
  per the workflow; Market Data shows its own per-view connection pill in the meantime.

## 9. Verification

Environment note: this phase was checked with SCSS compiled via the local `sass` package and
the full `src/main.jsx` import graph type/parse-checked with esbuild (both clean). The
project's own `npm run lint` (oxlint) and `npm run build` (vite/rolldown) use
platform-native binaries and should be run on your machine:

```bash
npm run lint
npm run build
```

Then `docker compose up --build` and open System Overview. Confirm the Market Data Stream
panel connects and its tick counter climbs. Navigate to Market Data, back to System
Overview, and to Market Data again: the same counter must keep increasing rather than reset.
Refresh the tab and confirm the restored counter is at least the pre-refresh value.
The table should show conventional pair symbols and units (`EUR/USD`, `USD per EUR`), and
its Δ must reflect the previous tick. Disabling the market-data stream flips rows to STALE
within ~5s while the connection pill shows RECONNECTING.

Pricing and Blotter retain one `STREAM_DISCONNECTED` audit warning per failed reconnect
cycle for demo visibility. The message explicitly says `reconnecting in 5s`, matching the
consumer retry interval and avoiding the impression that the service has stopped trying.
