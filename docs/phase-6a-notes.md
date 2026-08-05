---
phase: 6a
status: complete
revised: 2026-08-05
tags:
  - frontend
  - generator
  - trade-action
  - monitoring
  - audits
---

# Phase 6a — what you should know

This phase replaced the Generator and Trade Actions placeholders with polling screens. It also made
the trade generator configurable at runtime without creating new event feeds.

## 1. Reuse the audit trail instead of inventing feeds

Both screens poll the monitoring service's existing `/audits` endpoint. Trade-action-service already
writes `TRADE_CREATED`, `TRADE_CLOSED`, and `ACTION_REJECTED`, so another per-service event store
would duplicate data.

Generated intents use correlation IDs beginning with `gen-`; manual actions use `manual-`. The
Generator screen filters to generated rows, while Trade Actions shows both and labels their source.

```text
trade action worker → audit row with correlation_id
→ monitoring /audits poll
→ normalizeAuditEvents
→ intentRowsOf(generatedOnly?)
→ IntentFeed
```

The audit payload does not contain per-action latency, book, side, or quantity. The UI omits those
values rather than estimating them.

## 2. These are polling screens, not stream consumers

```text
Generator
  ├── /trade-generation/status every 2 s
  ├── /monitoring/audits every 3 s
  └── /blotter/books/summary every 30 s

Trade Actions
  ├── /trade-action/queue/status every 2 s
  └── /monitoring/audits every 3 s
```

They do not consume `FeedProvider`. Their state changes slowly enough that polling is simpler and
does not add another long-lived connection.

Books are the authority for supported trading asset classes. The generator screen therefore reads
classes from the book roster instead of inferring them from market ticks, which would wrongly add
the non-tradable index and omit curve-priced bonds.

## 3. Runtime generator configuration

Frequency and target open trades are mutable service state protected by a `threading.Lock`.
Environment variables provide startup defaults; the live `/status` response is authoritative after
startup.

The backend validates and clamps the complete request before changing either field. An invalid
mixed request applies nothing. Current ranges are:

- interval: 100–60,000 ms;
- target open trades: 1–10,000.

The generator loop reads the interval on every iteration. A `threading.Event` provides an
interruptible wait, so a config change wakes the loop immediately instead of waiting for a previous
long sleep to finish.

Close probability remains derived:

```text
p_close = min(0.9, 0.5 × open_trades / target_open_trades)
```

Capacity (`open / target`) and close probability answer different questions and are intentionally
not the same percentage.

## 4. Editable polled state needs a draft/server split

The screen renders `draft.value ?? server.value`. A draft protects the user's in-progress edit from
an incoming poll. Slider changes update locally immediately and commit after a short debounce.

After a successful write, the screen calls `refetch()` and reconciles with server truth. It does not
maintain an optimistic copy or rollback path. A draft entry is removed only if it still matches the
value that completed; a newer edit made during the request survives.

```text
edit draft → POST /config → server validates/applies → status.refetch()
→ remove only the committed draft value → render server truth
```

## 5. Synchronize replaceable state from its authority

The generator tracks open trades in memory for close selection and probability. It rebuilds that
Map from active blotter rows at startup and periodically afterwards.

Replacement is idempotent and avoids drift from trades opened or closed by other processes. The
same `sync_open_trades()` path handles startup and steady-state reconciliation.

## 6. Metrics must describe their population

Queue depth was removed as a headline signal because an always-draining queue usually reads zero
even while work is flowing. Client-derived rate tiles were also removed because cumulative counters
and the intent feed already show activity without sampling machinery.

Labels state whether a number is from the bounded visible feed or the current process. Never infer a
time-window rate from a count-limited list.

## Mental model

```text
Generator controls → POST config/start/stop → locked runtime state
                                  └── refetch status → server truth

generator intent → trade-action queue → audit row
                                  └── monitoring poll → Generator/Trade Actions feed

blotter active trades → sync_open_trades → generator's managed Map
```

## Concepts to keep

- **Module state behind a lock:** validate outside, mutate atomically inside, return a copy.
- **Interruptible sleep:** `Event.wait(timeout)` can wake when configuration changes.
- **Draft versus server state:** polling must not overwrite active user edits.
- **Refetch after write:** confirm server truth instead of guessing optimistically.
- **Sync by replacement:** rebuilding from authority is simpler and safer than incremental patches.
- **Dead-code checks:** lint/build do not prove abandoned exports were removed.

## Current limits

- Audit rows cannot provide per-action latency or full trade details.
- Generator configuration is process memory; restart returns to environment defaults.
- The simulator is still synthetic and is intended to be replaced by real-data strategies later.

## Main files

- `frontend/src/views/Generator/Generator.jsx` and `TradeActions/TradeActions.jsx`.
- `frontend/src/domain/generator.js` and `auditEvents.js`.
- `frontend/src/hooks/usePolling.js`.
- `services/trade-generation-service/app/generator.py` and API/config modules.
- `services/monitoring-service/app/` — audit filters.
- `services/trade-action-service/app/` — queue counters and audit creation.
