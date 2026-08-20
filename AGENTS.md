# Repository Guidelines

## Project Structure & Module Organization

The repository is a small trading platform composed of Python services and a React frontend. Service code lives in `services/<service>/app/`; every service builds from the single `docker/service.Dockerfile` with the shared root `requirements.txt`, and boots through `shared/service_runtime.py`. Shared database, domain, logging, serialization, and pricing utilities are in `shared/`. Alembic configuration and migrations live in `db/` and `alembic.ini`. The browser UI is in `frontend/src/`, organized into `views/`, reusable `components/`, `domain/` helpers, hooks, and API services. HTTP workflow examples are under `scenarios/`; documentation is in `docs/` — the base architecture, configuration and market-data references, the roadmap (`docs/implementation-roadmap.md`), and feature-oriented learning guides under `docs/implementation/` — with `docs/README.md` as the index. Documentation changes with the feature it describes and explains current behavior, data flow, decisions, constraints, and verification procedures rather than narrating the implementation process. Each feature guide opens with stable business decisions (polling windows, tiers, budgets, retention), and the same change updates the README's "Operating decisions" table and "Data flows" table whenever it adds, removes, or re-paces one.

## Build, Test, and Development Commands

- `docker compose up --build` builds and starts Postgres, migrations, all services, and the frontend.
- `docker compose down` stops the stack; add `-v` only when intentionally discarding local database data.
- `docker compose run --rm db-migrations alembic upgrade head` applies pending migrations.
- `cd frontend && npm install && npm run dev` starts the Vite frontend for UI work.
- `cd frontend && npm run build` creates a production frontend build.
- `cd frontend && npm run lint` runs Oxlint; `npm run deadcode` checks unused frontend code with Knip.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions, variables, and modules. Keep each service's transport handlers in `app/api.py`, configuration in `app/config.py`, and service-specific business logic in focused modules. Comments — in code, config, and Dockerfiles alike — serve exactly two purposes: a crucial in-place constraint, or a short stage marker inside a multi-stage process function (a polling loop, a guard ladder, a stream consumer) — a few words naming what the next block does, so a first-time read has the map. Never explanation or rationale, and no marker on a body that is a single obvious call. Docstrings fall under the same rule: at most a one-line contract where the name and signature genuinely cannot say it (an opaque tuple return, a non-obvious side effect). All rationale lives in `docs/` (knob rationale in `docs/configuration.md`, design reasoning in the relevant implementation guide). Database reads extract plain values (tuples, strings) inside the `session_scope()` block and never return ORM objects — commit expires managed instances, so attribute access after the block raises `DetachedInstanceError`; column queries (`session.query(Model.col, …)`) are safe, whole-entity results must be copied out. Environment variables are read only through `shared/config.py` helpers. Use two-space indentation in JavaScript/JSX, `camelCase` for functions and values, and `PascalCase` for React components. Name component files after their exported component, e.g. `TradeTable.jsx`; keep domain helpers lower camel case, e.g. `marketData.js`. Follow the existing import extensions and semicolon-free frontend style.

User-facing copy names market state, available actions, and constraints that affect a user's decision. Do not narrate implementation or loading strategy in the UI (for example, "loaded only when selected", "from PostgreSQL", or "via SSE"), and do not surface developer rationale as helper copy. Put those details in the relevant documentation. Keep status and helper text concise and actionable.

## Testing Guidelines

No unit-test suite by design: exercise affected API flows using the relevant `.http` file in `scenarios/` (for example, `scenarios/health.http`) and verify the stack with `docker compose up`. Scripted load scenarios record their measured results in `docs/performance.md`.

## Commit & Pull Request Guidelines

Recent history uses short, imperative, lowercase summaries such as `add books` and `valuation update`; keep commits narrowly scoped and similarly concise. Pull requests should describe the user-visible or service-level change, list validation performed, link related issues when applicable, and include screenshots for frontend changes. Call out database migrations, configuration changes, and compatibility impacts explicitly.

## Configuration & Data Safety

Use Compose environment variables for local credentials and endpoints; do not commit secrets. Treat migrations and queue/stream behavior as cross-service changes: validate consumers and producers together before merging.
