# Getting data in — HTTP, polling, SSE, and the throttle

How the frontend talks to seven backend services, keeps two live streams open for the whole
session, and turns a firehose of events into a screen that updates twice a second.

## 1. The path in six steps

```text
1. one boundary     every request goes through apiClient; failures become ApiError
2. one origin       /api/pricing/... — the Vite proxy reaches containers the browser can't
3. choose per fact  poll what changes slowly, stream what changes fast
4. seed + stream    both start at once; ordering rules decide which value wins
5. buffer           events land in a Map keyed by identity; nothing renders yet
6. flush            one shared 500 ms clock publishes to React state
```

## 2. Step 1 — the HTTP boundary

`services/apiClient.js` is the only place `fetch` is called. It exists because raw `fetch` has
three behaviors that would otherwise be re-handled in every view:

- **it does not reject on HTTP errors** — a 500 resolves normally, so `res.ok` must be checked
  every single time;
- **it has no timeout** — a hung request stays pending forever;
- **`.json()` throws on an empty body** — a successful `204 No Content` (what a delete returns)
  would crash the caller, so the client returns `null` for it instead.

```js
if (!res.ok) {
  const body = await res.json().catch(() => null)
  throw new ApiError(`Request failed (${res.status})`, { path, status: res.status, body })
}
```

`ApiError` carries `path`, `status`, `cause`, and the parsed error `body`. That last field is why
the Books screen can say *"Refused — this book still has 3 open positions"* rather than
"Error 409": the backend returns `{"active_trades": 3}` and the view reads it
([screens.md §5](screens.md#5-writes--validate-submit-observe)).

**Timeouts apply to writes, not reads.** Reads retry naturally on the next poll; a write is a
one-shot the user is waiting on:

```js
function withTimeout(signal, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  return { signal: signal ? AbortSignal.any([signal, controller.signal]) : controller.signal, … }
}
```

`AbortSignal.any` composes two independent reasons to cancel: the caller's signal (component
unmounted, a newer request started) and the timeout. Distinguishing them matters for the message
— `timedOut()` produces "the service did not answer", anything else is "Network error".

**Cancellation is a correctness feature, not an optimization.** Without it, a slow response from
a request you no longer care about can land after a newer one and overwrite it — the classic
race. Every polled fetch and every seed fetch passes a signal.

`services/endpoints.js` is the URL registry. Views reference `endpoints.monitoring.logs({…})`,
never a literal path, so a route change is one edit.

## 3. Step 2 — why the browser talks to itself

The frontend requests same-origin paths like `/api/pricing/valuations`. Vite's dev server
proxies them to the containers:

```js
'/api/pricing': { target: 'http://pricing-service:8002', rewrite: (p) => p.replace(/^\/api\/pricing/, '') }
```

This is not a convenience. **The browser cannot resolve `pricing-service`** — that name exists
only inside the Docker network; the page runs on the user's machine. The proxy also means no
service needs CORS configuration, and SSE flows through the same path (a proxy that buffers
would break streaming — this one doesn't).

The trade-off to know: production needs a real reverse proxy exposing the same public paths. The
frontend's URLs stay deployment-independent, which is the point.

## 4. Step 3 — poll or stream, decided per question

| Question | Mechanism | Why |
| --- | --- | --- |
| Which trades exist? What is their lifecycle? | poll blotter, 5 s | Membership changes slowly; the response is the durable truth |
| What is this trade worth *now*? | valuation SSE | Changes on every tick; lag is visible |
| What is the market doing? | market SSE | Same |
| Is the system healthy? | poll monitoring, 5 s | A health verdict is a slow fact |
| What is the generator/queue doing? | poll, 2–3 s | Counters, not events |
| What just got logged? | logs SSE + seed | A live tail *is* the feature |

### `usePolling` — the rules a bare `setInterval` gets wrong

```js
usePolling(fetchFn, { intervalMs = 5000, timeoutMs = 4000 })
  → { data, error, loading, lastPolled, lastUpdated, refetch }
```

| Rule | Why it exists |
| --- | --- |
| One request in flight at a time (`inFlight` guard) | `setInterval` overlaps requests when the server is slow, and responses can land out of order |
| Next tick scheduled *after* the response, `intervalMs − elapsed` | Keeps a steady cadence without stacking |
| Minimum retry delay | Prevents a tight failure loop hammering a service that is down |
| Abort on timeout and unmount | See §2 |
| Failure keeps the last good `data`, sets `error` | A blip must not blank the screen |
| `lastPolled` vs `lastUpdated` | *Attempted* and *succeeded* are different facts; the UI shows both |

`fetchFn` is held in a ref (`savedFn.current = fetchFn`), so a view can pass an inline arrow
function without restarting the polling loop on every render — the pattern from
[react.md §6](react.md#6-refs--three-different-jobs).

## 5. Step 4 — SSE, and what `EventSource` actually is

Server-Sent Events is a long-lived HTTP response with a tiny text framing:

```text
event: valuation_update
data: {"trade_id":"…","fair_value":12850.25}

event: book_risk_update
data: {"book_id":"…","beta":0.84}

```

Blank line ends a record. `new EventSource(url)` opens it and dispatches named events; it is
**not** a Promise and there is nothing to `await`. Chosen over WebSockets because the data flows
one way — server to browser — and SSE is plain HTTP: it goes through the same proxy, needs no
protocol upgrade, and reconnects on its own.

```jsx
const { status } = useSseStream(endpoints.pricing.stream, {
  events: ['valuation_update', 'book_risk_update'],
  onEvent: (name, data) => { … },
})
```

`useSseStream` owns **transport only** — connect, parse JSON, report status, reconnect, clean up.
It knows nothing about valuations, instruments, or log lines. Three details are worth reading in
the source:

- **JSON parsing is guarded.** A malformed `data:` line is dropped, not thrown — one bad event
  must not kill the stream.
- **The reconnect is explicit.** `EventSource` retries by itself, but silently; this hook closes
  the connection on error, sets `RECONNECTING`, and reconnects after a fixed delay, so the UI can
  *show* the state. A `failed` flag prevents a burst of errors from scheduling several reconnect
  timers.
- **The event callback lives in a ref**, so a re-rendering parent never restarts a healthy
  connection (see §4 above and [react.md §6](react.md#6-refs--three-different-jobs)).

### Snapshot and stream, together

```text
GET /snapshot → the complete latest-known state
GET /stream   → new observations as they happen
```

Both start immediately. The app does not wait for the snapshot before opening the stream,
because that gap is exactly when events go missing. The consequence: a stream event can arrive
*before* an older snapshot, so **domain rules decide which value wins, not arrival order.**

`useStreamSeed` re-runs the snapshot when the status goes `RECONNECTING → CONNECTED` — not on
every `CONNECTED`, or a normal mount would fetch twice:

```jsx
const wasInterrupted = previousStatusRef.current === STREAM_STATUS.reconnecting
previousStatusRef.current = status
return wasInterrupted && status === STREAM_STATUS.connected ? runSeed() : undefined
```

### The ordering rules, per feed

| Feed | Rule | Why |
| --- | --- | --- |
| Market data | Within one `stream_id`, higher `event_id` wins; across a restart, `event_time` arbitrates and accepted history resets | The generator restarts; ids restart with it |
| Valuations | A **final** valuation can never be replaced by a later-arriving live one; otherwise newer `valuation_time` wins | A lifecycle transition outranks a timestamp |
| Trades table | Blotter snapshot ⊕ valuation stream per trade: terminal flags decide first, then the newer `valuation_time`, with the stream winning an exact tie | Only the stream value carries browser receipt time, so only it can be aged into LIVE/STALE |
| Logs | Dedup by the collector's monotonic id; a new `run_id` clears the buffer | Seed and stream overlap by design; the id makes the union exact ([logging.md](../logging.md)) |

**Every one of these is evaluated per entity, not per feed.** Market-data `event_id`s are allocated
globally, but the comparison happens inside one instrument's slot — a higher id on ACME says
nothing about whether an EURUSD update is stale. The same holds per trade for valuations.

**Snapshots merge directly, without the buffer.** A snapshot is a rare reconciliation event, not a
stream of updates, so throttling it would only delay the correction it exists to deliver.

The valuation rule fixed a real bug: a superseded live value arriving after the closing valuation
made a closed trade look open and stale again. The server now applies the same rule before
publishing — **the same invariant enforced at both ends.**

**The honest gap in all of it:** the ordering rules can only arbitrate between values that carry
identity. Cold-start rows seeded by the backend do not all carry a complete per-entity id, so at
boot a first live event can lose to a late-arriving snapshot until the next tick corrects it.
Ordering rules are not sufficient on their own — they need every row to be identifiable, and a
lossless version would need versioned initial rows plus durable cursors ([§9](#9-what-this-architecture-does-not-give-you)).

### Connection status ≠ data freshness

`CONNECTED` describes the HTTP stream. `LIVE`/`STALE` describes the age of one instrument's last
received value. A connected feed can hold a stale instrument (nothing has ticked), and a
reconnecting feed still shows useful last-known values. Freshness is computed from *browser
receipt time* against a UI clock, so a row can become STALE with no event arriving at all:

```jsx
export function useElapsedTime(sinceMs) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => subscribeToStreamClock(setNow, FRESHNESS_INTERVAL_MS), [])
  return { now, elapsedMs: sinceMs == null ? null : Math.max(0, now - sinceMs) }
}
```

## 6. Steps 5–6 — ingest continuously, publish on a clock

The problem: valuations arrive faster than a screen needs to repaint, and `setState` per message
would re-render the app hundreds of times a second.

```text
wire event → normalize → bufferRef Map keyed by identity → (500 ms) → one setState
```

```jsx
export function useBufferedUpdates(onFlush) {
  const bufferRef = useRef(new Map())
  const onFlushRef = useRef(onFlush)
  onFlushRef.current = onFlush

  useEffect(() => subscribeToStreamClock(() => {
    if (bufferRef.current.size === 0) return
    const pending = Array.from(bufferRef.current.values())
    bufferRef.current = new Map()
    onFlushRef.current(pending)
  }), [])

  return useCallback((key, update) => { bufferRef.current.set(key, update) }, [])
}
```

Twenty lines, and they carry the app's whole performance story:

- **Keyed by identity**, so ten updates for one trade inside a window collapse to the newest.
  This is **coalescing, not sampling** — every event is still parsed and normalized; only
  intermediate *display* states are skipped.
- **The Map is a ref**, so accumulating costs zero renders.
- **The subscription is created once** and reaches the current callback through
  `onFlushRef` — otherwise every render would resubscribe.
- **Empty buffers don't flush**, so a quiet feed causes no renders at all.

The division of labour is **inversion of control**, and it is why one hook serves three feeds:
the buffer owns *when* a flush happens; the caller supplies *what flushing means* (merge
valuations, merge instruments, append log lines). Neither knows the other's job, so a new feed is
a new `onFlush` rather than a new scheduler.

One `streamClock` module owns a single 500 ms timer for the entire app. Feed buffers subscribe to
every tick; freshness clocks to every second tick, which means the one-second render carries both
in one React batch. One aligned scheduler beats several drifting timers, and it stops when its
last subscriber unmounts.

**The deliberate exception:** a *final* valuation bypasses the buffer entirely.

```jsx
if (received.closed) {
  setValuations((previous) => mergeValuations(previous, [received]))   // immediate
  return
}
pushUpdate(received.id, received)                                       // buffered
```

A business lifecycle transition must not wait behind display throttling.

## 7. Feeds live above routing

`FeedProvider` is mounted in `main.jsx`, outside `App`, so navigating between views replaces only
the page component. Market history and tick counts keep accumulating; no view opens a duplicate
stream.

```text
main.jsx
└── FeedProvider          ← EventSource × 2 live here, for the whole session
    └── App               ← routing happens below the streams
        └── AppShell → the current view
```

A feed hook is the composition of everything above:

```jsx
export function useValuationFeed() {
  const [valuations, setValuations] = useState({})
  const [bookRisk, setBookRisk] = useState({})

  const pushUpdate = useBufferedUpdates((pending) =>
    setValuations((previous) => mergeValuations(previous, pending)))

  const { status } = useSseStream(endpoints.pricing.stream, { events: […], onEvent })
  const seedStatus = useStreamSeed(status, (signal) => Promise.all([…]).then(…))

  return useMemo(() => ({ valuations, bookRisk, status, seedStatus }), […])
}
```

Transport is generic; the feed hook owns normalization and merge rules; the view owns display.
Three layers, and a change to any one of them stays there.

**Streams stay connected while the tab is hidden.** Closing them on `visibilitychange` was tried
and removed: a snapshot cannot reconstruct the ticks missed while away, so the saving costs real
observations. The accepted price is that three open app tabs can exhaust the six HTTP/1.1
connections per origin — the fix is HTTP/2 or one multiplexed stream, not discarding data.

## 8. The two variants worth studying

**Market feed — session persistence.** It restores instruments and the tick count from
`sessionStorage` on mount and writes them back on change, so a refresh does not blank the screen
while the first snapshot loads. Every read and write is wrapped in try/catch: storage can be
disabled or full, and a dashboard must not fail to boot over a preference.

**Logs feed — a per-view stream.** Every other stream is an app-root singleton; this one mounts
with the Logs view and closes on unmount, which is acceptable because it is cheap. It adds three
things the others don't need:

- **Pause**, which diverts arriving lines into a pending array and shows "Resume · N new" —
  a live tail that scroll-jumps while you are reading it is unusable;
- **run-id reset**, dropping the buffer when the collector restarts ([logging.md](../logging.md));
- **a render cap separate from the data cap** — 10,000 lines held and searchable, 500 rendered.

## 9. What this architecture does not give you

- **No exactly-once delivery.** SSE plus snapshot gives *eventual state*: a dropped event is
  repaired by the next snapshot or the next tick, not replayed. Fine for "what is it worth now",
  wrong for an auditable tape.
- **No offline queue.** A write that fails is reported, not retried in the background.
- **No cross-tab coordination.** Each tab holds its own streams and its own buffers.
- **Bounded server-side queues.** Each SSE client has a bounded queue on the server; a client too
  slow to drain it loses events and relies on snapshot repair.

Each is a deliberate trade recorded in [decisions.md](../decisions.md), not an oversight.
