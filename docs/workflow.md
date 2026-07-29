# How we work — frontend build

This is our collaboration process for building the Praca domowa nr 4 frontend. It's a
learning-oriented, review-gated workflow: I teach and implement, you stay in control.

## The loop (repeat per phase)

1. **Propose** — I describe the next small phase: what we'll build, the concepts it
   teaches, the files it touches, and any backend it depends on.
2. **You accept** — you approve, tweak the scope, or redirect. Nothing gets built until
   you say go.
3. **I implement** — I write the files into `frontend/`, keeping each phase small.
4. **I verify** — I run the relevant automated tests, lint checks, and production build,
   then exercise real-time behavior in the browser when the phase needs it.
5. **I write the phase notes** — every phase produces `docs/phase-N-notes.md` in the
   standard format below.
6. **You review** — you read the notes + code and run it. I explain any concept in chat
   on request. We iterate until you're happy, then move to the next phase.

## Phase notes format (every phase)

Each phase ends with a `docs/phase-N-notes.md` following this exact template, so notes are
consistent across phases:

1. **`## Suggested inspection order`** — comes first. A numbered, **grouped** reading path
   (e.g. Boot → Styles → Routing → Shell → Pages) that mirrors how the code is
   implemented. This is the map for reviewing the phase.
2. **Detailed notes per group** — one `##` section per group from the order above, and
   inside it a short concept note for each file (what to look at + the idea it teaches).

Rules: concept-focused (why, not line-by-line); no code (explanation lives here, code
stays comment-free); ordered so reading top-to-bottom follows the data/execution flow.

## Ground rules

- **Small phases, in order:** app shell first, then pages one at a time, then details
  (e.g. the bottom-left "streams connected" badge) last.
- **No comments in code.** All explanation lives in chat or in `docs/`. Code stays clean.
- **You make the decisions.** Technology choices from the homework are treated as
  guidelines. When there's a real fork (e.g. routing), I lay out the trade-offs and you
  pick.
- **Build simply, like a learner.** Match the designs in `docs/designs/`, but favour the
  clear, minimal-dependency approach over clever abstractions.
- **Honest UI over fake data.** Where backend is missing, the UI shows a real
  placeholder / "unavailable" state — never invented numbers.

## Backend-gap strategy

- **Big domain features** from `praca_domowa_04` (European options, IRS instruments and
  pricing, alpha/beta, Alembic migrations) are built **last**, after the UI is wired.
  The shared rate curve was completed with Phase 3; placeholders hold the remaining spots.
- **Small additions** (one endpoint, one field, a proxy entry) are done **inline** in the
  phase that needs them.

## Where things live

- `docs/workflow.md` — this file (how we work).
- `docs/frontend-plan.md` — the phase-by-phase plan, backend inventory, and per-phase
  context (concepts, files, deps, review checklist).
- `docs/phase-N-notes.md` — the review walkthrough for each completed phase (inspection
  order + per-file concept notes).
- `docs/designs/` — the reference mockups.
- `frontend/src/` — the app. Imports run one way, and this is the order to read them in:
  `config/` → `domain/` → `hooks/` → `providers/` → `views/` → `components/`, with
  `services/` (HTTP), `routes/`, `layout/` and `styles/` alongside. Nothing imports upward:
  a provider never reaches into a view, and a component never reaches into feature config.

## Progress

Tracked in the task list (Phase 1 → Phase 6, then end-of-project backend work). Current
detail always lives in `docs/frontend-plan.md`.
