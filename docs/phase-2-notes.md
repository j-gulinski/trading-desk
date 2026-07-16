# Phase 2 notes — Data layer + System Overview

## Suggested inspection order

Read one monitoring request end to end, then inspect the reusable UI pieces:

1. **Proxy** — `frontend/vite.config.js`
2. **Data layer** — `frontend/src/services/apiClient.js` → `endpoints.js`
3. **Configuration** — `config/monitoring.js`
4. **Polling and time** — `hooks/usePolling.js` → `hooks/useElapsedTime.js`
5. **Domain** — `domain/serviceStatus.js` → `domain/formatting.js`
6. **Components** — `StatusPill` → `ServiceCard` → `FilterChipGroup` → `Panel` → `EmptyState`
7. **The page** — `views/SystemOverview/SystemOverview.jsx`
8. **Monitoring backend** — `services/monitoring-service/app/config.py` → `main.py` → `monitor.py`

---

## 1. Proxy

The browser calls `/api/monitoring/status`. Vite forwards that relative path to
`http://monitoring-service:8003/status`. Browser code never needs a Docker hostname and no
cross-origin setup is required. Later phases add one `/api/<service>` proxy per backend.

## 2. Data layer

### `services/apiClient.js`

`request()` is the single JSON fetch boundary. It:

- adds `Accept: application/json` while preserving caller headers;
- turns network and non-2xx failures into a typed `ApiError`;
- handles `204 No Content`;
- accepts normal fetch options, including `signal` for cancellation;
- supplies reusable `apiGet`, `apiPost`, `apiPut`, and `apiDelete` helpers.

The old one-endpoint `services/api.js` was removed. Keeping one client avoids inconsistent
error handling and URL conventions as more views are implemented.

### `services/endpoints.js`

This is the registry of logical API names. Components use
`endpoints.monitoring.status`, not literal URL strings. It grows one service at a time.

## 3. Configuration

### `config/monitoring.js`

Monitoring-specific status policy lives outside the hook and normalizer.
`DEGRADED_LATENCY_MS` controls the POC latency boundary and `STALE_AFTER_MS` is
**15 seconds**. General request timing remains reusable hook configuration.

## 4. Polling and time

### `hooks/usePolling.js`

The reusable API is:

```js
usePolling(fetchFn, { intervalMs = 5000, timeoutMs = 4000 })
```

`fetchFn` receives `{ signal }` and must pass it to the API client. The hook returns
`{ data, error, loading, lastPolled, lastUpdated }`.

Important behavior:

- only one request is active at a time;
- the request is aborted after `timeoutMs` and on component unmount;
- the next start is aligned to the configured interval while accounting for request time;
- a minimum retry delay prevents a slow/failing request from creating a tight loop;
- failed requests retain the last good `data` but set `error`;
- `lastPolled` changes on every attempt; `lastUpdated` changes only on success.

System Overview uses the hook's default **5-second interval** and **4-second timeout**. A
failed `/status` call is direct evidence that monitoring is unavailable, so the page does
not wait before changing monitoring itself to `down`. Cached target services retain their
last known level until their own timestamps exceed the 15-second stale threshold.

### `hooks/useElapsedTime.js`

This hook owns the one-second display/freshness clock. Given `lastPolled`, it returns
`{ now, elapsedMs }`. Its interval resets when the source timestamp changes, producing an
even `0, 1, 2, 3, 4, 0` poll-age cadence. It also keeps freshness calculations advancing
when network requests fail or hang.

## 5. Domain model

### `domain/serviceStatus.js`

`normalizeServiceStatus(raw, options)` converts the backend object into a stable array of:

```text
{ id, label, level, status, latencyMs, ageMs, stale, error }
```

The rules are centralized here:

- **Roster:** always emit the seven known services, plus unexpected backend entries. The
  first failed request therefore renders a truthful grid rather than a static error page.
- **Status:** `DOWN` maps to `down`; only explicit `UP` can become `healthy` or `degraded`;
  missing, `UNKNOWN`, and unexpected statuses map to `unknown`.
- **Degraded:** an `UP` service with latency above `DEGRADED_LATENCY_MS` is `degraded`.
  The current threshold is **6ms** as a deliberate POC value.
- **Freshness:** checks older than `STALE_AFTER_MS` (**15 seconds**) are no longer trusted.
- **Stale:** an observed service whose timestamp is no longer refreshed maps to the
  separate `stale` level, regardless of its previous latency or status.
- **Failed frontend poll:** monitoring maps to `down` immediately. Previously observed
  targets retain their last known level until `STALE_AFTER_MS`, then map to `stale`;
  targets that have never been observed remain `unknown`.

`summarize()` produces total, healthy, degraded, stale, down, and unknown counts from the
normalized list. The domain functions are pure and straightforward to unit-test.

### Monitoring self-probe

The monitoring backend now includes itself in `TARGETS`. Like every other target, its URL
comes from shared environment configuration:
`MONITORING_SERVICE_HEALTHCHECK_URL=http://monitoring-service:8003/health`. Monitor threads
start only after the HTTP server socket exists, avoiding a false boot-time failure.
`/status` therefore includes monitoring's own `response_time_ms` and `last_checked`.

The monitoring latency is measured through the same Docker-network health endpoint path as
the other services. The frontend still treats a failed `/status` request as authoritative:
a cached self-probe cannot make an unreachable monitoring service appear healthy.

### `domain/formatting.js`

`formatElapsedTime(ms)` renders values such as `0s ago`, `3m ago`, or `—` and uses whole
elapsed seconds rather than rounding up at poll boundaries. `formatNumber()` provides
locale-aware thousands separators for later views.

## 6. Reusable components

- **`StatusPill`** renders the five normalized levels and is suitable for connection,
  valuation-freshness, queue, and service states.
- **`FilterChipGroup`** renders accessible single-select/toggle-off filter bubbles from
  `{ value, label, count, tone }` options. System Overview uses it for health levels; later
  table and event views can reuse it without copying button behavior.
- **`Panel`** provides the shared titled container for dashboards and detail sections.
- **`EmptyState`** provides consistent loading, empty, unavailable, and no-match messages.
- **`ServiceCard`** intentionally stays service-specific. It composes `StatusPill` and
  displays health latency without pretending to be a universal card abstraction.

The SCSS classes for filter chips are generic (`filter-chip*`), while grid and service-card
styles remain specific to System Overview.

## 7. System Overview composition

`SystemOverview.jsx` owns orchestration only:

1. poll `/api/monitoring/status` every 5 seconds with a 4-second request timeout;
2. advance the elapsed-time clock each second;
3. normalize and summarize the response;
4. apply the selected health filter;
5. render presentational components.

The header shows poll age and `RETRYING` after a failed attempt. Health-count bubbles are
clickable filters; clicking the selected bubble again clears the filter. Counts always
describe the complete roster, and a filter with no matches renders an explicit empty state.

If monitoring is already down at frontend boot, the first request settles and the page
shows monitoring as `down` and all six never-observed targets as `unknown`. If monitoring
dies after a successful response, the first failed poll changes monitoring to `down`. The
six cached target services remain at their last known levels until their timestamps are
older than 15 seconds, then become `stale`.

The SSE, errors, and logs panels remain honest placeholders until those feeds exist.

### Operational-events preparation

Successful periodic market-data snapshots are stored in `market_data_snapshots` but no
longer also produce a `SNAPSHOT_WRITTEN` audit row. This keeps the audit feed usable for
business events and significant operational state changes. A later step can enrich that
feed with low-frequency transition pairs such as `DEPENDENCY_DOWN` / `DEPENDENCY_RECOVERED`
and `WORKER_FAILED` / `WORKER_RECOVERED`; ordinary retries, debug output, and stack traces
remain technical stdout logs.

## 8. Verification

The Phase 2 verification commands are:

```bash
npm run lint
npm run build
```
