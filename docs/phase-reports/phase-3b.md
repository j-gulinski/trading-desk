# Phase 3b — review closure

Phase 3b makes the delivered two-provider workflow executable from the repository and
reviewable as a set of decisions. It does not add a market-data provider. It closes the public
quote contract, scenario drift and quote-detail review issue before NBP/ECB work begins.

**Exit criterion, met:** a fresh isolated Compose stack can open, value and close AAPL trades on
Finnhub and Twelve Data independently; the assignment's current quote routes work directly on
port 8001; the selected quote stays visible while its observation tape scrolls.

## Decisions preserved

| Decision | Review consequence |
| --- | --- |
| `/market-data/...` is the canonical direct quote namespace; short service-root routes are compatibility aliases. | The assignment requests run unchanged and existing consumers do not break. |
| Provider detail returns one normalized object and 404 for an unknown provider or inactive provider-symbol. | A ticket or scenario never has to guess which row in a list was requested. |
| A provider-specific SSE route filters the existing event contract rather than defining a second schema. | All/provider consumers interpret identical `market_tick` and `market_remove` payloads. |
| The current quote card owns no scrollbar; only the observation tape scrolls. | Provider time, received time, basis and current mark remain available while reviewing history. |
| Volume, displayed depth and open interest remain separate unsupported capabilities. | No placeholder zero or generic pressure indicator claims data the wired quote endpoints do not supply. |
| Review documentation uses Observe → Explain → Probe. | A future review tests the reasoning and failure boundary, not only the happy-path clicks. |

## Review evidence — 2026-08-22

The review used Compose project `trading-desk-review`, which created its own fresh Postgres
volume and left the normal project volume untouched. Alembic reached `f4a8c1d27b3e`; all six
HTTP services and the frontend started from rebuilt images.

Market session: US market CLOSED. AAPL produced these independent observations:

| Provider | Mark | Provider time | Received during review | State |
| --- | ---: | --- | --- | --- |
| Finnhub | 309.35 | 2026-08-21 20:00:00Z | 2026-08-22 15:57:22Z | CLOSED |
| Twelve Data | 309.35001 | 2026-08-21 19:59:00Z | 2026-08-22 15:57:23Z | CLOSED |

The canonical snapshot, quote detail and history responses matched their short aliases. Unknown
provider detail and stream requests returned 404. After a Twelve Data refresh followed by a
Finnhub refresh, `/market-data/stream/FINNHUB` emitted only the Finnhub event.

The provider-bound scenario produced two trades in one equity book:

| Provider | Trade ID | Open/valuation | Close/final valuation |
| --- | --- | --- | --- |
| Finnhub | `e3d72bb2-1f5f-4f93-a7b1-5b95c9075644` | provider retained | provider retained, final=true |
| Twelve Data | `5bdcad41-760d-4918-863f-46a57826299d` | provider retained | provider retained, final=true |

Repeating the Finnhub `client_request_id` left two persisted trades total and incremented the
duplicate counter once. A second close returned 422 `trade is not open`. The temporary trades,
book and AAPL watchlist memberships were then cleaned up.

For the UI check, the panel body computed to `overflow-y: hidden` and the tape to
`overflow-y: auto`. At a constrained 1368×650 viewport, tape scroll moved from 0 to 134.4 px
while the current card stayed at the same 125.3–398.9 px vertical bounds. The browser console
reported no warnings or errors.

## Checks

- `python3 -m compileall -q shared services db`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run deadcode`
- `docker compose config --quiet`
- fresh `docker compose -p trading-desk-review up --build -d`
- canonical/alias REST checks and filtered SSE check
- provider-bound open, duplicate, valuation, close and double-close checks
- `git diff --check`

## Review preparation

Use [the review runbook](../validation-runbook.md) for the reusable walkthrough. Its prompts cover
the two clocks, provider identity, seed-before-stream recovery, sparse history, CLOSED versus
STALE, provider error isolation, Template Method versus composition/ABC, and the distinction
between volume, depth and open interest.

Phase 4 begins only from this reviewed boundary: NBP/ECB reference FX and reporting-currency
conversion, without changing the provider-bound execution contract proven here.
