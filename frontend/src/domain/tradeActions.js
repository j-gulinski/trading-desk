import {
  CURVE_PRICED_ASSET_CLASSES,
  TRADE_QUANTITY_BOUNDS,
} from '../config/tradeActions.js'
import { freshnessOf, instrumentId } from './marketData.js'
import { formatNumber } from './formatting.js'

export function newOpenTradeRequestId() {
  return `manual-open-${crypto.randomUUID()}`
}

export function instrumentCatalogOf(raw) {
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

export function isCurvePriced(assetClass) {
  return CURVE_PRICED_ASSET_CLASSES.includes(assetClass)
}

export function termSchemasOf(raw) {
  return {
    schemas: raw?.schemas && typeof raw.schemas === 'object' ? raw.schemas : {},
    curves: Array.isArray(raw?.curves) ? raw.curves : [],
  }
}

export function curveChoicesFor(curves, currency) {
  return currency ? curves.filter((curve) => curve.currency === currency) : curves
}

const SYMBOL_SANITIZE = /[^A-Z0-9_.-]/g

export function derivedTermSymbol(assetClass, terms) {
  const parts = [assetClass === 'EUROPEAN_OPTION' ? 'OPT' : assetClass]
  if (assetClass === 'EUROPEAN_OPTION') {
    if (terms.underlying_symbol) parts.push(terms.underlying_symbol)
    if (terms.option_type) parts.push(terms.option_type)
    if (terms.strike) parts.push(String(terms.strike))
  } else {
    if (terms.settlement_currency) parts.push(terms.settlement_currency)
    if (terms.maturity_years) parts.push(`${terms.maturity_years}Y`)
  }
  return parts
    .join('-')
    .toUpperCase()
    .replace(SYMBOL_SANITIZE, '')
    .slice(0, 32)
}

export function termFormComplete(schema, terms) {
  if (!schema) return false
  return schema.fields.every((field) => {
    const value = terms[field.name]
    return value != null && value !== ''
  })
}

export function termCurrencyOf(assetClass, terms, catalog) {
  if (terms.settlement_currency) return terms.settlement_currency
  if (assetClass === 'EUROPEAN_OPTION' && terms.underlying_symbol) {
    const entry = (catalog ?? []).find(
      (instrument) => instrument.symbol === terms.underlying_symbol,
    )
    return entry?.currency ?? null
  }
  return null
}

function executionPriceOf(instrument, side) {
  if (instrument == null) return null
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

const WHOLE_UNIT_CLASSES = ['EQUITY']

export function tradeFormErrorsOf({ bookId, symbol, quantity, quote, assetClass }) {
  const errors = {}
  if (!bookId) errors.book = 'Pick a book.'
  if (!symbol) errors.instrument = 'Pick an instrument.'
  if (symbol && quote == null) errors.provider = 'Pick a market data provider.'
  else if (quote?.state === 'STALE') {
    errors.provider = 'This quote is stale. Wait for the provider to update.'
  } else if (quote != null && !quote.tradeable) {
    errors.provider = `${quote.provider} cannot fill this trade right now.`
  }
  const whole = WHOLE_UNIT_CLASSES.includes(assetClass)
  if (
    !Number.isFinite(quantity) ||
    (whole && !Number.isSafeInteger(quantity)) ||
    quantity < TRADE_QUANTITY_BOUNDS.min ||
    quantity > TRADE_QUANTITY_BOUNDS.max
  ) {
    errors.quantity = `${whole ? 'Quantity must be a whole number' : 'Notional must be'} between ${formatNumber(
      TRADE_QUANTITY_BOUNDS.min,
    )} and ${formatNumber(TRADE_QUANTITY_BOUNDS.max)}.`
  }
  return errors
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
  const intent = {
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
    source: 'MANUAL',
  }
  return intent
}

export function buildCurveTradeIntent({
  clientRequestId,
  bookId,
  assetClass,
  symbol,
  side,
  quantity,
  terms,
  currency,
  provider,
  previewPrice,
}) {
  return {
    action_type: 'OPEN_TRADE',
    client_request_id: clientRequestId,
    book_id: bookId,
    asset_class: assetClass,
    symbol,
    side,
    quantity,
    terms,
    currency: currency ?? undefined,
    market_data_provider: provider || undefined,
    client_seen_price: String(previewPrice),
    source: 'MANUAL',
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

export function buildCloseTradeIntent(tradeId) {
  return {
    action_type: 'CLOSE_TRADE',
    trade_id: tradeId,
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
