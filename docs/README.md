# Documentation

Two layers. The **phase reports** are the detailed record: every decision (chose /
rejected / why), the difficult concepts taught step by step, and the evidence — that is
where explanations live. Everything else is a **lean reference sheet** carrying only the
current facts a session needs for context; a reference sheet states what is, never argues
why.

**Working on the project?** Read [`../AGENTS.md`](../AGENTS.md) for the house rules.
Phase 6 is the final shipped boundary; the optional section of
[implementation-roadmap.md](implementation-roadmap.md) is a backlog, not required work.

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
   [curves.http](../scenarios/curves.http), with the integrated
   [full-provider-flow.http](../scenarios/full-provider-flow.http) — the review procedure and the
   executable API paths.
6. [performance.md](performance.md) — repeatable bounded idempotency, SSE fan-out,
   board-read and valuation-growth checks with the latest measured sample.

## Phase reports — the detailed record

- [phase-0](phase-reports/phase-0.md) — fork & deep clean
- [phase-1](phase-reports/phase-1.md) — provider contracts & schema
- [phase-2](phase-reports/phase-2.md) — the Finnhub vertical
- [phase-3a](phase-reports/phase-3a.md) — the two-provider workflow, review record
- [phase-3b](phase-reports/phase-3b.md) — review closure
- [phase-4](phase-reports/phase-4.md) — NBP/ECB reference FX and the reporting currency
- [phase-5](phase-reports/phase-5.md) — rate curves, model-priced execution, and a
  catalog a rates desk would recognise: a risk-free curve per currency, curve roles
  stated in the interface, derived instrument identifiers, and the ticket built around
  the economics (the latest evidence and the exact boundary handed to Phase 6)
  - [phase-5-krzywe-i-kod](phase-reports/phase-5-krzywe-i-kod.md) — its companion, in
    Polish: Part I teaches the domain (what each curve is, how it is built, what the two
    curve roles mean, every number worked through), Part II walks the code process by
    process for a review
- [phase-6](phase-reports/phase-6.md) — Alpha Vantage, persisted budget controls,
  complete provenance/audit guarantees, bounded valuation persistence, reconciled
  portfolio summaries and the final acceptance evidence

## The plan

[implementation-roadmap.md](implementation-roadmap.md) — the historical phase plan and
optional post-acceptance extensions. For implemented behavior the phase reports and
reference sheets above are authoritative.
