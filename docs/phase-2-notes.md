---
phase: 2
status: complete
revised: 2026-08-05
tags:
  - frontend
  - data-layer
  - polling
  - monitoring
  - system-overview
---

# Phase 2 — what you should know

This phase created the reusable HTTP and polling layers and used them to build System Overview.

## 1. One HTTP boundary

All JSON requests pass through `services/apiClient.js`. The wrapper:

- applies common headers;
- converts network and non-2xx responses into `ApiError`;
- handles `204 No Content`;
- accepts `AbortSignal` cancellation;
- exposes `apiGet`, `apiPost`, `apiPut`, and `apiDelete`.

Raw `fetch` does not reject a `500` response, so converting HTTP failures at one boundary prevents
every view from inventing different error handling.

`services/endpoints.js` centralizes logical URLs. Components refer to
`endpoints.monitoring.status`, not container names or literal paths.

## 2. The browser uses same-origin proxy paths

The frontend requests `/api/monitoring/...`; Vite forwards it to the monitoring container during
development. The browser never needs Docker DNS names, and the backend does not need feature-level
CORS configuration.

This separates browser URLs from deployment topology. A production reverse proxy must provide the
same public paths.

## 3. `usePolling` owns request scheduling

```js
usePolling(fetchFn, { intervalMs: 5000, timeoutMs: 4000 })
```

The hook returns `data`, `error`, `loading`, `lastPolled`, `lastUpdated`, and `refetch`.

Important rules:

- only one request runs at a time;
- timeout and unmount abort the current request;
- request duration is deducted from the next interval;
- a minimum retry delay prevents tight failure loops;
- failure retains the last good data while exposing the new error;
- `lastPolled` means attempted, while `lastUpdated` means succeeded.

This is safer than `setInterval(fetch, 5000)`, which can overlap slow requests and allow older
responses to overwrite newer ones.

`useElapsedTime` provides a UI clock so freshness can change even when no request succeeds. It does
not fetch data.

## 4. Normalize backend data before rendering

`normalizeServiceStatus` converts the backend payload into a stable view model:

```text
{ id, label, level, status, latencyMs, ageMs, stale, error }
```

The page never works directly with raw response objects. Central normalization means a backend
shape change is fixed once and keeps React components presentation-focused.

Status policy is explicit:

- the known service roster always renders;
- explicit `DOWN` is down;
- slow `UP` can be degraded;
- old observations become stale;
- missing/unseen services remain unknown;
- failure to reach monitoring marks monitoring itself down immediately.

Thresholds live in `config/monitoring.js`; the domain function applies them. This separates policy
values from the mechanism using them.

## 5. Honest UI states are part of the contract

The screen distinguishes loading, unavailable, stale, no results, and healthy data. A failed poll
does not erase previously observed services. If monitoring dies, cached target services age into
STALE rather than incorrectly becoming DOWN.

Generic components were extracted only where reuse was real:

- `StatusPill` for normalized status;
- `FilterChipGroup` for accessible filters;
- `Panel` for titled sections;
- `EmptyState` for explicit non-data states.

`ServiceCard` remains specific because one usage is not enough evidence for a generic abstraction.

## Mental model

```text
SystemOverview
  ├── usePolling → apiClient → /api/monitoring/status → Vite proxy
  ├── useElapsedTime → current UI time
  └── normalizeServiceStatus
          ├── summary counts
          ├── selected filter
          └── ServiceCard + StatusPill
```

## Concepts to keep

- **Boundary errors:** convert transport failures once, not in every component.
- **Cancellation:** abort obsolete work so late responses cannot win races.
- **View models:** normalize external data before it reaches presentation.
- **Honest states:** keep last-known data and label uncertainty instead of inventing values.
- **Extract on proven reuse:** generic components should solve repeated problems, not imagined ones.

## Main files

- `frontend/src/services/apiClient.js` and `endpoints.js` — HTTP boundary and URL registry.
- `frontend/src/hooks/usePolling.js` and `useElapsedTime.js` — polling and freshness time.
- `frontend/src/domain/serviceStatus.js` — monitoring normalization and policy.
- `frontend/src/views/SystemOverview/SystemOverview.jsx` — page orchestration.
- `frontend/vite.config.js` — browser-to-service development proxy.
