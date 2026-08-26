# Review runbook — multi-provider trading

This is the durable review contract for the Finnhub/Twelve Data vertical. It verifies the
running behavior and prepares the explanation behind it. Current behavior facts are in
[market-data.md](market-data.md) and [architecture.md](architecture.md); the detailed
explanations are in the phase reports. The executable API path
is [provider-trading.http](../scenarios/provider-trading.http). The latest completed example of
the evidence record is [phase-3b.md](phase-reports/phase-3b.md).

## Review method

Use the same three moves at every checkpoint:

1. **Observe** — show a visible result or persisted record.
2. **Explain** — connect that result to the business decision and service boundary.
3. **Probe** — change one condition and predict the result before running it.

A pass is not “the screen worked.” A pass means the prediction matched and the evidence can be
traced from UI/API to the owning row, event or log. This keeps future reviews useful even when
provider prices, market sessions and timestamps have changed.

## Preconditions

- Set valid `FINNHUB_API_KEY` and `TWELVE_DATA_API_KEY` values in `.env`.
- Start from a fresh review database when validating a phase boundary. To preserve the normal
  Compose volume, stop the normal stack without `-v`, then use an isolated project:

  ```bash
  docker compose down
  docker compose -p trading-desk-review up --build -d
  ```

- Wait for `GET http://localhost:8001/health` and every service in
  `scenarios/health.http` to report UP.
- Keep one equity book active. Watch one US equity on both providers and wait for both rows to
  receive a usable LIVE or confirmed-CLOSED quote.

## 1. Prove the public contract

**Observe:** Run `scenarios/market-data.http` one request at a time. Confirm the canonical
direct-service routes return health, provider state, the snapshot, filtered quotes, one
provider-symbol quote and an immediate refresh. Run each SSE request separately because it
remains open waiting for events.

**Explain:** `/market-data/snapshot` supplies current state and stream identity; SSE supplies
future changes. `/market-data/stream/<provider>` applies the same event schema but filters out
other providers. `/providers` remains at the service root because it describes adapter runtime,
not a quote collection.

**Probe:** Request an unknown provider on quote detail and the provider stream; predict 404.
Compare a canonical route with its short compatibility alias and predict the same payload shape.

**Pass evidence:** HTTP status, response shape, provider identity and two timestamps are all
visible without editing the scenario URLs.

## 2. Explain quote identity and the two clocks

**Observe:** Open Market Data and select the same symbol first on Finnhub, then Twelve Data.
The side panel changes provider while keeping Provider time and Received visible in the fixed
current-quote card. Scroll a long observation tape; only the tape moves.

**Explain:** `(provider, symbol)` is the identity. Provider time answers “when did the market
event occur?” Received answers “when did this system ingest it?” Open-market freshness uses the
provider clock. During a confirmed closure, recent receive times prove that confirmation polling
is still healthy even though the market event time does not advance.

**Probe:** Before selecting the second provider, predict which price, history rows and timestamps
will change. If they merge across providers, the boundary has failed.

**Pass evidence:** Each provider has its own current row and newest-first history; the current
card stays visible while 60 observations can scroll.

## 3. Explain search, watchlist and the active set

**Observe:** Keep New Trade open on an equity or option book. Search for an equity, add Finnhub,
then add Twelve Data for the same symbol. The symbol appears in the open ticket without closing
it or waiting for its poll. Remove one provider membership. The other subrow continues and the
symbol master is not duplicated. When the last membership is removed, a selected ticket symbol
and its dependent provider/curve state clear.

**Explain:** Search reports provider capability; the watchlist records a user choice. The active
set is watchlist ∪ open-trade pairs ∪ benchmark. Removing a watchlist membership may leave a row
polled when an open trade still depends on that exact provider-symbol. For non-US equities the
exchange is part of identity: `ASB:GPW / PLN` must never resolve to `ASB / NYSE / USD`.

**Probe:** Open a trade, then remove its watchlist membership. Predict `still_polled` and explain
why stopping that feed would break provider-bound valuation. Search for ASBIS and explain why
the exchange-qualified row may honestly show `NO DATA` on the current provider plan.

**Pass evidence:** `DELETE /watchlist/<symbol>?provider=` removes only the requested membership,
and any continued polling names its retained origin. A watchlist mutation immediately refetches
the open ticket's instrument catalog and option term choices; a disposable TSLA check completed
both add and selected-state removal transitions in about 0.3 s, before the five-second fallback.
The ASBIS regression check retained `ASB:GPW`, rejected a USD/NYSE payload against PLN/GPW and
showed `NO DATA` because the configured Twelve Data tier does not entitle that market.

## 4. Prove provider-bound execution and PnL

**Observe:** Run `scenarios/provider-trading.http` top to bottom. Open one trade through Finnhub
and one through Twelve Data. Inspect both in Trades and Valuations, then close them.

**Explain:** The browser submits provider identity and `client_seen_price`; the server rereads
the board and chooses ask for BUY, bid for SELL, or mid when no spread exists. Validation runs
before the 202 response for immediate feedback and again in the worker because the market may
move while queued. The trade freezes the provider, so entry, unrealized PnL and close never jump
to the other feed.

**Probe:** Predict the response to a missing provider, a STALE quote and a client price more than
1% from the server quote. Repeat a `client_request_id` and predict one persisted trade.

**Pass evidence:** Trade and valuation rows agree on provider and quote time; close uses the same
provider; the duplicate request creates no second trade.

## 5. Prove pacing and failure isolation

**Observe:** Open System Overview. Finnhub exposes minute allowance and tier cadences. Twelve
Data exposes minute and daily credit state plus batch cadence. Open an active provider card and
inspect its `provider_http_response` log entries.

**Explain:** A local empty bucket is normal pacing and does not degrade health. Provider answers
drive health transitions: 429 → RATE_LIMITED, 401/403 → AUTH_FAILED, network/5xx → ERROR. A bad
symbol is a data error and does not quarantine the provider.

**Probe:** Temporarily use an invalid Twelve Data key. Predict that only Twelve Data enters
AUTH_FAILED while Finnhub continues. Restore the key immediately and observe recovery.

**Pass evidence:** Provider status, cooldown, safe endpoint metadata and recovery are visible;
credentials never appear in log fields.

## 6. Keep adjacent market concepts honest

**Observe:** Use the [volume, depth and open-interest capability note](market-data.md#volume-depth-and-open-interest)
and inspect the normalized quote. It contains prices and clocks, not a generic “pressure” field.

**Explain:** Volume counts executed activity over an interval. Displayed depth is resting size at
ordered bid/ask levels. Open interest is outstanding derivatives contracts. None supplies BUY
or SELL pressure by itself, and none can be reconstructed from `last` or a sparse quote tape.

**Probe:** For any proposed new field, require five answers before coding: exact measure,
instrument scope, interval/as-of, units, and provider entitlement. Missing answers mean the
capability remains unsupported rather than zero-filled.

**Pass evidence:** The UI makes no unsupported claim and the provider capability boundary states
what is unavailable.

## 7. Explain the Python design boundary

**Observe:** Read `providers/base.py`, one provider package's `client.py`, `normalizer.py` and
`feed.py`, then its entry in `providers/__init__.py`.

**Explain:** `ProviderClient.get()` is a Template Method: shared transport calls provider hooks
for authentication, response decoding and body classification. The default body classifier is
a no-op; providers whose APIs encode errors inside HTTP 200 override it. Separate feeds compose
cadence, budget, active-set and normalization policies because those policies differ materially.
The runtime registration validates declared capabilities and provider identity. That explicit
contract is sufficient for this small provider set; another inheritance rule would not validate
the financial meaning of a payload.

**Probe:** Ask whether moving every scheduler into subclasses would remove duplication or only
hide unlike policies behind inheritance. Prefer the existing registration and fail-fast catalog
checks over another inheritance layer.

**Pass evidence:** Shared HTTP behavior exists once, while provider pacing remains explicit and
independently testable.

## 8. Prove the curves and model-priced execution

**Observe:** On Market Data, the Rate curves section overlays the stored sets, with the
legend above the chart naming each curve by currency plus the system-owned family and
qualifier, then separating its trade use, basis, as-of and source (the PLN reference
projection's older as-of is the source's real publication lag); compare EUR · Government
bonds · AAA with EUR · Government bonds · all ratings and select points — sourced
anchors are filled, derived points hollow, and the inspector names tenor, rate, source
series, source as-of, ingest time, system key and the raw response. Open the ticket on an IRS
book: each curve picker uses a short name, then shows what the curve does in that trade,
basis, index, as-of and source as separate facts. After selecting maturity, index and both
IRS curves, use the curve-implied fair fixed rate; the model value then updates as terms,
the selected curves or the option's underlying quote change. A manually entered fixed rate
is a percent (`4.5`), the unit the label asks for.

**Explain:** Stored rates and rate terms are the published percent values; pricing
consumes decimal fractions, converted once in shared code. A set's as-of is its oldest
source date. PLN · Reference projection · 3M is a labeled two-anchor composite (monthly
OECD series, ~2-month
lag), not an observed WIBOR curve. The server recomputes every model value itself. The
trade records curve name plus provider/as-of entry provenance; later valuation resolves the
latest retained set under the stored name.

**Probe:** Confirm USD · Government bonds (`USD_GOVERNMENT_BONDS` in the API) appears for
a USD bond but not an IRS or option. Ask the
API for a PLN swap discounted on USD_GOVERNMENT_BONDS (rejected with the currency in the sentence)
and a 6M floating
leg projected off PLN · Reference projection · 3M (rejected naming the declared 3M index). Run
`scenarios/curves.http` for the API-level flow. In the browser, switch from an EUR bond
ticket to the option book: the option terms and quantity must be empty and the discount
curve disabled with `Choose underlying first`. Select AAPL and confirm that only USD option
curves become available and that the sole eligible curve is selected automatically. Select
a provider, then change the underlying; provider selection must be recomputed—no selection
when several providers are eligible, automatic selection when only one is. A still-valid
curve may remain, but a currency-incompatible curve must be replaced by the new currency's
sole eligible curve or cleared when several valid choices exist.

**Pass evidence:** The chart, inspector and pickers agree with `/market-data/curves`;
rejections carry readable reasons; an accepted trade's terms show entry curve provenance;
book/underlying transitions cannot retain a curve of the wrong currency.

## Review questions

A reviewer should be able to interrupt the walkthrough with these questions:

1. Which timestamp should drive quote age, and when is the other timestamp decisive?
2. Why does CLOSED remain usable while STALE is blocked?
3. Why are two provider prices not collapsed into a best-price router?
4. What state is lost if the service uses SSE without a database seed?
5. Why is the observation tape not a continuous intraday chart?
6. Which component owns provider failure, and why does one bad symbol not stop the feed?
7. What does the shared client guarantee, and what does capability registration validate?
8. Why are volume, order-book depth and open interest three separate capabilities?
9. Why is a curve set's as-of its oldest source date, and where does an interpolated
   point admit what it is?

The answers are the decision boundaries above; class names are supporting evidence, not the
answer by themselves.

## Review record

Keep this compact record with the PR or phase handoff so a later review has reproducible context:

```text
commit:
reviewed_at / market session:
fresh database project:
provider states and remaining budgets:
provider-symbol and both observed clocks:
opened trade IDs -> provider -> entry snapshot:
closed trade IDs -> provider -> close snapshot:
failure probe and recovery evidence:
commands/checks run:
open questions (facts still unverified):
```

Record IDs and timestamps, never API keys or full vendor responses.

## Reset

- Close trades created during validation.
- Remove temporary watchlist provider memberships.
- Deactivate temporary books after they have no active trades.
- If the isolated review project was used, remove only its containers and volume:

  ```bash
  docker compose -p trading-desk-review down -v
  ```
