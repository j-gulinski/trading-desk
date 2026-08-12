# React, as this project uses it

Written for someone who knows backend engineering and wants the React model to click rather than
a tour of the API. Every concept here appears in this codebase, and every example is real code
from it.

The one shift in thinking: **you never update the screen. You describe what the screen should
look like for the current data, and React works out the DOM operations.** Everything below is a
consequence of that.

## 1. The rendering model in six steps

```text
1. something changes state          setInstruments(next)
2. React calls your component       Valuations(props) runs again, top to bottom
3. you return a description         JSX → a tree of plain objects ("elements")
4. React diffs it against the last  reconciliation
5. React patches only the diffs     the real DOM changes minimally
6. effects run                      useEffect callbacks for what changed
```

Two consequences that catch backend developers out:

- **Your component function runs many times.** It is not a constructor. Anything expensive or
  side-effecting placed directly in the body runs on every render.
- **Values inside one render are frozen.** Each render has its own `props`, its own state
  variables, its own closures. A callback created in render #4 sees render #4's values forever,
  even if it runs later. That is the *stale closure*, and §4 shows how this project avoids it.

## 2. Boot, and what StrictMode is for

```jsx
// main.jsx
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <FeedProvider>
      <App />
    </FeedProvider>
  </StrictMode>
)
```

One `<div id="root">` in `index.html`; React owns everything inside it. `FeedProvider` sits
*outside* `App` deliberately — that is what keeps the SSE connections alive across navigation
(§8).

**StrictMode double-invokes effects in development**: mount → unmount → mount. This is not a
bug, it is a test. An effect that acquires something without releasing it produces *two* live
resources instead of one, and you see it immediately rather than in production. In this project
it is the reason every stream, timer, and listener has a cleanup function — a missing one shows
up as two `EventSource` connections to the same endpoint in the Network tab.

## 3. Components are functions; composition is the layout tool

A component takes props and returns elements. That is the whole contract.

```jsx
// App.jsx — the entire router
export default function App() {
  const path = useHashRoute()
  const route = findRoute(path)
  const Page = route.component

  return (
    <AppShell route={route}>
      <Page />
    </AppShell>
  )
}
```

`routes/routes.js` is the single registry both `App` and `Sidebar` read, which is what stops the
menu and the rendered page from drifting apart. `findRoute` falls back to the first route for an
unknown path — deliberately, rather than rendering a 404 page: with a fixed nine-entry menu, a
bad hash is a typo or a stale bookmark, and landing on System Overview is more useful than an
error screen. Hash routing (`#/market-data`) also needs no server-side fallback configuration,
because everything after `#` never reaches the server.

`AppShell` knows nothing about any page. It receives one through `children` and renders the
frame around it:

```jsx
<AppShell route={route}>{/* whatever the route resolves to */}</AppShell>
```

That is **composition**: a reusable component owns *structure* while the caller supplies
*content*. `SidePanel` is the same idea at feature level — it owns the heading, close button,
body and footer; trade details, the New Trade form, and the log story panels supply what goes
inside. Six features, one shell, no shell knowledge of any of them.

The alternative — passing data down through five layers of props to reach the component that
needs it — is **prop drilling**, and §8 is how this project avoids it.

## 4. State, and the two ways to get it wrong

```jsx
const [instruments, setInstruments] = useState(readStoredInstruments)
```

**Lazy initializer.** Passing the *function* `readStoredInstruments` rather than calling it means
React runs it only on the first render. `useState(readStoredInstruments())` would re-read
`sessionStorage` on every single render and throw the result away. The same pattern appears in
`useHashRoute` (`useState(readPath)`) and `useTableState`.

**Functional updates.** This is the important one:

```jsx
setValuations((previous) => mergeValuations(previous, pending))   // right
setValuations(mergeValuations(valuations, pending))               // wrong here
```

The second form uses `valuations` from *the render that created this callback*. In a live feed
the callback is invoked from a timer that outlives that render, so it would merge into stale
state and silently drop updates. The functional form asks React for the current value at the
moment it applies. **Rule of thumb: if the next state depends on the previous state, and the
update can fire asynchronously, use the function form.**

**State is not for everything.** Three questions before adding `useState`:

| Question | If yes |
| --- | --- |
| Can it be computed from existing state/props? | Don't store it — derive it (§9) |
| Does the UI need to re-render when it changes? | If no, use a ref (§5) |
| Does another component need it? | Lift it up, or use context (§8) |

## 5. Effects: acquire, then release

Every subscription in this app follows one shape, established by the smallest hook in the
codebase:

```jsx
export function useHashRoute() {
  const [path, setPath] = useState(readPath)

  useEffect(() => {
    const onChange = () => setPath(readPath())
    window.addEventListener('hashchange', onChange)     // acquire
    return () => window.removeEventListener('hashchange', onChange)   // release
  }, [])

  return path
}
```

```text
read the current external value
  → subscribe inside useEffect
  → update React state when it changes
  → unsubscribe in the cleanup function
```

`usePolling`, `useSseStream`, `useElapsedTime`, `usePanelChrome`, and `useBufferedUpdates` are
all this same shape with a different resource: a timer, an `EventSource`, a clock subscription,
document listeners. **The effect that acquires a resource must release it** — that is the whole
discipline, and StrictMode (§2) enforces it.

### The dependency array is an identity comparison

React re-runs an effect when any dependency is `!==` what it was. That is reference identity,
not deep equality — which is why this line exists in `useSseStream`:

```jsx
const eventNames = events.join(',')      // 'valuation_update,book_risk_update'
useEffect(() => {
  const names = eventNames.split(',')
  ...
}, [url, eventNames])                    // a string compares by value
```

The caller passes `events: ['valuation_update', 'book_risk_update']` — a **new array object on
every render**. Depending on that array directly would tear down and rebuild the SSE connection
on every render of the parent, forever. Joining it into a string collapses identity to value.

The three ways this bites, and the fixes used here:

| Symptom | Cause | Fix in this codebase |
| --- | --- | --- |
| A connection restarts constantly | An array/object/function in the deps is recreated each render | Reduce to a primitive (`events.join(',')`) or wrap in `useCallback`/`useMemo` |
| An effect uses stale values | A value was left out of the deps | Put changing *callbacks* in a ref instead (§6) |
| An effect never re-runs when it should | `[]` used where a dep was needed | Only use `[]` for genuinely mount-scoped resources |

## 6. Refs — three different jobs

A ref is a mutable box that survives re-renders and **never triggers one**. This project uses
refs for three distinct purposes, and telling them apart makes the code read clearly:

**1. Work that must not cause renders.**

```jsx
// useBufferedUpdates.js
const bufferRef = useRef(new Map())
return useCallback((key, update) => {
  bufferRef.current.set(key, update)     // hundreds of times per second, zero renders
}, [])
```

Incoming ticks accumulate here. If this were state, every wire event would re-render the app —
which is the exact problem the buffer exists to solve.

**2. The latest callback, for a long-lived subscription.**

```jsx
// useBufferedUpdates.js
const onFlushRef = useRef(onFlush)
onFlushRef.current = onFlush             // updated on every render, no effect needed

useEffect(() => subscribeToStreamClock(() => {
  ...
  onFlushRef.current(pending)            // always the newest version
}), [])                                  // subscribe once, ever
```

This is the workhorse pattern of the whole app. The subscription must be created once, but it
must call the *current* callback — which closes over the current state. Putting the callback in
the deps would resubscribe constantly; leaving it out would call a stale version. The ref
resolves the conflict. `usePolling` (`savedFn`), `useSseStream` (`onEventRef`), and
`useTableState` (`captureSnapshotRef`) all do the same.

**3. A DOM node.**

```jsx
const panelRef = useRef(null)
...
<aside ref={panelRef}>          // usePanelChrome asks: does this element contain the click?
```

## 7. Keys: identity, not just a lint rule

In a list, `key` tells React which element is which across renders, so it can move a row instead
of rebuilding it:

```jsx
{rows.map((row) => <tr key={rowKey(row)}>…</tr>)}
```

But `key` has a second, more powerful use — and it fixed a real bug here. React preserves a
component's state when its **type and position** are unchanged. Create-book and edit-book both
rendered `BookFormPanel`, so changing only the `bookId` prop *reused the previous form's state*:
you would open Edit and see the values you had typed into Create.

```jsx
<BookFormPanel key={`${panel.type}:${panel.bookId ?? 'new'}`} … />
```

A changed key means "this is a different thing": React unmounts the old component and mounts a
fresh one, so `useState` re-initializes and the previous effect's cleanup aborts its in-flight
request. The story panel uses the same trick (`key={`${story.kind}:${story.id}`}`) so opening a
second story never shows the first one's data.

**`key` controls state identity. It is not a styling or animation concern** — this codebase
handles the "don't replay the slide-in animation" question separately, with a `switchingPanel`
flag. Two decisions that look like one.

## 8. Context — for genuinely shared things only

Two contexts exist in this app, both for things that must not be recreated per view:

```jsx
// FeedProvider.jsx — mounted above the router in main.jsx
<MarketFeedContext.Provider value={marketFeed}>
  <ValuationFeedContext.Provider value={valuationFeed}>
    {children}
```

- **Two separate contexts, not one object.** A valuation update must not invalidate the market
  context — every consumer of a context re-renders when its value changes, so combining them
  would make every market view re-render on every valuation.
- **The value is memoized** (`useMemo` in `useMarketFeed`/`useValuationFeed`), so it changes
  identity only when its contents actually change.
- **The consumer hook throws if used outside the provider:**

  ```jsx
  function useFeed(context, label) {
    const feed = useContext(context)
    if (feed == null) throw new Error(`${label} feed must be used inside FeedProvider`)
    return feed
  }
  ```

  A clear error at the boundary beats `undefined` propagating into a component three levels down.

`PanelProvider` is the same idea for a different problem: any component anywhere can open a side
panel, and only one may be open, so the coordination state lives above them all.

**Context is not a state manager.** It is a way to avoid passing a prop through components that
don't care about it. Everything else in this app is local `useState`, and nothing needed Redux
or Zustand — because the only genuinely global state is two feeds.

## 9. Derived state: if you can compute it, don't store it

```jsx
// StreamsBadge reads both feed contexts and computes during render:
//   how many are connected, and what the weakest status is.
// It stores nothing.
```

The same rule shapes the views: `Valuations.jsx` holds only three pieces of state —
`activeClass`, `activeBook`, `query` — and everything on screen is computed from those plus the
feed:

```jsx
const openRows     = valuationRowsOf(Object.values(valuations), now).filter(…)
const summary      = summarizeValuations(openRows)
const matchingRows = sortValuationRows(openRows.filter(…), table.sort)
const visibleRows  = matchingRows.slice(0, MAX_RENDERED_ROWS)
```

Every one of those is recomputed on every render, and that is *correct*: there is no second copy
that can drift out of sync with the feed, no invalidation logic, and no bug where a filter
changes but a cached total doesn't. Where it becomes expensive, the answer is a measurement and
then a bound ([performance.md](../performance.md)) — not a cache.

## 10. Memoization, and when it earns its place

`useMemo` (cache a value) and `useCallback` (cache a function identity) exist to keep
*identities* stable, not to make arithmetic faster. Used without a reason they add code and
allocate anyway.

Where they earn it here:

| Use | Why it is justified |
| --- | --- |
| `useMemo` on feed context values | Prevents every consumer of the context from re-rendering on unrelated renders |
| `useMemo` on `columnById` in `useTableState` | Rebuilding a Map per render, consumed by several callbacks below it |
| `useCallback` on `applySort`, `pushUpdate` | They are dependencies of effects and other callbacks — unstable identity would restart subscriptions |
| `memo` on `Sparkline` | Measured: unchanged instruments were rebuilding SVG geometry on every tick |

Where it is deliberately absent: the row derivation pipelines above. Five full sorts of 1,197
rows measured ~0.8 ms total — memoizing that would add reconciliation logic to save nothing.
**Measure, then memoize.**

## 11. Custom hooks are just functions that use hooks

No magic. A custom hook is a function whose name starts with `use` and which calls other hooks;
it exists so stateful logic can be reused without inheritance or wrapper components. The rules:
call hooks at the top level (never in a condition or loop), and only from components or other
hooks — React matches hooks to state slots by call order.

The full inventory of this app, which doubles as a map of where behavior lives:

| Hook | Owns | Key idea |
| --- | --- | --- |
| `useHashRoute` | the current path | The subscribe/cleanup shape (§5) |
| `usePolling` | scheduled GETs | One request in flight; timeout; interval minus elapsed |
| `useSseStream` | one `EventSource` | Transport only: connect, parse, status, reconnect |
| `useStreamSeed` | snapshot fetch | Runs at mount and after a real reconnect |
| `useBufferedUpdates` | ingest→render throttling | Latest-per-key Map + shared clock |
| `useElapsedTime` | a UI clock | Lets rows age into STALE with no events |
| `useMarketFeed` / `useValuationFeed` / `useLogsFeed` | one feed each | Compose the four above with domain merge rules |
| `useTableState` | columns and sort | Presentation state only — never the rows |
| `usePanelChrome` | Escape + outside click | Two document listeners, scoped to a panel's life |
| `useStoredFlag` | one persisted boolean | `localStorage` with try/catch on both sides |

Notice what is *not* in that list: nothing owns business data. Rows are derived in views from
feed state and domain functions (§9).

## 12. The traps this project actually hit

| Trap | Symptom | Fix |
| --- | --- | --- |
| Stale closure in an async callback | Updates silently lost under load | Functional `setState`; callbacks in refs |
| Missing effect cleanup | Two `EventSource`s per stream in dev | Return an unsubscribe from every effect; StrictMode exposes it |
| Array/object in a dependency array | A stream reconnecting on every render | `events.join(',')` — compare by value |
| Same component type reused for a different subject | Edit form pre-filled with Create's values | Explicit `key` per session (§7) |
| `a or b` on a numeric value | A legitimate price of `0` treated as missing | Check `!= null` explicitly (`first_present` on the backend, `??` here) |
| `text-transform: uppercase` on Greek letters | `β × index + α` rendered as `B × INDEX + A` | CSS transforms apply to all of Unicode — rename the label |
| Rendering every matching row | 361–472 ms long tasks at 1,197 rows | Bound the *rendered* window, keep the data |
| A defaulted parameter hiding an unwired feature | `bookRisksOf(rows)` — no error, alpha/beta structurally `null` forever | Check the screen, not just the payload (below) |

**Wiring is part of the feature.** Alpha and beta were computed correctly, published on the SSE
stream, and visible in the raw events — while one card rendered a hardcoded `n/a` and Business
Overview called `bookRisksOf(rows)` without the risk map, whose defaulted `riskMetrics = {}`
turned the omission into a permanently empty result rather than a crash. Both screens looked
plausible; neither had ever displayed a real number. **A backend publishing correct data proves
nothing until a screen consumes it** — which is why "check it in a browser" is the last step of
the recipe in [frontend/README.md §4](README.md#4-recipe--adding-a-new-view), not an afterthought.

## Where to go next

- [data.md](data.md) — how values get into the state these components render.
- [screens.md](screens.md) — how a view is assembled from these pieces.
- [styling.md](styling.md) — the SCSS system and the layout mechanics.
