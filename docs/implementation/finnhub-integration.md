# Finnhub integration — the first real quote path

This guide follows Finnhub quotes end to end: client → scheduler →
database → SSE stream → pricing → the screen. The point of doing one provider *deep*
instead of three providers shallow: everything written here — client shape, error handling,
budget, polling tiers — is written once, in shared modules with per-provider hooks, so the
shape exists exactly once no matter how many providers plug into it (one shape for every
provider is a house rule, plan D24).

Start with the vocabulary and whole-path sections, then use the numbered implementation areas
for deeper study. Each area states the problem, mechanism, design reason and operational
boundary. The final sections contain repeatable verification and the current integration
boundaries.

## Core vocabulary

The provider domain defines empty market tables and normalized contracts. Finnhub is the
first transport that fills them. The terms:

- **The normalized quote** — the single shape every provider payload is converted into
  before anything stores or reads it. Fields: `bid`, `ask`, `last` exactly as the provider
  gave them (missing stays NULL — a spread is never invented); `mid`, derived from those;
  `price_basis`, saying which fields produced mid (`BID_ASK`, `LAST`, or an official
  `REFERENCE_MID`); `quote_grade`, saying what kind of price this is (`REALTIME` live
  tradable, `EOD` a daily close, `REFERENCE` an official fixing); and **two clocks** —
  `provider_timestamp` (the provider's own event time, e.g. when the trade printed) and
  `received_at` (when our system ingested it).
- **The board** — table `market_data_spot_prices`: the *latest* quote per
  (provider, symbol), one row per pair, overwritten in place on every poll. It is what the
  UI, the ticket, and pricing read. Current price only — no history, no raw payloads.
- **History** — table `market_data_snapshots`: one row appended each time a price actually
  *changes*, carrying the provider's raw JSON payload. This is the audit store. The
  `trades` table already carries an `entry_snapshot_id` column — a foreign key meant to
  point at the exact history row a trade was priced from. Nothing fills that column yet,
  and the retention sweep already honors it: it never deletes a
  referenced row. A trade's link back to raw provider bytes is what "provenance" means
  below.
- **Freshness** — a quote's state given its age: `LIVE` (younger than its threshold),
  `STALE` (older), `MISSING` (should exist, nothing arrived), `UNSUPPORTED` (this provider
  cannot serve this asset class at all). The thresholds depend on the feed cadence:
  threshold = 3× the symbol's polling cadence.
- **The watchlist** — table `watchlist_items`: the user-curated list of symbols the system
  cares about, and the replacement for the old hardcoded instrument catalog. What is not
  watched is not tradeable. The **benchmark** rides along: `BENCHMARK_SYMBOL` (SPY — an
  ETF that tracks the S&P 500) is always polled because pricing samples its returns to
  compute each book's alpha/beta.
- **The snapshot and the stream** — how the browser gets data. One `GET /snapshot` fetch
  at connect delivers the whole board at once; then a long-lived `/stream` connection
  delivers a `market_tick` event after every successful poll. The stream is SSE —
  server-sent events, a one-way HTTP response that never ends and that the service keeps
  writing lines into. The ordering fields on each event are Step 5's subject.
- **The audit trail** — table `audit_logs`: the business record. Services write a row for
  notable events (a trade created, a provider failing); the UI's log panels read it.
  Step 4.5 adds provider events to it.

Full reference with the provider fact sheets: [market-data.md](../market-data.md).

## The whole path — what happens, in which order

The numbered sections each describe one component. This section is the connected story
those components add up to — three sequences, each stage pointing at the step that explains
it in depth.

### One quote's journey (the steady state)

1. **AAPL is in the active set.** A watchlist row for AAPL (or an open AAPL trade) exists
   in the database; the feed reloads that list every 15 s and assigns AAPL a tier. The
   tier decides how often it is polled. *(Step 4.2)*
2. **The heartbeat finds it due.** Once per second the Finnhub feed thread wakes; AAPL's
   own "poll me again at" time has passed, so it is collected, tier-1 symbols first.
   *(Step 4.3)*
3. **One budget token is spent.** The token bucket has one of its 48-per-minute tokens
   available and gives it up. If the bucket were empty, nothing fails — AAPL stays due and
   next second's pass retries. *(Step 2)*
4. **The client calls Finnhub.** `GET /quote` for AAPL, key merged in at the last moment,
   10 s timeout, one retry. A failure here would become a typed provider error and the
   condition machine would pause the feed and write an audit row. *(Steps 1, 4.4 and 4.5)*
5. **The payload becomes a normalized quote.** `{c: 310.03, t: 1787083200}` → a last-only
   quote, basis `LAST`, grade `REALTIME`, `provider_timestamp` from `t` — the provider's
   clock, not ours. *(Step 1)*
6. **The database is written, in one transaction.** The board row (FINNHUB, AAPL) is
   updated in place; a history row is appended only if the price differs from the last
   one. *(Step 3)*
7. **A tick goes out on the stream.** The full quote plus `stale_after_seconds`, tagged
   with stream and event ids so every consumer can keep events in order. *(Step 5)*
8. **Pricing revalues.** Pricing looks up `spots[(FINNHUB, "AAPL")]`, revalues every trade
   bound to that provider and symbol, and writes a valuation row stamped with the provider
   and the provider's quote time. Were this the benchmark pair (FINNHUB, SPY), it would
   also sample the return for alpha/beta. *(Step 6)*
9. **The screens update.** The board rerenders the row — Age counting from the provider's
   clock — and the blotter carries the new valuation into Trades, Books, and Valuations.
   *(Step 7)*
10. **The symbol is rescheduled.** Next poll time = now + cadence: 15 s (tier 1) or 60 s
    (tier 2) while the market is open, 300 s for everyone while it is closed. *(Steps 4.3
    and 4.4)*

### When the stack restarts

1. Postgres and migrations come up first; each service boots and starts its background
   threads.
2. market-data serves `/snapshot` straight from the board *table* — the full board is
   available to every consumer before the first Finnhub call even completes. *(Step 3)*
3. pricing seeds its quote cache from that snapshot, then attaches to the stream — the
   same seed-then-follow order the browser uses — so trades revalue within seconds of a
   restart instead of waiting for fresh polls. *(Step 3)*

### When a trade is opened

1. The ticket submits; trade-action validates the symbol against the watchlist and writes
   the trade row. The row itself is the handoff — no service calls another.
2. Within 2 s, pricing's refresh loop notices the new ACTIVE trade and values it
   immediately off the already-cached quote — no waiting for the next poll. *(Step 6)*
3. Within 5 s, the blotter's reconcile (or the valuation stream, whichever is first) makes
   the trade visible in Trades/Books/Valuations. *(Step 6)*
4. Within 15 s, the feed's active-set reload promotes the symbol to tier 1: polls tighten
   to 15 s, the staleness threshold from 180 s to 45 s. *(Step 4.2; watched live in
   Step 8)*

## Integration decisions

These rules form the Finnhub policy layer; each includes its reason and the section where
the mechanics live. The README's "Operating decisions" table summarizes the
business-facing subset.

1. **Poll only the active set** — watchlist + open-trade symbols + benchmark, nothing
   else. Free budgets cannot poll "the market"; scope is the user's decision. *(4.2)*
2. **Two tiers: 15 s where money is at stake** (open trades + benchmark), **60 s
   watched-only.** Budget flows to open positions and the alpha/beta input first. *(4.2)*
3. **A confirmed-closed market slows everyone to 300 s; an unknown status never slows
   polling.** The last trade cannot move overnight. *(4.4)*
4. **Freshness threshold = 3× the open-market cadence (45 s / 180 s) and never stretches
   at night.** Age stays honest — which is why overnight rows read STALE. *(4.4)*
5. **Budget = 80% of the provider's limit (48 of 60/min), and every call spends a token**
   — quotes, the status check, manual refreshes. The margin keeps the provider's own
   limiter untriggered. *(Step 2)*
6. **An empty budget is not a pause** — the round ends, symbols stay due, next second
   retries. Only provider answers pause the feed: 429 → `Retry-After` else 60 s; bad
   key → 5 min; network → 10 s. *(4.3, 4.5)*
7. **Audits on transitions only, and a bad symbol never pauses the feed.** One event, one
   row; one ticker cannot quarantine the rest. *(4.5)*
8. **The board overwrites; history appends only on a price change, carrying the raw
   payload.** Cheap current reads, noise-free audit trail. *(Step 3)*
9. **Retention: 90 days, except rows a trade references.** Provenance outlives
   housekeeping; 90 days balances chart depth and hosted database storage. *(Step 3)*
10. **A database row is the registration** — a watchlist insert or a new trade joins
    polling within ≤15 s, and a manual refresh forces it immediately. *(4.2, 4.6)*
11. **Money math reads exactly one provider's quote** — trades resolve to
    `DEFAULT_QUOTE_PROVIDER` (FINNHUB) until execution records a provider; benchmark
    sampling is locked to (FINNHUB, SPY). *(Step 6)*

## Step 1 — the provider client layer

**Needed:** six providers, six different ways to fail. Finnhub uses proper HTTP status
codes; Twelve Data and Alpha Vantage return `200 OK` with an error hidden in the body. The
scheduler must treat "rate limited" as one concept with one reaction, no matter which
provider said it and how. So: one base class owns transport and error classification; each
provider client adds only its endpoints and its own body rules.

- **`clients/base.py` is the whole transport contract.** The core, verbatim:

  ```python
  class ProviderError(Exception):
      def __init__(self, provider, detail):
          super().__init__(f"{provider}: {detail}")
          self.provider = provider
          self.detail = detail

  class ProviderAuthError(ProviderError): ...
  class ProviderRateLimited(ProviderError): ...   # carries retry_after_seconds
  class ProviderUnavailable(ProviderError): ...   # network/timeout after one retry
  class ProviderDataError(ProviderError): ...     # body-level: "no such symbol", error JSON

  class ProviderClient:
      provider = None
      base_url = None

      def auth_params(self): return {}
      def classify_body(self, payload): pass

      def get(self, path, params=None):
          query = urllib.parse.urlencode({**(params or {}), **self.auth_params()})
          body = self._fetch(f"{self.base_url}{path}?{query}")
          payload = json.loads(body)          # not JSON → ProviderDataError
          self.classify_body(payload)
          return payload
  ```

- **The exception hierarchy IS the error classification.** Callers never inspect strings or
  status codes — they catch a type: `except ProviderRateLimited`. Each exception carries
  its facts as fields, like a C# exception subclass with extra properties set in the
  constructor; `super().__init__(...)` sets the message tracebacks print.
- **`_fetch` (not shown) turns HTTP outcomes into those exception types.** 10 s timeout,
  one retry on network failure, then: 401/403 → `ProviderAuthError`, 429 →
  `ProviderRateLimited` with the `Retry-After` header parsed, other non-2xx →
  `ProviderError`.
- **A concrete client only fills in the blanks.** `FinnhubClient` is 20 lines:
  `auth_params` returns `{"token": key}`, `quote()` and `market_status()` name endpoints,
  `classify_body` raises on an `{"error": …}` body.
  - This is the Template Method pattern: the base class runs the algorithm (merge params →
    fetch → parse → classify) and subclasses override the named hooks. C# shape: an
    abstract base whose public method calls `virtual`/`abstract` members. Python needs no
    `abstract` keyword — a subclass that forgets `base_url` fails loudly on first use.
- **`classify_body` is nearly empty for Finnhub — and the hook is still load-bearing.**
  Finnhub reports failure through real status codes, so its body rule is one line. The
  hook exists because two of the registered providers do not: the probes showed Twelve
  Data answering `200 OK` with `{"code": 429}` in the body, and Alpha Vantage answering
  `200 OK` with an `"Information"` key. Each client owns its own few-line body rule; the
  base class's algorithm never changes.
  - Idiom note: `{**(params or {}), **self.auth_params()}` unpacks two dicts into a new
    one; later keys win. C# equivalent: `new Dictionary<string, string>(a)` followed by
    indexer assignments from `b`, in one expression. The API key merges in at the last
    moment, inside the client — it never appears in a log line.
- **The normalizer turns a Finnhub payload into a normalized quote.** Finnhub's `/quote`
  returns `{c, t, …}` — current price and a unix-seconds trade time. `normalize_finnhub_quote`
  rejects empty answers (`c: 0` is Finnhub's "unknown symbol") and builds the quote with
  `last` only — Finnhub gives no bid/ask, so `bid`/`ask` stay NULL rather than a made-up
  spread, basis `LAST`, grade `REALTIME`. The `t` field becomes `provider_timestamp` via
  `datetime.fromtimestamp(t, tz=timezone.utc)`: the *provider's* clock, the actual last
  trade, not our receive time.

## Step 2 — the request budget

**Needed:** Finnhub's free tier allows 60 requests per minute. House rule: never run at the
limit — run at ~80%, so scheduled polls plus manual refreshes can never trip the provider's
own limiter and get the key blocked (plan D7). The standard tool for "at most N per minute,
spent one at a time" is a token bucket.

- **`budget.py`, the bucket in full:**

  ```python
  class TokenBucket:
      def __init__(self, capacity, refill_per_second):
          self.capacity = capacity
          self.refill_per_second = refill_per_second
          self._tokens = float(capacity)
          self._refilled_at = time.monotonic()
          self._lock = threading.Lock()

      def _refill(self):
          now = time.monotonic()
          self._tokens = min(self.capacity,
                             self._tokens + (now - self._refilled_at) * self.refill_per_second)
          self._refilled_at = now

      def try_take(self):
          with self._lock:
              self._refill()
              if self._tokens < 1:
                  return False
              self._tokens -= 1
              return True
  ```

- **There is no timer thread.** The bucket refills lazily: on every call it computes
  elapsed-time × rate and caps at capacity. `try_take` never blocks — on `False` the
  scheduler just stops the round; symbols stay due and the next pass retries. One bucket is
  shared by the scheduler thread and HTTP refresh handlers, hence the lock.
- **Every request spends one token** — quotes, the market-status check, manual refreshes.
  Capacity 48 = 80% of 60, refilling at 48/60 per second (`FINNHUB_BUDGET_PER_MINUTE`).
  - Why `time.monotonic()` and not `datetime.now()`: monotonic time is a stopwatch — it
    only moves forward, immune to NTP corrections and DST. A wall clock can jump backwards,
    which would make `now - refilled_at` negative and *drain* the bucket. C# analogy:
    `Stopwatch` for intervals, `DateTime.UtcNow` for timestamps. House rule from this
    integration: budget and cooldown math use monotonic time; stored and displayed timestamps use `utcnow()`.
- **`DailyLedger` counts requests per UTC day.** For Finnhub — limited per minute, not per
  day — the count is display only: the ops endpoints report it as `requests_today`. It
  lives in the shared budget module because two registered providers are constrained per
  *day* (Twelve Data 800/day, Alpha Vantage 25/day — probed facts), and a per-day request
  count is the fact any daily budget rule has to start from.

## Step 3 — storing quotes: board upsert, change-only history, retention

**Needed:** the provider domain defines the board and history tables; this component makes
them behave according to that contract. Three
behaviors, and the why of each:

- The **board** must stay one row per (provider, symbol) no matter how often we poll —
  update in place, never append — so the "current market" read is always one cheap query
  and the table cannot grow.
- **History** must grow only when a price actually *changes*. Why: polling continues while
  the market is closed, and appending an identical price every 5 minutes all night would be
  storage noise. Change-only means a closed market writes approximately nothing.
- **Retention**: history older than `SNAPSHOT_RETENTION_DAYS` (90; 30 at first ship) is
  deleted daily —
  *except* rows a trade points at. Why: a trade's link to the raw payload it was priced
  from is its audit trail; routine housekeeping must never amputate it.

- **`store_quote` does board + history in one transaction:**

  ```python
  def store_quote(quote):
      """Board upsert plus change-only history append; returns True when the price moved."""
      with session_scope() as session:
          row = (session.query(MarketDataSpotPrice)
                 .filter_by(provider=quote.provider, symbol=quote.symbol)
                 .with_for_update().one_or_none())
          changed = row is None or any(
              getattr(row, field) != getattr(quote, field) for field in PRICE_FIELDS)
          now = utcnow()
          if row is None:
              row = MarketDataSpotPrice(market_data_id=uuid.uuid4(), provider=quote.provider,
                                        symbol=quote.symbol, created_at=now)
              session.add(row)
          for field in QUOTE_FIELDS:
              setattr(row, field, getattr(quote, field))
          if changed:
              session.add(MarketDataSnapshot(snapshot_id=uuid.uuid4(), created_at=now,
                                             raw_payload=quote.raw_payload,
                                             **{f: getattr(quote, f) for f in QUOTE_FIELDS}))
          return changed
  ```

  ("Upsert" = update the row if it exists, insert it if not.)
- **`with_for_update()` makes concurrent writers safe.** It emits `SELECT … FOR UPDATE` — a
  row lock held until commit. If the scheduler and a manual refresh hit the same symbol in
  the same instant, the second waits, re-reads the committed row, and updates instead of
  double-inserting. The unique constraint stays as the backstop.
- **"Changed" compares prices only** (bid/ask/last/mid). A poll that re-confirms the same
  price still updates the board's `received_at` — freshness stays honest — but appends no
  history row.
  - Decimal nuance that makes this correct: `Decimal("310.03") == Decimal("310.030")` is
    `True`. Decimal compares numeric value, not printed form, so a formatting difference
    can never masquerade as a price move.
  - The `getattr`/`setattr` loops walk one shared tuple of field names, which keeps board
    and history column-identical by construction (history adds only `raw_payload`).
    `**{…}` then unpacks that dict into the constructor as keyword arguments.
- **The retention sweep runs daily in the service** and implements the skip as a
  `NOT IN (subquery of snapshot ids referenced by trades)` filter. First run logged
  `snapshot_retention_swept deleted=0` — the honest no-op on a young database.
- **`/snapshot` reads the database, so restarts are warm for free.** The earlier service
  kept quotes in an in-process dict that died with the process. The board table
  *is* the state now: a restarted service serves its full board before the first poll
  completes, and the UI's existing seed logic needed no change.

## Step 4 — the scheduler

**Needed:** something must decide which symbols to poll, at what pace, without exceeding
the budget — and react sanely when Finnhub fails. Those responsibilities live in four small
files rather than one scheduler module. The subsections: 4.1 the layout, 4.2 the symbol universe, 4.3 and
4.4 walk `finnhub_feed.py` function by function — what happens where, exactly — 4.5 the
condition machine it calls into, 4.6 the on-demand refresh, 4.7 the whole thing in one
breath.

### 4.1 — how the code is organized

| File | Job | Lines |
| --- | --- | --- |
| `active_set.py` | answers *which symbols do we care about right now?* | 38 |
| `provider_runtime.py` | one class holding a provider's live condition: status, pause timer, budget, market session | 131 |
| `finnhub_feed.py` | everything Finnhub-specific: the polling loop, cadences, what its errors mean | 204 |
| `scheduler.py` | the registry: which feeds are wired, and the functions the HTTP API calls | 38 |

Why this shape: adding a provider must not mean editing inside Finnhub's logic. Providers
poll differently — Finnhub one symbol at a time against a per-minute limit; Twelve Data
(probed) can batch many symbols into one call against a daily allowance — so the *loop*
belongs to each feed file. What is identical for every provider (the symbol universe, the
condition/budget machinery) is shared. A new provider is one new feed file plus one line
in the registry; no existing file changes.

### 4.2 — which symbols to poll (`active_set.py`)

The rule, in plain words: poll every watchlist symbol, plus every symbol that has an open
trade, plus the benchmark SPY — nothing else (plan D4). Polling "the whole market" is
impossible on free budgets, so scope is the user's decision, expressed through the
watchlist.

Each symbol gets a priority tier (plan D7):

- **Tier 1, polled every 15 s** — symbols with open trades, and the benchmark. This is
  where money is at stake: open positions need fresh marks, and SPY feeds the alpha/beta
  calculation.
- **Tier 2, polled every 60 s** — watchlist symbols nobody holds. A minute of lag costs
  nothing there, and the saved budget goes to tier 1.

How the list stays current: the feed reloads it from the database every 15 seconds. There
is no "register a symbol" call anywhere — inserting a watchlist row or opening a trade
*is* the registration (the repo's "database row is the handoff" rule). You can watch the
consequence: open a trade, and within one reload its symbol jumps from tier 2 to tier 1 —
Step 8 caught exactly that live, the staleness threshold tightening from 180 s to 45 s.

The function, verbatim:

```python
def load_active_set():
    with session_scope() as session:
        watched = [
            (item.symbol, item.asset_class, item.currency)
            for item in watchlist_items(session)
        ]
        open_rows = (
            session.query(Trade.symbol, Trade.asset_class, Trade.trade_currency)
            .filter(Trade.status == "ACTIVE")
            .distinct()
            .all()
        )
    entries = {
        symbol: ActiveSymbol(symbol, asset_class, currency, 1)
        for symbol, asset_class, currency in open_rows
    }
    open_symbols = set(entries)
    for symbol, asset_class, currency in watched:
        tier = 1 if symbol in open_symbols or symbol == BENCHMARK_SYMBOL else 2
        entries[symbol] = ActiveSymbol(symbol, asset_class, currency, tier)
    entries.setdefault(BENCHMARK_SYMBOL, ActiveSymbol(BENCHMARK_SYMBOL, "EQUITY", "USD", 1))
    return entries
```

Reading it top to bottom: query the watchlist and the open trades inside one session;
start from the open trades (tier 1 by definition); overlay the watchlist rows, deciding
each one's tier; finally make sure the benchmark is present even if nobody watches it.
The result is a plain dictionary of frozen `ActiveSymbol` records — symbol, asset class,
currency, tier.

A consequence worth saying out loud: **tier changes are rebuilds, not transitions.**
No stored tier is ever mutated — every reload recomputes the whole set from the database
and swaps it in, so "promotion" is just the next rebuild seeing an open trade that the
last one did not. The new tier's effects then arrive at three moments: poll *ordering*
changes on the very next round; the *staleness threshold* tightens at the rebuild itself
(180 s → 45 s, the jump Step 8 caught live); the *cadence* changes at that symbol's next
poll, because the reload never rewrites `_next_due` — one leftover old-cadence interval,
then the new pace.

- **Deep-dive: why the function extracts plain values inside the session.** House
  convention (AGENTS.md): read what you need *inside* the `with session_scope():` block
  and return plain values — tuples, strings — never ORM objects. The mechanism that
  forces it: `session_scope` commits and closes the session when the block ends, and on
  commit SQLAlchemy *expires* every object the session manages — attribute values are
  wiped, to be re-read fresh from the database on next access. Touching an attribute
  after the block therefore triggers a database re-read through a session that no longer
  exists, and SQLAlchemy raises `DetachedInstanceError`. C# analogy: reading a
  lazy-loaded navigation property on an EF Core entity after its `DbContext` is disposed
  — an entity detached from its unit of work.

  That is why the watchlist branch copies `(item.symbol, item.asset_class, item.currency)`
  out per row, while the open-trade query below it needs no copying: it selects *columns*
  (`Trade.symbol, …`), and column queries already return plain tuples — copies of values,
  owned by nobody. Only whole-entity queries return session-managed objects. (The
  alternative, `expire_on_commit=False`, was rejected: it hides the session boundary
  everywhere and invites stale reads instead.)

### 4.3 — the loop itself (`poll_loop`)

The loop is where the client, budget, persistence and publisher become a running system. Those
built a component that, alone, does nothing — nobody calls the client, nobody spends the
budget, nothing writes or publishes. `poll_loop` is the one thread where they all meet,
and this subsection walks it line by line.

First, the state it works with — the whole of the module's memory, four names at the top
of the file:

```python
PROVIDER = FINNHUB
runtime = ProviderRuntime(FINNHUB, FINNHUB_BUDGET_PER_MINUTE, bool(FINNHUB_API_KEY))
_client = FinnhubClient(FINNHUB_API_KEY)
_next_due = {}
```

- `runtime` — the provider's live condition object (4.5's subject): status, cooldown
  timer, Step 2's budget, the market session, the current active set. Everything else in
  the file reads and writes through it. The third argument makes a missing API key mean
  status `DISABLED` from birth.
- `_client` — one instance of Step 1's HTTP client.
- `_next_due` — a plain dict, symbol → the `time.monotonic()` moment its next poll is
  allowed. This dict **is** the schedule; there is no timer object anywhere. The leading
  underscore is Python's module-private convention (C#: `internal`).

The loop, verbatim:

```python
def poll_loop():
    if not FINNHUB_API_KEY:
        log.warning("finnhub_disabled", reason="FINNHUB_API_KEY is not set")
        return
    last_set_refresh = 0.0
    last_status_refresh = 0.0
    while True:
        now = time.monotonic()
        # paused by a cooldown: wait, poll nothing
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        # reload which symbols to poll: watchlist + open trades + benchmark
        if not last_set_refresh or now - last_set_refresh >= ACTIVE_SET_REFRESH_SECONDS:
            try:
                runtime.set_active(load_active_set())
            except Exception:
                log.exception("active_set_load_failed")
                time.sleep(5)
                continue
            last_set_refresh = now
        # re-check whether the US market is open
        if not last_status_refresh or now - last_status_refresh >= MARKET_STATUS_REFRESH_SECONDS:
            _refresh_market_status()
            last_status_refresh = now
        # collect due symbols Finnhub can serve, tier 1 first
        pollable = [
            entry for entry in runtime.active_entries()
            if supports_quotes(FINNHUB, entry.asset_class)
        ]
        due = sorted(
            (entry for entry in pollable
             if _next_due.get(entry.symbol, 0) <= time.monotonic()),
            key=lambda entry: (entry.tier, entry.symbol),
        )
        # poll while budget lasts: an empty bucket ends the round, symbols stay due
        for entry in due:
            if runtime.cooldown_seconds_left() > 0 or not runtime.try_take():
                break
            _guarded_fetch(entry)
            _next_due[entry.symbol] = time.monotonic() + _cadence_seconds(entry.tier)
        # forget symbols that left the active set
        _prune_next_due(pollable)
        time.sleep(1)
```

Reading it top to bottom — what happens where:

1. **The no-key guard** (first three lines): without `FINNHUB_API_KEY` the function logs
   one warning and returns, so the thread ends before the loop starts. `runtime` was
   already built with wired = `False`, so `/providers` reports `DISABLED` — nothing else
   in the service needs a special case.
2. **`while True` … `time.sleep(1)`** at the bottom is the heartbeat: everything between
   runs at most once per second.
3. **The cooldown gate runs before anything else.** While a pause from 4.5 is active, the
   loop sleeps and `continue`s — no polls, no housekeeping. It sleeps in slices of at most
   5 s rather than the whole pause at once, so the thread re-checks the world every few
   seconds instead of oversleeping a 5-minute pause in one block.
4. **The active-set reload, every 15 s** (`ACTIVE_SET_REFRESH_SECONDS`): calls 4.2's
   `load_active_set()` and hands the result to `runtime.set_active(...)`. This is the
   line that connects a database write — a watchlist insert, a new trade — to polling,
   with no registration call anywhere. The `try/except` around it matters: this is the
   loop's only database read, and an unhandled exception would kill the thread — a dead
   background thread stops the feed *silently*. So a database hiccup logs
   `active_set_load_failed`, waits 5 s, and the loop survives.
5. **The market-status check, every 10 min** (`MARKET_STATUS_REFRESH_SECONDS`): calls
   `_refresh_market_status()` (4.4). `last_status_refresh` advances whether or not the
   check succeeded — a failed check is simply retried 10 minutes later, and the old
   answer stands in the meantime.
6. **`pollable`** filters the active set through `supports_quotes(FINNHUB, asset_class)`
   — the shared capability matrix, consulted every cycle. A watchlist FX row would be
   dropped right here: Finnhub cannot serve it, so no token is ever wasted asking.
7. **`due`** keeps the pollable symbols whose `_next_due` moment has passed — a symbol
   never polled defaults to `0`, i.e. due immediately — sorted by
   `(entry.tier, entry.symbol)`: tier 1 strictly first, alphabetical inside a tier so the
   order is deterministic run to run.
8. **The polling `for` loop re-checks two gates per symbol, and `break`s — not skips —
   when either fails.** `cooldown_seconds_left() > 0`: a 429 *inside this very round*
   just paused the provider, so the round must stop instantly. `not runtime.try_take()`:
   Step 2's bucket is empty — and if there is no token for this symbol there is none for
   the rest either. Either way the unfetched symbols simply stay due; the next heartbeat
   retries.
9. **`_guarded_fetch(entry)` is the poll itself** — the pipeline and its failure
   handling, walked in 4.4.
10. **The reschedule is unconditional**: `_next_due[symbol] = now + _cadence_seconds(tier)`
    runs whether the fetch succeeded or failed. Deliberate: a symbol that failed at the
    data level (an unknown ticker) waits its full cadence instead of being retried every
    second, while provider-level failures are already handled by the cooldown gate above.
11. **`_prune_next_due(pollable)`** deletes schedule entries for symbols that left the
    active set — a removed watchlist row or a closed trade would otherwise leave its
    timer in the dict forever.

Why a heartbeat and not a thread per symbol: 25 symbols would mean 25 threads competing
for one shared budget; a single loop per provider makes every spend decision in one
place. The registry starts one such thread per wired feed — today, one.

### 4.4 — one poll, from token to tick

The happy path is `_fetch_and_publish` — six calls, each delegated to one component:

```python
def _fetch_and_publish(entry):
    runtime.record_request()
    payload = _client.quote(entry.symbol)
    quote = normalize_finnhub_quote(
        entry.symbol, entry.asset_class, entry.currency, payload, utcnow()
    )
    persistence.store_quote(quote)
    tick = _wire_quote(quote)
    publish_quote(tick)
    runtime.record_success()
    return tick
```

Line by line: `record_request` counts the call in Step 2's daily ledger (the budget token
was already taken by the caller); `_client.quote` is Step 1's HTTP GET; `normalize_finnhub_quote`
is Step 1's normalizer — payload in, normalized quote out, or `ProviderDataError` on an
empty answer; `store_quote` is Step 3's board-plus-history transaction; `_wire_quote`
flattens the quote object into the plain dict that actually travels, adding `event_time`
and the symbol's `stale_after_seconds`; `publish_quote` is Step 5's SSE publish, from
which pricing (Step 6) and the browser (Step 7) take over; `record_success` flips the
runtime back to `OK` — and writes the `PROVIDER_RECOVERED` audit if it was degraded.

`_guarded_fetch` wraps it, and is the **only** place where exceptions become provider
state. Verbatim:

```python
def _guarded_fetch(entry):
    try:
        return _fetch_and_publish(entry), None
    except ProviderRateLimited as error:
        cooldown = error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
        runtime.enter_cooldown(
            "RATE_LIMITED", "rate limited", error.detail, cooldown,
            "PROVIDER_RATE_LIMITED", "WARNING",
        )
        return None, "FINNHUB is rate limited"
    except ProviderAuthError as error:
        runtime.enter_cooldown(
            "AUTH_FAILED", "authentication failed", error.detail,
            AUTH_FAILURE_COOLDOWN_SECONDS, "PROVIDER_AUTH_FAILED", "ERROR",
        )
        return None, "FINNHUB rejected the API key"
    except ProviderDataError as error:
        log.warning("quote_unavailable", provider=FINNHUB, symbol=entry.symbol,
                    detail=error.detail)
        return None, error.detail
    except ProviderError as error:
        runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
        return None, error.detail
```

- **It returns a `(tick, error)` pair, never an exception** — callers (the loop, the
  refresh endpoint) get data or a human-readable sentence. C# shape: a try/catch ladder
  that returns a result object instead of rethrowing.
- **The arm order is Step 1's hierarchy made concrete**: each `except` names one exception
  type, most specific first; the final `except ProviderError` is the catch-all that also
  receives `ProviderUnavailable` (a subclass — network failure, 5xx). Same rule as C#
  catch clauses: most-derived first, or the base clause swallows everything.
- **Each arm names its 4.5 reaction**: 429 → `runtime.enter_cooldown("RATE_LIMITED", …)`
  honoring `Retry-After` (60 s default); 401/403 → `enter_cooldown("AUTH_FAILED", …)` for
  5 minutes; a data-level answer (unknown ticker, empty quote) → one per-symbol
  `log.warning` and **no** runtime call at all — the provider is fine, the symbol is not;
  anything else → `runtime.transient_error(…, 10 s)`.

Three helpers complete the file's fetch side:

- **`_cadence_seconds(tier)` — the closed-market decay lives here, and nowhere else.**
  `if runtime.market_open() is False: return 300`, else 15 s or 60 s by tier. The
  `is False` is deliberate: before the first status check `market_open()` returns `None`
  — *unknown* — and unknown must not slow polling, so only a confirmed "closed" decays.
  (Python nuance: `None` is falsy, so `not runtime.market_open()` would silently treat
  "don't know yet" as "closed". C#: a `bool?` checked with `marketOpen == false` —
  collapsing `null` into `false` is exactly the bug.) The why of the decay: the last
  trade cannot move overnight, so faster polling would only burn budget re-confirming a
  frozen number.
- **`stale_after_seconds(symbol)` — the freshness threshold, 3× the tier cadence.** It
  reads the tier's *open-market* cadence directly (15/60 s), not `_cadence_seconds` —
  which is precisely why the threshold does not stretch to 900 s at night. A quote whose
  last trade is three hours old reads STALE because it *is* three hours old; the calmer
  CLOSED display is a boundary listed at the end of this guide.
- **`_refresh_market_status()` — the status check pays like everyone else.** It calls
  `runtime.try_take()` and `record_request()` before `_client.market_status()`; if the
  bucket is empty it skips — no token, no call, housekeeping included. On success the
  answer lands in `runtime.set_market_status(isOpen, session)`; on failure it logs and
  the previous answer stands.

### 4.5 — when Finnhub says no (`provider_runtime.py`)

The `runtime` object created at the top of the feed file — one `ProviderRuntime` instance
per provider — is where every 4.4 arm lands. It carries one visible condition at all
times: `OK`, `RATE_LIMITED`, `AUTH_FAILED`, `ERROR`, or `DISABLED` (no API key
configured). Failures change the condition, pause polling, and write an audit row — a
  failure drill where a key dies should *show* what happened, not silently stop.

What each failure does, spelled out:

| Finnhub's answer | Condition | Pause | Audit |
| --- | --- | --- | --- |
| 429 — too many requests | `RATE_LIMITED` | what `Retry-After` asks, else 60 s | `PROVIDER_RATE_LIMITED`, WARNING |
| 401/403 — key rejected | `AUTH_FAILED` | 5 min (faster retries cannot help a bad key) | `PROVIDER_AUTH_FAILED`, ERROR |
| network failure / 5xx | `ERROR` | 10 s | log only — transient noise |
| next successful quote | `OK` | — | `PROVIDER_RECOVERED` |

The 429 row should never actually fire — the bucket runs at 80% of the allowance exactly
so we never hit the provider's own limiter. The state exists in case it happens anyway.

Two details keep the trail honest:

- Audits are written on *transitions* only — one row when a pause starts, not sixty rows
  during a 60-second pause. Where: `enter_cooldown` audits only when the status actually
  changes, and `record_success` writes `PROVIDER_RECOVERED` only when leaving a degraded
  status.
- A "no data for this symbol" answer (an unknown ticker) is **not** a provider failure. It
  is logged per symbol and never pauses the feed — one bad ticker must not quarantine
  24 good ones. Where: 4.4's `ProviderDataError` arm, the only arm that touches nothing.

The pause is observable while it runs: `/providers/FINNHUB/health` shows the condition and
`cooldown_seconds_left` counting down. That JSON is built by `runtime_snapshot()` at the
bottom of the feed file — `runtime.snapshot(...)` plus the sorted list of currently
pollable symbols — and it is what both ops endpoints serve.

### 4.6 — refresh on demand (`refresh_symbol`)

`POST /refresh?symbol=AAPL` lands in `refresh_symbol`, in the same feed file. It runs one
poll *now* through exactly the same path the loop uses — and before that, it walks a
guard ladder in this exact order, each rung answering with its own HTTP status:

1. No API key → **503**.
2. Symbol not in the active set → one forced `load_active_set()` reload first (the
   watchlist row may have been inserted seconds ago), then **404** if still absent.
3. Finnhub does not serve the symbol's asset class (`supports_quotes`) → **422**.
4. A cooldown is running → **503**, with the seconds left in the message.
5. `runtime.try_take()` fails — the bucket is momentarily empty → **429**.
6. Otherwise `_guarded_fetch(entry)` — the very function from 4.4. Success pushes the
   symbol's `_next_due` a full cadence out (the data is fresh; polling again sooner would
   waste a token) and returns **200** with the tick. A failure returns **429** if the
   runtime now says `RATE_LIMITED`, else **502**.

Nothing in the UI calls it yet — it is the ops lever, and Step 8 exercises every one of
its codes.

### 4.7 — the scheduler in one breath

The retellable version. One background thread per provider wakes every second. If the
provider is paused, it waits. Every 15 seconds it reloads its symbol list from the
database — so a new watchlist row or a fresh trade joins polling within 15 seconds at
worst, with no registration call; a manual refresh forces the reload and skips even that
wait. (A new *trade* never waits at all: its symbol is already watched and quoted, so
pricing values it within seconds off the cached quote — the 15 s only gates its promotion
to the fast tier.) Every 10 minutes the thread asks Finnhub whether the US market is
open. Then
it takes the symbols whose time has come, most important first, and for each one spends
one budget token and runs the same six-stage pipeline: HTTP call → normalize → store →
flatten → publish → mark healthy. Every symbol then waits its own cadence — 15 s with
money at stake, 60 s watched-only, 300 s for everyone when the market is closed. An
empty budget is not a pause: the round just ends, everyone stays due, and the next
second retries as tokens refill. Only the provider's own answers pause the feed — a
failure never throws out of the loop, it becomes provider state — a visible condition, a
pause, an audit row — and the next success clears it. The manual refresh endpoint is the
same pipeline behind a ladder of honest status codes.

## Step 5 — publishing: ticks the UI can trust

**Needed:** the browser merges two sources — one `/snapshot` fetch at connect, then the
live SSE stream — and it survives reconnects and service restarts by *ordering* events:
every tick carries a stream id (which process sent this), an event id (a counter within
that process), and an event time, and the client drops anything out of order. That
machinery is shared by every feed, so the publisher emits the same ordering fields with
provider-tagged payloads.

- **`publisher.py` mints the ordering:** a process-lifetime `stream_id` (UUID) plus a
  lock-guarded increasing `event_id` on every `market_tick`. A restart changes the stream
  id; the frontend detects the switch and resets per-row ordering — unchanged client code.
- **A tick is the full normalized quote** — every field from the vocabulary section, both
  clocks included — plus `stale_after_seconds` (3× the symbol's current cadence). Any
  consumer can classify LIVE/STALE locally, no follow-up requests.
- **Every successful poll publishes, even an unchanged price.** The stream answers "still
  fresh, still confirmed"; history answers "when did it actually change". Two questions,
  two write disciplines.

## Step 6 — pricing re-keyed to (provider, symbol)

**Needed:** money math must read exactly one provider's quote. A trade valued with Finnhub
prices must never move because a different provider quoted the same symbol — if sources
could mix inside a PnL number, nobody could say where that number came from (plan D13).
Two changes deliver that: the pricing cache learns which provider each quote came from,
and every valuation row records which quote it used.

- **The quote cache is now keyed by provider AND symbol** — `spots[(provider, symbol)]`, a
  tuple as a composite dictionary key. When a tick arrives, pricing reprices only the
  trades bound to that tick's provider. Two providers quoting the same symbol are two
  separate rows end to end — never averaged, never mixed.
- **Which provider is a trade bound to? Today: always FINNHUB.** The trade row has a
  `market_data_provider` column, but nothing writes it at execution yet — it is NULL on
  every trade. So pricing falls back to a constant: `DEFAULT_QUOTE_PROVIDER = FINNHUB` in
  pricing's config. The fallback is exact, not approximate, because Finnhub is the only
  wired provider — there is no other provider a trade could possibly mean.
- **Every valuation row records the quote it used**: `market_data_provider` and
  `market_data_timestamp` — the provider's own trade time, not our receive time (plan D2).
  Step 8 shows a real row: `FINNHUB / 2026-08-18 20:00:00+00`, the closing bell.
- **The alpha/beta input is locked to one quote stream.** Book alpha/beta is computed from
  SPY's price changes. If two providers both quoted SPY, pricing would see every price
  twice — once per provider, at slightly different values — and the return series would be
  garbage. So sampling accepts a tick only when it matches both `BENCHMARK_SYMBOL` and
  `BENCHMARK_PROVIDER`. With one wired provider the guard changes nothing today; it exists
  because the day a second provider quotes SPY, the double-sampling would begin silently,
  from the very first tick (deviation 2).
- **A scenario-analysis bug got fixed while touching this code.** Quotes travel over SSE
  as JSON, and exact decimal prices are serialized as *text strings*. The scenario tab
  applies a shock by multiplying prices — and the multiply skipped anything that was not a
  number. So the shocked price equaled the unshocked price, and every scenario PnL showed
  0.00 while presenting itself as a result. Fix: pricing parses bid/ask/last/mid to
  `Decimal` the moment a tick arrives, and the shock math works on Decimal. Converting at
  the stream boundary prevents scenario pricing from silently skipping numeric strings.

## Step 7 — the board UI: provider and age

**Needed:** each quote must expose its provider and its age measured from the provider's
clock. The board adds those columns without changing unrelated behavior.

- **Row identity became `PROVIDER:SYMBOL`.** The board's row is (provider, symbol) — the
  same symbol from two providers is two rows — so the row id, sort tiebreak, and session
  storage moved to the compound key; the storage version bumped so stale pre-provider
  sessions are discarded, not half-restored.
- **Two new columns, two different clocks.** *Age* counts from the provider's own
  last-trade time and re-renders every second; *Updated* keeps showing when we received the
  event. Last night's closed-market board read "Age 1h 21m / Updated 23:20:10" — the gap
  between the clocks is the whole freshness story, visible.
- **Staleness became per-row.** The old fixed 5-second threshold matched the deleted
  1-second simulator. Each tick now carries its own `stale_after_seconds` and the row
  classifies itself; the STALE summary card reads "past feed threshold".
- **The ticket needed two compatibility fixes during end-to-end validation:**
  1. *Re-selecting the same instrument wiped the price preview for good.* The dropdown's
     change handler always cleared the preview, but the fetch effect only re-runs when its
     inputs change — and re-picking the same symbol changes nothing. Pre-fork this healed
     invisibly within a second (every tick re-triggered the fetch); at honest cadences the
     heal could be five minutes away. React mechanics in one line: `useEffect(fn, deps)`
     re-runs only when a value in `deps` differs from the last render. Fix: clear the
     preview only when the selection actually changed.
  2. *The preview's refresh trigger still looked up rows by bare symbol* — forever missing
     against the new `PROVIDER:SYMBOL` ids. It now finds the row by symbol across
     providers — exact while each symbol has a single provider row, which is the state of
     the board today.

## Step 8 — verification procedure and acceptance criteria

1. Add an equity with Finnhub selected and wait for its first board row.
2. Verify that `GET /quotes?provider=FINNHUB` exposes the full normalized quote contract:
   provider, symbol, basis, grade, both timestamps and freshness thresholds.
3. Compare `provider_timestamp` with `received_at`. Age follows the provider timestamp;
   ingestion delay is their difference.
4. Check provider operations. During the regular session, open-position and benchmark
   symbols use the 15-second tier while watchlist-only symbols use 60 seconds. Outside the
   session, both use 300-second confirmation polling and healthy rows classify `CLOSED`.
5. Refresh a watched symbol with `POST /refresh?symbol=<symbol>&provider=FINNHUB`; expect 200
   and a new tick. Expect 404 for a symbol outside the active set, 400 for a missing symbol
   and 404 for an unknown provider.
6. Poll an unchanged price repeatedly. The board's `received_at` advances, while history
   appends only when a price field changes.
7. Open a LIVE trade through Finnhub. Verify that trade detail and valuations retain
   `FINNHUB` and the provider quote timestamp. The symbol moves to tier 1 after active-set
   reconciliation.
8. Restart pricing and verify that active trades revalue from `/snapshot` before the next
   provider poll.
9. Run Python compilation, frontend lint, dead-code analysis and the production build, then
   inspect Market Data, Trades, Valuations and System Overview without console errors.

## Compatibility and supporting decisions

1. **`DEFAULT_QUOTE_PROVIDER` is a legacy fallback.** Pricing caches by (provider, symbol),
   but older trade rows may have no `market_data_provider`. The fallback names Finnhub and
   every use is logged; new trades are provider-bound.
2. **`BENCHMARK_PROVIDER` prevents double sampling.** Alpha/beta accepts SPY ticks only from
   the configured benchmark feed, even when several providers quote SPY (Step 6).
3. **Decimal conversion happens at the stream boundary.** Scenario shocks and money math
   operate on `Decimal`; JSON strings never silently bypass multiplication (Step 6).
4. **The ticket consumes the provider board consistently.** Re-selecting an instrument and
   refresh-trigger lookup preserve a valid price preview (Step 7).
5. **Route names are service-root** (`/quotes`, `/refresh`, `/providers`), matching the
   existing `/snapshot` and `/stream` — the browser path is `/api/market-data/<route>` and
   the proxy strips the prefix.
6. **Scheduler mechanics stayed constants, not env vars** (active-set reload 15 s, status
   check 10 min, timeout 10 s, threshold ×3, cooldowns). The config rule covers tunables
   with a rationale; these are implementation cadence. The five real knobs — tier cadences,
   closed cadence, budget, retention — are env vars with their why in configuration.md.

## Operational refinements

These refinements share one root: code written when
quotes arrived every second now runs against real feeds that may tick once in five
minutes.

- **A new trade took minutes to appear in Trades/Books/Valuations — fixed at both ends.**
  The chain was: the blotter (the read-model service behind the Trades and Books screens)
  lists an ACTIVE trade only after its first *valuation* arrives, and pricing only valued
  on *ticks* — with the market closed (300 s cadence), a fresh trade could be invisible for
  five minutes. Pre-fork ticks came every second and hid the coupling. Two fixes:
  1. *Pricing values a trade the moment it enters the active set* (inside the existing 2 s
     refresh loop), off the already-cached quote — no waiting for a poll, no extra API
     spend. And so a restart does not start blind, pricing now seeds its quote cache from
     market-data's `/snapshot` before connecting to the stream — the same order the
     frontend uses: seed from the snapshot, then follow the stream.
  2. *The blotter reconciles its ACTIVE cache against the database every 5 s* — a trade
     shows up even if no market data exists for it yet, and a final valuation missed
     during a disconnect can no longer leave a phantom ACTIVE trade behind. This also makes
     the architecture doc's "blotter polls on its own cadence" literally true instead of
     boot-only.

  Acceptance behavior: an open intent becomes visible in the blotter with fair value within
  the polling window; closing produces a final realized valuation; a pricing restart
  revalues active trades from the seeded snapshot without waiting for a new provider tick.
- **Closing one side panel closed the other one too.** With the ticket and a log story
  panel open at once (they stack in the same right-hand slot), clicking either X — in
  fact, clicking anywhere in either panel — dismissed both: each panel treats any click
  outside *itself* as "close me", and the other panel's surface is exactly that. Fix: the
  outside-click test now ignores clicks landing inside *any* side panel, and Escape closes
  only the topmost panel, peeling them one at a time. Verified in the browser, both
  directions and both keys during UI validation.
- **The scheduler was one file doing four jobs — split into four files.** The layout is
  Step 4.1's table: the
  symbol universe (`active_set.py`), the per-provider condition machine
  (`provider_runtime.py`), everything Finnhub (`finnhub_feed.py`), and the registry the
  HTTP API reads (`scheduler.py`). A new provider is one new feed file plus one registry
  line. The split does not change the ops endpoints, refresh behavior or thresholds.
- **Comment policy settled.** Docstrings that had drifted toward rationale prose were
  trimmed to one-line contracts. The standing bar, codified in AGENTS.md, is that `#`
  comments serve exactly two purposes — a crucial constraint the code cannot
  express, or a short stage marker inside a multi-stage process function naming what the
  next block does, so a first-time read has the map (`poll_loop` carries six,
  `refresh_symbol` three). Never rationale — all why lives in the implementation guides —
  and no marker where the lines already announce themselves: linear pipelines (pricing's
  stream consumer) and single-call loops (`trade_refresh_loop`, `retention_sweep_loop`)
  carry none.

## Component boundaries

- Finnhub owns US equity and ETF transport; Twelve Data and future providers use separate
  clients and runtimes behind the same normalized quote contract.
- Watchlist membership, provider comparison and provider-bound execution are described in
  [multi-provider-trading.md](multi-provider-trading.md), not duplicated here.
- Market-session-aware freshness is shared policy in `shared/freshness.py`; the Finnhub feed
  supplies exchange state and open/closed cadences but does not define UI labels.
- Curves and curve-priced instruments remain outside quote-feed responsibility.
- Valuation persistence is owned by pricing; Finnhub only publishes normalized market events.
