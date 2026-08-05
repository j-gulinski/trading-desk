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

Each `docs/phase-N-notes.md` is a compact learning guide, not a build diary. It should answer only:

1. **What exists now?** One short outcome paragraph.
2. **How is it structured?** The important ownership and data-flow boundaries.
3. **Which concepts are worth learning?** Explain the few non-obvious mechanisms and why they exist.
4. **What is the main process flow?** One small diagram or numbered path where it genuinely helps.
5. **What limits remain?** Only current limitations, not already superseded work.
6. **Where should I read the code?** A short list of the main files.

Remove chronological build logs, rejected prototypes, repeated status text, exhaustive verification
transcripts, and line-by-line file tours. Keep a historical detail only when it explains a current
constraint or prevents the same bug from returning. Short code snippets are welcome when they make
a concept concrete. A revision updates the existing explanation so the note always describes the
current implementation.

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
- `docs/phase-N-notes.md` — concise learning guides for each completed phase.
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
