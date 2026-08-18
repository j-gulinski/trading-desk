# Phase 1 — contracts & schema

Phase 1's job was to turn the plan's data-model decisions (D2–D6, D11) into things code can
be checked against: the shared contracts every later phase normalizes *into* (quote, curve,
freshness, provider capability), the database schema those contracts persist to, and the
retirement of the last synthetic remnant — `INSTRUMENT_CATALOG` — in favor of the
watchlist-backed symbol master. Nothing fetches data yet; that is Phase 2's vertical slice.
This phase also started `docs/market-data.md`, the domain reference seeded with the provider
fact sheets. **Exit criterion, met:** the migration runs up, down, and up again clean on a
fresh database (evidence in Step 4).

## Step 1 — the market-data contracts

**Needed:** six providers will produce six raw payload shapes, but the plan's promises —
never synthesize a spread, grade every price honestly, four freshness states, per-point curve
provenance — are properties of *one* shape. That shape had to exist, in `shared/`, before any
client is written, or each client would improvise its own.

- **Four small modules, one concern each** (matching the repo's flat single-purpose `shared/`
  idiom): `freshness.py` (states + grades + the classifier), `providers.py` (the registry and
  class-level capability matrix), `quotes.py` (`NormalizedQuote` + `build_quote`),
  `curves.py` (`CurvePoint`/`CurveSet` + builders).
- **`build_quote` is where D11 lives, mechanically.** It stores `bid`/`ask`/`last` exactly as
  given (NULL stays NULL), then derives `mid` by precedence: both sides present →
  `(bid+ask)/2` and basis `BID_ASK`; else an official fixing → basis `REFERENCE_MID`; else
  `last` → basis `LAST`; else **`ValueError`** — an unpriced quote cannot be constructed, so
  everything downstream may rely on `mid` existing. The basis tag records which branch fired,
  so the UI can always say what kind of number it is showing.
- **Prices parse to `Decimal` at the contract boundary** — the D8 ingest rule, applied from
  the first line of new code rather than retrofitted in Phase 7. The parse is
  `Decimal(str(value))`: providers send strings, which convert exactly; if a float ever
  sneaks in, going *through the string form* captures the number as printed
  (`Decimal(str(0.1))` → `0.1`) instead of exposing the binary representation
  (`Decimal(0.1)` → `0.1000000000000000055511151231257827…`) — the wire text is the truth,
  not the float that briefly carried it.
- **States and grades are `str`-subclassing enums** (the `Severity` precedent): they compare
  and serialize as plain strings — `shared/serialization.to_json` already renders enums by
  value, DB columns store `TEXT`, and HTTP payloads need no translation layer.
- **The freshness classifier is a pure, total function**: (supported?, timestamp, now,
  threshold) → state. `UNSUPPORTED` is checked first because it is a *capability* fact — "this
  provider cannot serve this class" — and must never be conflated with `MISSING` ("should
  serve it, nothing arrived"). Threshold *values* are deliberately not here: they are 2–3× each
  feed's scheduled cadence, so they belong to the scheduler phases as configuration.
- **The registry is data plus two accessors — and it is only half of "capabilities."**
  `PROVIDERS` maps each of the six providers to its group and its verified class→grade facts
  (e.g. Alpha Vantage equity = `EOD`); `quote_grade()` / `supports_quotes()` answer "can this
  provider serve this asset class, and at what honesty grade." Capabilities come in two
  layers because the question has two levels:
  - *Class level — this module, static.* "Finnhub cannot serve FX on the free tier" is a
    property of the provider's *product*, established by the probes, so it is hardcoded data.
    This layer is what makes `UNSUPPORTED` a distinct freshness state: Finnhub × EURUSD is
    not missing data, it is data that can never arrive.
  - *Symbol level — the `capabilities` JSONB on `watchlist_items`, filled at watchlist-add
    (Phase 3).* Class facts are not enough: Twelve Data serves "EQUITY" as a class and may
    still not know one specific ticker. At add time the system asks each provider once
    ("do you quote NVDA?") and caches the per-provider verdict on the row — e.g.
    `{"FINNHUB": true, "TWELVE_DATA": true, "ALPHA_VANTAGE": false}`. The scheduler then
    never spends budget polling a provider that cannot serve the symbol, and the UI renders
    exactly those cells as UNSUPPORTED. It is a DB column rather than an in-process cache so
    a restart does not re-spend the probe budget — "computed *once* at watchlist-add" stays
    literally true. (Metals cells were left absent pending the real-key check; resolved in
    the closing section below.)
- **Curve points carry their own provenance** (`source_series`, `source_as_of`): the Phase 5
  curve inspector's "which FRED series, as of when" drill is a schema fact from day one, and a
  NULL `source_series` is the explicit marker of an interpolated point (the PLN composite).
- **One line of `build_curve_set` carries three Python idioms worth knowing** — it is how the
  "points are always in tenor order" invariant is made:

  ```python
  points=tuple(sorted(points, key=lambda point: point.tenor_years))
  ```

  - `lambda point: point.tenor_years` is an anonymous function, nothing more:
    `lambda <params>: <expression>` defines a function whose body is that one expression and
    whose return value is the expression's result. It is exactly equivalent to writing
    `def tenor_of(point): return point.tenor_years` and passing `tenor_of` by name — `lambda`
    is for functions too trivial to deserve a name. Java analogy: the
    `p -> p.getTenorYears()` you hand to `Comparator.comparing(...)`.
  - `sorted(points, key=...)` returns a **new list**, never mutating its input. The `key`
    function is called once per element to extract a sort key, and elements are ordered by
    comparing those keys, ascending; the sort is *stable* (equal keys keep their original
    relative order). The `key` is required here: without it Python would compare two
    `CurvePoint` objects directly and raise — dataclasses define no `<` unless asked
    (`order=True`).
  - `tuple(...)` freezes the result. `CurveSet` is `@dataclass(frozen=True)`, which blocks
    reassigning *fields* (`curve.points = …` raises) — but frozen does not reach inside a
    field: a `list` stored in a frozen dataclass could still be `.append()`-ed or reshuffled
    by any consumer. Converting to a tuple closes that hole, so a constructed curve genuinely
    cannot change.
  - Why sort at construction at all: `build_curve_set` is the single gate every curve passes
    through, so ascending tenor order becomes an *invariant of the contract* — Phase 5's
    interpolation and the CurveChart may rely on it instead of each re-sorting defensively.
    The other common idiom for this exact key is `operator.attrgetter("tenor_years")` —
    identical behavior, a matter of taste; the lambda states what it extracts without knowing
    the `operator` module. Honest limit: a lambda body is one expression, no statements —
    anything with real logic gets a named function (house style).

## Step 2 — the symbol master replaces the catalog

**Needed:** `INSTRUMENT_CATALOG` was the last piece of the synthetic world — six hardcoded
instruments deciding what the ticket offers and what trade-action accepts. In the provider
world that authority belongs to the user's watchlist (D4): what isn't watched isn't tradeable.
Consumers: term schemas (option-underlying choices), trade-action (`/instruments`, open
validation), pricing (`/price` preview), the ticket UI (via HTTP only).

- **`shared/symbols.py` is the new home**: the asset-class taxonomy (spot vs curve-priced —
  `SPOT_ASSET_CLASSES` moved here from term_schemas), the canonical symbol convention (the
  validation pattern trade-action previously kept privately), and the watchlist lookups
  (`watchlist_item` / `watchlist_items` / `watchlist_spot_symbols`), each taking the caller's
  DB session.
- **Option-underlying choices went dynamic without changing the wire contract.** The schema
  field now carries `choices_source: "WATCHLIST_SPOT"` internally; `public_term_schemas`
  resolves it to a concrete `choices` list (and strips the marker), so the frontend keeps
  receiving exactly what it always did — a plain choices array. `validate_terms` resolves the
  same marker against the same watchlist at validation time, so what the ticket offers and
  what the backend accepts cannot drift apart.
- **`/instruments` keeps its shape, changes its source**: `[{symbol, asset_class, currency}]`
  read from `watchlist_items` — today an honest `[]`, and the ticket's instrument picker
  renders its "No instrument" empty state untouched.
- **Open validation reads the watchlist row** — symbol must exist with the intent's asset
  class; the frozen terms become `{asset_class, currency}` from the master. One mechanical
  consequence: `_resolve_terms` moved *inside* the worker's session block (it queries the DB
  now), so term resolution, book lookup and the audit write share one transaction. The
  rejection message tells the new truth: *"symbol is not on the watchlist for this asset
  class."*
- **The catalog's non-catalog residents were rehomed, and the file deleted.**
  `BENCHMARK_SYMBOL` → `shared/config.py` (it is env-driven configuration; code default now
  `SPY` per D14 — the old `MARKET_INDEX` default pointed at a symbol that no longer exists);
  `DEFAULT_CURVE` / `DEFAULT_VOLATILITY` → `term_schemas.py` (they are term defaults);
  `CURVE_PRICED_ASSET_CLASSES` → `symbols.py` (taxonomy).
- **What this leaves untradeable, honestly.** The catalog's predefined bonds (`GOVT_2Y/5Y`)
  were synthetic instruments; with no custom BOND term schema until Phase 5's curve work, BOND
  books hold no tradeable instruments during the interregnum. Nothing regressed in practice —
  with zero market data, *every* open already failed at the price check — but the source of
  truth is now the one that will carry real data.

## Step 3 — the migration

**Needed:** the DB still described the simulator: an append-only spot table with a `spot`
column and a `'SIMULATED'` source default, whole-board JSON snapshots, curves as parallel
JSONB arrays, and no watchlist. The plan's §5 model — board / history / curve sets / watchlist
plus the D2 provenance columns — had to land as one hand-written revision.

- **One revision, `f4a8c1d27b3e`, chained on the existing head** — the fifth link in the
  chain, not a reset: a fresh DB replays init → … → provider schema, and the running DB moved
  forward with `alembic upgrade head` like any deploy. Hand-written rather than
  autogenerated: half the change (drop-and-recreate semantics, constraint names, the FK
  choice below) is intent autogenerate cannot infer from model diffs.
- **The market tables are dropped and recreated, not ALTERed.** They change *identity*, not
  just columns — an append log became a keyed latest-board; JSON blob snapshots became
  per-quote history rows. Translating synthetic rows would manufacture fake provider data;
  the pre-fork data lives on in the archived repo, and a fresh DB is the deployment path. The
  business tables (`trades`, `valuations`, `books`, `audit_logs`) are only ever ALTERed —
  their rows are real.
- **What "up/down clean" actually proves** — the exit criterion is a statement about
  *reversibility and truthfulness of the migration script*, not about data. `upgrade` proves
  the DDL is valid against the real schema left by the previous four revisions; `downgrade`
  proves the script knows exactly what it created (every add has a matching drop — the old
  tables are rebuilt column-for-column, `'SIMULATED'` default included); the second `upgrade`
  proves the downgrade left no debris that collides on re-run. Postgres makes each direction
  atomic: it supports **transactional DDL** (alembic logs `Will assume transactional DDL`),
  so a revision that fails halfway rolls back entirely — no half-migrated schema states. The
  common idiom is to never write `downgrade` ("roll forward only"); it is kept working here
  because it is this phase's cheapest full test of the script, at the price of maintaining the
  old DDL by hand in the file.
- **The board's constraints are the design, in DDL.** `UNIQUE (provider, symbol)` is what
  makes it a *board* (upsert target, one row per pair — D5's bounded-growth answer);
  `mid`/`price_basis`/`quote_grade`/`received_at` are `NOT NULL` because `build_quote`
  guarantees them — the DB now rejects any row that bypasses the contract. The board carries
  **no raw payload**: history owns raw, the board is the read-optimized latest state.
- **History is the provenance store**: same quote columns plus `raw_payload JSONB`, append
  keyed by `(provider, symbol, received_at)` — the index that serves both "latest row for this
  pair" (what a trade freezes) and the Phase 6 drill.
- **`trades.entry_snapshot_id` is a deliberately strict FK** (no cascade, no SET NULL): the
  Phase 2 retention sweep must *skip* snapshot rows referenced by trades. A trade's raw-payload
  provenance therefore outlives the 30-day window by construction — the alternative (cascade
  or nulling) would let routine housekeeping silently amputate the audit story.
- **Curve sets + points as two tables** — `UNIQUE (provider, curve_name, as_of_date)` makes
  "≤ one set per source per day" a constraint rather than a hope; points `CASCADE` with their
  set (replacing a set replaces its points) and are unique per tenor within it.
- **`watchlist_items` is keyed by the symbol itself** — the one table where a natural primary
  key states the semantics ("the watchlist implies one row per symbol") better than a
  surrogate UUID would.

## Step 4 — verification

- **The exit gauntlet, on a throwaway postgres:18 with an empty volume:**

  ```
  === UPGRADE HEAD (fresh) ===  … Running upgrade b7e2f1a9c3d4 -> f4a8c1d27b3e, provider market schema
  === DOWNGRADE -1 ===          … Running downgrade f4a8c1d27b3e -> b7e2f1a9c3d4, provider market schema
  === RE-UPGRADE HEAD ===       … Running upgrade b7e2f1a9c3d4 -> f4a8c1d27b3e, provider market schema
  ```

  Schema inspected after: board unique + NOT NULLs as designed, all five D2 trade columns,
  valuations swapped to provider + timestamp, curve-point FK `ON DELETE CASCADE`, watchlist
  keyed by symbol.
- **The running stack rebuilt and migrated in place** (db-migrations exited 0 on the same
  revision); monitoring shows 7/7 UP, streams 2/2 connected, `/snapshot` still
  `{spots: {}, curves: {}}`.
- **The symbol master, exercised end-to-end** with a temporary `AAPL` row (inserted, verified,
  deleted — the DB is left empty):
  - `/instruments`: `[]` → `[{"symbol": "AAPL", "asset_class": "EQUITY", "currency": "USD"}]`
  - term schemas: option underlying choices `[]` → `["AAPL"]`
  - open on a non-watchlist symbol → audited `ACTION_REJECTED — Open rejected: symbol is not
    on the watchlist for this asset class`
  - `/price` on an unknown symbol → 404 `instrument not found`; option preview on the
    watchlisted underlying → passes validation, then the honest 503 `required market data is
    not available`; option on a non-watchlisted underlying → 400 `invalid underlying_symbol`.
- **Static and UI:** `py_compile` clean across the tree; oxlint, knip, and `vite build` clean;
  Playwright over System Overview (with the ticket panel open), Market Data, Valuations and
  Books — zero console errors or warnings.

## Deviations from the plan's text

Each item is something Phase 1's plan bullet does not name, with its why:

1. **`valuations.market_data_reference` dropped.** Legacy column no code ever wrote (always
   NULL); D2's `market_data_provider` + `market_data_timestamp` are its honest replacement.
2. **FUTURES hidden, not dropped** (owner ruling 2026-08-18). The class was removed from the
   offered surfaces (pricing spot/shock tuples, the frontend book-class list and unit
   formatter) because no free provider serves futures quotes — but every asset class,
   futures included, *was* implemented pre-fork, so the HW5 PDF's conditional ticket list
   ("jeżeli te instrumenty zostały już zaimplementowane", p. 6) is met by the archived repo.
   The class is dormant, to be restored when a futures data source exists; Phase 7's README
   "known limitations" section records the hidden status honestly.
3. **`BENCHMARK_SYMBOL` code default changed `MARKET_INDEX` → `SPY`** as part of its move to
   `shared/config.py` — the old default named a deleted synthetic symbol; D14 names SPY.
4. **`watchlist_items.capabilities JSONB` added.** D4 says the per-symbol capability matrix is
   "computed once at watchlist-add, cached" — persisting the cache on the row is what makes it
   *once*: an in-process cache would re-spend provider probe budget on every restart. Written
   from Phase 3.
5. **`mid NOT NULL` on board and history** — the plan lists the quote columns without
   nullability; the constraint encodes `build_quote`'s "no unpriced quote" guarantee.
6. **Constant rehoming** (`DEFAULT_CURVE`, `DEFAULT_VOLATILITY` → `term_schemas.py`;
   `CURVE_PRICED_ASSET_CLASSES` → `symbols.py`) — fallout of deleting their former home.
7. **`_resolve_terms` moved inside the worker's DB session** — it queries the watchlist now;
   resolution, book lookup and audit share one transaction.

No new environment knobs this phase — the D24 table is unchanged except the benchmark row's
default.

## Carried forward, deliberately

- **`DEFAULT_CURVE` still says `USD_GOV`** — a curve name no provider will ever publish. The
  real curve catalog (`USD_TREASURY`, `EUR_GOV_*`, `PLN_*`) and the term-schema curve pickers
  are Phase 5; renaming now would fake a decision that phase owns.
- **Scenario `.http` files still reference catalog symbols** (`ACME` etc.) — the plan rewrites
  scenarios in Phase 7; they were already inert (no market data existed to trade against).
- **BOND books are untradeable until Phase 5** (see Step 2) — the catalog bonds were
  synthetic; real bond terms arrive with the curve work.
- **`NewTradePanel`'s curve/revision plumbing still speaks the old tick vocabulary** — the
  ticket is rebuilt in Phase 4 against the provider board; today it renders the honest empty
  state.

## Closed right after the phase (2026-08-18)

- **The four API keys are registered** in `.env` and each was sanity-probed live: Finnhub
  quotes AAPL, Twelve Data quotes, Alpha Vantage returns EUR→USD with real bid/ask, FRED
  serves DGS10. Phase 2 is unblocked.
- **Metals check resolved (review outcome #5):** Twelve Data serves `XAU/USD` with a real
  key → **XAUUSD stays tradeable via Twelve Data** (`COMMODITY: REALTIME` added to the
  registry). Alpha Vantage rejects XAU while accepting EUR→USD on the same endpoint → its
  COMMODITY cell stays UNSUPPORTED. Evidence and payload shapes: `docs/market-data.md`.
