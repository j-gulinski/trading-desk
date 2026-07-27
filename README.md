# Trading Microservices

A miniature trading / risk stack: market data is generated and streamed, trades are opened
and closed, active positions are continuously revalued and their PnL published, and a React
frontend shows the live market and the blotter. Postgres is the single source of truth, SSE
carries the live streams, everything runs on Docker Compose.

This README covers the decisions worth knowing. Implementation detail lives in `docs/`.

---

## Services

| Service | Port | Responsibility | Key endpoints |
|---|---|---|---|
| market-data | 8001 | generate + persist market data, publish the live feed | `/snapshot`, `/stream` (SSE) |
| pricing | 8002 | value ACTIVE trades, write valuations, publish PnL | `/valuations`, `/valuation-stream` (SSE), `POST /scenario` |
| monitoring | 8003 | poll every `/health` + `SELECT 1` on Postgres | `/status`, `/audits` |
| books | 8004 | CRUD trading books, validate asset class | `/books`, `/books/<id>` |
| blotter | 8006 | read side: live cache + DB history | `/books/summary`, `/trades`, `/trades/<id>/…` |
| trade-generation | 8007 | simulated order source | `/start`, `/stop`, `/generate-once` |
| trade-action | 8008 | queue + worker, the only writer of `trades` | `POST /trade-actions`, `/batch`, `/close-all` |
| frontend | 3000 | React + Vite UI | — |

Every service also answers `GET /health`.

## Running

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD etc.
docker compose up --build
```

Compose starts Postgres, runs Alembic migrations once (a `db-migrations` one-shot container
gated on the Postgres healthcheck), then the services. Schema comes from Alembic, **not**
`Base.metadata.create_all`. Migrations alone: `docker compose run --rm db-migrations`.

---

## The end-to-end flow

```
intent → trade-action (queue + worker) → trades (ACTIVE)
       → pricing values it on the next market tick → valuations + valuation_update (SSE)
       → blotter caches live PnL; on close, pricing finalizes realized PnL
```

1. An `OPEN_TRADE` intent hits trade-action, is queued, returns **202 Accepted**, and a
   worker validates it (book exists, asset class matches, idempotent) and inserts an
   `ACTIVE` trade in one transaction.
2. Pricing's refresh loop (~2 s) picks up the new trade and values it on each market tick,
   writing a valuation and publishing `valuation_update`.
3. A `CLOSE_TRADE` intent flips it to `CLOSED`. Pricing then writes one final valuation with
   `unrealized = 0`, `realized` set, `total = realized`.

---

## Decisions worth reading

### Only one writer, and the guard is in the database

trade-action owns every write to `trades`. A `queue.Queue` separates fast HTTP intake from
DB writes and a single worker serialises them. **Double-close is prevented in SQL, not in
Python:**

```sql
UPDATE trades SET status='CLOSED' WHERE trade_id=:id AND status='ACTIVE'
```

the close only wins if `rowcount == 1`. `trades.client_request_id` is UNIQUE, so a re-sent
intent cannot create a second trade — which is what makes the non-durable queue acceptable.

### PnL signs live in exactly one place

| Asset class | Fair value |
|---|---|
| EQUITY / COMMODITY | `price × qty` |
| FUTURES | `price × multiplier × qty` |
| FX (forward) | `forward × qty`, `forward = spot × (1 + r_d·T) / (1 + r_f·T)` |
| BOND | `Σ CF_t / (1 + r(t))^t × qty`, rate interpolated off the `USD_GOV` curve |

The classic domain bug is the sign, so pricing owns all of it:

- BUY: `unrealized = (current − trade) × qty × multiplier`
- SELL: `unrealized = (trade − current) × qty × multiplier`

Per-trade pricing terms (futures multiplier, bond coupon/maturity/curve) are copied into
`trades.metadata` (JSONB) at creation, so trades are self-describing and pricing never reads
the instrument catalog at runtime. Money is `NUMERIC` everywhere, never float.

### Two sources of truth for one price, reconciled by identity

Every generated market event carries a process `stream_id`, a monotonic `event_id` and a
canonical `event_time`, and `/snapshot` exposes the same fields. The browser starts the
snapshot request and the stream **concurrently** — waiting for one would guarantee a gap —
and resolves the resulting race per instrument: same process and a higher sequence number
wins; a changed process is a restart and resets that instrument's window; a late frame from
a dead process is dropped. A reconnect refetches the snapshot and merges it the same way
rather than replacing state wholesale.

The documented exception: hard-coded rows that exist before any generator has ticked carry
only the envelope's `stream_id`, so during the first seconds after a backend start a late
snapshot can briefly overwrite a newer live value. Recurring ticks converge.

Full walkthrough in [`docs/phase-3-notes.md`](docs/phase-3-notes.md).

### The blotter is a read model, not a second source of truth

**Live lists and PnL come from the stream cache; single-trade history comes from the DB.**

- The live working set holds **only ACTIVE trades**, indexed on
  `book_id / asset_class / status / symbol`; queries intersect the smallest id-set first
  instead of scanning. Bootstrapped from the DB at startup, kept current off the stream,
  **evicted on close** — so memory tracks open risk, not total history.
- `GET /trades` resolves by status: ACTIVE from the cache, CLOSED from the DB, no status
  returns both.
- **Realized** PnL in `/books/summary` is aggregated from the DB (final valuation rows), so
  it survives restarts; **unrealized** is summed live from the cache.

### Audit logs are business records, technical logs are not

- **Technical logs** — `structlog` JSON to stdout, for watching the app in a console.
- **Audit logs** — business events in the `audit_logs` table via `write_audit(...)`, for
  reconstructing what happened. When a business write and its audit belong together they
  **share one transaction** (`session=`), so a trade and its `TRADE_CREATED` row commit
  atomically — one commit, one `fsync`, no possibility of one without the other.

The System Overview "Errors & Warnings" panel reads these back through monitoring's
`GET /audits`, which is backed by a **partial index** on `audit_logs(created_at)`
`WHERE severity IN ('WARNING','ERROR','CRITICAL')`. Partial because the high-volume
`TRADE_CREATED`/`TRADE_CLOSED` rows (~5/s under the generator) never enter it, so the index
stays tiny while serving the only query that matters.

A lighter alternative — emit audits as log lines and have a forwarder batch-insert them —
would take the audit write off the business path and batch its commits, but it can lose
events (a container dying before the forwarder reads the line) and gives up atomicity with
the business change. Not worth it here, where correctness matters more than volume.

### A benchmark that means something

`MARKET_INDEX` is an equal-weighted basket of the risky spot instruments (ACME, XAUUSD,
ES_FUT), rebased to a fixed reference level, so its moves are connected to instruments you
can actually see on screen. FX and rates are excluded because their return dynamics are not
comparable. It is deliberately not part of the tradeable `AssetClass` enum, and it does not
appear in the instrument table.

The simulator uses one readable per-tick volatility per asset, then applies real tick sizes
and two-sided spreads, with gentle mean reversion so a long demo does not drift somewhere
implausible. Curve level, slope and small per-tenor moves all derive from one
curve-volatility value, so the curve moves coherently without a large tuning surface.

### Scenario shocks reuse the pricing engine

`POST /scenario` re-prices one ad-hoc position under a market shock and returns base vs
scenario. Nothing is created and nothing is persisted, but it runs through the *same*
valuation code as live pricing, so a shock P&L matches what the position would really book.

Percentage shocks apply to spot/forward; bond shocks are basis points bumped across every
tenor of the `USD_GOV` curve and re-PV'd, so the P&L isolates the rate move.
`scenario_pnl = scenario value − base value`, side-aware. See
`scenarios/scenario-analysis.http`.

---

## Cost and scale

Everything is sized for a demo: ten instruments, ~3 market events/s, a handful of open
trades. This section records what the costs actually are and which one breaks first, so the
answer is measured rather than guessed later.

### The live market screen

N = instruments on screen, H = history points each (capped at 100). The UI re-renders at
most **2.7×/s** — a 600 ms flush plus a 1 s freshness clock — and each render walks this
chain. Measured in Chrome:

| Work | Grows as | N = 10 (today) | N = 1,000 |
|---|---|---|---|
| Trend-line geometry | O(N·H) | 0.17 ms | 12.4 ms |
| Trend-line DOM (only rows that ticked) | O(N·H) | 0.32 ms | 24.5 ms |
| Row derivation (deltas, freshness) | O(N) | 0.02 ms | 1.1 ms |
| Sort | O(N) in practice | 0.005 ms | 0.25 ms |
| Persist to `sessionStorage` | O(N·H) | ~10 kB | ~1 MB |

Today the whole chain runs in **under a millisecond against a 16.7 ms frame budget**. The
render rate is bounded by the flush timer, not by the work — nothing here is optimised, and
nothing needs to be.

Two results worth keeping:

- **Sorting is O(N log N) on paper and O(N) in practice.** Comparison values are captured
  when you click a header rather than read live, so on every later render the array is
  already in order and V8's TimSort exits after one linear scan — 999 comparisons for 1,000
  rows, not 9,966. Sorting live values would lose that *and* make rows jump under the
  cursor.
- **Drawing costs ~150× more than sorting.** If this table ever feels slow it will be the
  DOM, never the algorithms.

### If it had to scale

In order of payoff:

1. **Virtualize the table.** Only ~30 rows fit on a screen; render only those and N stops
   mattering — it fixes node count, string churn, DOM rebuilds and paint at once.
2. **Drop the update counter from the React row key** so a ticking row is patched instead of
   remounted, and flash one cell rather than the whole row.
3. **Animate `opacity` instead of `background`** so the flash composites rather than
   repaints.
4. **Downsample history for display** if `HISTORY_LENGTH` grows — a 96 px sparkline cannot
   show more than ~96 points, so beyond that the work is invisible.

### Bounds on the backend

| Bound | Value | At the limit |
|---|---|---|
| SSE queue per client | 500 events | event dropped and logged; memory stays bounded |
| Browser feed buffer | latest value per instrument | intermediate ticks coalesced, never queued |
| Blotter live cache | ACTIVE trades only | closed trades evicted on close |
| trade-action worker | one thread | writes serialise; intake stays fast because the queue absorbs bursts |

None of these is a throughput optimisation — each exists to stop something growing without
limit. A real feed would need measured queue sizing, server-side subscriptions and durable
replay before any of them counted as production numbers.

---

## Known limitations

- The trade-action queue is in-process and **non-durable** — in-flight intents are lost on
  restart. Idempotency makes a re-send safe.
- trade-generation tracks open trade ids **in memory**, so after a restart it can only close
  trades it opened in the new run.
- Blotter live caches are empty for a moment after restart until valuations stream in;
  `bootstrap_trades()` warms the active set from the DB to shrink that window.
- Per-asset PnL is brought *closer* by notional-sized quantities, not made equal — one
  futures contract is the smallest step, so some spread remains.
- The market screen reconciles current state; it is **not** an audit trail. Samples are lost
  on disconnect and coalesced during bursts. A tick tape would need durable replay.
- Producer/consumer stream audits are not yet failure-isolated, so those loops are not a
  production-resilience template.
