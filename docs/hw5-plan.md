# HW5 phase plan — Real Market Data Integration

> **Planning artifact, not a system document.** It describes intended work as of 2026-08-16;
> the topic docs (architecture, pricing, …) stay the source of truth for what exists. Retire or
> refresh this file as phases land. Sources: `praca_domowa_05` PDF, kurs-5 session
> (`finance-hub/content/transcripts/kurs-5-topics.md`), `finance-hub/content/homework/hw5-notes.md`,
> and a full code survey (2026-08-16).

Suggested budget from the session: **~2 weeks** for "implement, test, stress-test" [kurs-5
00:04:52]. Next session likely 2026-08-31. The phases below sum to ~12 working days.

---

## 1. What is actually being asked

Three sources, one merged requirement set.

### From the PDF (grading contract)

- **Six providers, all mandatory.** Group A (Alpha Vantage, Finnhub, Twelve Data) = tradable
  quotes; Group B (NBP, ECB, FRED) = official reference data and curves. Hand-written HTTP
  clients only (`urllib`) — no SDKs, no `requests`, no pandas.
- **market-data-service becomes the only external gateway**: provider clients, normalizer,
  polling scheduler, persistence, internal SSE, provider health state, audit logging.
- **Normalized quote**: provider, asset_class, symbol, bid/ask/last (each optional), currency,
  `provider_timestamp`, `received_at`, `raw_payload`. Missing prices stay missing — the price
  basis rule (mid → last → …) must be explicit and documented.
- **Endpoint set**: `/providers`, `/providers/<p>/health`, `/market-data/snapshot`,
  `/market-data/quotes` (+ query and `<provider>/<symbol>` forms), `/market-data/stream`
  (+ per-provider), `/curves`, `/curves/<provider>`, `POST /market-data/refresh`,
  `POST /curves/refresh` (refresh = immediate fetch, not waiting for the scheduler).
- **Trading ticket**: book, asset class, symbol, side, quantity/notional, **provider choice**,
  live price from the chosen provider, price timestamp, currency, optional comment; a
  **three-provider comparison row** (value, timestamp, LIVE/STALE/MISSING per provider);
  **MISSING blocks the trade**; the STALE policy (block vs warn) is ours to choose *and
  document*.
- **Provider is a dimension of the position**: trades freeze `market_data_provider`,
  entry price, price timestamp, quote/snapshot ref; valuations, close, realized and unrealized
  PnL all use *that* provider's data — never mixed. Server-side validation: no market trade
  without a current quote from the chosen source.
- **Curves**: PLN FX reference from NBP, EUR reference from ECB, USD Treasury/rates from FRED;
  ≥1 USD discount curve, ≥1 EUR-or-PLN curve/point-set. Curve rows must reconstruct provider,
  point, as-of and the original API response.
- **Audit events**: fetch, fetch failure, rate-limit hit, quote persisted, curve point
  persisted, trade created/rejected/closed, valuation update, valuation blocked on missing
  provider data.
- **Ops**: everything under one `docker compose up --build`; API keys only via env /
  `.env` (gitignored) + committed `.env.example`; README that lets a stranger run and test the
  system, including per-provider endpoint documentation based on official docs.

### From kurs-5 (the teacher's spoken expectations — beyond the PDF)

1. **Domain analysis over integration** — "żeby to nie było tylko: kolejna integracja, ale w
   ogóle nie wiem co pobieram" [00:05:10]. For every dataset: what is it, why fetch it, how is
   it used, where is it visible in the UI. This is a graded expectation, not garnish.
2. **Multiple curves, currency- and tenor-aware** — projection + discount curve selectable on a
   swap; a PLN-settled swap must not discount on a USD curve [00:05:22–00:06:13]. What you can
   import defines what you can trade, and vice versa [00:06:39].
3. **Don't destroy the generator** — "lepiej dostawić nowy mikroserwis niż zastępować ten
   generator w pełni, żeby mieć coś jeszcze do dema" [00:19:13]. Intent: the synthetic demo must
   stay runnable (he wants a nice demo form later). See decision D1.
4. **Test + stress test** the result; **profile RAM/CPU per Docker container** [00:04:52,
   00:16:37, 00:17:21].
5. **HW6 preview**: simple investment strategies over real data, portfolio behavior analysis
   [00:07:01] — HW5's persisted quote history is HW6's fuel; don't throw it away.

### Carry-over action items folded into this phase

- Answer whether `MARKET_INDEX` is polled or streamed, and whether pricing and UI share one
  stream [00:14:19] — it **is** one SSE stream consumed by both (pricing's
  `market_data_client` and the frontend's market feed); write it down in docs.
- Prepared answer on log-file security / geo-redundancy (the session's only criticism)
  [00:27:46].
- Analysis note on concurrent writes to log files [00:33:47].
- **Decimal-for-money audit** — "Nie korzystaliśmy z floatów" [00:52:47]. See D8; the survey
  found real float exposure in `shared/pricing_math.py`.

---

## 2. Current state → gap map

The good news first — **seams already prepared** (survey 2026-08-16):

| Prepared seam | Where | What it buys |
| --- | --- | --- |
| Dual-curve IRS already implemented | `shared/pricing_math.py:86-124` — `irs_pv(meta, curve, projection_curve=None)` | The single largest HW5 feature exists; it has just never been passed a second curve |
| `market_inputs` / `price_from_inputs` split | `pricing-service/app/valuation_engine.py:21-79` | Provider- and curve-selection are pure `market_inputs` changes; the math is untouched |
| `TERM_SCHEMAS` server-driven forms | `shared/term_schemas.py` | Adding `settlement_currency` / `discount_curve` / `projection_curve` fields gives ticket UI, validation and freeze-at-open **for free** |
| Frozen-terms JSONB on trades | `trades.metadata` | Curve choices ride the existing freeze pattern, no migration |
| `valuations.market_data_reference` | `shared/models.py:73` | Migrated, nullable, **never written** — free slot for the quote ref |
| `market_data_spot_prices.source` | `persistence.py:101` (constant `"SIMULATED"`) | The provider column already exists on spots; only values change |
| `CurveType` enum with `DISCOUNT` | `shared/enums.py:51-54` | Declared, never produced |
| `BENCHMARK_SYMBOL` env-overridable | `shared/catalog.py:6` | Real benchmark (SPY) is a config change; the alpha/beta estimator survives by design |
| LIVE/STALE vocabulary + `StatusPill` | `config/valuations.js:8-14` | UI freshness needs `MISSING` added, not invented |
| Structured logs + edge-triggered audits | logging stack | Provider failures land as routine filterable lines |

**The four symbol-only keyings that must become `(provider, symbol)`** — the one structural
change `docs/README.md` predicted:

1. Pricing cache — `pricing-service/app/cache.py:24-25`.
2. SSE tick contract — no provider field on the wire.
3. Frontend instrument identity — `domain/marketData.js:38` (`id = symbol`).
4. `market_data_spot_prices` — no provider-aware index or uniqueness.

**Genuinely missing** (no code at all): provider HTTP clients, normalizers, polling scheduler,
rate-limit/backoff handling, provider health state and endpoints, symbol master, freshness with
`provider_timestamp` vs `received_at`, curve ETL, `/curves` endpoints, provider fields on
trades/valuations, ticket comparison view, curve pickers, `.env` provider keys.

**Bugs found during the survey — fix inside this phase** (each is on HW5's path anyway):

- **Scenario spot shocks are a silent no-op**: cached spot values are JSON *strings* (Decimal →
  str in `shared/serialization.py`), so `isinstance(value, (int, float))` in `scenario.py:16-23`
  never matches; every EQUITY/FX/option scenario returns PnL 0. Dies naturally when the cache
  starts parsing quotes into Decimal (D8).
- **The generator can close manual provider-bound trades**: it tracks *all* open trades and its
  close-picker filters by symbol, not source (`trade-generation-service/app/generator.py:170-175`).
  Once user trades are provider-bound, a generator close would price them off the wrong source.
  Fix: filter closes to `source == GENERATED`.
- **Frontend freshness measures the stream, not the quote**: staleness keys off `receivedAtMs`
  (browser arrival), so it answers "is SSE flowing", not "how old is this price"
  (`domain/marketData.js:311-314`). Real providers need `provider_timestamp`-based freshness
  with per-provider thresholds.

---

## 3. Decisions to lock before building

Written in `decisions.md` style — chose / rejected / why. These go into `decisions.md` as they
are confirmed in code.

**D1 — Where the providers live: inside market-data-service; the generator becomes provider
`SIMULATED`.**
The gateway keeps its port (8001), its `/snapshot` + `/stream` contract and its consumers; the
provider abstraction gets seven implementations, one of which is the existing synthetic
generator running in-process behind `ENABLE_RANDOM_MARKET_DATA_FALLBACK`. *Rejected:* a second
"real market data" microservice next to the old one — it violates the PDF's single-gateway rule
(or forces a rename-and-reroute of every consumer) and adds an internal transport hop that
teaches nothing. **The teacher's actual concern** — keep the demo runnable [00:19:13] — is
honored more robustly: flag on = the entire old demo runs through the new pipeline, plus a git
tag (`pre-hw5-simulator`) / fork preserves the pure-simulator build for his "fajna forma
graficzna". If unsure, this is the one decision worth a one-line confirmation with the teacher;
it deliberately reads his advice by intent, not letter.

**D2 — Provider becomes a first-class column where it's queried, JSONB where it's a term.**
Trades gain real columns `market_data_provider`, `entry_price_timestamp`, `entry_quote_ref`
(the spot row's `market_data_id` as text), `created_by_service`; valuations gain
`market_data_provider`, `market_data_timestamp` (plus the already-free `market_data_reference`).
Curve *choices* (`discount_curve`, `projection_curve`, `settlement_currency`) stay in frozen
terms — they are economics, and the schema already holds them. *Rejected:* everything-in-JSONB
(provider is a filter/join dimension for blotter, PnL and audit — the schema cannot express
that today, which is the house bar for a migration).

**D3 — Freshness: two clocks, three states, server-computed.**
Every quote carries `provider_timestamp` (their clock) and `received_at` (ours). Status per
`(provider, symbol)`: `LIVE` if age(provider_timestamp) ≤ threshold, `STALE` above it, `MISSING`
if no quote (or no successful fetch ever). Thresholds are per provider, derived from the polling
budget (≈ 3 × poll interval). One shared implementation (`shared/freshness.py`) used by
market-data (labels on the wire), trade-action (server-side re-validation at submit) and the
ticket. **Policy: MISSING blocks; STALE warns + requires explicit confirmation, and the
acknowledgement is recorded in the trade's audit trail.** Rationale to document in README:
outside US market hours *every* equity quote is legitimately stale — a hard STALE block would
brick the ticket all weekend; blocking is reserved for "no data", warning for "old data".

**D4 — Symbol master in code, not a table.**
`shared/symbols.py`: `internal_symbol → {provider: provider_symbol}` plus per-provider quote
conventions (Finnhub `AAPL`, Twelve Data `EUR/USD`, Alpha Vantage from/to params…). The catalog
switches to a real universe: a handful of US large caps + FX majors (incl. `USDPLN` for the NBP
tie-in) + `XAUUSD`; `BENCHMARK_SYMBOL=SPY`. *Rejected:* a `provider_symbols` table — reference
data that changes with a code release can live with the code (same argument as the instrument
catalog); a table is the future step when symbols become user-editable.

**D5 — Curve model: point-per-row ingest + assembled-curve publish.**
New table `market_data_curve_points` (provider, curve_name, currency, tenor, rate, `as_of_date`,
source series id, `received_at`, raw payload) — this granularity is *real*, because each USD
tenor arrives from a distinct FRED series call with its own response. The existing
`market_data_curves` (arrays) stays as the assembled-curve event log the stream and pricing
consume, extended with `provider` + `as_of_date`. Assembly = explicit ETL step: points → curve,
conventions documented per curve. *Rejected:* only array rows (loses point provenance the PDF
demands), only point rows (forces every consumer to re-assemble).

**D6 — Curve catalog (the domain-analysis centerpiece).**
- `USD_TREASURY` — FRED `DGS1MO…DGS30` constant-maturity par yields, used directly with the
  existing interpolation; *documented simplification:* par yields treated as zero rates (no
  bootstrap), consistent with the existing annual-compounding simplification.
- `EUR_GOV_AAA` and `EUR_GOV_ALL` — ECB Data Portal yield-curve dataflow (SDMX/CSV), genuine
  spot (zero) rates at standard tenors; two real EUR curves from one source means
  **projection-vs-discount selection is demonstrable on real data**.
- `PLN_REF` — the honest composite: NBP's API serves FX (tables A/C — note table C carries
  bid/ask) but **no interest rates**, and WIBOR is licensed. Candidates, verified at
  implementation time: FRED/OECD Poland series (3M interbank, 10Y long-term — some OECD series
  were discontinued; check first), else a configured NBP reference-rate flat curve, explicitly
  labeled a proxy. The investigation and its write-up **is** the deliverable the teacher asked
  for; a PLN swap then prices on a PLN curve and rejects a USD one.
- FX reference rates (NBP tables, ECB EXR) are stored as quotes from providers `NBP`/`ECB` with
  daily-cadence freshness thresholds — reference data, not tradable feeds.

**D7 — Polling budgets are per provider, and the budgets *are* the domain analysis.**
Free tiers (verify at signup): Finnhub ~60 req/min → the 30–60 s workhorse; Twelve Data
~8 credits/min & 800/day → one batch poll every few minutes; **Alpha Vantage ~25 req/day** →
a few scheduled fetches per day + budget-guarded manual refresh; its comparison column will
honestly read STALE most of the time, and the README says why. NBP/ECB/FRED: daily-cadence
polls (hourly checks are plenty). Scheduler: one thread per provider, interruptible sleep
(house pattern), jitter, exponential backoff on failure, rate-limit responses classified
separately from errors (`RATE_LIMITED` state + audit, not an error counter). Refresh endpoints
wake the scheduler via its `Event` and respect the budget guard.

**D8 — Decimal policy: cashflow and discount math in Decimal; transcendental option math stays
float; one conversion at the boundary.**
Convert `discount_factor`, `bond_pv`, `irs_legs`/`irs_pv` (Decimal supports fractional powers);
keep `black_scholes_price` float (`math.erf`/`log`/`sqrt`) with a single documented boundary.
The pricing cache parses wire strings into Decimal at ingest — which also kills the scenario
no-op bug. Use `decimal.localcontext` where precision needs a local override (ties directly to
the kurs-5 presentation; the global-precision trap is the defense answer). Re-verify the IRS
telescoping identity to 1e-10 after conversion.

**D9 — The trade generator becomes a provider-bound consumer.**
It reads the unified snapshot, stamps the quote's provider + timestamp into its intents, only
closes `GENERATED` trades (bug fix), and follows the same freshness validation as everyone else
(one pipe, one rulebook). In real-data mode it trades the Finnhub universe at a gentle pace;
with the fallback flag on, it trades `SIMULATED` exactly as today. *Rejected:* retiring it —
the PDF permits it, the teacher wants demos, and HW6's "strategy runner" will grow out of it.

**D10 — Multi-currency PnL: minimal and honest.**
Valuations keep the instrument currency; `/books/summary` shows per-currency subtotals and one
converted total using the latest official reference rate (NBP/ECB), labeled with the rate's
as-of. The alpha/beta engine consumes the converted series — documented limitation, not hidden.
*Rejected for now:* full FX-aware risk (HW6+ territory).

---

## 4. Phase plan

Each phase ends demoable, with its phase report (build-order steps: needed → chosen → added)
feeding the docs and finance-hub updates. Estimates assume focused days.

### Phase 0 — Contracts, schema, config *(~1 day)*

- Tag the current state `pre-hw5-simulator` (the teacher's demo artifact).
- `shared/`: normalized quote + curve point contracts; provider registry (names, groups,
  capabilities); `shared/freshness.py`; `shared/symbols.py` (D4); per-provider config surface.
- **One hand-written migration** (mnemonic id, real docstring, per house style):
  spots + `provider_timestamp`, `received_at`, unique `(source, symbol, provider_timestamp)`,
  lookup index `(source, symbol, event_time desc)`; curves + `provider`, `as_of_date`; new
  `market_data_curve_points`; trades + D2 columns; valuations + `market_data_provider`,
  `market_data_timestamp`.
- `.env.example`: four API keys, per-provider intervals, `ENABLE_RANDOM_MARKET_DATA_FALLBACK`.
- Start `docs/market-data.md` — the data catalog skeleton: provider → endpoints → what the data
  is → why fetched → where used → where visible. Filled as each provider lands. **Starting this
  on day one is what makes the domain analysis real instead of retrofitted.**

### Phase 1 — Provider skeleton; first real quote end-to-end (Finnhub) *(~2 days)*

- `providers/base.py`: urllib client with timeout, key injection, error classification
  (transport / HTTP / rate-limit / business-empty), per-provider health state (last success,
  last error, last poll, error count), last-good retention.
- `SIMULATED` provider = the existing generator behind the provider interface (D1);
  `FINNHUB` provider + quote normalizer (mapping decisions documented: no bid/ask on the free
  quote endpoint → last + explicit basis).
- Polling scheduler (D7); persistence via idempotent upsert on the new unique key; provider-
  tagged SSE events (`provider` joins the tick payload); audit events for fetch/fail/persist.
- Endpoints: `/providers`, `/providers/<p>/health`, `/market-data/quotes...`,
  `POST /market-data/refresh`; snapshot gains the provider dimension (spot ids become
  `provider:symbol` — mirrored in the frontend instrument id).
- Pricing: cache keyed `(provider, symbol)`; tick→trade selection filters on the trade's frozen
  provider (legacy trades default to `SIMULATED`).
- trade-action: accepts + persists provider fields; validates "current quote exists from the
  chosen provider" by reading the spot table through `shared/freshness.py` (DB row is the
  handoff — no new service call).
- **Exit demo:** open an AAPL trade on a live Finnhub quote; watch its PnL stream off Finnhub
  data; the audit trail reads FETCHED → PERSISTED → TRADE_CREATED with one correlation story.

### Phase 2 — Provider breadth, freshness, ticket comparison *(~2 days)*

- Alpha Vantage + Twelve Data clients/normalizers; symbol master in use; per-provider budgets
  + backoff + rate-limit classification live; refresh guarded by budget.
- Freshness engine on the wire (LIVE/STALE/MISSING per provider+symbol); trade-action enforces
  D3 server-side (reject MISSING; record STALE acknowledgement).
- **Ticket v2**: three-provider comparison row (bid/ask/last, status pill, timestamp), provider
  selection, STALE confirm flow, MISSING disabled, optional comment; intent carries provider +
  price + timestamp + quote ref.
- Providers health card on the monitoring screen (status, last success/error, error count,
  calls used vs budget, next poll).
- **Exit demo:** the comparison row disagrees between providers (show the spread); kill one API
  key → that provider degrades visibly while the system trades on the others.

### Phase 3 — Official data: NBP / ECB / FRED and curve ETL *(~2 days)*

- Three Group-B clients: NBP FX tables (A mid, C bid/ask), ECB EXR + yield-curve dataflow,
  FRED series observations with a tenor-mapped series registry.
- Curve ETL: points → `market_data_curve_points` → assembled curves (D5/D6) → provider-tagged
  `curve_tick` events; `/curves`, `/curves/<provider>`, `POST /curves/refresh`.
- FX reference rates stored as NBP/ECB quotes with daily thresholds.
- Market Data view: multi-curve section (name, currency, provider, as-of) + curve inspector
  (points with per-point provenance).
- **Exit demo:** three real curves on screen; click any point → the FRED/ECB series and raw
  response that produced it.

### Phase 4 — Multi-curve pricing and currency discipline *(~1.5 days)*

- Pricing cache holds a curve registry (name → curve + currency + provider); `market_inputs`
  returns `discount_curve` + `projection_curve`; `trades_for_curve` matches the set.
- `TERM_SCHEMAS`: IRS gains `settlement_currency`, `discount_curve`, `projection_curve`
  (choices from the registry) — ticket pickers appear without frontend work; bonds get the
  currency check; `validate_terms` stops hardcoding USD.
- Server-side rule: **curve currency must equal settlement currency** (trade-action +
  `/price` preview both reject with the reason).
- Books summary: per-currency subtotals + reference-rate-converted total (D10).
- **Exit demo:** the teacher's scenario verbatim — a PLN swap with PLN discount and chosen
  projection curve prices; the same swap pointed at `USD_TREASURY` is rejected with a readable
  reason.

### Phase 5 — Provenance UX and view polish *(~1.5 days)*

- Trade detail: provenance block — provider, entry price, price timestamp, quote ref, link into
  the story panel (the audit fetch → the trade).
- Provider column through Trades/Valuations/blotter; valuation SSE payload matches the PDF
  example (provider, market_data_timestamp, current vs entry price).
- Valuation blocked on missing provider data → honest UI state + `VALUATION_BLOCKED` audit.
- Frontend freshness switched to provider timestamps for quotes (per-provider thresholds from
  the snapshot payload).
- **Exit demo:** click any trade and answer "why this price, from whom, when, and what did the
  provider actually send" without leaving the screen.

### Phase 6 — Hardening, performance, documentation *(~2 days)*

- Idempotency proof (duplicate poll → zero duplicate rows); restart warm-start from last-good
  DB state; SSE reconnect behavior with real cadences.
- **Stress test + profiling** (teacher's ask): crank `SIMULATED` rates + open-trade count,
  record `docker stats` (CPU/RSS per container) before/after, find the first bottleneck;
  extend `docs/performance.md` with the numbers.
- D8 Decimal conversion + scenario-bug fix + telescoping re-verification.
- README overhaul to the PDF's section list (architecture, per-provider endpoint docs, keys
  how-to, schema, normalization + price basis, curve construction, ticket, PnL rules, STALE
  policy + rationale, run + test commands, known limitations). Finish `docs/market-data.md`;
  update `architecture.md`, `pricing.md` (multi-curve), `decisions.md` (D1–D10 rows),
  consolidated limitations.
- Write down the carry-over answers: market-index stream (one stream, both consumers), log
  security/geo-redundancy position, log write-queueing note (in `logging.md`).

---

## 5. Portfolio angle — what makes this build stand out

The scope filter stays the house rule (*"zbyt duży zakres"* is the homework's own pitfall):
every idea below is a small delta on required work, not a new subsystem.

1. **"Why this price" provenance drill** (Phase 5) — trade → provider → quote → raw payload →
   audit story in one click. Reproducible PnL is the most finance-credible property this system
   can demonstrate, and it's an extension of the existing story panel, not new infra.
2. **Rate limits as visible operations** (Phase 2) — the providers card showing budget spent,
   backoff state, next poll. Turns the ugliest constraint of free APIs into the most
   operational-looking screen in the demo.
3. **Provider disagreement, quantified** (Phase 2) — the comparison row computes the spread
   between sources in bps and flags divergence. One derived number that shows you *analyzed*
   the data instead of piping it.
4. **The PLN curve investigation** (Phase 3) — a written, honest "how do you build a PLN
   discount curve from free official data" note (NBP has no rates API; WIBOR is licensed; what
   proxies exist and what they cost in correctness). Exactly the teacher's "co pobieram i po
   co" — and nobody else in the group will have it.
5. **Two real EUR curves → real projection/discount choice** (Phases 3–4) — the dual-curve swap
   machinery finally fed two genuine curves, selected on the ticket, currency-validated.
6. **STALE policy argued from market hours** (Phase 2 + README) — weekend-aware reasoning for
   warn-vs-block reads like desk experience, not homework.
7. **Real benchmark for alpha/beta** (one env var) — `BENCHMARK_SYMBOL=SPY` closes the
   "self-referential benchmark" limitation and proves the estimator survived the switch
   untouched, exactly as `decisions.md` bet it would.
8. **Stress test with numbers** (Phase 6) — `docker stats` before/after tables in
   `performance.md`. Directly requested, rarely done, cheap.
9. **The demo story** — fallback flag + `pre-hw5-simulator` tag: one system, flip a flag,
   synthetic vs real. That *is* the teacher's "coś do dema".

Deliberately **not** in scope: vol surface/Greeks, order matching, auth, message broker,
websocket feeds, an instruments table, backtesting UI (that's HW6's opening).

---

## 6. finance-hub — learning content plan

The hub's own rulebook says most of HW5 is *implementation evidence for existing owners*, not
new pages (`project-concept-map.md` §10: "To jest praca implementacyjna, nie treściowa";
one-owner rule K-16). The work splits into bookkeeping now, modules per the wave plan, and
evidence updates as code lands.

### Now (bookkeeping, ~1 short session)

1. **Propagate kurs-5 into `action-items.json`** — the 14 items from
   `kurs-5-topics.md:710-739` are entirely missing (sources stop at kurs-4). Includes the two
   load-bearing ones: Docker profiling, context-manager prep.
2. **Fix the dead reference** `hw5-notes.md:158` (points at deleted
   `docs/implementation-plan.md`; the successor is `docs/README.md` "What comes next" — and,
   once merged, this plan file).
3. **Resolve the two phantom slugs** in `hw5-notes.md:159`: assign curve ETL → M13 (+M10) and
   rate-limits/backoff → M10 (+M49) per K-16, or register them properly; today they exist
   nowhere else in the repo.
4. **Re-evidence stale register entries**: `context-managers` (evidence still says "slot after
   next lesson" — the lesson happened; add kurs-5 E1 quotes + L14A, raise ceiling),
   `float-precision` (add L13A/L14A + kurs-5 B27), `benchmarking-culture` (add the [00:16:37]
   direct question).
5. **Stale inventories**: `presentations-inventory.md` (stops at L11A — register presentation
   14, note 13 was never shared), `advanced-path-coverage.md` (no L13/L14).

### Modules (per the v3 wave plan — write, don't restructure)

- **M38 `context-managery`** — completes W9; fully carded (`MODULE-MAP.md:1343-1380`) with
  kurs-5 ceiling quotes and Part III anchored on this repo's own `session_scope`, locks and SSE
  hub. The v2 `context-managers.mdx` lacks everything kurs-5 added (`return True` anti-pattern
  with the "someone changes the body" argument, `ExitStack`, `decimal.localcontext`,
  instructor's ranking).
- **M07 / M08** (float precision, runtime errors) — already written, sitting uncommitted in the
  working tree; run the gates and commit as W9 progresses.
- **M40 `profilowanie-i-pomiar`** — head of W11; its carded opening question *is* the kurs-5
  profiling exchange, and HW5's Phase 6 stress-test numbers become its Part III evidence.
- **Add the genuinely uncovered concept**: concurrent file writes / write queueing (ceiling S7,
  defense question K5-Q2, "obecnie luka") — extend the M50 `architektura-logow` card with it so
  it has an owner before M50 is written.

### As HW5 code lands (evidence updates, end of each phase)

Update the "Stan implementacji / granica projektu" sections of the owner pages —
`market-data-provenance-normalization` (adapters + provider-bound trades arrive: its stated
project boundary falls), `instrument-reference-data` (symbol master exists), 
`market-data-staleness` (gains a project-state section it currently lacks; MISSING becomes
real), `market-data-curves-scenarios`/M13 (multi-curve, real ETL), `trade-lifecycle` +
`pnl-book-aggregation` (provider consistency section), `audit-trail-compliance` (provider
events), `sqlalchemy-alembic` (the HW5 migration as the worked example) — plus flip the
matching "Stan implementacji" lines in `hw5-notes.md`. Each phase report is the raw material;
the hub update is its distillation.

### Defense prep (before the next session)

The four kurs-5 questions with prepared answers: log security/geo-redundancy (Q1 — position:
files stay node-local, readable only via the monitoring reader; cross-site would move to a
shipper + authenticated transport, and ssh-only access is the interim answer the teacher
himself described); write queueing (Q2 — analysis note + M50 concept); market index
poll-vs-stream (Q3 — one stream, both consumers, now documented); plus the Decimal audit
result (what was float, what is now Decimal, and why Black–Scholes stays float).

---

## 7. Open questions (small, non-blocking)

- **D1 confirmation** with the teacher if a natural moment appears (new-service-by-letter vs
  provider-ized generator by intent). The plan proceeds on D1 as written.
- Alpha Vantage's current free-tier daily budget (changes over time) — verify at key signup;
  only affects its poll schedule constants.
- FRED's OECD Poland series availability (D6) — decides which PLN composite variant ships;
  both variants are planned for.
- Whether to audit every valuation update or a throttled subset (PDF lists the event; house
  rule says per-tick events are DEBUG) — decide in Phase 5 with real cadences in hand and
  document the choice in README.
