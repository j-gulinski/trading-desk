import { freshnessOf, instrumentId } from './marketData.js'
import { curveTitle } from './curves.js'

export function newOpenTradeRequestId() {
  return `manual-open-${crypto.randomUUID()}`
}

function instrumentCatalogOf(raw) {
  return (Array.isArray(raw) ? raw : [])
    .filter(
      (instrument) =>
        typeof instrument?.symbol === 'string' &&
        typeof instrument?.asset_class === 'string',
    )
    .map((instrument) => ({
      ...instrument,
      assetClass: instrument.asset_class,
      currency: instrument.currency ?? 'USD',
      providers: Array.isArray(instrument.providers) ? instrument.providers : [],
    }))
}

export function ticketOptionsOf(raw) {
  return {
    instruments: instrumentCatalogOf(raw?.instruments),
    schemas: raw?.schemas && typeof raw.schemas === 'object' ? raw.schemas : {},
    curves: Array.isArray(raw?.curves) ? raw.curves : [],
  }
}

export function curveChoicesFor(
  curves,
  currency,
  fieldName = 'discount_curve',
  indexTenor = null,
  assetClass = null,
) {
  const role = fieldName === 'projection_curve' ? 'PROJECTION' : 'DISCOUNT'
  const tradeUse = assetClass == null ? null : `${assetClass}:${role}`
  return curves
    .filter((curve) => (currency ? curve.currency === currency : true))
    .filter((curve) => (curve.roles ?? []).includes(role))
    .filter((curve) => tradeUse == null || (curve.uses ?? []).includes(tradeUse))
    .filter((curve) => (
      role !== 'PROJECTION' ||
      indexTenor == null ||
      curve.index_tenor == null ||
      curve.index_tenor === indexTenor
    ))
    .sort((a, b) => curveTitle(a).localeCompare(curveTitle(b)))
}

export function termFormComplete(schema, terms) {
  if (!schema) return false
  return schema.fields.every((field) => {
    const value = terms[field.name]
    return value != null && value !== ''
  })
}

export function termCurrencyOf(schema, terms, catalog) {
  const underlying = schema?.underlying_field ? terms[schema.underlying_field] : null
  if (underlying) {
    const entry = (catalog ?? []).find((instrument) => instrument.symbol === underlying)
    return entry?.currency ?? null
  }
  if (terms.settlement_currency) return terms.settlement_currency
  return null
}

function executionPriceOf(instrument, side) {
  if (instrument == null) return null
  if (side == null) return instrument.value
  const quoted = side === 'BUY' ? instrument.ask : instrument.bid
  return Number.isFinite(quoted) ? quoted : instrument.value
}

const TRADEABLE_STATES = ['LIVE', 'CLOSED']

export function providerQuotesOf({ instrument, feed, side, now }) {
  if (instrument == null) return []
  const serving = new Set(instrument.providers)
  return Object.keys(instrument.capabilities ?? {}).map((provider) => {
    if (!instrument.capabilities?.[provider]) {
      return { provider, state: 'UNSUPPORTED', reason: `does not quote ${instrument.assetClass}` }
    }
    if (!serving.has(provider)) {
      return { provider, state: 'UNWATCHED', reason: 'not on the watchlist for this symbol' }
    }
    const quote = feed[instrumentId(provider, instrument.symbol)]
    if (quote == null) {
      return { provider, state: 'MISSING', reason: 'watched, no quote yet' }
    }
    const state = freshnessOf(quote, now)
    if (state === 'MISSING') {
      return { provider, state, reason: 'watched, no quote yet' }
    }
    const price = executionPriceOf(quote, side)
    return {
      provider,
      state,
      price: Number.isFinite(price) && price > 0 ? price : null,
      bid: quote.bid,
      ask: quote.ask,
      last: quote.last,
      currency: quote.currency,
      atMs: quote.providerTimestampMs,
      providerTimestamp: quote.providerTimestamp,
      receivedAt: quote.receivedAt,
      grade: quote.grade,
      tradeable: TRADEABLE_STATES.includes(state) && Number.isFinite(price) && price > 0,
    }
  })
}

export function tradeableInstrumentsOf(instruments, assetClass) {
  if (!assetClass) return []
  return (Array.isArray(instruments) ? instruments : []).filter(
      (instrument) => instrument.assetClass === assetClass,
    )
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
}

// Realtime live quotes first, then any other tradeable state, newest provider time wins.
const QUOTE_PREFERENCE = { LIVE: 2, CLOSED: 1, EOD: 1 }

export function preferredQuoteProviderOf(quotes) {
  const ranked = quotes
    .filter((quote) => quote.tradeable)
    .map((quote) => ({
      quote,
      rank: (QUOTE_PREFERENCE[quote.state] ?? 0) * 2 + (quote.grade === 'EOD' ? 0 : 1),
    }))
    .sort((a, b) => b.rank - a.rank || (b.quote.atMs ?? 0) - (a.quote.atMs ?? 0))
  return ranked[0]?.quote.provider ?? null
}

export function buildOpenTradeIntent({
  clientRequestId,
  bookId,
  assetClass,
  symbol,
  side,
  quantity,
  quote,
}) {
  return {
    action_type: 'OPEN_TRADE',
    client_request_id: clientRequestId,
    book_id: bookId,
    asset_class: assetClass,
    symbol,
    side,
    quantity,
    currency: quote.currency ?? 'USD',
    market_data_provider: quote.provider,
    client_seen_price: String(quote.price),
    source: 'TRADING_TICKET',
  }
}

export function buildCurveTradeIntent({
  clientRequestId,
  bookId,
  assetClass,
  side,
  quantity,
  terms,
  currency,
  provider,
  previewPrice,
  staleCurveAcknowledged = false,
}) {
  return {
    action_type: 'OPEN_TRADE',
    client_request_id: clientRequestId,
    book_id: bookId,
    asset_class: assetClass,
    side,
    quantity,
    terms,
    currency: currency ?? undefined,
    market_data_provider: provider || undefined,
    client_seen_price: String(previewPrice),
    source: 'TRADING_TICKET',
    stale_curve_acknowledged: staleCurveAcknowledged,
  }
}

export function buildReassignIntent(sourceBookId, targetBookId) {
  return {
    action_type: 'REASSIGN_TRADES',
    book_id: sourceBookId,
    target_book_id: targetBookId,
    client_request_id: `manual-move-${crypto.randomUUID()}`,
  }
}

export function buildCloseTradeIntent(tradeId, clientSeenPrice) {
  return {
    action_type: 'CLOSE_TRADE',
    trade_id: tradeId,
    client_seen_price: String(clientSeenPrice),
    close_reason: 'MANUAL_CLOSE',
    client_request_id: crypto.randomUUID(),
  }
}

const DIRECTION_BY_EVENT = {
  TRADE_CREATED: { direction: 'IN', label: 'TRADE_IN', tone: 'healthy' },
  TRADE_CLOSED: { direction: 'OUT', label: 'TRADE_OUT', tone: 'stale' },
  TRADE_REASSIGNED: { direction: 'MOVED', label: 'REASSIGNED', tone: 'info' },
  ACTION_REJECTED: { direction: 'REJECTED', label: 'REJECTED', tone: 'down' },
}

export function intentRowsOf(events) {
  if (!Array.isArray(events)) return []
  const rows = []
  for (const event of events) {
    const mapped = DIRECTION_BY_EVENT[event.eventType]
    if (!mapped) continue
    rows.push({
      id: event.id,
      atMs: event.createdAtMs,
      direction: mapped.direction,
      label: mapped.label,
      tone: mapped.tone,
      tradeId: event.entityId,
      correlationId: event.correlationId,
      message: event.message,
    })
  }
  return rows
}

export function summarizeIntents(rows) {
  const summary = { total: rows.length, opened: 0, closed: 0, rejected: 0 }
  for (const row of rows) {
    if (row.direction === 'IN') summary.opened += 1
    else if (row.direction === 'OUT') summary.closed += 1
    else summary.rejected += 1
  }
  return summary
}

function count(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function countOrNull(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function queueStatusOf(raw) {
  if (raw == null) {
    return {
      available: false,
      accepted: 0,
      processed: 0,
      created: 0,
      closed: 0,
      rejected: 0,
      avgProcessingMs: null,
      lastProcessingMs: null,
    }
  }

  return {
    available: true,
    accepted: count(raw.accepted),
    processed: count(raw.processed),
    created: count(raw.created),
    closed: count(raw.closed),
    rejected: count(raw.rejected),
    avgProcessingMs: countOrNull(raw.avg_processing_ms),
    lastProcessingMs: countOrNull(raw.last_processing_ms),
  }
}

export function lastActionAtOf(rows) {
  if (!Array.isArray(rows)) return null
  let newest = null
  for (const row of rows) {
    if (Number.isFinite(row.atMs) && (newest == null || row.atMs > newest)) newest = row.atMs
  }
  return newest
}
