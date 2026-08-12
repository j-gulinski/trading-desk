# Trading Microservices

A local trading and risk system that exercises the complete path from market movement to a
browser-visible PnL change. Market Data publishes prices and curves, Trade Action owns trade
creation and closing, Pricing continuously values active trades, PostgreSQL stores business
history, Blotter provides read models, and a React frontend consumes snapshots plus SSE streams.

The project is intentionally small enough to inspect end to end, but it preserves the boundaries
that matter in a real system: one writer per business entity, explicit event ordering, terminal
close state, bounded queues, latest-value coalescing, and a distinction between live state and
historical records.

## Running

```bash
docker compose up --build
```

Then open **http://localhost:3000**. No API keys or extra configuration are needed — Alembic
migrations run as part of startup, the market data generator begins ticking immediately, and the
trade generator can be started from the Generator screen. Backend services also expose their ports
directly (8001–8008, PostgreSQL on 5432) for `curl`-level inspection.

**Frontend ↔ backend connection:** the browser cannot resolve Docker Compose container names, so
the frontend calls only relative paths (`/api/pricing/...`, `/api/blotter/...`) and the Vite dev
server (port 5173 in the container, mapped to 3000) proxies each `/api/<service>` prefix to the
matching container (`vite.config.js`). SSE streams flow through the same proxy. Services find each
other inside the Compose network by container name; the database URL and service addresses come
from environment variables in `docker-compose.yml`.

## System at a glance

| Component | Responsibility |
| --- | --- |
| Market Data | Generate and persist spot, futures, FX, index, and curve events; publish snapshot and SSE |
| Trade Action | Validate intents and act as the only writer of trade lifecycle state |
| Trade Generator | Produce simulated opens and closes around a bounded open-book target |
| Pricing | Value cash products, European options, and IRS; publish PnL and book alpha/beta |
| Blotter | Combine live caches with database history for trade- and book-oriented reads |
| Books | Own trading-book configuration |
| Monitoring | Aggregate service health and important audit events |
| React frontend | Maintain live feed context and present market, valuation, and system views |
| PostgreSQL | Source of truth for trades, valuations, books, and business audit history |

```text
market event -> Market Data publisher -> Pricing consumer
  Pricing: update spot/curve -> compute valuation -> persist valuation -> publish SSE
                                                      └──> React valuation context -> screens
trade intent -> Trade Action -> OPEN trade in DB (+audit)
  -> Pricing loop refreshes active-set from DB cache

CLOSE intent -> Trade Action -> DB close (status=CLOSED, close_price)
             -> Pricing periodic finalization loop (TRADE_REFRESH_SECONDS)
             -> final valuation (final=true, unrealized=0, realized=closed PnL) persisted and published
             -> React valuation context -> screens (terminal row state)
```

## Minimal derivative calculations

The project deliberately uses one small, explainable model per new product. Pricing owns both calculations; React only displays the server-provided result.

- **European options:** Black–Scholes, with no dividends. The live inputs are the underlying spot `S` and the existing USD curve discount factor `DF(T)`; strike `K`, maturity `T`, and call/put type are the trade's own frozen terms — every option is defined at open, none are cataloged — and volatility is the house default (`σ = 0.22`) stamped into the terms server-side. For a call:

  ```text
  d1   = [ln(S/K) - ln(DF) + 0.5σ²T] / [σ√T]
  d2   = d1 - σ√T
  call = S×N(d1) - K×DF×N(d2)
  ```

  The result is a unit premium. Existing quantity, multiplier, and BUY/SELL PnL logic then applies it to the position. This means options reprice when ACME or the USD curve moves, but not when time passes or volatility changes.

- **Interest-rate swaps:** both legs walk the same payment schedule, with no notional exchange. The fixed leg discounts known coupons. The floating leg forecasts each period's rate as the forward implied by a **projection curve** and discounts the resulting cashflow off the **discount curve**:

  ```text
  fixed leg PV    = Σ N × fixed rate × accrual × DF_disc(tᵢ)
  forward(tᵢ₋₁,tᵢ) = DF_proj(tᵢ₋₁) / DF_proj(tᵢ) − 1
  floating leg PV = Σ N × forward(tᵢ₋₁,tᵢ) × DF_disc(tᵢ)
  pay-fixed NPV   = floating leg PV − fixed leg PV
  ```

  The projection curve defaults to the discount curve (only `USD_GOV` is published today), under which the floating leg **telescopes exactly** to the textbook closed form `N × [1 − DF(maturity)]` — verified numerically to `1e-10`. So the code shows the standard two-curve model, produces the simple formula's number, and pricing off a real projection curve later is a one-argument change. Proof and discussion in [`docs/pricing.md`](docs/pricing.md#5-irs--the-float-leg-teaches-the-two-curve-model).

- **Alpha/beta per book:** a rolling regression of book returns against benchmark returns, computed inside Pricing and published per book over the valuation SSE stream (plus a `GET /book-risk` seed). Full write-up — concepts, the capital-base convention, data flow, configuration — in [`docs/alpha-beta.md`](docs/alpha-beta.md).

  ```text
  one sample   = (book return, benchmark return), taken per benchmark tick
  book return  = ΔPnL since last benchmark tick / capital base (1m default, configurable)
  beta         = cov(book, benchmark) / var(benchmark)     over the last 100 samples
  alpha        = mean(book) − beta × mean(benchmark)       (also published as window totals)
  ```

  The decisions that shape it:

  - **Capital base:** a book has no NAV, only a PnL stream, so returns assume a fixed capital base ($1M, `BOOK_CAPITAL_BASE`). Alpha and beta scale as `1/capital_base`, so every event also carries the base and the capital-free `dollar_beta` (PnL per 100% benchmark move) plus `r_squared`. Positions are never scaled to the base — more exposure than assumed capital simply reads as β > 1 (leverage).
  - **Window totals, never annualized:** at 2-second ticks, annualizing multiplies minutes of noise by ~15.7M periods; the UI instead shows what the book and benchmark each did over the same observed window, and each card can expand a `return ≈ β × index + α` breakdown computed with the live numbers.
  - **`PORTFOLIO` card:** all books' summed PnL through the same regression (dollar betas add; capital defaults to base × book count) — desk-level netting next to the per-book numbers.
  - **Honest statuses:** `INSUFFICIENT_DATA` below 20 samples, `ZERO_BENCHMARK_VARIANCE` when the benchmark hasn't moved — a warming-up note instead of fabricated numbers.
  - **Benchmark choice:** the synthetic `MARKET_INDEX` — an equal-weight basket of the generated equity/commodity/futures prices. A basket, rather than any single symbol, so no book is trivially β = 1 against its own instrument and every asset class faces the same market-wide yardstick (the role a real S&P 500 plays for a real desk). Because it is built from the instruments the books trade, measured co-movement is real (single-name equity book R² ≈ 0.5, FX/rates books β ≈ 0) — but also partly self-referential, a documented limitation accepted instead of tuning synthetic dynamics that real data will make obsolete. The estimator is benchmark- and cadence-agnostic, so switching to a real index series is a config change: `BENCHMARK_SYMBOL` in `shared/catalog.py`.

- **Scenario analysis** reuses the same pricing functions: it gathers the live market inputs, applies the shock to those inputs (a fractional spot bump for equities/FX/futures/options via the underlying; a parallel basis-point curve bump for bonds and IRS), and reprices with the identical code path the valuation stream uses. There is no second pricing implementation to drift out of sync.

## Data model for derivative terms

`trades.asset_class` is a plain `TEXT` column and every per-trade economic term (strike, maturity, volatility, notional, fixed rate, direction, curve name, underlying) lives in the `trades.metadata` `JSONB` column — the "flexible JSON column" structure. No schema migration was needed for European options or IRS: opening a trade freezes the instrument's terms into `trade_metadata`, so a trade is priced for its whole life from the terms it was executed with, even if the catalog changes later. Pricing dispatches on `asset_class` and reads everything else from the metadata document.

The instrument universe is split the way a desk splits it. `shared/catalog.py` holds only **listed, quoted instruments** (equity, FX, commodity, futures, government bonds) — you trade them by picking one, and their terms are copied at open. **OTC classes** (European options, IRS) have no catalog entries: every option and swap is defined by its terms at open. `shared/term_schemas.py` declares per OTC class which fields define a product, with bounds and server-side defaults (curve, multiplier, volatility); Trade Action validates client-supplied terms against that schema, and the New Trade form renders its input fields *from* the same schema — a listed book shows an instrument picker, an OTC book shows term fields, with no mode switch. A defined product exists only as the trade's frozen terms — publishing it to a shared instrument list (a normalized `instruments` table) is deferred to the generic-catalog phase.

The full data-model reasoning — including why no migration was required — is in [`docs/architecture.md`](docs/architecture.md#6-data-model).

## Frontend views

Wireframes for every view live in [`docs/designs/`](docs/designs/) (one PNG per screen, including
the New Trade ticket and the trade-details drawer); they were drawn first and the screens were
implemented from them. The views map to the microservices one-to-one with one deliberate merge:
**there is no separate Monitoring screen — System Overview absorbs it** (service health,
response times, SSE stream status, and recent errors all come from Monitoring's `/status` and
audit endpoints), because at this system size a separate screen would duplicate the overview's
purpose.

| View | Purpose |
| --- | --- |
| System Overview | Service health, stream status, error feed (includes Monitoring) |
| Logs | Central log stream: live tail, service/level filters, correlation story panel |
| Generator / Trade Actions | Generator control and config; queue, throughput, rejections |
| Business Overview | Top-level PnL, book risk, valuation freshness |
| Market Data | Live ticks, curve, sparklines, LIVE/STALE marking |
| Valuations & Risk | Fair value stream, top open positions, per-book alpha/beta cards |
| Books | Book CRUD with integrity-guarded delete |
| Trades & PnL | Operational blotter: trades, valuation history, audit logs |
| New Trade (top bar) | Trading ticket: catalog instruments or schema-driven OTC terms |

**View configurability** (chosen for domain sense, not option count): every table has a column
picker with drag-reorder, sort captured on click, and class/book/status/text filters; Market Data
adds a tick-history depth setting. Choices persist per key in `localStorage`
(`frontend/src/config/storage.js`) so an operator's layout survives reloads, and Market Data's
tick history survives navigation via `sessionStorage`. Alpha/beta benchmark
selection is deliberately backend config (`BENCHMARK_SYMBOL`), not a UI toggle — switching the
benchmark invalidates the rolling window, which is not a per-user decision.

## Screen data sources

Two SSE feeds — market data and valuations — are opened once in `FeedProvider` above routing and
shared through React context, so switching screens never reconnects a stream. Everything else is
plain HTTP polling with a per-screen interval. The dividing rule: **streams carry high-frequency
values** (prices, fair value, PnL), **polls carry slow-moving state** (trade membership, config,
queue counters, health). Writes never update the client optimistically — after a successful POST
the owning poll refetches server truth out of cycle (`usePolling().refetch()`).

| Screen | Stream (shared context) | Polls | Writes |
| --- | --- | --- | --- |
| Market Data | market SSE + one-shot snapshot seed (repeated on reconnect) | — | — |
| Valuations | valuation SSE + one-shot seed; stream-only by decision — the UNREALIZED PNL summary derives from stream rows, no summary poll | — | — |
| Business Overview | valuation SSE (same shared context) | — | — |
| Trades & PnL | valuation SSE overlays live fair value / PnL by trade ID | Blotter `/trades/overview` every 5 s (membership, terms, closed history); detail drawer polls `/trades/{id}` only while open | close intent → Trade Action |
| Trade Actions | — | `/queue/status` every 2 s; monitoring audits every 3 s | trade intents → Trade Action |
| Generator | — | generator `/status` every 2 s; monitoring audits (generated intents) every 3 s; books summary every 30 s | start / stop / generate-once / config → Trade Generator |
| System Overview | none of its own — stream health is read from both shared feed contexts | monitoring `/status` every 5 s; monitoring audits (errors) every 5 s; monitoring `/logs` (warning+, recent errors strip) every 5 s | — |
| Logs | monitoring `/logs/stream` SSE (per-view, opened on entry, closed on leave) + `/logs` seed | `/logs` meta every 10 s (service chips, sparklines, warn pulse) | — |
| Books | — | `/blotter/books/summary` every 5 s (totals and netted per-symbol positions in one response) | create / edit / delete book → Books; `REASSIGN_TRADES` → Trade Action |
| New Trade (top bar, every route) | market feed remains visible elsewhere; the form uses backend pricing truth and survives route changes | books summary + Trade Action `/instruments` and `/instruments/term-schemas`; Pricing `/price` on selection or on each valid change of custom terms | `OPEN_TRADE` intent (catalog symbol, or custom symbol + validated terms) with the displayed entry value → Trade Action |

## Decisions that define the system

### Ownership is explicit

- Trade Action is the only service that changes trade lifecycle state.
- Pricing owns valuation and PnL calculation.
- PostgreSQL owns durable history; streams and caches are delivery/read models.
- Blotter may combine live and historical data, but it does not become a second writer.
- Books owns which books exist; it asks Blotter over HTTP about trades rather than reading the
  `trades` table, and refuses a destructive operation it cannot verify.

Trade closing is guarded in SQL:

```sql
UPDATE trades
SET status = 'CLOSED'
WHERE trade_id = :id AND status = 'ACTIVE'
```

Only `rowcount == 1` means the close won. A unique `client_request_id` makes resubmitting an intent
idempotent.

Retiring a book is guarded the same way, one level up: a book is deactivated only when Blotter
reports zero ACTIVE trades for it. If Blotter cannot answer, the deletion is refused rather than
allowed — `409` means the book still has positions, `503` means we could not tell.

### Tick-to-screen order

| Order | Stage | Ordering and cost |
| ---: | --- | --- |
| 1 | Market Data creates a tick | The event carries `stream_id`, monotonic `event_id`, and canonical `event_time` |
| 2 | Pricing consumes the tick | Spot/curve cache is updated before dependent trades are selected |
| 3 | Pricing selects affected trades | Spot ticks value matching symbols and option underlyings; curve ticks value dependent bonds, options, and IRS |
| 4 | Pricing calculates valuations | BUY/SELL sign, multiplier, FX forward, bond DCF, Black–Scholes premium, or simplified IRS NPV is applied centrally |
| 5 | Pricing persists | Each accepted valuation is currently written separately |
| 6 | Pricing checks current identity | An event superseded by a newer/final valuation is not published |
| 7 | Per-client queue receives the event | `put_nowait` prevents one slow browser from blocking Pricing |
| 8 | Browser consumes SSE | Every delivered message is parsed and normalized immediately |
| 9 | Browser applies ordering | Final valuations apply immediately; live updates coalesce latest-per-trade |
| 10 | Shared 500 ms scheduler flushes | Live state can publish twice per second; freshness advances on every second scheduler tick |
| 11 | Valuation screen derives its view | Full context → status → filter → sort → first 100 matching rows |

The expensive backend path finishes before queue publication. Increasing queue capacity can absorb
a burst, but it cannot make calculation or database persistence faster.

### Snapshot and stream are concurrent

Waiting for a snapshot before opening the stream creates a guaranteed gap, so each feed starts
both at once: the SSE stream carries continuous changes, an HTTP snapshot seeds current state and
repairs reconnects. They can arrive in either order; timestamp-guarded merge rules reconcile them
(a final valuation is terminal, otherwise the strictly newer one wins, and a snapshot merges into
context rather than replacing it). A final event immediately turns a row `CLOSED`; only non-final
open valuations can be `LIVE` or `STALE`.

### Frontend ingestion is continuous; React publication is throttled

Every delivered SSE event is parsed and normalized immediately — what is throttled is publication
into React. Repeated live updates for the same trade collapse into a latest-value `Map` that
flushes to state at most every 500 ms; final valuations, snapshots, and connection status bypass
the buffer because terminal and structural facts should never wait. The feed hooks stay mounted
above routing, so switching screens never reconnects a stream, and only the active route runs its
screen-specific derivations. Live tables render a bounded window — a DOM boundary, not data
eviction: summaries and filters still see everything. Scheduler mechanics and the per-screen
derivation pipelines are in [`docs/performance.md`](docs/performance.md).

## Logging and observability

The system keeps two separate trails that meet only through `correlation_id`. The
**audit trail** (`audit_logs` in Postgres) is the *business* record — trade created, action
rejected, worker started — written deliberately at business moments and queryable forever. The
**application logs** are the *technical* record — connections, retries, rejections with reasons,
per-tick computation at DEBUG — high-volume, structured JSON, and deliberately not stored in the
database.

```text
service (structlog JSON) ──► stdout                      (docker compose logs — unchanged)
                        └──► ./logs/<service>.log        (RotatingFileHandler, shared bind mount)
                                        │
monitoring-service sweeper thread ───── tails all files each second, parses JSON lines
                                        │
                    per-service ring buffers (deque, bounded, in-memory)
                                        │
              GET /logs (snapshot+filters+meta)   GET /logs/stream (SSE live tail)
                                        │
frontend  Logs view (filters, search, live tail, pause)
        └► System Overview "Recent errors" strip
        └► correlation story panel (logs + audits merged per id)
```

Why files and a sweeper, not a logs table: high-volume technical logs would bloat Postgres for no
query benefit, and there is a bootstrap problem — a database-connection failure cannot be logged
to the database (stop postgres and watch `audit_write_failed` ERROR lines land in the files; the
file trail captures exactly what the DB cannot). Services never push logs anywhere: writing the
local file is their only obligation, so a service never blocks, fails, or slows down because the
observer is down. The pattern is the minimal version of real log shipping — Filebeat/Fluentd
tailing files a process wrote locally — with transport (files), aggregation (sweeper), and
storage policy (bounded buffers) as separate concerns. A future service joins the Logs view by
merely writing `/var/log/trading/<name>.log`; the sweeper discovers files, not services.

Mechanics: rotation is size-based (`LOG_FILE_MAX_BYTES`, default 5 MB × 3 backups) — every line
carries an ISO timestamp, so dating lives in the line, not the filename. The sweeper tracks
`(inode, offset)` per file and survives rotation without gaps or replays; on a monitoring
restart it warm-starts from the last ~64 KB of each file. Buffers are one `deque(maxlen=10_000)`
*per service*, so one chatty service cannot evict another's history. SSE client queues are
bounded and drop-on-full, like every other stream in the app. If `LOG_DIR` is unwritable the
service logs one warning and continues stdout-only — logging never takes a service down.

Correlation flow: the trade-action worker binds `correlation_id` (the intent's
`client_request_id`) into structlog contextvars for each dequeued intent, so every log line of
that action's processing carries the same id as its audit rows. Clicking a correlation id
anywhere opens the story panel: every log line (from the sweeper buffers) and every audit row
(from Postgres) with that id, merged chronologically — one intent traced across services and
across both trails.

**Failure-cascade demo** (watch a failure narrate itself): open the Logs view, then

1. `docker compose stop market-data-service` — pricing logs `stream_failed` WARNINGs on each
   ~5 s retry, monitoring writes one `DEPENDENCY_DOWN` transition audit (not one per poll), the
   Overview error pulse rises, and the `WARNING+` level chip isolates the cascade.
2. `docker compose start market-data-service` — one reconnect line per consumer,
   `STREAM_CONNECTED` and `DEPENDENCY_RECOVERED` audits, and the pulse decays.

What is deliberately *not* promised: no log persistence beyond the rotating files (no table, no
search index), no cross-restart search (buffers are memory), no external log stack (ELK/Loki are
over-scope), no runtime log-level switching from the UI (config is env-owned), and no
multi-line/stack-trace folding beyond what `log.exception` renders into a single JSON line.

## Performance and scaling

The system is bounded, not optimized: client queues, latest-value coalescing, and the bounded
render window protect it from bursts without pretending to raise throughput. The limits were
measured, not guessed, and they arrive in a specific order — Pricing's per-valuation database
transactions first (at ~2,100 open trades it had to persist ~1,000 valuations per second and rows
went stale), browser DOM work for many simultaneously changing rows second, lifetime-history
growth third, and sorting nowhere close (five full 1,197-row sorts: 0.8 ms). Each growth symptom
has one chosen next step — batched inserts per tick, on-demand closed history, table
virtualization, incremental book-risk totals — rather than speculative optimization of
everything at once.

The full analysis — every bound with its deliberate tradeoff, the measurements behind the
bottleneck ordering, and the symptom → next-option table — is in
[`docs/performance.md`](docs/performance.md).

## Important limitations

- Trade Action uses an in-process, non-durable queue. Idempotency makes retry safe, but in-flight
  work can be lost on restart.
- Trade Generator tracks open-trade IDs in memory, seeded from the Blotter at startup and
  re-synced every 10 seconds. Trades opened or closed outside the generator can take up to one
  sync interval to enter its equilibrium calculation.
- SSE is current-state delivery, not durable replay. Snapshot/reconnect repairs state but does not
  reconstruct every missed event.
- Pricing currently persists valuations one at a time and retains latest closed valuations in its
  in-memory snapshot collection for the process lifetime. Book-risk sampling walks that whole
  collection on every benchmark tick to total PnL per book, so its per-tick cost grows with
  runtime trade history — negligible at the demo target, and the first thing to optimize at scale
  (see [`docs/performance.md`](docs/performance.md)).
- The Blotter list is a recent working window, not a complete historical archive: active rows are
  not paginated, non-active history is bounded, and exact totals/cursors are not published.
- Book alpha/beta measures the PnL of everything in the book at face exposure; hedge-aware
  exposure netting (an option offsetting its underlying) is deliberately out of scope.
- Options carry a fixed per-trade volatility and do not reprice on the passage of time alone;
  there is no vol feed, no Greeks, and IRS uses a single published curve for both
  discounting and projection.
- Custom-defined instruments are not published to a shared catalog: another trader cannot pick
  up a product you defined; it exists only in the trade that carries its terms.
- Application logs are retained only as the rotating files (~5 MB × 3 per service) and the
  collector's in-memory buffers (last 10,000 lines per service): no database table, no search
  index, and no cross-restart search beyond the 64 KB warm-start tail. The Logs view shows the
  recent window, not an archive.

## Where to read more

Start at [`docs/README.md`](docs/README.md) — it is the index and the reading order.

| Document | What it holds |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Service ownership, the three system rules, one trade end to end, the data model |
| [`docs/pricing.md`](docs/pricing.md) | Frozen terms, discount factors, Black–Scholes, IRS, the scenario engine |
| [`docs/alpha-beta.md`](docs/alpha-beta.md) | The full alpha/beta walkthrough with a worked example |
| [`docs/logging.md`](docs/logging.md) | File sink, the sweeper, the Logs view, correlation and trade stories |
| [`docs/frontend/`](docs/frontend/) | The frontend set: React model, data & streams, screens, styling |
| [`docs/performance.md`](docs/performance.md) | Optimizations and tradeoffs, measured bottlenecks, growth playbook |
| [`docs/decisions.md`](docs/decisions.md) | Every decision, what was rejected, and why — the fastest way back into context |
