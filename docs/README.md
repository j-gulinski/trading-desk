# Documentation

Two layers. The **phase reports** are the detailed record: every decision (chose /
rejected / why), the difficult concepts taught step by step, and the evidence — that is
where explanations live. Everything else is a **lean reference sheet** carrying only the
current facts a session needs for context; a reference sheet states what is, never argues
why.

**Working on the next phase?** Read [`../AGENTS.md`](../AGENTS.md) for the house rules,
then [implementation-roadmap.md](implementation-roadmap.md) §6 — the standing phase
template and the task-level plans. The roadmap is a working plan, not a contract: each
phase re-derives its decisions and ends by adding its report to `phase-reports/`.

## Reference sheets

1. [Root README](../README.md) — run the stack, the services, the operating rules.
2. [architecture.md](architecture.md) — service ownership, the market-data vertical in
   one diagram, code map, data model, shared runtime, conventions.
3. [market-data.md](market-data.md) — provider facts, normalized contracts, freshness,
   feeds, endpoints, storage.
4. [configuration.md](configuration.md) — every runtime knob: default, reader, one-line
   why.
5. [validation-runbook.md](validation-runbook.md) with
   [provider-trading.http](../scenarios/provider-trading.http),
   [reference-fx.http](../scenarios/reference-fx.http) and
   [curves.http](../scenarios/curves.http) — the review procedure and the
   executable API paths.

## Phase reports — the detailed record

- [phase-0](phase-reports/phase-0.md) — fork & deep clean
- [phase-1](phase-reports/phase-1.md) — provider contracts & schema
- [phase-2](phase-reports/phase-2.md) — the Finnhub vertical
- [phase-3a](phase-reports/phase-3a.md) — the two-provider workflow, review record
- [phase-3b](phase-reports/phase-3b.md) — review closure
- [phase-4](phase-reports/phase-4.md) — NBP/ECB reference FX and the reporting currency
- [phase-5](phase-reports/phase-5.md) — real rate curves, the curve chart, and
  model-priced execution (the latest evidence and the exact boundary handed to Phase 6)

## The plan

[implementation-roadmap.md](implementation-roadmap.md) — the working plan: the standing
phase template, task-level phases 5–7, and the post-acceptance sequence. Forward-looking
by design; for implemented behavior the phase reports and reference sheets above are
authoritative.
