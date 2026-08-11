# Implementation plan — finishing trading-microservices

2026-08-09 · Plan of record, supersedes `docs/frontend-plan.md` (deleted; history in git) and
`docs/minimal-advanced-pricing.md` (deleted; documented the first options/IRS attempt this plan
refactors). Sources: instructor review sessions kurs-3 (2026-07-31 analysis) and kurs-4
(2026-08-09, transcript analysis in finance-hub), plus a full code audit of the working tree
(uncommitted change set: +694/−172 across 27 files).

**Revised 2026-08-10 — simplification pass.** B1, A1 and C1 were re-scoped against what the
homework PDF (`praca_domowa_04`) actually requires and what the kurs-4 session actually decided.
Rule applied throughout: the PDF is the graded contract and it *explicitly allows* the simple
models; the session recap raises the bar on **understanding**, not on implementation. Where the
old plan added machinery beyond both (second published curve, alpha/beta engine rewrite), it was
cut. Rationale in "Why this shape" below.

## Why a refactor, in one paragraph

The first options/IRS implementation works end-to-end but was judged insufficient. The
instructor's core critique (kurs-4 [00:03:17]–[00:09:16]): the **instrument catalog is too
static** — `ACME_CALL_100_6M` hardcodes strike/underlying/maturity, while the sell-side world
(his JP Morgan framing) defines instrument parameters arbitrarily and publishes new instruments
to the market; the New Trade form should adapt its fields to the instrument *type*, not pick
from a fixed list. He explicitly suggested JSONB for the terms (already partially true:
catalog terms are copied into `trade_metadata` JSONB at open). Additionally the IRS float leg
uses the single-curve shortcut `notional × (1 − DF(maturity))`, whereas the kurs-4 recap
[00:17:56]–[00:21:41] teaches the two-curve model (common **discount curve** + separate
**projection curve** for forecasting the floating rate). On top of that the audit found
integration gaps: scenario engine can't price the new products, alpha/beta is published by the
backend but hardcoded to `'n/a'` in the UI, the trade generator ignores derivatives, tests
exist only as a stale `.pyc`, and no Alembic migration was written ("Alembic first" was the
old plan's own rule).

## Workstream A — generic instrument catalog (the refactor core)

Goal: instruments become *typed templates + per-trade terms*, not fixed products.

- **A1. Schema audit + README note (no migration needed for B/C).** Code audit 2026-08-10:
  `trades.asset_class` is `Text` (not a DB enum) and per-trade terms already land in
  `trade_metadata JSONB` — the schema supports EUROPEAN_OPTION/IRS as-is. This *is* one of the
  approaches the homework explicitly lists as acceptable ("dodanie elastycznej kolumny
  JSON/JSONB z parametrami instrumentu"); the PDF's only hard demand is that the structure be
  coherent and **well described**. Deliverable: README data-model section explaining the
  choice. The `instruments` table (`symbol`, `asset_class`, `display_name`, `terms JSONB`,
  `is_active`, seeded from `INSTRUMENT_CATALOG`) moves to A2 — write that migration when the
  generic-catalog work actually starts, not before. Trades keep `trade_metadata` as the frozen
  terms snapshot at execution — already the case, keep it.
- **A2. Term schemas per asset class. DONE 2026-08-10 (per Jakub's request).**
  `shared/term_schemas.py`: one declaration per OTC class (`EUROPEAN_OPTION`, `IRS`) of fields,
  types, bounds, and defaults (curve, multiplier, volatility); `validate_terms` is the single
  validator used by trade-action on OPEN and by pricing for previews. Trade-action requires
  `terms` for OTC opens (with a symbol-format check) and uses the catalog for listed opens.
  **Catalog split (same day, Jakub):** the pre-baked derivative entries (`ACME_CALL_100_6M`,
  `USD_IRS_*`) were removed — `INSTRUMENT_CATALOG` now holds listed/quoted instruments only;
  OTC products are always defined by terms. Existing trades unaffected (frozen terms).
- **A3. Adaptive New Trade form. DONE 2026-08-10.** The form fetches the schemas
  (`GET /instruments/term-schemas`) and renders fields from the schema of the chosen asset
  class. No mode toggle: a listed class shows the instrument picker (buy-side: quote what
  exists), an OTC class shows term fields (sell-side: underlying/strike/maturity etc., rates in
  percent, symbol derived from the terms by a fixed naming scheme — read-only, never typed —
  live backend-mark preview from the ad-hoc terms; volatility is a server-side default, not a
  user input).
- **A4. Pricing accepts ad-hoc terms. DONE 2026-08-10.** `POST /price` takes either
  `{symbol}` or `{asset_class, terms}` (validated through the same `validate_terms`).
  Still open from A-scope: the `instruments` table + publishing a defined instrument to a
  shared catalog (today a custom product exists only as the trade's frozen terms — another
  trader cannot pick it up), and removing the `0.22` vol fallback.

## Workstream B — valuation correctness + integration debt

- **B1. IRS float leg as projected cashflows — dual-curve *shaped*, single curve *fed*.**
  Refactor `irs_legs`: the float leg iterates the same payment schedule as the fixed leg; each
  period's floating rate is the forward implied from a **projection curve**
  (`DF_proj(t_prev)/DF_proj(t) − 1`), the cashflow `notional × fwd` is discounted off the
  **discount curve**. The `projection_curve` argument **defaults to the discount curve** — the
  instructor's own recap used the same curve for both at this level ("przyjmowaliśmy tą samą
  krzywą, bo jakkolwiek ma to sens"). Do **not** publish a second market-data curve: the PDF
  explicitly accepts `notional × (1 − DF(maturity))`, and with a single curve the new float leg
  telescopes to *exactly* that number — check it once by hand (see B5 note), and it doubles as
  the interview answer ("my float leg is the sum of projected cashflows; under one curve it
  collapses to the closed form"). A real projection curve becomes a one-argument change when
  real data arrives — suitability for free, no extra work now.
- **B2. Scenario engine parity.** `scenario.py` duplicates equity/FX/bond pricing and 404s on
  options/IRS. Rewrite `_base_price_from_cache`/`_shocked_price` on top of
  `price_instrument` with shocked inputs (spot bump for options via underlying, parallel curve
  bump for IRS/bonds). Kills the duplication and the gap in one move.
- **B3. Cache regressions.** `trades_for_curve` keys on `metadata.curve` — old bond trades
  without that key silently stop repricing; fix with a code fallback to asset-class match (no
  data migration needed). Fix `spot.get("mid") or spot.get("last")` zero-falsy chain with
  explicit None checks.
- **B4. Generator support decision.** Generator currently excludes derivatives and no longer
  tracks manually opened ones (`sync_open_trades` filter). Decision: generator keeps
  simulating cash products only (kurs-4: "Trade Generation Service stays a simulator"), but
  must **track** manually opened derivative trades again so equilibrium logic and books stay
  truthful.
- **B5. Cut (Jakub, 2026-08-10) — no test suite this phase.** One thing survives as a manual
  sanity check after B1: on a single curve the new float leg must reproduce
  `notional × (1 − DF(maturity))` to the cent (telescoping identity) — verify once in a REPL
  and note the identity in the README's pricing section; it's still the interview answer.
- **B6. Dedup `minimum_observations`** — one owner (`pricing_math.alpha_beta`); `book_risk.py`
  passes through.
- **B8. Generator learns about new books (added + DONE 2026-08-10).** The kurs-3 live test
  ([00:32:27]: a book created while the generator runs got no trades) exposed that
  `set_books(ensure_books())` ran once at startup. Now: books re-synced on the same 10 s
  cadence as open trades, inactive books excluded, and multiple books per asset class all
  receive generated flow. The kurs-3 sidebar feedback needed no work — `.content:has(.side-panel)`
  already pads the layout so the panel pushes the table instead of covering it.
- **B7. Real-data readiness — a design stance, not a work item (demoted 2026-08-10, Jakub).**
  No provider extraction this phase. The suitability requirement is met passively: the
  published market-data contract (tick/curve dicts over SSE + snapshot endpoints) is what
  consumers depend on, and real Yahoo data can be published through that same contract later.
  The only rule enforced *now*: code touched by this plan must not deepen synthetic coupling —
  no new hardcoded symbol literals, benchmark/curve names referenced from one place. The
  actual provider interface inside market-data-service is written when the real-data phase
  starts, not before.

## Workstream C — alpha/beta finish (agreed for "next week" in kurs-4)

Session decision [00:10:12]–[00:16:41], read precisely: what was rejected was Jakub's idea of
**building an index by averaging the generated ticks** (and generally investing effort in making
a synthetic index behave realistically). The agreed direction: accept simplifications now,
shaped so real S&P 500 data slots in later **without rework** ("żeby nie modyfikować jak już
[przejdziemy] na realne dane"). Static-percentage defaults were named as an *allowed*
simplification, not a requirement.

- **C1. Backend: keep the engine, change nothing in the math.** `pricing_math.alpha_beta` +
  `BookRiskEngine` already implement *exactly* the estimator printed in the homework PDF
  (rolling window ~100, `beta = cov/var`, `alpha = mean_book − beta·mean_bench`,
  `INSUFFICIENT_DATA` / `ZERO_BENCHMARK_VARIANCE` guards — both edge cases the PDF calls out),
  sampled against the `MARKET_INDEX` tick the PDF explicitly permits as benchmark ("benchmark
  może być jednym syntetycznym instrumentem… np. MARKET_INDEX"). Do **not** rewrite this to the
  static-expected-return model: that would replace working, PDF-conformant code with a model
  we'd rewrite *again* for real data — the exact churn the session said to avoid. The cov/var
  estimator is the one thing that runs unchanged on a real S&P 500 return series. The
  "no artificial index" decision is honored by freezing investment in `MARKET_INDEX` realism
  (no tick averaging, no dynamics tuning — it stays a dumb random walk) and by the C3 seam.
  Note the engine is already cadence-agnostic: it samples a return whenever a benchmark tick
  arrives, so when the benchmark becomes daily S&P 500 closes the window simply becomes ~100
  trading days — no change needed.
- **C2. UI.** `BookRiskCard` currently hardcodes `'n/a'` with the real implementation
  commented out — wire the published values, fix the dangling `" · "` footer;
  `BusinessOverview.jsx:33` must pass the risk map into `bookRisksOf` (today alpha/beta is
  always null there).
- **C3. Real-data suitability — passive only (demoted 2026-08-10, Jakub).** No dedicated seam
  work. Suitability is already structural: the estimator consumes any benchmark return series,
  and sampling funnels through a single point (`market_data_client`'s benchmark check). While
  touching that file for other reasons, read the benchmark symbol from one constant/config
  entry instead of an inline literal — that's the entire concession to the future. Real S&P
  500 later = point that constant at the real series. Entry prices still from the simulator
  (kurs-4 decision: Trade Generation Service stays a simulator; only market data becomes
  real).
- **C4. Hedge-aware exposure — parked.** Instructor flagged option-hedge exposure netting as
  "nietrywialne"; explicitly out of scope for the simplified version, listed as a known
  limitation (good defend-it material).

## Workstream D — logging / observability (open for 3 sessions; must close)

Design anchor: the kurs-2 "sweeper" discussion — per-service log **files** (dated,
size-rotated), a collector reads them; do *not* stuff Postgres with logs ("postgres 50 GB
zapchany logami"), and remember a DB-connection failure can't be logged to the DB.

- **D1. File sink.** structlog already renders JSON to stdout; add a rotating file handler per
  service (shared/logging_config.py), volume-mounted so files survive container restarts.
- **D2. Sweeper/collector.** Extend monitoring-service: a thread scanning the mounted log dir,
  tailing each service's current file, keeping an in-memory ring buffer (bounded, like the
  audit cap of 100/5 min) + `GET /logs?service=&level=&since=` endpoint. No DB writes.
- **D3. UI.** Logs panel per service (kurs-1 feedback: logs per microservice, not on
  overview) with level filter and correlation-id search linking to audit events.
- **D4. E5 leftovers from the old plan.** `DEPENDENCY_DOWN`/`RECOVERED` and
  `WORKER_FAILED`/`RECOVERED` transition audits; per-action processing latency so the
  "average processing time" stat and per-row `ms` stop rendering `n/a`.

## Workstream E — finish & submission

- **E1. Commit strategy.** The +694/−172 change set is uncommitted. Land it as reviewable
  commits *after* B1–B3 refactor (avoid committing the shortcut IRS then immediately rewriting
  it): (1) enums+catalog+migration, (2) pricing math + tests, (3) pricing service integration,
  (4) trade-action/generator, (5) frontend, (6) docs.
- **E2. Cut (Jakub, 2026-08-10)** — no new `.http` scenario collections this phase.
- **E3. README.** Rewrite the "Minimal derivative calculations" section after B1 (float leg as
  projected cashflows + the telescoping identity), add the submission items the old plan still
  listed: proxy explanation, benchmark choice and why (PDF requires this explicitly), which
  views poll and why, why Monitoring has no sidebar page, why top-level PnL sits on Business
  Overview, WARNING-severity departure from the errors mockup, data-model note from A1.
- **E4. Cut (Jakub, 2026-08-10)** — no wireframe exports.
- **E5. Defend-your-project sync.** Every workstream ends by updating the finance-hub
  "defend-project-architecture" material: decision, alternatives, known limitations. The
  project is a portfolio piece; kurs-4 [00:35:13]: as a generic Python/React project it looks
  good, but finance employers will expect deeper process realism — that framing drives what we
  polish.

## Order and sizing

| # | Item | Size | Depends on |
|---|------|------|-----------|
| 1 | A1 schema audit + README data-model note | S | — |
| 2 | B1 float-leg refactor (+ one-off identity check) | S | — |
| 3 | B2 scenario parity + B3 cache fixes + B6 | M | B1 |
| 4 | C2 alpha/beta UI wiring (C1/C3 = no code beyond one constant) | S | — |
| 5 | E1 commits land here | S | 2–4 |
| 6 | D1–D4 logging pack — hw5 re-requires this audit/log infrastructure | M/L | — (parallel ok) |
| 7 | B4 generator tracking | S | — |
| 8 | A2–A4 generic catalog + adaptive form — DONE 2026-08-10 except `instruments` table/publishing | L | — |
| 9 | E3 README | S | all above |

Kurs-4 expectations for next session: alpha/beta demoed (4), visible progress on logs (6).
The generic catalog (8) is explicitly "not core, but would be good" — it can trail. Cut
entirely per Jakub 2026-08-10: test suite (B5), `.http` scenario collections (E2), wireframe
exports (E4), and any *active* future-proofing (B7/C3 demoted to a design stance: don't deepen
synthetic coupling; the Yahoo provider gets written when that phase starts). The graded
critical path is now: float-leg refactor, scenario/cache fixes, alpha/beta UI wiring, README.

## Homework 5 readiness (checked 2026-08-10, do not build yet)

Homework 5 (`praca_domowa_05_real_market_data_integration.pdf`) replaces the random
generator as the primary data source: Alpha Vantage / Finnhub / Twelve Data quote listed
instruments, NBP / ECB / FRED feed reference curves, market-data-service becomes the only
external gateway (own HTTP clients, no SDKs/requests), and every trade freezes the provider
it was created from — PnL is computed from that provider forever.

**Phase-7 decisions that hw5 confirms — no rework:**

- **Trading ticket already exists.** hw5: "if the student didn't prepare it in the previous
  homework, they must add it now" — NewTradePanel is that ticket. hw5 additions are purely
  additive: 3-provider comparison row, provider picker, LIVE/STALE/MISSING badge, optional
  comment. The "cannot trade without a current price" rule is already enforced.
- **Listed-vs-OTC split is hw5's data topology.** Group A providers quote exactly the listed
  catalog classes; Group B feeds the curves that price OTC (IRS, options) and bonds. Nothing
  about the split needs to move.
- **`market_inputs` / `price_from_inputs` seam.** Provider selection is a market_inputs
  concern only (which quote/curve to read); pricing math is untouched. The frozen
  `metadata` JSONB extends to `market_data_provider`, `reference_price_timestamp`,
  `snapshot_id` — same freeze-at-open pattern as terms.
- **`first_present(("mid","last","spot"))`** is hw5 "typowe problemy #3" (missing bid/ask)
  already solved; the mapping decision just needs a README sentence.
- **Curve as the only rate authority** means the FRED treasury curve arrives as *data*
  (a curve named e.g. USD_TREASURY), not a code change; `DEFAULT_CURVE` is one constant.
- **Random generator survives as the sanctioned fallback** (`ENABLE_RANDOM_MARKET_DATA_FALLBACK`)
  — hw5 explicitly allows it as a technical fallback, so nothing built this phase is wasted.
- **Already compliant infrastructure:** structlog in all 7 services, `write_audit` everywhere,
  Alembic, MarketDataSpotPrices/Curves/Snapshots with `raw_payload` (spot even has a
  `source` column — the provider column in embryo), and the Vite proxy already uses the
  relative-path pattern hw5 prescribes verbatim.

**Structural deltas hw5 will force (decide then, not now):**

- **Provider becomes a key dimension.** Internal stream and pricing cache are keyed by
  symbol today; hw5 needs (provider, symbol). Biggest single change; touches cache,
  tick handling, and the ticket's price subscription.
- market-data-service grows `providers/`, `normalization/`, polling scheduler, provider
  health — new modules beside the generator, which demotes to fallback.
- Real symbols (AAPL…) enter the listed catalog; the symbol-mapping layer
  (internal_symbol vs provider_symbol) naturally lives in catalog entries.
- Migrations: provider columns on Trades/Valuations (or the metadata JSONB), provider +
  `as_of_date` on curves, spot `source` default stops being `'SIMULATED'`.
- **Benchmark decision:** MARKET_INDEX only exists in the synthetic generator. Either the
  fallback keeps publishing it, or alpha/beta re-benchmarks to a real symbol (e.g. SPY via
  the providers). Flag for the hw5 design pass.

**Priority effect now:** D1–D4 logging is doubly required — hw5's mandatory audit-event
list (provider fetch, fetch failure, rate-limit hit, quote/curve writes, valuation-failure-
due-to-missing-provider-data) lands on this infrastructure. E1 commits should land before
hw5 work starts so the phase boundary is clean in history. No pre-emptive hw5 code:
anything built now would guess at the normalized-stream shape.

## Why this shape — rationale for the 2026-08-10 revision

**Two authorities, one rule.** The homework PDF is the graded contract; the kurs-4 session is
direction and depth-of-understanding. Wherever they seem to conflict, the resolution is: build
what the PDF grades, *understand* what the session teaches, and leave a named seam where the
session points at the future. Nothing in either source requires machinery beyond that — the PDF
literally says the goal is "poprawne zaprojektowanie struktury danych, przepływu informacji i
uproszczonych modeli obliczeniowych", not "pełny profesjonalny system wyceny", and its
known-pitfalls list ends with "Zbyt duży zakres" as pitfall #15.

**Real-data compatibility is the tiebreaker, and existing code has no tenure.** The session is
explicit that the next phase replaces the data, not the mechanism: Yahoo Finance quotes for
actually-listed instruments become the base, the Trade Generation Service stays a simulator,
and "pewnie trzeba będzie jakieś modyfikacje zrobić pod kątem elastyczności tego rozwiązania".
So every decision below is ranked by one question: *does this survive the switch to real
market data unchanged?* — not by whether code already exists. Under that criterion this phase
**fully replaces** what is synthetic-shaped (the IRS float-leg closed form → projected
cashflows; the scenario engine's duplicated pricing → `price_instrument`) and **keeps** what
already is the real-data shape (the cov/var estimator, the SSE tick/curve contract, JSONB
terms). Suitability is passive, not a project (Jakub's call): no provider abstractions or
seams built ahead of need — only the rule that code touched now must not add new synthetic
coupling (no fresh hardcoded symbols; benchmark/curve names referenced from one place). "It
works today" is never the argument; "it works identically on real data" is.

**IRS — why the middle road.** Three options existed. (a) Keep `notional × (1 − DF)` untouched:
PDF-compliant, but the code then shows nothing of the two-leg/two-curve model the instructor
recapped and flagged as interview material — the float leg looks like a magic formula. (b) Full
dual-curve with a published `USD_PROJ` feed: demanded by nobody — the PDF blesses the closed
form, the instructor said course-level generality "jest wystarczające" at fund interviews and
used the same curve as projection in his own recap; the feed would drag market-data generator,
persistence, curve consumers and UI into scope for zero graded credit. (c) **Chosen:** float leg
as a per-period sum of forward-implied cashflows with `projection_curve` defaulting to the
discount curve. It produces the *same number* as the PDF formula (telescoping — verified once
by hand, documented in README), makes the code read exactly like the lesson ("fixed leg: known
coupons discounted; float leg: rates from the projection curve, same discounting"), and makes a
real projection curve a one-argument change later. Cost: one ~10-line loop plus a 3-line
forward-rate helper — every
piece defensible on a whiteboard at Jakub's current level (a forward rate is just a ratio of two
discount factors; no bootstrapping, no interpolation beyond the existing linear `rate_at`).

**Alpha/beta — why the estimator stays and everything around it opens up.** The old C1
("rewrite to static expected-return/exposure defaults") over-read the session. What Jakub
proposed and the instructor rejected was *constructing* an index by averaging generated ticks;
what the instructor offered — static defaults — was a floor ("możesz przyjąć uproszczenia"),
not a target, and it fails the tiebreaker: a static-default model is a synthetic-era artifact
that would have to be rewritten the day real S&P 500 returns arrive. The rolling cov/var
estimator is the opposite case — it is *defined* over a real return series; today it merely
runs on a fake one. The PDF prints exactly this estimator (rolling window ~100, cov/var beta,
mean-residual alpha, too-few-observations and zero-variance guards) and permits `MARKET_INDEX`
as an interim benchmark — and `pricing_math.alpha_beta` + `BookRiskEngine` already implement
all of it, including both guard statuses and cadence-agnostic sampling (per benchmark tick now,
per daily close later). So the estimator is kept **because it is the real-data shape**, not
because it exists. The synthetic parts around it stay swappable without dedicated work: the
benchmark symbol lives in one constant (C3), the index stays a dumb random walk with zero
further investment. Remaining deliverables: wire
the UI (C2 — the only reason alpha/beta "doesn't exist" in demos today) and the README defense
the PDF demands ("opisz świadomie, jaki benchmark został przyjęty i dlaczego"): *synthetic
benchmark per HW4 allowance; unrealistic dynamics — known limitation; replaced by real S&P 500
through the benchmark/provider seams in HW5; hedge-aware exposure netting parked as nontrivial
per instructor.*

**Migrations — why "audit" beats "write one anyway".** The PDF requires migrations *if* the
schema can't hold the new classes ("Jeżeli istniejąca struktura tabel… nie pozwala"). It can:
`asset_class` is `Text`, terms live in `trade_metadata JSONB` — which is verbatim one of the
PDF's acceptable approaches. What the PDF actually grades is coherence and description, so the
deliverable is the README data-model section. Writing an `instruments` table now would couple
the graded core to the generic-catalog side quest the instructor explicitly labeled "nie core
feature na ten moment".

**Net effect.** The revision removes work that served neither the grade nor the real-data
future (market-data second curve, engine rewrite, premature migration, and — per Jakub's cuts —
tests, `.http` collections, wireframes, anticipatory seam-building). What's added is minimal:
one small float-leg loop, one constant, UI wiring, one README section. Complexity goes where
the grade and the demo are: working data flow on screen and honest documentation of
simplifications — which doubles as defend-your-project material (E5).

## Deliberately out of scope (unchanged decisions)

Vol feed / implied vol, option time decay between sessions, Greeks, separate risk service,
hedge-aware exposure netting (C4), real order matching. Each is a one-line "known limitation"
in README — honest limits beat half-features in a portfolio review.
