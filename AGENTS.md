# Repository Guidelines

## Project Structure & Module Organization

The repository is a small trading platform composed of Python services and a React frontend. Service code lives in `services/<service>/app/`; each service has its own `requirements.txt` and `Dockerfile`. Shared database, domain, logging, serialization, and pricing utilities are in `shared/`. Alembic configuration and migrations live in `db/` and `alembic.ini`. The browser UI is in `frontend/src/`, organized into `views/`, reusable `components/`, `domain/` helpers, hooks, and API services. HTTP workflow examples are under `scenarios/`; documentation is in `docs/`, organized by topic (architecture, pricing, alpha/beta, logging, performance, decisions, and a `frontend/` set) with `docs/README.md` as the index.

## Build, Test, and Development Commands

- `docker compose up --build` builds and starts Postgres, migrations, all services, and the frontend.
- `docker compose down` stops the stack; add `-v` only when intentionally discarding local database data.
- `docker compose run --rm db-migrations alembic upgrade head` applies pending migrations.
- `cd frontend && npm install && npm run dev` starts the Vite frontend for UI work.
- `cd frontend && npm run build` creates a production frontend build.
- `cd frontend && npm run lint` runs Oxlint; `npm run deadcode` checks unused frontend code with Knip.

## Coding Style & Naming Conventions

Use four-space indentation and `snake_case` for Python functions, variables, and modules. Keep each service's transport handlers in `app/api.py`, configuration in `app/config.py`, and service-specific business logic in focused modules. Use two-space indentation in JavaScript/JSX, `camelCase` for functions and values, and `PascalCase` for React components. Name component files after their exported component, e.g. `TradeTable.jsx`; keep domain helpers lower camel case, e.g. `marketData.js`. Follow the existing import extensions and semicolon-free frontend style.

## Testing Guidelines

No automated test framework or coverage threshold is currently configured. Exercise affected API flows using the relevant `.http` file in `scenarios/` (for example, `scenarios/full-flow.http`) and verify the stack with `docker compose up`. When adding tests, place them alongside the owning service or frontend feature, use descriptive `test_<behavior>` Python names or `*.test.jsx` frontend names, and document any new runner command.

## Commit & Pull Request Guidelines

Recent history uses short, imperative, lowercase summaries such as `add books` and `valuation update`; keep commits narrowly scoped and similarly concise. Pull requests should describe the user-visible or service-level change, list validation performed, link related issues when applicable, and include screenshots for frontend changes. Call out database migrations, configuration changes, and compatibility impacts explicitly.

## Configuration & Data Safety

Use Compose environment variables for local credentials and endpoints; do not commit secrets. Treat migrations and queue/stream behavior as cross-service changes: validate consumers and producers together before merging.
