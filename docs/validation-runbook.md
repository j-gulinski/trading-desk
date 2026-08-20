# Validation runbook — multi-provider trading

This runbook validates the completed two-provider workflow. It assumes the stack
is running with valid `FINNHUB_API_KEY` and `TWELVE_DATA_API_KEY` values and the frontend is
open at http://localhost:3000.

## Preconditions

- Keep one equity book active.
- Watch NVDA on both Finnhub and Twelve Data.
- Leave another equity available to add during the walkthrough.
- Let each provider return at least one usable quote before beginning validation.

## Walkthrough

### 1. Compare market quotes

Open Market Data. NVDA appears once with separate Finnhub and Twelve Data provider subrows.
Compare Mark, last-tick move, daily move and quote age. Use the provider filter to isolate
either feed.
The benchmark strip separately summarizes Last, Previous close, Change today and quote age.
Select each NVDA provider subrow in turn. Its side panel must show the matching provider, current quote
fields and a newest-first tape of observed price changes.

Interpret quote state as follows:

- LIVE means the provider timestamp is inside that feed's open-market freshness budget.
- CLOSED means the venue is closed and confirmation polling is healthy.
- STALE means an expected provider update is overdue.
- NO DATA means the selected feed has not supplied its first usable quote.

No trend line, manual Refresh button or repeated quality label should appear in the tape.
Leave one Finnhub panel open through a price change and confirm the newest observation
appears automatically. Opening the panel and receiving a changed tick may read stored
history; neither action makes an upstream provider request.

### 2. Add and remove one provider

Search for an equity. Select a provider and add it. Search for the same symbol again and add
the other provider. The board creates the second provider subrow without duplicating the symbol's
master data.

Remove one row with its × action. Only that provider membership disappears; the other feed
continues. A POS or BMK marker means an open position or the benchmark still requires the
row, so it cannot be removed from active polling through the watchlist control.

### 3. Open a provider-bound trade

Open New trade, select the equity book and NVDA. The provider choices update from the live
market stream and show the executable price, freshness, time and age. Select one feed, enter the
quantity and submit.

Both LIVE and confirmed-CLOSED rows are eligible when they have a usable price. CLOSED is
the venue session, not a booking prohibition in this portfolio application. STALE and NO
DATA rows remain blocked.

Open the created trade in Trades. Its detail names the pricing provider and quote time.
Valuations continue to use that provider rather than switching to whichever feed most
recently changed. Open Valuations and confirm Capital invested equals the sum of the visible
open rows' entry values.

### 4. Inspect provider operations

Open System Overview. Finnhub shows its request allowance and separate open-position and
watchlist cadences. Twelve Data shows its batch size, cadence and daily credit usage.
Unavailable registry entries show only NOT AVAILABLE.

Click an active provider card. Logs opens with structured Provider API and provider filters
already selected. Each completed call produces one row showing the endpoint, symbol or
search scope, HTTP status, result count and duration; credentials never enter the log
payload.

### 5. Optional provider-failure drill

Temporarily using an invalid Twelve Data key makes only Twelve Data enter AUTH_FAILED and
start its cooldown. Finnhub continues independently. Restore the key immediately after the
drill.

## Reset

- Close any trade created during validation.
- Remove temporary watchlist provider memberships with their row actions.
- The board reloads from the database; no browser-only state needs rebuilding.

Use `scenarios/provider-trading.http` for the equivalent API-level validation path.
