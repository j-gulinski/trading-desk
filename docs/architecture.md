# Architecture — the system, told as one trade

Seven Python services, one Postgres, one React frontend, all started by `docker compose up
--build`. This document explains what each service owns, the three rules that make the whole
thing hang together, and then walks a single trade from a click to a number on screen.

Read this first. Everything else ([pricing](pricing.md), [alpha-beta](alpha-beta.md),
[logging](logging.md), [frontend](frontend/README.md)) is a zoom-in on one part of this picture.

## 1. The system in eight steps

The shape of the whole system, in the order data moves:

```text
1. market-data       invents prices          → publishes ticks + curves (SSE)
2. trade-generation  invents trade intents   → posts them to trade-action
3. trade-action      is the only writer      → queue → worker → trades table + audit row
4. pricing           reads active trades     → reprices on every tick → publishes valuations (SSE)
5. blotter           reads trades+valuations → serves the operational read model
6. books             owns book metadata      → guarded create/edit/retire
7. monitoring        watches everything      → health, audits, log collection
8. frontend          merges snapshot+stream  → screens that stay live without reloading
```

Two things are deliberately *not* in that list: no message broker, and no service-to-service
call about a trade. Which brings us to the three rules.

## 2. Three rules that explain most of the code

### Rule 1 — the database row is the handoff

Trade-action inserts a trade. Pricing does not get told; it re-queries `ACTIVE` trades every
two seconds and swaps its in-memory working set wholesale. Blotter does the same on its own
cadence.

**Why:** polling the one source of truth means a service that restarts rebuilds its whole world
from the database with no replay protocol, no message ordering to reason about, and no
dependency on another service being alive at the right moment. The cost is latency — up to
`TRADE_REFRESH_SECONDS` (2 s) before a new trade is priced — which is invisible in a UI that
already streams.

**What it rules out:** exactly-once event semantics and instant propagation. Both are real
trade-offs, both documented rather than hidden.

### Rule 2 — one writer per table

Every mutation of `trades` goes through trade-action-service, even when the request comes from
the Books screen. Books-service owns `books`. Pricing owns `valuations`.

This is why "move trades to another book" is a `REASSIGN_TRADES` intent sent to trade-action
rather than an UPDATE inside books-service, and why deleting a book asks blotter whether it
still has active trades instead of reading blotter's tables.

**The corollary — fail closed.** When books-service cannot reach blotter to verify the
precondition, it answers `503`, not "probably fine". An unavailable dependency is never
permission for a destructive action:

```text
books-service → blotter active-trade check
  ├── active trades exist → 409  (precondition failed)
  ├── blotter unavailable → 503  (could not verify)
  └── zero active trades  → deactivate
```

### Rule 3 — freeze at the boundary

When a trade opens, the instrument's economics — strike, maturity, volatility, notional, fixed
rate, direction, curve, underlying — are validated once and frozen into the trade's
`metadata` JSONB column. Every later process prices the trade from its own frozen terms and
never looks anything up again.

Change the catalog tomorrow, delete an entry entirely: an open trade keeps the economics it was
executed with. This is also why adding two whole asset classes (options, IRS) required **no
database migration** — see [pricing.md §2](pricing.md).

The three rules in one sentence, worth being able to say out loud: **freeze at the boundary,
poll the truth, route by what you froze.**

## 3. Who owns what

| Service | Port | Owns | Publishes |
| --- | --- | --- | --- |
| market-data | 8001 | synthetic spot prices, the `USD_GOV` curve, `MARKET_INDEX` | `GET /snapshot`, SSE `/stream` |
| pricing | 8002 | valuations, book alpha/beta, scenario analysis | `GET /valuations`, `GET /book-risk`, SSE `/valuation-stream`, `POST /price`, `POST /scenario` |
| monitoring | 8003 | health polling, audit queries, log collection | `GET /status`, `GET /audits`, `GET /logs`, SSE `/logs/stream` |
| books | 8004 | book metadata and lifecycle | `GET/POST/PUT/DELETE /books` |
| blotter | 8006 | the operational read model over trades | `GET /trades/overview`, `/trades/{id}`, `/books/summary` |
| trade-generation | 8007 | the simulator and its runtime config | `GET /status`, `POST /config`, `/start`, `/stop` |
| trade-action | 8008 | **every** mutation of `trades` | `POST /trade-actions` (202), `GET /queue/status`, `GET /instruments/term-schemas` |
| frontend | 3000 | nine views over the above | — |

The browser never talks to any of these directly. It requests same-origin paths like
`/api/pricing/valuations`; Vite's dev-server proxy forwards to the container by name. That keeps
Docker DNS names out of the browser (which cannot resolve them) and means no service needs CORS
configuration. A production deployment must provide the same public paths through a real reverse
proxy — the frontend's URLs are deployment-independent by construction.

## 4. One trade, end to end

A custom equity option, from an empty form to a live PnL number. Every subsystem appears exactly
once.

**Define.** The user picks an options book in the New Trade ticket. Because `EUROPEAN_OPTION` is
an OTC class, the form renders no instrument picker — it fetches
`GET /instruments/term-schemas` and builds its fields *from the schema*: underlying ACME, Put,
strike 137, maturity 1.25. Volatility is never asked for; it is a pricing input, not a term of
the contract, so the server stamps its house default.

**Preview.** As the terms validate, the form derives the symbol (`ACME_PUT_137_1.25Y` — always
derived, never typed) and posts `{asset_class, terms}` to pricing's `POST /price`. Pricing runs
the *same* `validate_terms` the worker will run — the server never trusts frontend validation —
and returns a live model mark. Nothing is stored; a preview is a pure quote.

**Open.** Submit sends one `OPEN_TRADE` intent with a client-generated `client_request_id`. The
API does not execute it: it puts the intent on an in-process queue, returns `202`, and a single
worker thread picks it up. `202` means *queued*, not *done* — the UI never pretends otherwise.

**Execute.** The worker validates the terms again, checks that the book exists, is active, and
expects this asset class, then in **one transaction** inserts the trade and writes its
`TRADE_CREATED` audit row. The trade and its audit trail cannot exist without each other. A
duplicate `client_request_id` hits a unique constraint and lands in a `duplicates` counter —
idempotency by database constraint, not by checking first.

**Discover.** Nobody tells pricing. Within ~2 s its refresh loop re-queries active trades and
the new one is in the working set (Rule 1).

**Reprice.** ACME ticks. Pricing selects trades to revalue by matching the tick against frozen
metadata — `symbol == "ACME"` **or** `metadata.underlying_symbol == "ACME"`, which is how an
option whose own symbol never ticks still reprices when its underlying moves. Black–Scholes runs
on the live spot and the curve's `DF(1.25)`; the valuation is persisted and published on the
SSE stream.

**Display.** The browser merges the valuation into its feed context (latest-per-trade buffer,
flushed on a shared 500 ms clock) and the row shows LIVE fair value and unrealized PnL.

**Close.** A close is another intent through the same queue. The worker flips the status and
writes `TRADE_CLOSED`; pricing's next refresh drops the trade from the active set and
`finalize_closed_trades` writes one terminal valuation where unrealized becomes realized. That
final valuation is *terminal*: no later live value can overwrite it, on the server or in the
browser.

```text
ticket ──POST──► trade-action queue ──worker──► trades row + audit row
                                                     │
                                          (2 s poll) │
                                                     ▼
market tick ──────────────────────────────────► pricing reprices ──SSE──► browser
                                                     │
                                                     └──► valuations table ──► blotter read model
```

## 5. The two trails

The system records what happens twice, on purpose, and the distinction runs through every
screen:

| | audit trail | application logs |
| --- | --- | --- |
| Records | business moments: trade created, action rejected, dependency down | technical events: retries, connections, failures with reasons |
| Written | deliberately, one row per event | freely, wherever the code finds it useful |
| Stored | Postgres `audit_logs`, forever | rotating files + bounded memory buffers, recent window only |
| Answers | "what happened to this trade?" | "why did it happen / what was the system doing?" |

They are separate mechanisms and meet in exactly one place: both can carry the same
`correlation_id`. That single shared field is what makes the story panel possible — see
[logging.md §7](logging.md).

**The audit trail doubles as the UI's activity feed, and that was the point.** The Generator and
Trade Actions screens read monitoring's existing `/audits` rather than a purpose-built events
endpoint: trade-action already writes `TRADE_CREATED`, `TRADE_CLOSED`, and `ACTION_REJECTED` for
every intent, so a second per-service feed would have duplicated the same data behind a second
schema to keep in sync. Telling the two sources apart needs no extra field either — the intent's
own `correlation_id` carries it, since the generator mints `gen-…` ids and the UI mints
`manual-…` ones. **The id prefix is the source discriminator**, so the Generator screen filters on
`gen-` while Trade Actions shows both and labels each. Before adding a store, check whether an
existing one already records the event under a name you can query.

## 6. Data model

Four tables carry the domain, and one design choice defines them.

- **`books`** — `book_id`, `name`, `expected_asset_class`, `is_active`. Retirement is a soft
  delete: a deactivated book keeps its closed trades and realized PnL, so it stays visible
  behind an "include deactivated" toggle and can never be a reassignment target.
- **`trades`** — identity, book, side, quantity, prices, lifecycle status, and
  **`metadata JSONB`** holding the frozen terms. `asset_class` is `TEXT`, not a database enum.
- **`valuations`** — one row per repricing, plus the terminal row written at close.
- **`audit_logs`** — service, event type, severity, message, `entity_type`/`entity_id`,
  `correlation_id`, timestamp.

**Why `TEXT` + JSONB and not a typed instrument schema.** The homework explicitly lists "a
flexible JSON/JSONB column with instrument parameters" as an acceptable approach, and the schema
already held it: adding `EUROPEAN_OPTION` and `IRS` needed no migration at all. A migration is
justified by a structure the current schema *cannot* hold — not by a structure that merely feels
more proper. The honest cost is named in [decisions.md](decisions.md): a custom-defined
instrument exists only inside its own trade's frozen terms; publishing it so another trader
could pick it up would need a real `instruments` table.

Migrations that do exist live in `db/versions/` (Alembic) and run as a one-shot `db-migrations`
container before any service starts.

## 7. Patterns inside a service

Each service is a small threaded Python process — a Bottle app plus one or two background
threads sharing module state. Five patterns recur, and each exists because of a specific failure.

### Module state behind a lock

The generator's runtime config (interval, target open trades) is mutable state read by a loop and
written by an HTTP handler. The discipline is three-part: **validate outside the lock, mutate
atomically inside it, return a copy.**

```text
request → validate and clamp the WHOLE request   (nothing applied yet)
        → acquire lock → apply all fields → release
        → return a copy of the new state
```

Validating first is what makes a mixed valid/invalid request apply *nothing* rather than half of
itself. Returning a copy means a caller can never hold a reference into live state and read a
torn value mid-update.

"Validate" here means **clamp, not reject** — interval to 100–60,000 ms, target open trades to
1–10,000 — so a slider dragged to an absurd value still yields a running generator rather than a
`400`. And the state is deliberately **process memory**: a restart returns to the environment
defaults, because the sliders are a demo control surface, not a configuration store.

### Interruptible sleep

A loop that does `time.sleep(interval)` cannot notice that the interval just changed — a config
change would take effect only after the previous long sleep expired.

```python
stop_event.wait(timeout=interval_seconds)   # returns early when something happens
```

`threading.Event.wait(timeout)` is a sleep that can be woken. The generator reads the interval on
every iteration and waits on an event, so a new setting applies immediately instead of "in up to
60 seconds".

### Never hold a lock across I/O

Market-data's publisher allocates its event id and takes a coherent snapshot copy **inside** the
lock, then does the database write **after releasing it**:

```text
with lock:   assign event_id, copy current state     ← microseconds
(released)   persist to Postgres, publish to clients ← milliseconds, and can block
```

If persistence happened under the lock, one slow database write would stall tick generation for
everyone. The same shape appears in the log collector (buffer under the lock, fan out to SSE
clients outside it) and is the general rule: **a lock protects an invariant, not a workflow.**

### Cache invalidation by disagreement

Blotter caches active trades indexed by `book_id`. When trades are reassigned, that indexed field
changes underneath the cache — and blotter is not the writer, so it never sees the update
directly.

```text
database reassignment
  → pricing's active-set refresh picks up the new book_id
  → the valuation it publishes carries the new book_id
  → blotter compares it with its cached value
  → on disagreement, atomically re-index the trade
```

The correction rides an existing channel rather than adding an invalidation protocol. The honest
limit: a moved trade that never receives another valuation would not re-index until restart —
acceptable because every catalogued symbol keeps ticking.

**The general lesson:** a denormalized read model must have *some* path that notices when the
data it indexed on changes. A cache with no invalidation story is a bug with a delay.

### One number, one request

A book card shows an unrealized total and a per-symbol breakdown. Originally these came from
different sources, so they represented different instants and did not always add up — the
classic "the total doesn't match the rows" bug.

`/books/summary` now computes both **in one pass over the same cached trades and valuations**, so
the card total is the sum of the returned rows by construction. It also makes gaps visible:
a position with a missing valuation participates in the net position and marks it STALE, rather
than vanishing from a stream-only breakdown.

**A total and its decomposition must come from one snapshot.** If they can be computed
separately, they will eventually disagree, and the user will believe neither.

### Guard the transition, not the route

Deactivating a book requires zero ACTIVE trades. That check cannot live only in
`DELETE /books/{id}` — `PUT /books/{id}` with `{"is_active": false}` reaches the same state
change. The guard is attached to the transition, so every path into it is covered.

**When a rule protects a state change, put it where the state changes.**

## 8. Conventions this project follows

Carried over from how it was built, and worth keeping:

- **No explanatory comments in code.** Rationale lives in these docs; code carries only the
  one- or two-line comments that state a constraint the code cannot show. Prose duplicated in
  both places drifts apart, and the docs always win that fight.
- **Honest UI over fake data.** Where a value is unavailable, screens show a real state —
  PENDING, `n/a`, `12/20 returns`, "unavailable — retrying" — never an invented zero.
- **Extract on proven reuse.** A component becomes generic after the second real caller, not in
  anticipation of one.
- **Statuses over fabrication, in the domain too.** `INSUFFICIENT_DATA` and
  `ZERO_BENCHMARK_VARIANCE` are first-class published values, not errors and not nulls.
- **Bounded everything.** Every queue, buffer, and rendered table has an explicit cap, and the
  cap is documented next to what it protects ([performance.md](performance.md)).

## 9. Where to look next

| Question | Document |
| --- | --- |
| How is an option or a swap actually priced? | [pricing.md](pricing.md) |
| What do the ALPHA/BETA cards mean? | [alpha-beta.md](alpha-beta.md) |
| How does a log line get from a service to the screen? | [logging.md](logging.md) |
| How does the browser stay live without re-rendering everything? | [frontend/README.md](frontend/README.md) |
| What breaks first under load? | [performance.md](performance.md) |
| Why was X done this way and not the obvious way? | [decisions.md](decisions.md) |
