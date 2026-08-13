# Decision register

Every fork where a different choice was plausible: what was picked, what was rejected, and the
one-line reason. The full argument lives in the linked document — this page exists so you can
find it, and so a question like "why isn't there a message broker?" has a direct answer.

Read the **Rejected** column carefully: it is the half that shows the decision was made rather
than defaulted into.

## Architecture

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| Service-to-service handoff | The database row; consumers poll | Message broker, direct HTTP calls | A restarting service rebuilds its world from one source of truth, with no replay protocol and no liveness coupling. Cost: ~2 s propagation | [architecture](architecture.md#2-three-rules-that-explain-most-of-the-code) |
| Who may write `trades` | Only trade-action-service | Each service writing what it needs | "Move trades between books" becomes an intent, not a cross-service UPDATE; one place to audit and validate | [architecture](architecture.md#2-three-rules-that-explain-most-of-the-code) |
| Destructive precondition unverifiable | Fail closed (`503`) | Assume it is safe | An unavailable dependency is not permission to delete | [architecture](architecture.md#2-three-rules-that-explain-most-of-the-code) |
| Write acknowledgement | `202 Accepted` + confirm by observation | Synchronous execution, or optimistic UI rows | The queue is what makes manual and generated flow share one pipe; the UI never claims a queued action is done | [frontend](frontend/screens.md#5-writes--validate-submit-observe) |
| Browser → backend | Same-origin `/api/*` through the Vite proxy | Direct calls to container ports | The browser cannot resolve Docker DNS names, and seven services would each need CORS | [frontend](frontend/data.md#3-step-2--why-the-browser-talks-to-itself) |
| Monitoring vs System Overview | One screen | Two separate views | Both answer "is the system healthy right now?"; splitting them creates two pages competing to be opened first | [frontend](frontend/screens.md#9-where-each-views-logic-lives) |

## Data model

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| Instrument economics | Frozen into `metadata` JSONB at open | Look up the catalog at pricing time | A catalog change can never rewrite the economics of an executed trade | [pricing](pricing.md#2-terms-travel-with-the-trade) |
| Two new asset classes | No migration — `asset_class` is `TEXT`, terms are JSONB | Write an `instruments` table first | A migration is justified by a structure the schema *cannot* hold; this one could, and the homework lists JSONB as an accepted approach | [architecture](architecture.md#6-data-model) |
| Instrument definition | Listed = catalog pick; OTC = terms per trade | One catalog holding pre-baked derivatives | `ACME_CALL_100_6M` is a fixed call pretending to be *the* option you can trade — the static-catalog critique in object form | [pricing](pricing.md#listed-vs-otc-is-the-only-mode-switch) |
| Book retirement | Soft delete, guarded by zero ACTIVE trades | Hard delete, or unguarded flag | Closed trades and realized PnL still belong to the book | [architecture](architecture.md#6-data-model) |
| Trade symbol | Derived from terms by a fixed scheme | User-typed | Two people defining the same product get the same symbol; real conventions later change one function | [pricing](pricing.md#listed-vs-otc-is-the-only-mode-switch) |

## Pricing

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| IRS floating leg | Per-period forward-implied cashflows, projection curve defaulting to the discount curve | (a) the `N × (1 − DF(T))` closed form; (b) a second published curve | (a) is a magic formula that teaches nothing; (b) drags generator, persistence and UI into scope for no insight. The chosen form telescopes to (a) exactly — proven, verified to 1e-10 | [pricing](pricing.md#5-irs--the-float-leg-teaches-the-two-curve-model) |
| Normal CDF | `math.erf` | scipy | Exact identity, no dependency; the homework asks for it explicitly | [pricing](pricing.md#4-european-options--blackscholes-from-the-standard-library) |
| Risk-free rate in Black–Scholes | `−ln(DF)` from the curve | A separate rate parameter | One rate authority that cannot drift out of sync with the curve | [pricing](pricing.md#4-european-options--blackscholes-from-the-standard-library) |
| Volatility | A server-stamped default in the frozen terms | A field on the ticket | Vol is a pricing input, not a term of the contract; a real vol source later replaces the default's origin, not the form | [pricing](pricing.md#2-terms-travel-with-the-trade) |
| Scenario engine | Re-run the same pricing function with shocked inputs | Its own copy of each model | The old copy 404'd on options and IRS; two implementations can disagree about what an instrument is worth | [pricing](pricing.md#7-scenario-analysis--shock-the-inputs-not-the-price) |
| Zero-mark guard | Reject worthless opens, exempt IRS | One rule for all classes | An option premium of zero means economically empty; a swap PV of zero means struck at par | [pricing](pricing.md#2-terms-travel-with-the-trade) |
| Generator scope | Simulates cash only, but *tracks* every open trade | Generating derivatives too, or tracking only its own | Equilibrium logic must count reality; the simulator has no price authority over a manual derivative | [pricing](pricing.md#8-the-generator-simulates-cash-but-tracks-everything) |

## Risk (alpha / beta)

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| Estimator | Rolling cov/var regression over ~100 samples | Static expected-return/exposure defaults | cov/var is *defined* over a real return series; it survives the switch to real data untouched. A static model would be rewritten the day real returns arrive | [alpha-beta](alpha-beta.md) |
| Benchmark | The synthetic `MARKET_INDEX` basket, symbol in one constant | Constructing an index by averaging generated ticks; tuning synthetic dynamics | Investment in synthetic realism is thrown away at the real-data switch; a basket (not a single symbol) means no book is trivially β = 1 against its own instrument | [alpha-beta](alpha-beta.md#9-switching-to-real-market-data) |
| Sample storage | Raw `(ΔPnL, benchmark return)` in dollar space | Return space, divided by capital at sample time | Changing `BOOK_CAPITAL_BASE` rescales the next event instead of invalidating minutes of samples; and dollar exposures *add*, so portfolio aggregation is a sum | [alpha-beta](alpha-beta.md#4-the-1m-capital-base--what-it-is-and-is-not) |
| Reporting period | Window totals | Annualized alpha | ×15.7M periods/year turned minutes of noise into six-digit percentages. **Never annualize tick-cadence statistics** | [alpha-beta](alpha-beta.md#2-step-by-step-what-happens-on-every-benchmark-tick) |
| PnL series | Cumulative total (realized + unrealized) | Open positions only | Differences neutralize closed trades automatically; open-only would drop a trade's lifetime PnL in one sample — a fake, market-unrelated jump | [alpha-beta](alpha-beta.md#2-step-by-step-what-happens-on-every-benchmark-tick) |
| Not enough data | Publish `INSUFFICIENT_DATA` / `ZERO_BENCHMARK_VARIANCE` as values | Publish 0.0, or nothing | A status is information; a fabricated zero is a lie that renders identically to a real one | [alpha-beta](alpha-beta.md#3-reading-the-numbers) |
| PORTFOLIO card | A synthetic book through the identical engine | A special aggregation path | Dollar betas add, so the desk view is one summed series — and the additivity check doubles as an engine self-test | [alpha-beta](alpha-beta.md#5-the-portfolio-card) |
| Benchmark move in the attribution row | Σ of that book's own sampled returns | The compounded level move (`last / first − 1`) over a globally tracked history | The OLS identity sums per-sample returns, so only that sum makes the three rows add up. The compounded figure is a different quantity *and* spanned a different window — books start sampling late and reset when they leave the snapshot — so the row could disagree with the total in sign, not just in rounding | [alpha-beta](alpha-beta.md#the-breakdown-on-every-card) |

## Logging and observability

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| Where log lines go | Local files, tailed by a sweeper | (a) a `logs` table; (b) services POST to monitoring | (a) a DB failure cannot be logged to the DB, and volume bloats Postgres; (b) inverts the dependency — a service must never slow down because the observer is down | [logging](logging.md#2-the-shape-decision--files-and-a-sweeper) |
| Collector host | monitoring-service, one daemon thread | A separate shipper container; asyncio | Monitoring is already the observer and already proxied; the work is blocking file I/O, so async adds a scheduler in front of the same calls | [logging](logging.md#6-step-4--the-sweeper-collects-the-files) |
| Buffer shape | One `deque(maxlen)` **per service** | One shared buffer | Fairness: a service flipped to DEBUG floods only its own slots | [logging](logging.md#6-step-4--the-sweeper-collects-the-files) |
| Rotation policy | By size | By date | Every line already carries an ISO timestamp, and stdlib has no combined size+date handler | [logging](logging.md#3-step-1--every-service-writes-its-log-to-a-file) |
| Per-tick events | DEBUG | INFO | One `log.info` on a tick path grows files by MB/minute and makes the tail unreadable; the events still exist behind one env var | [logging](logging.md#4-step-2--keep-the-files-worth-reading-and-the-ids-findable) |
| Entity ids in logs | Always kwargs | Interpolated into the message | Structured keys are what search and the story panels key on; a message string is where ids go to be unfindable | [logging](logging.md#4-step-2--keep-the-files-worth-reading-and-the-ids-findable) |
| Exception rendering | Add `format_exc_info` to the processor chain | Leave `log.exception` as configured | Without it, JSONRenderer emitted `exc_info: true` and the traceback was lost everywhere — an error line that cannot say what failed | [logging](logging.md#3-step-1--every-service-writes-its-log-to-a-file) |
| Collector line ids | Clock-seeded counter + a per-process `run_id` | `itertools.count(1)` | Ids restarting at 1 froze open browser tabs and silently killed `since_id` cursors; the clock keeps them rising and the run id makes a restart observable | [logging](logging.md#step-6--ids-that-survive-a-restart) |
| Query strategy | Walk buffers newest-first, exit at `limit` | Filter and sort everything | With 70k buffered records the old path sorted all of them to answer `limit=1` (0.7 ms vs. a full sort) | [logging](logging.md#step-7--what-it-costs) |
| Story panel keys | Both `correlation_id` and `trade_id` | Only one of them | Neither is a superset: 311 of 400 audit rows had no entity id, 323 had no correlation id | [logging](logging.md#9-step-7--the-story-panels-two-ways-to-ask-a-question) |
| Audit write failure | Fail open (log it) for standalone audits; strict for session-bound ones | One rule for both | An observing audit must not kill the path it observes; an audit inside a business transaction must fail with it | [logging](logging.md#10-step-8--audit-trail-gaps-closed-on-the-way) |
| Dependency up/down | Audit only the transition | Audit every poll result | A state change is a business event; a 5-second poll result is not | [logging](logging.md#10-step-8--audit-trail-gaps-closed-on-the-way) |

## Frontend

| Decision | Chose | Rejected | Why | More |
| --- | --- | --- | --- | --- |
| Routing | Hash routes + a route registry | React Router | No nested routes or loaders are needed; hash routing needs no server fallback. One registry keeps menu and pages from drifting | [frontend](frontend/README.md) |
| State management | React state + two context feeds | Redux/Zustand | The only shared state is two feeds; a store would add ceremony without removing a problem | [frontend](frontend/data.md#7-feeds-live-above-routing) |
| Render rate | Coalesce into a Map, flush on one 500 ms clock | `setState` per event; sampling | Every event is still parsed — only intermediate *display* states are skipped. One shared clock beats several drifting timers | [frontend](frontend/data.md#6-steps-56--ingest-continuously-publish-on-a-clock) |
| Final valuations | Bypass the buffer, merge immediately, and win against later live values | Same path as every other update | A lifecycle transition must not wait behind display throttling or be undone by a stale in-flight value | [frontend](frontend/data.md#5-step-4--sse-and-what-eventsource-actually-is) |
| Hidden tabs | Keep streams connected | Close on `visibilitychange` | A snapshot cannot reconstruct the ticks missed while away; the saving costs real observations | [frontend](frontend/data.md#7-feeds-live-above-routing) |
| Sorting live columns | Capture comparison values at sort time | Sort on current values every render | Rows would jump continuously while you try to click one | [frontend](frontend/screens.md#3-tables--usetablestate-and-datatable) |
| Large tables | Bound the *rendered* rows, keep all data | Virtualization; or dropping data | 1,197 rows produced 361–472 ms tasks; a 250-row window cut them to 102–192 ms. Virtualization is the next step, not the first | [performance](performance.md) |
| Panel state identity | Explicit `key` per session | Rely on prop changes | React preserves a component of the same type and position, so Edit reused Create's state | [frontend](frontend/react.md#7-keys-identity-not-just-a-lint-rule) |
| Persistence | Workspace preferences yes, current question no | Persist filters too | Reopening on yesterday's filter is a bug that looks like a feature | [frontend](frontend/screens.md#4-filters) |
| Benchmark / log level in the UI | Backend config only | User toggles | Changing the benchmark invalidates every rolling window; log level has one owner. Neither is a per-user decision | [frontend](frontend/screens.md#4-filters) |
| Missing values | Explicit states (`PENDING`, `n/a`, `12/20 returns`) | Zeroes and empty screens | An invented zero renders identically to a real one | [frontend](frontend/screens.md#7-states-are-part-of-the-contract) |

## Scope

Things deliberately *not* built, each a known limitation instead of a half-feature: a test suite,
`.http` collections, an `instruments` table with publishing, a vol surface or Greeks, hedge-aware
exposure netting, log persistence beyond rotating files, external log stacks (ELK/Loki), runtime
log-level switching, log-based alerting, a separate risk service, and real order matching.

The rule behind that list, from the homework's own pitfall #15 (*"zbyt duży zakres"*): a working
data flow with honest documentation of its simplifications beats a wider surface of half-built
features.
