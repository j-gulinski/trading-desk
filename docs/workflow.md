# How we work — frontend build

This is our collaboration process for building the Praca domowa nr 4 frontend. It's a
learning-oriented, review-gated workflow: I teach and implement, you stay in control.

## The loop (repeat per phase)

1. **Propose** — I describe the next small phase: what we'll build, the concepts it
   teaches, the files it touches, and any backend it depends on.
2. **You accept** — you approve, tweak the scope, or redirect. Nothing gets built until
   you say go.
3. **I implement** — I write the files into `frontend/`, keeping each phase small.
4. **I verify** — I run the relevant automated tests, lint checks, the production build, and
   `npm run deadcode` (knip — catches unused exports that lint and build both pass; every
   mid-phase reversal tends to leave some behind), then exercise real-time behavior in the
   browser when the phase needs it.
5. **I write the phase notes** — every phase produces `docs/phase-N-notes.md` in the
   standard format below.
6. **You review** — you read the notes + code and run it. I explain any concept in chat
   on request. We iterate until you're happy, then move to the next phase.

## Phase notes format (every phase)

Each phase ends with a `docs/phase-N-notes.md`. Phase 3 used a file-by-file walkthrough that opened
with an inspection order; from Phase 4 onward the notes became a **decision log with process flows**,
because that is what actually gets re-read — the questions that came up during review are about *why*
a thing works the way it does, not what each file contains. This section describes that shape, which
is the one to follow.

1. **Front matter** — `phase`, `status`, `reviewed`, `tags`.
2. **Phase outcome in one line** — what the phase actually delivers, stated once.
3. **What was decided and why** — the forks, each with the alternative that lost and the reason.
   This is the bulk of the document.
4. **What changed during the build** — deviations from the approved plan, and what surfaced them.
   Scope drift is recorded here rather than left implicit.
5. **Mental model: what owns what** — an ASCII diagram of the ownership boundaries.
6. **Process flows** — the two or three paths worth tracing end to end (a value from wire to screen,
   an action from click to database).
7. **Honest gaps** — anything the mockups show that the backend cannot answer, and what the screen
   renders instead.
8. **Verification performed** — with the measured numbers, not just the checklist.
9. **Concepts seen for the first time in this phase** — each new technique named and explained in
   a few sentences: what it is, why the naive alternative fails, and where it recurs later. This
   is the teaching payload; as of 2026-08-03 every phase note (1 through 6a) carries this section.
10. **Files for first-pass review** — the reading path, **at the end**. By this point the reader knows
    why each file exists, so the list is a route rather than an introduction.
11. **Known limits** — what belongs to a later phase.

Rules: concept-focused (why, not line-by-line); no code in the source (explanation lives here, code
stays comment-free) — short snippets *in the notes* are fine when they make a flow concrete; record
measurements when a decision rests on one. Free-form topic sections between the flows and the
concepts are welcome when a question needs plain-terms treatment (Phase 5's value-selection rule,
Phase 4's scheduler section). **A revision pass is folded in, never appended**: its decisions extend
the numbered decision list, its deletions sit with the deviations that caused them, its measurements
merge into the verification section, and the front matter gains a `revised:` date. The note must
read as one story however many passes produced it — a trailing "review pass" log means the earlier
sections now describe a state that no longer exists.

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

Tracked in the task list (Phase 1 → Phase 6a → 6b-1 → 6b-2 → 6c → Phase 7a real-data seam
review → end-of-project phases E1–E5 → Phase 7b consolidation sweep). Current detail always
lives in `docs/frontend-plan.md`.

Phase 6 is split into **6a / 6b-1 / 6b-2 / 6c** — it had grown to roughly four screens, and Phases 4
and 5 each ran three revision passes past their stated goal. 6b was split again once the
book-lifecycle work (delete guard, trade reassignment) turned out to be the
heaviest backend feature since Phase 3. Each sub-phase gets its own notes file and review gate.
