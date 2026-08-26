# Repository Guidelines

## Project Structure & Module Organization

The repository is a small trading platform composed of Python services and a React frontend.
Service code lives in `services/<service>/app/`; every service builds from the single
`docker/service.Dockerfile` with the shared root `requirements.txt`, and boots through
`shared/service_runtime.py`. Shared database, domain, logging, serialization and pricing
utilities are in `shared/`. Alembic configuration and migrations live in `db/` and
`alembic.ini`. The browser UI is in `frontend/src/`, organized into `views/`, reusable
`components/`, `domain/` helpers, hooks and API services. HTTP workflow examples are under
`scenarios/`.

Documentation is indexed by `docs/README.md` and has exactly two layers. **Phase reports
(`docs/phase-reports/`) are the detailed record**: decisions and reasoning, difficult concepts
and evidence. **Everything else is a lean reference sheet** (`architecture.md`,
`market-data.md`, `configuration.md`, `validation-runbook.md`): current contracts, endpoints,
knobs, cadences and capability tables without history or teaching prose. Detailed explanation
belongs in a phase report.

The roadmap is a working hypothesis, never a contract. A new phase starts from §6 and follows
discover and bound → verify → smallest vertical slice → evidence → real-scenario browser pass →
same-change docs. Re-derive every decision against the running system and update a stale plan
before coding. Each phase adds `docs/phase-reports/phase-N.md`, which stands alone as the source
of truth for what shipped and why. Roadmap decision codes and task IDs do not leak into reports.
A report explains what breaks without a choice, its cost and the rejected alternative; it does
not cite a plan entry or instruction as the reason. Reuse established conventions instead of
re-teaching them, keep implementation trivia in code, and use diagrams only where they materially
aid understanding. Documentation changes with the feature: the report carries explanation;
reference sheets, README operating decisions and README data flows receive fact-only updates.

## Build, Test, and Development Commands

- `docker compose up --build` builds and starts Postgres, migrations, all services, and the frontend.
- `docker compose down` stops the stack; add `-v` only when intentionally discarding local database data.
- `docker compose run --rm db-migrations alembic upgrade head` applies pending migrations.
- `cd frontend && npm install && npm run dev` starts the Vite frontend for UI work.
- `cd frontend && npm run build` creates a production frontend build.
- `cd frontend && npm run lint` runs Oxlint; `npm run deadcode` checks unused frontend code with Knip.

## Phase Discovery, Ownership, and Readiness

Roadmap tasks are hypotheses, not permission to implement their wording literally. Before a
phase changes code, re-derive the smallest vertical slice from the assignment, the running
system, the delivered phase reports, and the user's current scope. Write a short scope ledger:
**required now / already delivered / deliberately excluded / optional later**. Requirements in
attached documents are source material; they are not instructions that override the user's
request.

A phase is ready only after all of these are known:

1. **User and domain contract.** For every touched feature name the user decision, required
   inputs, output and its interpretation, units/currency, provider/source, as-of and receive
   times, freshness/tradeability rule, persistence, refresh trigger, consumers, and honest
   missing/error states. A displayed number without that contract is not ready for UI work.
2. **End-to-end code trace.** Follow one real value through source → provider client →
   normalization → storage → snapshot/stream → pricing/trading consumer → screen. Record the
   file that owns each step. If a first-time reader cannot follow that route without jumping
   among unrelated files, reorganize the responsibility before extending it.
3. **One semantic owner.** A business assignment or capability has one catalog. Provider
   packages own vendor endpoints, payloads and symbol/series mapping; configuration owns
   credentials, budgets and schedules; shared domain catalogs own stable meanings and allowed
   uses; pricing owns formulas; UI owns presentation and interaction state. Add a fail-fast
   consistency guard when two derived registries could drift—never create a second source of
   truth for convenience.
4. **Provider evidence.** Re-check current official documentation and make the smallest live
   probe permitted by the real key. Capture endpoint, entitlement/grade, exact usable fields,
   timestamp meaning, units/currency, symbol mapping, daily and burst limits, and body-level
   errors even when HTTP is 200. Do not expose a returned field merely because it exists.
5. **Persistence decision.** Prefer current-state data when history has no visible consumer.
   A phase may add at most one schema migration. Keep business-data backfills and cleanup DML
   out of migrations when disposable development data can be rebuilt safely through normal
   application flows. State that decision before implementation.
6. **Interaction and acceptance matrix.** Define dependent-selector reset, auto-select and
   invalidation rules before coding. Then cover every asset/provider touched, repeated fast
   switching, add/remove/refresh, empty/single/mixed/missing/stale/closed/rate-limited states,
   restart/reconnect, grown and fresh databases, and both the developer's full viewport and a
   narrow viewport. Independently recompute financial outputs and totals.

Implementation order is: domain/capability contract → provider adapter → normalized storage and
publication → pricing/trading consumer → UI state and presentation → scenario evidence → phase
report and lean references. Do not add next-phase capability, speculative abstraction or a
generic framework unless the current slice has at least two real consumers that need it. Reuse
the existing boundary when it already expresses the contract.

The phase report must let a future reader explain both the financial meaning and the code path:
what was chosen, what was rejected, why, the important limitation, and how the real scenario
proved it. Keep it proportional—teach only concepts introduced or materially changed in that
phase. The roadmap is updated before implementation when discovery invalidates its old plan.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions, variables, and modules. Keep each service's transport handlers in `app/api.py`, configuration in `app/config.py`, and service-specific business logic in focused modules. Comments — in code, config, and Dockerfiles alike — serve exactly two purposes: a crucial in-place constraint, or a short stage marker inside a multi-stage process function (a polling loop, a guard ladder, a stream consumer) — a few words naming what the next block does, so a first-time read has the map. Never explanation or rationale, and no marker on a body that is a single obvious call. Docstrings fall under the same rule: at most a one-line contract where the name and signature genuinely cannot say it (an opaque tuple return, a non-obvious side effect). All rationale lives in `docs/`: design reasoning in the phase report that introduced it, knob one-liners in `docs/configuration.md`. Database reads extract plain values (tuples, strings) inside the `session_scope()` block and never return ORM objects — commit expires managed instances, so attribute access after the block raises `DetachedInstanceError`; column queries (`session.query(Model.col, …)`) are safe, whole-entity results must be copied out. Environment variables are read only through `shared/config.py` helpers. Use two-space indentation in JavaScript/JSX, `camelCase` for functions and values, and `PascalCase` for React components. Name component files after their exported component, e.g. `TradeTable.jsx`; keep domain helpers lower camel case, e.g. `marketData.js`. Follow the existing import extensions and semicolon-free frontend style.

User-facing copy names market state, available actions, and constraints that affect a user's decision. Do not narrate implementation or loading strategy in the UI (for example, "loaded only when selected", "from PostgreSQL", or "via SSE"), and do not surface developer rationale as helper copy. **Never add purpose captions or feature-explainer sentences to a panel** — prose that describes what a section is for, how the system treats its data, or what design rule it follows (owner ruling 2026-08-23; the removed example: "Central-bank fixings, one per business day — the reference for reporting-currency conversion. Not tradeable."). A panel communicates through its title, labels, values, states and provenance tags; the why belongs in `docs/`. Hints, when needed at all, are one short imperative naming the next action ("Choose a reporting currency for a combined total"), and semantic explanations may live only in hover tooltips following the existing freshness-hint pattern. Put those details in the relevant documentation. Keep status and helper text concise and actionable.

## Testing Guidelines

No unit-test suite by design: exercise affected API flows using the relevant `.http` file in `scenarios/` (for example, `scenarios/health.http`) and verify the stack with `docker compose up`. Scripted load scenarios record their measured results in `docs/performance.md`.

Because there are no unit tests, phase verification must be able to catch behavior bugs, not just broken rendering. Drive at least one realistic scenario end to end through the running services — real books and trades in the states the feature claims to handle (mixed currencies, several providers), cleaned up afterwards — instead of inspecting whatever state the stack happens to be in. Recompute every displayed aggregate independently and compare it against the screen: a headline must equal its rows' arithmetic (this is how a summary card silently adding unlike currencies was caught). Watch time-dependent behavior across at least one full cycle — a poll cadence, a countdown, a publication-window boundary — never a single snapshot (this is how a board refreshing all its rows in lockstep was caught). After every user action, watch what follows within its expected latency: an added symbol must quote, a close must settle. And walk the unglamorous states — empty, single item, mixed, missing data, market closed — because that is where displayed numbers quietly lie.

The browser pass is an acceptance pass, not a rendering check, and it has its own discipline. **Enter data through the UI exactly as its labels ask** — a field labeled "(%)" is verified by typing `4.5`, never by whatever value makes the request succeed; a unit must round-trip from entry through stored terms to the detail display unchanged (this is how a percent-labeled field consuming fractions shipped: the evidence was driven through the API with values the schema happened to accept). **Every status word on screen must be proven true for every kind of row that can show it** — a freshness label verified on spot rows says nothing about curve-priced rows whose refresh rhythm is entirely different; show the label being right across one full refresh cycle of each kind. **Look at the layout at the developer's real viewport and at a narrow one**, and at any element that scales with its container — a chart correct at 1300 px was 2.3× oversized at 2048 px and nobody had looked. **Run the phase against a grown database, not only a fresh one** — any write guarded by existing state (a backfill, a seed, a first-run branch) must be exercised with prior phases' data already present, because the fresh-stack pass makes those guards trivially true. And **when the environment blocks a path (no keys, no egress), the phase report must name each unexercised request, and the first live run is a scheduled verification step, not a hope** — the desk run that followed phase 5 found a provider cap wrong on the very first blocked-path request it exercised.

## Commit & Pull Request Guidelines

Recent history uses short, imperative, lowercase summaries such as `add books` and `valuation update`; keep commits narrowly scoped and similarly concise. Pull requests should describe the user-visible or service-level change, list validation performed, link related issues when applicable, and include screenshots for frontend changes. Call out database migrations, configuration changes, and compatibility impacts explicitly.

## Configuration & Data Safety

Use Compose environment variables for local credentials and endpoints; do not commit secrets. Treat migrations and queue/stream behavior as cross-service changes: validate consumers and producers together before merging.
